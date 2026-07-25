import enum
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.core import cache_service
from app.core.config import settings
from app.core.redis_client import get_redis_client
from app.services.monitoring import llm_token_usage_total

SchemaT = TypeVar("SchemaT", bound=BaseModel)

logger = logging.getLogger(__name__)


class TaskComplexity(str, enum.Enum):
    SIMPLE = "simple"
    COMPLEX = "complex"


GROQ_MODEL = "llama-3.3-70b-versatile"
GPT4O_MODEL = "gpt-4o"

# Approximate USD per 1M tokens — good enough for relative cost monitoring,
# not meant to reconcile exactly against a provider invoice.
_PRICING_PER_MILLION = {
    GROQ_MODEL: {"input": 0.59, "output": 0.79},
    GPT4O_MODEL: {"input": 2.50, "output": 10.00},
}

# If a "simple" task's input is unusually large, escalate to GPT-4o rather
# than risk quality issues on a smaller model.
LONG_INPUT_TOKEN_THRESHOLD = 6000

COST_LOG_KEY = "llm_cost:log"
COST_LOG_MAX_ENTRIES = 200

# Identical prompts (e.g. the same resume text re-parsed, or the same weak
# answer re-scored) return the cached response instead of paying for another
# LLM call. 24h matches the JD-embedding cache's TTL in cache_service.py.
LLM_RESPONSE_CACHE_TTL_SECONDS = 24 * 60 * 60


class LLMBudgetExceededError(RuntimeError):
    """Raised when today's LLM spend has hit the configured daily cap
    (settings.LLM_DAILY_BUDGET_USD) — a hard stop against runaway cost from a
    bug, an abusive client, or an unexpectedly expensive prompt loop."""


def _prompt_cache_key(task_name: str, temperature: float, prompt: str | list[Any], schema_name: str = "") -> str:
    """Deterministic across identical calls regardless of which model ends up
    serving it (primary or fallback) — the cache is about "we already have an
    answer for this exact input," not about which provider produced it."""
    content = prompt if isinstance(prompt, str) else " ".join(str(getattr(m, "content", m)) for m in prompt)
    raw = f"{task_name}:{temperature}:{schema_name}:{content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _daily_cost_key() -> str:
    return f"llm_cost:daily:{datetime.now(timezone.utc):%Y-%m-%d}"


async def get_daily_cost() -> float:
    redis = get_redis_client()
    try:
        raw = await redis.get(_daily_cost_key())
        return float(raw) if raw else 0.0
    except Exception:
        logger.warning("Failed to read daily LLM cost from Redis", exc_info=True)
        return 0.0
    finally:
        await redis.aclose()


async def _enforce_budget(task_name: str) -> None:
    """No-op unless LLM_DAILY_BUDGET_USD is set (default 0 = disabled), so
    this never surprises a dev/staging environment that hasn't opted in."""
    if settings.LLM_DAILY_BUDGET_USD <= 0:
        return
    spent = await get_daily_cost()
    if spent >= settings.LLM_DAILY_BUDGET_USD:
        raise LLMBudgetExceededError(
            f"Daily LLM budget of ${settings.LLM_DAILY_BUDGET_USD:.2f} already spent "
            f"(${spent:.2f} so far today) — refusing task={task_name} until the daily window resets"
        )


def estimate_tokens(text: str) -> int:
    """Rough chars/4 heuristic for routing decisions — not used for billing."""
    return max(1, len(text) // 4)


def choose_model(complexity: TaskComplexity, estimated_tokens: int = 0) -> str:
    if complexity == TaskComplexity.COMPLEX:
        return GPT4O_MODEL
    if estimated_tokens > LONG_INPUT_TOKEN_THRESHOLD:
        return GPT4O_MODEL
    return GROQ_MODEL


_llm_cache: dict[str, BaseChatModel] = {}


def _get_llm(model_name: str, temperature: float = 0) -> BaseChatModel:
    cache_key = f"{model_name}:{temperature}"
    if cache_key not in _llm_cache:
        if model_name == GROQ_MODEL:
            _llm_cache[cache_key] = ChatGroq(
                model=model_name, temperature=temperature, api_key=settings.GROQ_API_KEY
            )
        else:
            _llm_cache[cache_key] = ChatOpenAI(
                model=model_name, temperature=temperature, api_key=settings.OPENAI_API_KEY
            )
    return _llm_cache[cache_key]


def _fallback_model(model_name: str) -> str:
    return GPT4O_MODEL if model_name == GROQ_MODEL else GROQ_MODEL


def get_llm(
    complexity: TaskComplexity, estimated_tokens: int = 0, temperature: float = 0
) -> tuple[BaseChatModel, str]:
    """Returns (chat_model, model_name) chosen by the routing policy."""
    model_name = choose_model(complexity, estimated_tokens)
    return _get_llm(model_name, temperature), model_name


def extract_usage(response: BaseMessage) -> tuple[int, int]:
    usage = getattr(response, "usage_metadata", None)
    if usage:
        return usage.get("input_tokens", 0) or 0, usage.get("output_tokens", 0) or 0
    return 0, 0


def _compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = _PRICING_PER_MILLION.get(model, _PRICING_PER_MILLION[GPT4O_MODEL])
    return (input_tokens / 1_000_000) * pricing["input"] + (output_tokens / 1_000_000) * pricing["output"]


async def log_cost(task_name: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Best-effort cost logging to Redis — never raises, so a Redis outage
    can't take down the LLM calls it's just meant to be monitoring."""
    llm_token_usage_total.labels(model=model, agent=task_name, token_type="input").inc(input_tokens)
    llm_token_usage_total.labels(model=model, agent=task_name, token_type="output").inc(output_tokens)

    cost = _compute_cost(model, input_tokens, output_tokens)
    entry = {
        "task": task_name,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
        "timestamp": time.time(),
    }

    redis = get_redis_client()
    try:
        await redis.incrbyfloat("llm_cost:total_usd", cost)
        await redis.incrbyfloat(f"llm_cost:by_model:{model}", cost)
        daily_key = _daily_cost_key()
        await redis.incrbyfloat(daily_key, cost)
        await redis.expire(daily_key, 60 * 60 * 48)  # self-cleans; re-set every call, cheap
        await redis.lpush(COST_LOG_KEY, json.dumps(entry))
        await redis.ltrim(COST_LOG_KEY, 0, COST_LOG_MAX_ENTRIES - 1)
    except Exception:
        logger.warning("Failed to log LLM cost to Redis (task=%s)", task_name, exc_info=True)
    finally:
        await redis.aclose()

    return cost


async def get_total_cost() -> float:
    redis = get_redis_client()
    try:
        raw = await redis.get("llm_cost:total_usd")
        return float(raw) if raw else 0.0
    except Exception:
        logger.warning("Failed to read total LLM cost from Redis", exc_info=True)
        return 0.0
    finally:
        await redis.aclose()


async def get_recent_costs_by_model(since_timestamp: float) -> dict[str, float]:
    """Sums cost_usd per model from the recent cost log entries newer than
    `since_timestamp` — used to approximate "this pipeline run's" LLM spend for
    MLflow tracking. Reads the shared best-effort log (see log_cost's COST_LOG_KEY),
    so concurrent pipeline runs would double-count each other's costs; acceptable
    for this app's current single-run-at-a-time usage."""
    redis = get_redis_client()
    totals: dict[str, float] = {}
    try:
        raw_entries = await redis.lrange(COST_LOG_KEY, 0, COST_LOG_MAX_ENTRIES - 1)
        for raw in raw_entries:
            entry = json.loads(raw)
            if entry["timestamp"] < since_timestamp:
                break  # list is newest-first; everything older follows
            totals[entry["model"]] = totals.get(entry["model"], 0.0) + entry["cost_usd"]
    except Exception:
        logger.warning("Failed to read recent LLM costs from Redis", exc_info=True)
    finally:
        await redis.aclose()
    return totals


async def invoke_with_routing(
    complexity: TaskComplexity, task_name: str, prompt: str, temperature: float = 0
) -> str:
    """Plain-text invocation with routing, cost logging, and automatic
    single-retry fallback to the other provider if the primary call raises
    (timeout, rate limit, outage) — a Groq or OpenAI incident degrades this
    call to higher latency/cost instead of failing it outright.

    For structured output use invoke_structured_with_fallback(), which gets
    the same fallback behavior.

    Identical (task_name, temperature, prompt) calls are served from a Redis
    cache instead of hitting the model again, and once settings.LLM_DAILY_BUDGET_USD
    is exhausted for the day, new (non-cached) calls raise LLMBudgetExceededError.
    """
    cache_key = _prompt_cache_key(task_name, temperature, prompt)
    cached = await cache_service.get_cached_llm_response(cache_key)
    if cached is not None:
        logger.debug("LLM cache hit for task=%s", task_name)
        return cached

    await _enforce_budget(task_name)

    estimated = estimate_tokens(prompt)
    primary_model = choose_model(complexity, estimated)
    fallback_model = _fallback_model(primary_model)

    last_exc: Exception | None = None
    for attempt, model_name in enumerate((primary_model, fallback_model)):
        try:
            llm = _get_llm(model_name, temperature)
            response = await llm.ainvoke(prompt)

            input_tokens, output_tokens = extract_usage(response)
            if input_tokens == 0 and output_tokens == 0:
                input_tokens, output_tokens = estimated, estimate_tokens(str(response.content))
            await log_cost(task_name, model_name, input_tokens, output_tokens)

            if attempt == 1:
                logger.warning(
                    "LLM fallback succeeded for task=%s using %s after %s failed", task_name, model_name, primary_model
                )
            result = str(response.content)
            await cache_service.set_cached_llm_response(cache_key, result, LLM_RESPONSE_CACHE_TTL_SECONDS)
            return result
        except Exception as exc:
            last_exc = exc
            logger.warning("LLM call failed (task=%s, model=%s): %s", task_name, model_name, exc)

    raise RuntimeError(
        f"Both primary ({primary_model}) and fallback ({fallback_model}) LLM calls failed for task={task_name}"
    ) from last_exc


async def invoke_structured_with_fallback(
    complexity: TaskComplexity,
    task_name: str,
    prompt: str | list[Any],
    output_schema: type[SchemaT],
    temperature: float = 0,
) -> SchemaT:
    """Structured-output invocation with the same routing, cost logging, and
    cross-provider fallback as invoke_with_routing(). `prompt` may be a plain
    string or a pre-formatted message list (e.g. from a ChatPromptTemplate),
    for callers that need a system/human role split.

    Also shares invoke_with_routing()'s response cache and daily budget cap."""
    cache_key = _prompt_cache_key(task_name, temperature, prompt, schema_name=output_schema.__name__)
    cached = await cache_service.get_cached_llm_response(cache_key)
    if cached is not None:
        logger.debug("LLM cache hit for task=%s", task_name)
        return output_schema.model_validate_json(cached)

    await _enforce_budget(task_name)

    estimate_source = prompt if isinstance(prompt, str) else " ".join(str(getattr(m, "content", m)) for m in prompt)
    estimated = estimate_tokens(estimate_source)
    primary_model = choose_model(complexity, estimated)
    fallback_model = _fallback_model(primary_model)

    last_exc: Exception | None = None
    for attempt, model_name in enumerate((primary_model, fallback_model)):
        try:
            llm = _get_llm(model_name, temperature)
            structured_llm = llm.with_structured_output(output_schema, include_raw=True)
            result = await structured_llm.ainvoke(prompt)
            parsed: SchemaT = result["parsed"]

            input_tokens, output_tokens = extract_usage(result["raw"])
            await log_cost(task_name, model_name, input_tokens, output_tokens)

            if attempt == 1:
                logger.warning(
                    "LLM fallback succeeded for task=%s using %s after %s failed", task_name, model_name, primary_model
                )
            await cache_service.set_cached_llm_response(cache_key, parsed.model_dump_json(), LLM_RESPONSE_CACHE_TTL_SECONDS)
            return parsed
        except Exception as exc:
            last_exc = exc
            logger.warning("LLM call failed (task=%s, model=%s): %s", task_name, model_name, exc)

    raise RuntimeError(
        f"Both primary ({primary_model}) and fallback ({fallback_model}) LLM calls failed for task={task_name}"
    ) from last_exc
