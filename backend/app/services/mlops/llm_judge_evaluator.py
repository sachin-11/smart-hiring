"""LLM-as-judge evaluation of interview answer scoring.

RAGAS (see ragas_evaluator.py) evaluates the *retrieval* half of this app's AI
surface. Nothing evaluated the *generation/judgment* half — whether the
answer-scoring model (Groq, routed for low latency during a live interview)
is actually scoring well. This runs a sample of already-scored answers past
a second, independent, deliberately stronger model (GPT-4o) blind to the
original score, and measures agreement — the same idea as a human calibration
review, applied to the model that stands in for one.
"""

import logging
import random
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interview import Interview, InterviewStatus
from app.models.mlops import AnswerJudgeLog
from app.schemas.interview import AnswerJudgment
from app.services import guardrails, llm_router
from app.services.llm_router import TaskComplexity
from app.services.mlops import experiment_tracker

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_SIZE = 5
AGREEMENT_TOLERANCE = 1  # judge score within this many points counts as "agrees"
DISAGREEMENT_ALERT_THRESHOLD = 0.3  # alert if more than 30% of the sample disagrees
CANDIDATE_POOL_SIZE = 50


async def _sample_scored_exchanges(db: AsyncSession, sample_size: int) -> list[tuple[uuid.UUID, dict]]:
    """Pulls (interview_id, exchange) pairs from recently completed interviews.
    Only real, actually-scored exchanges are eligible — intro small talk
    (score=None) is excluded the same way it's excluded from the average score."""
    stmt = (
        select(Interview)
        .where(Interview.status == InterviewStatus.COMPLETED)
        .where(Interview.ai_feedback.is_not(None))
        .order_by(Interview.updated_at.desc())
        .limit(CANDIDATE_POOL_SIZE)
    )
    interviews = (await db.execute(stmt)).scalars().all()

    pool: list[tuple[uuid.UUID, dict]] = []
    for interview in interviews:
        exchanges = (interview.ai_feedback or {}).get("exchanges", [])
        for exchange in exchanges:
            if exchange.get("score") is not None and exchange.get("answer"):
                pool.append((interview.id, exchange))

    random.shuffle(pool)
    return pool[:sample_size]


async def _judge_answer(question: str, answer: str, category: str) -> AnswerJudgment:
    guardrails.guard_input(answer, context="llm_judge_eval")
    prompt = (
        "You are an independent interview quality auditor. Score this candidate's answer "
        "the same way a technical interviewer would: how specific, well-reasoned, and directly "
        "responsive it is to the question. You have not seen any prior score for this answer — "
        "form your own independent judgment from the question and answer alone.\n\n"
        f"Question ({category}): {question}\n"
        f"Candidate's answer: {guardrails.wrap_untrusted(answer, 'candidate_answer')}\n\n"
        "Score from 1 (weak/evasive) to 5 (excellent) and give one-sentence reasoning."
    )
    # Deliberately the stronger/complex-tier model, auditing a sample of what the
    # faster/cheaper model (routed SIMPLE, for live-interview latency) produced.
    return await llm_router.invoke_structured_with_fallback(
        TaskComplexity.COMPLEX, "judge_answer_quality", prompt, AnswerJudgment
    )


async def run_evaluation(db: AsyncSession, sample_size: int = DEFAULT_SAMPLE_SIZE) -> dict:
    samples = await _sample_scored_exchanges(db, sample_size)
    if len(samples) < 2:
        raise ValueError(
            f"Need at least 2 scored interview answers to run a meaningful judge eval; found {len(samples)}."
        )

    run_id = uuid.uuid4()
    rows: list[AnswerJudgeLog] = []

    for interview_id, exchange in samples:
        judgment = await _judge_answer(exchange["question"], exchange["answer"], exchange["category"])
        original_score = exchange["score"]
        agrees = abs(judgment.score - original_score) <= AGREEMENT_TOLERANCE

        row = AnswerJudgeLog(
            id=uuid.uuid4(),
            run_id=run_id,
            interview_id=interview_id,
            question=exchange["question"],
            answer=exchange["answer"],
            original_score=original_score,
            judge_score=judgment.score,
            judge_reasoning=judgment.reasoning,
            agrees=agrees,
            alert_triggered=not agrees,
        )
        db.add(row)
        rows.append(row)

    await db.commit()

    agreement_rate = sum(1 for r in rows if r.agrees) / len(rows)
    avg_abs_diff = sum(abs(r.judge_score - r.original_score) for r in rows) / len(rows)
    alert = (1 - agreement_rate) > DISAGREEMENT_ALERT_THRESHOLD

    if alert:
        logger.warning(
            "LLM-judge eval run %s: agreement rate %.2f is below the %.0f%% threshold",
            run_id,
            agreement_rate,
            (1 - DISAGREEMENT_ALERT_THRESHOLD) * 100,
        )

    summary = {
        "run_id": run_id,
        "sample_size": len(rows),
        "agreement_rate": agreement_rate,
        "avg_absolute_score_diff": avg_abs_diff,
        "alert_triggered": alert,
    }

    try:
        await experiment_tracker.log_judge_run(
            run_id,
            {"agreement_rate": agreement_rate, "avg_absolute_score_diff": avg_abs_diff},
            alert,
        )
    except Exception:
        logger.exception("Failed to log judge eval run %s to MLflow", run_id)

    return {**summary, "rows": rows}
