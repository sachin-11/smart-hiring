import enum
import json
import logging
import time

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.redis_client import get_redis_client
from app.services.monitoring import llm_token_usage_total

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


def get_llm(
    complexity: TaskComplexity, estimated_tokens: int = 0, temperature: float = 0
) -> tuple[BaseChatModel, str]:
    """Returns (chat_model, model_name) chosen by the routing policy."""
    model_name = choose_model(complexity, estimated_tokens)
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
    return _llm_cache[cache_key], model_name


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
    """Plain-text invocation with routing + cost logging.

    For structured output, call get_llm() directly and build your own chain
    so you can pass include_raw=True and log usage from the raw message.
    """
    estimated = estimate_tokens(prompt)
    llm, model_name = get_llm(complexity, estimated_tokens=estimated, temperature=temperature)
    response = await llm.ainvoke(prompt)

    input_tokens, output_tokens = extract_usage(response)
    if input_tokens == 0 and output_tokens == 0:
        input_tokens, output_tokens = estimated, estimate_tokens(str(response.content))
    await log_cost(task_name, model_name, input_tokens, output_tokens)

    return str(response.content)
