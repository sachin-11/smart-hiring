import json
import logging
import uuid
from typing import TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.question_generator import generate_questions
from app.core.database import get_db_context
from app.core.redis_client import get_redis_client
from app.models.candidate import Candidate
from app.models.interview import Interview, InterviewStatus
from app.models.job import Job
from app.schemas.interview import AnswerQuality
from app.services import guardrails, llm_router
from app.services.llm_router import TaskComplexity

logger = logging.getLogger(__name__)

SESSION_KEY_PREFIX = "session:"
SESSION_TTL_SECONDS = 2 * 60 * 60
MAX_FOLLOW_UP_DEPTH = 2
FOLLOW_UP_SCORE_THRESHOLD = 3

INTRO_CATEGORY = "intro"
INTRO_COUNT = 2


def _build_intro_turns(candidate_name: str | None, job_title: str) -> list[dict]:
    """A short, fixed (non-LLM, non-scored) rapport-building opener — greeting +
    "how are you" + a self-introduction prompt — before the real, scored
    questions start, mirroring how a real interview actually opens."""
    first_name = candidate_name.split()[0] if candidate_name else None
    greeting_name = f", {first_name}" if first_name else ""
    return [
        {
            "question": (
                f"Hello{greeting_name}! Welcome, and thank you for joining us today for the "
                f"{job_title} role. How are you doing today?"
            ),
            "category": INTRO_CATEGORY,
            "rationale": "Warm, formal opening greeting.",
        },
        {
            "question": "Glad to hear that! Let's get started — could you tell me a little about yourself and your background?",
            "category": INTRO_CATEGORY,
            "rationale": "Open-ended self-introduction to build rapport before the scored questions begin.",
        },
    ]


class InterviewTurnState(TypedDict):
    session_id: str
    candidate_id: str
    job_id: str
    questions: list[dict]
    current_q_index: int
    follow_up_depth: int
    current_question: str
    current_category: str
    answer_text: str
    history: list[dict]
    score: int | None
    feedback: str | None
    is_follow_up: bool
    complete: bool
    next_question: str | None
    next_category: str | None
    errors: list[str]


def _display_progress(current_q_index: int, all_turns_len: int) -> tuple[int, int]:
    """Maps the internal turn index (which includes the intro turns at the
    front) to a "Question X of Y" the candidate actually sees — the intro
    isn't counted as one of the scored questions."""
    real_total = all_turns_len - INTRO_COUNT
    real_index = max(0, current_q_index - INTRO_COUNT)
    return real_index, real_total


# --- Nodes -----------------------------------------------------------------------


async def analyze_answer_node(state: InterviewTurnState) -> dict:
    """Scores answer quality 1-5 via a fast Groq model — response latency here
    directly gates how quickly the next question can be voiced back to the candidate."""
    if state["current_category"] == INTRO_CATEGORY:
        # Rapport-building small talk isn't scored — no LLM call needed, just
        # record it and move straight on (see _route_after_analysis).
        exchange = {
            "question": state["current_question"],
            "category": INTRO_CATEGORY,
            "is_follow_up": False,
            "answer": state["answer_text"],
            "score": None,
            "feedback": None,
        }
        return {"score": None, "feedback": None, "history": [*state["history"], exchange]}
    try:
        guardrails.guard_input(state["answer_text"], context=f"interview_answer session={state['session_id']}")
        prompt = (
            "You are grading a candidate's interview answer for quality: how specific, "
            "well-reasoned, and directly responsive it is to the question asked. Vague, "
            "evasive, or off-topic answers score low; concrete, well-supported answers score high.\n\n"
            f"Question ({state['current_category']}): {state['current_question']}\n"
            f"Candidate's answer: {guardrails.wrap_untrusted(state['answer_text'], 'candidate_answer')}\n\n"
            "Score from 1 (weak/evasive) to 5 (excellent) and give one-sentence feedback."
        )
        parsed = await llm_router.invoke_structured_with_fallback(
            TaskComplexity.SIMPLE, "analyze_interview_answer", prompt, AnswerQuality
        )

        exchange = {
            "question": state["current_question"],
            "category": state["current_category"],
            "is_follow_up": state["follow_up_depth"] > 0,
            "answer": state["answer_text"],
            "score": parsed.score,
            "feedback": parsed.feedback,
        }
        return {"score": parsed.score, "feedback": parsed.feedback, "history": [*state["history"], exchange]}
    except Exception as exc:
        logger.exception("analyze_answer_node failed for session=%s", state["session_id"])
        return {"errors": [*state["errors"], f"analyze_answer failed: {exc}"]}


async def generate_follow_up_node(state: InterviewTurnState) -> dict:
    """Digs deeper on a weak answer instead of moving on — Groq again, same latency reasoning."""
    try:
        prompt = (
            "The candidate gave a weak or vague answer to an interview question. Write ONE "
            "focused follow-up question that probes for the specific detail they missed. "
            "Stay in the same category and do not repeat the original question verbatim.\n\n"
            f"Original question ({state['current_category']}): {state['current_question']}\n"
            f"Candidate's answer: {guardrails.wrap_untrusted(state['answer_text'], 'candidate_answer')}\n"
            f"Why it was weak: {state['feedback']}\n\n"
            "Reply with only the follow-up question text."
        )
        follow_up = await llm_router.invoke_with_routing(TaskComplexity.SIMPLE, "generate_follow_up", prompt)
        return {
            "next_question": follow_up.strip(),
            "next_category": state["current_category"],
            "is_follow_up": True,
            "follow_up_depth": state["follow_up_depth"] + 1,
            "complete": False,
        }
    except Exception as exc:
        logger.exception("generate_follow_up_node failed for session=%s", state["session_id"])
        return {"errors": [*state["errors"], f"generate_follow_up failed: {exc}"]}


async def advance_node(state: InterviewTurnState) -> dict:
    """Moves to the next pre-generated question, or marks the interview complete."""
    next_index = state["current_q_index"] + 1
    if next_index >= len(state["questions"]):
        return {
            "current_q_index": next_index,
            "follow_up_depth": 0,
            "is_follow_up": False,
            "complete": True,
            "next_question": None,
            "next_category": None,
        }

    next_q = state["questions"][next_index]
    return {
        "current_q_index": next_index,
        "follow_up_depth": 0,
        "is_follow_up": False,
        "complete": False,
        "next_question": next_q["question"],
        "next_category": next_q["category"],
    }


async def error_handler_node(state: InterviewTurnState) -> dict:
    logger.error("Interview turn failed for session=%s: %s", state["session_id"], state["errors"])
    return {}


# --- Conditional routing -----------------------------------------------------------


def _route_after_analysis(state: InterviewTurnState) -> str:
    if state["errors"]:
        return "error_handler"
    if state["current_category"] == INTRO_CATEGORY:
        return "advance"
    if state["score"] < FOLLOW_UP_SCORE_THRESHOLD and state["follow_up_depth"] < MAX_FOLLOW_UP_DEPTH:
        return "generate_follow_up"
    return "advance"


# --- Graph construction --------------------------------------------------------------

_compiled_graph: CompiledStateGraph | None = None


def build_graph() -> CompiledStateGraph:
    graph = StateGraph(InterviewTurnState)

    graph.add_node("analyze_answer", analyze_answer_node)
    graph.add_node("generate_follow_up", generate_follow_up_node)
    graph.add_node("advance", advance_node)
    graph.add_node("error_handler", error_handler_node)

    graph.set_entry_point("analyze_answer")
    graph.add_conditional_edges("analyze_answer", _route_after_analysis)

    graph.add_edge("generate_follow_up", END)
    graph.add_edge("advance", END)
    graph.add_edge("error_handler", END)

    return graph.compile()


def get_compiled_graph() -> CompiledStateGraph:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


# --- Redis session memory -----------------------------------------------------------


async def _load_session(session_id: uuid.UUID) -> InterviewTurnState | None:
    redis = get_redis_client()
    try:
        raw = await redis.get(f"{SESSION_KEY_PREFIX}{session_id}")
        return json.loads(raw) if raw else None
    finally:
        await redis.aclose()


async def _save_session(session_id: uuid.UUID, state: InterviewTurnState) -> None:
    redis = get_redis_client()
    try:
        await redis.set(f"{SESSION_KEY_PREFIX}{session_id}", json.dumps(state), ex=SESSION_TTL_SECONDS)
    finally:
        await redis.aclose()


async def _delete_session(session_id: uuid.UUID) -> None:
    redis = get_redis_client()
    try:
        await redis.delete(f"{SESSION_KEY_PREFIX}{session_id}")
    finally:
        await redis.aclose()


# --- Public API ----------------------------------------------------------------------


async def start_interview(candidate_id: uuid.UUID, job_id: uuid.UUID) -> dict:
    async with get_db_context() as db:
        candidate = await db.get(Candidate, candidate_id)
        if candidate is None:
            raise ValueError("Candidate not found")
        job = await db.get(Job, job_id)
        if job is None:
            raise ValueError("Job not found")

        resume_data = {
            "skills": candidate.skills or [],
            "experience_years": candidate.experience_years,
        }
        jd_data = {
            "title": job.title,
            "required_skills": job.required_skills or [],
            "nice_to_have_skills": job.nice_to_have_skills or [],
            "responsibilities": job.responsibilities or [],
            "seniority_level": job.seniority_level.value if job.seniority_level else None,
        }
        candidate_name = candidate.full_name
        job_title = job.title

        interview = Interview(
            id=uuid.uuid4(),
            candidate_id=candidate_id,
            job_id=job_id,
            status=InterviewStatus.IN_PROGRESS,
        )
        db.add(interview)
        await db.commit()
        session_id = interview.id

    questions = await generate_questions(jd_data, resume_data)
    all_turns = _build_intro_turns(candidate_name, job_title) + [q.model_dump() for q in questions]
    first_turn = all_turns[0]

    state: InterviewTurnState = {
        "session_id": str(session_id),
        "candidate_id": str(candidate_id),
        "job_id": str(job_id),
        "questions": all_turns,
        "current_q_index": 0,
        "follow_up_depth": 0,
        "current_question": first_turn["question"],
        "current_category": first_turn["category"],
        "answer_text": "",
        "history": [],
        "score": None,
        "feedback": None,
        "is_follow_up": False,
        "complete": False,
        "next_question": None,
        "next_category": None,
        "errors": [],
    }
    await _save_session(session_id, state)

    display_index, display_total = _display_progress(0, len(all_turns))
    return {
        "session_id": session_id,
        "question": first_turn["question"],
        "category": first_turn["category"],
        "question_index": display_index,
        "total_questions": display_total,
    }


async def _finalize_interview(session_id: uuid.UUID, state: InterviewTurnState) -> None:
    scored = [ex["score"] for ex in state["history"] if ex.get("score") is not None]
    average_score = sum(scored) / len(scored) if scored else None
    transcript_lines = [f"Q ({ex['category']}): {ex['question']}\nA: {ex['answer']}" for ex in state["history"]]

    async with get_db_context() as db:
        interview = await db.get(Interview, session_id)
        if interview is None:
            logger.error("Interview row %s disappeared before finalization", session_id)
            return
        interview.status = InterviewStatus.COMPLETED
        interview.transcript = "\n\n".join(transcript_lines)
        interview.ai_score = average_score
        interview.ai_feedback = {"exchanges": state["history"]}
        await db.commit()

    await _delete_session(session_id)


async def submit_answer(session_id: uuid.UUID, answer_text: str) -> dict:
    state = await _load_session(session_id)
    if state is None:
        raise ValueError("Interview session not found or has expired")

    state["answer_text"] = answer_text

    graph = get_compiled_graph()
    update = await graph.ainvoke(state)
    state.update(update)

    if state["errors"]:
        await _save_session(session_id, state)
        raise RuntimeError("; ".join(state["errors"]))

    display_index, display_total = _display_progress(state["current_q_index"], len(state["questions"]))
    result = {
        "session_id": session_id,
        "score": state["score"],
        "feedback": state["feedback"],
        "is_follow_up": state["is_follow_up"],
        "complete": state["complete"],
        "question": None,
        "category": None,
        "question_index": display_index,
        "total_questions": display_total,
    }

    if state["complete"]:
        await _finalize_interview(session_id, state)
    else:
        state["current_question"] = state["next_question"]
        state["current_category"] = state["next_category"]
        await _save_session(session_id, state)
        result["question"] = state["next_question"]
        result["category"] = state["next_category"]

    return result


async def stop_interview(session_id: uuid.UUID) -> dict:
    """Recruiter-initiated early termination of an in-progress interview
    (candidate no-show, technical issue, recruiter cutting it short, etc).
    Persists whatever was answered so far — same shape as a natural
    completion — but marks the interview CANCELLED so it stays distinguishable
    from one the candidate actually finished."""
    state = await _load_session(session_id)
    if state is None:
        raise ValueError("Interview session not found, already ended, or expired")

    scored = [ex["score"] for ex in state["history"] if ex.get("score") is not None]
    average_score = sum(scored) / len(scored) if scored else None
    transcript_lines = [f"Q ({ex['category']}): {ex['question']}\nA: {ex['answer']}" for ex in state["history"]]

    async with get_db_context() as db:
        interview = await db.get(Interview, session_id)
        if interview is None:
            raise ValueError("Interview record not found")
        interview.status = InterviewStatus.CANCELLED
        interview.transcript = "\n\n".join(transcript_lines)
        interview.ai_score = average_score
        interview.ai_feedback = {"exchanges": state["history"]}
        await db.commit()

    await _delete_session(session_id)
    return {"session_id": session_id, "status": InterviewStatus.CANCELLED, "questions_answered": len(state["history"])}


async def get_live_transcript(session_id: uuid.UUID) -> dict | None:
    """Returns the in-progress transcript from Redis, including the current
    unanswered question. Returns None once the interview is finalized (at
    which point the caller should read the persisted Interview row instead)."""
    state = await _load_session(session_id)
    if state is None:
        return None

    exchanges = list(state["history"])
    exchanges.append(
        {
            "question": state["current_question"],
            "category": state["current_category"],
            "is_follow_up": state["follow_up_depth"] > 0,
            "answer": None,
            "score": None,
            "feedback": None,
        }
    )
    display_index, display_total = _display_progress(state["current_q_index"], len(state["questions"]))
    return {
        "candidate_id": state["candidate_id"],
        "job_id": state["job_id"],
        "status": InterviewStatus.IN_PROGRESS,
        "exchanges": exchanges,
        "question_index": display_index,
        "total_questions": display_total,
    }
