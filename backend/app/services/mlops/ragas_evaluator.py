"""RAGAS-based evaluation of the candidate-lookup RAG flow (embedding retrieval over
resumes + LLM answer grounded in the retrieved resumes). Runs weekly in production
(see MODULE_7_SETUP.md for how that's wired) or on demand via POST /mlops/ragas/run.
"""

import logging
import sys
import types
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate, ParsingStatus
from app.models.mlops import RagEvalLog
from app.services import embedding_service, llm_router
from app.services.llm_router import TaskComplexity
from app.services.mlops import experiment_tracker

logger = logging.getLogger(__name__)

FAITHFULNESS_ALERT_THRESHOLD = 0.75
DEFAULT_SAMPLE_SIZE = 5
RETRIEVAL_TOP_K = 2


def _apply_vertexai_compat_shim() -> None:
    """ragas 0.4.3 unconditionally imports ChatVertexAI from
    langchain_community.chat_models.vertexai, a module langchain-community>=0.4
    removed. We never use Vertex AI, so stub the module before ragas imports it.
    See MODULE_7_SETUP.md for the full story (this also ruled out `evidently`).
    """
    module_name = "langchain_community.chat_models.vertexai"
    if module_name in sys.modules:
        return

    stub = types.ModuleType(module_name)

    class _ChatVertexAIStub:
        def __init__(self, *args, **kwargs) -> None:
            raise ImportError("Vertex AI is not used in this project (ragas compatibility stub)")

    stub.ChatVertexAI = _ChatVertexAIStub
    sys.modules[module_name] = stub


_apply_vertexai_compat_shim()

from ragas.embeddings import OpenAIEmbeddings as RagasOpenAIEmbeddings  # noqa: E402
from ragas.llms import llm_factory  # noqa: E402
from ragas.metrics.collections import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness  # noqa: E402

_ragas_llm = None
_ragas_embeddings = None


def _get_ragas_llm():
    global _ragas_llm
    if _ragas_llm is None:
        _ragas_llm = llm_factory("gpt-4o", provider="openai", client=embedding_service.get_openai_client())
    return _ragas_llm


def _get_ragas_embeddings():
    global _ragas_embeddings
    if _ragas_embeddings is None:
        _ragas_embeddings = RagasOpenAIEmbeddings(
            client=embedding_service.get_openai_client(), model=embedding_service.EMBEDDING_MODEL
        )
    return _ragas_embeddings


async def _sample_candidates(db: AsyncSession, sample_size: int) -> list[Candidate]:
    stmt = (
        select(Candidate)
        .where(Candidate.parsing_status == ParsingStatus.COMPLETED)
        .where(Candidate.resume_embedding.is_not(None))
        .where(Candidate.skills.is_not(None))
        .where(func.cardinality(Candidate.skills) > 0)
        .order_by(Candidate.created_at.desc())
        .limit(sample_size)
    )
    return list((await db.execute(stmt)).scalars().all())


def _build_question(candidate: Candidate) -> str:
    # A skill-lookup question, not a name lookup: dense retrieval matches semantic
    # content (skills/experience), not a person's name, so a name-shaped question
    # ("What skills does X have?") retrieves whichever resumes are generically
    # closest to that phrasing rather than X's own resume. This mirrors how the
    # app actually uses embeddings in production (JD-to-candidate skill matching,
    # Module 3) and is the retrieval task the embedding index is actually good at.
    primary_skill = candidate.skills[0]
    return f"Which candidate has experience with {primary_skill}?"


def _build_reference(candidate: Candidate) -> str:
    skills = ", ".join(candidate.skills or [])
    return f"{candidate.full_name or 'This candidate'} has experience with {skills}."


async def _retrieve_contexts(db: AsyncSession, question: str, top_k: int = RETRIEVAL_TOP_K) -> list[str]:
    """The actual retrieval half of the RAG flow being evaluated: embeds the question
    and does a real pgvector similarity search over resumes — the same retrieval
    primitive matching_service uses for candidate search (Module 3)."""
    question_embedding = await embedding_service.generate_embedding(question)
    stmt = (
        select(Candidate)
        .where(Candidate.resume_embedding.is_not(None))
        .where(Candidate.parsing_status == ParsingStatus.COMPLETED)
        .order_by(Candidate.resume_embedding.cosine_distance(question_embedding))
        .limit(top_k)
    )
    candidates = (await db.execute(stmt)).scalars().all()
    return [f"{c.full_name or 'Candidate'}: {c.resume_text or ''}"[:2000] for c in candidates]


async def _generate_answer(question: str, contexts: list[str]) -> str:
    """The generation half of the RAG flow: answers strictly from retrieved context,
    via Groq for low latency — same routing policy as the rest of the app (Module 4)."""
    context_block = "\n\n".join(contexts)
    prompt = (
        "Answer the question using ONLY the candidate profiles below. If the answer "
        "isn't supported by the profiles, say you don't have enough information.\n\n"
        f"Candidate profiles:\n{context_block}\n\n"
        f"Question: {question}"
    )
    return await llm_router.invoke_with_routing(TaskComplexity.SIMPLE, "ragas_eval_answer", prompt)


async def run_evaluation(db: AsyncSession, sample_size: int = DEFAULT_SAMPLE_SIZE) -> dict:
    candidates = await _sample_candidates(db, sample_size)
    if len(candidates) < 2:
        raise ValueError(
            f"Need at least 2 candidates with a parsed resume + embedding to run a meaningful "
            f"retrieval eval; found {len(candidates)}."
        )

    llm = _get_ragas_llm()
    embeddings = _get_ragas_embeddings()
    faithfulness_metric = Faithfulness(llm=llm)
    answer_relevancy_metric = AnswerRelevancy(llm=llm, embeddings=embeddings)
    context_precision_metric = ContextPrecision(llm=llm)
    context_recall_metric = ContextRecall(llm=llm)

    run_id = uuid.uuid4()
    rows: list[RagEvalLog] = []

    for candidate in candidates:
        question = _build_question(candidate)
        reference = _build_reference(candidate)
        contexts = await _retrieve_contexts(db, question)
        answer = await _generate_answer(question, contexts)

        faithfulness_score = (await faithfulness_metric.ascore(user_input=question, response=answer, retrieved_contexts=contexts)).value
        answer_relevancy_score = (await answer_relevancy_metric.ascore(user_input=question, response=answer)).value
        context_precision_score = (
            await context_precision_metric.ascore(user_input=question, reference=reference, retrieved_contexts=contexts)
        ).value
        context_recall_score = (
            await context_recall_metric.ascore(user_input=question, retrieved_contexts=contexts, reference=reference)
        ).value

        row = RagEvalLog(
            id=uuid.uuid4(),
            run_id=run_id,
            question=question,
            reference=reference,
            retrieved_contexts=contexts,
            answer=answer,
            faithfulness=faithfulness_score,
            answer_relevancy=answer_relevancy_score,
            context_precision=context_precision_score,
            context_recall=context_recall_score,
            alert_triggered=faithfulness_score < FAITHFULNESS_ALERT_THRESHOLD,
        )
        db.add(row)
        rows.append(row)

    await db.commit()

    avg_faithfulness = sum(r.faithfulness for r in rows) / len(rows)
    alert = avg_faithfulness < FAITHFULNESS_ALERT_THRESHOLD
    if alert:
        logger.warning(
            "RAGAS eval run %s: average faithfulness %.3f is below the %.2f alert threshold",
            run_id,
            avg_faithfulness,
            FAITHFULNESS_ALERT_THRESHOLD,
        )

    summary = {
        "run_id": run_id,
        "sample_size": len(rows),
        "avg_faithfulness": avg_faithfulness,
        "avg_answer_relevancy": sum(r.answer_relevancy for r in rows) / len(rows),
        "avg_context_precision": sum(r.context_precision for r in rows) / len(rows),
        "avg_context_recall": sum(r.context_recall for r in rows) / len(rows),
        "alert_triggered": alert,
    }

    try:
        await experiment_tracker.log_ragas_run(
            run_id,
            {k: v for k, v in summary.items() if k.startswith("avg_")},
            alert,
        )
    except Exception:
        logger.exception("Failed to log RAGAS run %s to MLflow", run_id)

    return {**summary, "rows": rows}
