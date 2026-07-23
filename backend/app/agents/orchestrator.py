import logging
import uuid
from typing import TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.database import get_db_context
from app.models.candidate import Candidate, ParsingStatus
from app.models.job import Job
from app.schemas.pipeline import CandidateReport, InterviewQuestionSet
from app.services import llm_router, matching_service
from app.services.llm_router import TaskComplexity

logger = logging.getLogger(__name__)

MATCH_SCORE_THRESHOLD = 0.7


class HiringState(TypedDict):
    candidate_id: str
    job_id: str
    resume_data: dict
    jd_data: dict
    match_score: float
    interview_questions: list
    report: dict
    current_step: str
    errors: list


# --- Nodes -----------------------------------------------------------------------


async def parse_resume_node(state: HiringState) -> dict:
    """Loads the candidate's already-parsed resume (Module 2) and asks a fast
    Groq model for a short summary — a genuinely 'simple/extraction' task."""
    try:
        async with get_db_context() as session:
            candidate = await session.get(Candidate, uuid.UUID(state["candidate_id"]))
            if candidate is None:
                return {"current_step": "parse_resume", "errors": [*state["errors"], "Candidate not found"]}
            if candidate.parsing_status != ParsingStatus.COMPLETED:
                return {
                    "current_step": "parse_resume",
                    "errors": [
                        *state["errors"],
                        f"Candidate resume not parsed yet (status={candidate.parsing_status.value})",
                    ],
                }

            resume_data = {
                "name": candidate.full_name,
                "email": candidate.email,
                "skills": candidate.skills or [],
                "experience_years": candidate.experience_years,
                "experience": candidate.experience or [],
                "education": candidate.education or [],
                "resume_text": candidate.resume_text or "",
            }

        summary_prompt = (
            f"Summarize this candidate's background in one concise sentence.\n"
            f"Skills: {', '.join(resume_data['skills']) or 'none listed'}\n"
            f"Experience: {resume_data['experience_years'] or '?'} years\n"
            f"Resume excerpt: {resume_data['resume_text'][:1500]}"
        )
        summary = await llm_router.invoke_with_routing(TaskComplexity.SIMPLE, "parse_resume", summary_prompt)
        resume_data["summary"] = summary

        return {"current_step": "parse_resume", "resume_data": resume_data}
    except Exception as exc:
        logger.exception("parse_resume_node failed")
        return {"current_step": "parse_resume", "errors": [*state["errors"], f"parse_resume failed: {exc}"]}


async def analyze_jd_node(state: HiringState) -> dict:
    """Loads the job's already-analyzed requirements (Module 3) and asks a
    fast Groq model for a short summary."""
    if state["errors"]:
        return {}
    try:
        async with get_db_context() as session:
            job = await session.get(Job, uuid.UUID(state["job_id"]))
            if job is None:
                return {"current_step": "analyze_jd", "errors": [*state["errors"], "Job not found"]}

            jd_data = {
                "title": job.title,
                "description": job.description,
                "required_skills": job.required_skills or [],
                "nice_to_have_skills": job.nice_to_have_skills or [],
                "responsibilities": job.responsibilities or [],
                "seniority_level": job.seniority_level.value if job.seniority_level else None,
                "min_experience": job.min_experience,
            }

        summary_prompt = (
            f"Summarize this job's key requirements in one concise sentence.\n"
            f"Title: {jd_data['title']}\n"
            f"Required skills: {', '.join(jd_data['required_skills']) or 'none listed'}\n"
            f"Responsibilities: {', '.join(jd_data['responsibilities']) or 'none listed'}"
        )
        summary = await llm_router.invoke_with_routing(TaskComplexity.SIMPLE, "analyze_jd", summary_prompt)
        jd_data["summary"] = summary

        return {"current_step": "analyze_jd", "jd_data": jd_data}
    except Exception as exc:
        logger.exception("analyze_jd_node failed")
        return {"current_step": "analyze_jd", "errors": [*state["errors"], f"analyze_jd failed: {exc}"]}


async def match_candidates_node(state: HiringState) -> dict:
    """Cross-encoder relevance score for this specific candidate/job pair."""
    if state["errors"]:
        return {}
    try:
        resume_text = state["resume_data"].get("resume_text", "")
        jd_text = state["jd_data"].get("description", "")
        score = await matching_service.score_single_pair(jd_text, resume_text)
        return {"current_step": "match_candidates", "match_score": round(score, 4)}
    except Exception as exc:
        logger.exception("match_candidates_node failed")
        return {"current_step": "match_candidates", "errors": [*state["errors"], f"match_candidates failed: {exc}"]}


async def generate_questions_node(state: HiringState) -> dict:
    """Only reached when match_score > threshold — GPT-4o generates tailored
    interview questions."""
    if state["errors"]:
        return {}
    try:
        prompt = (
            f"Generate 5 interview questions for a candidate applying to this role.\n\n"
            f"Job: {state['jd_data'].get('title')}\n"
            f"Required skills: {', '.join(state['jd_data'].get('required_skills', []))}\n"
            f"Responsibilities: {', '.join(state['jd_data'].get('responsibilities', []))}\n\n"
            f"Candidate skills: {', '.join(state['resume_data'].get('skills', []))}\n"
            f"Candidate experience: {state['resume_data'].get('experience_years')} years\n\n"
            "Mix technical and behavioral questions. For each, give a short rationale for "
            "why it's relevant given this specific candidate and role."
        )
        llm, model_name = llm_router.get_llm(
            TaskComplexity.COMPLEX, estimated_tokens=llm_router.estimate_tokens(prompt)
        )
        structured_llm = llm.with_structured_output(InterviewQuestionSet, include_raw=True)
        result = await structured_llm.ainvoke(prompt)
        parsed: InterviewQuestionSet = result["parsed"]

        input_tokens, output_tokens = llm_router.extract_usage(result["raw"])
        await llm_router.log_cost("generate_questions", model_name, input_tokens, output_tokens)

        return {
            "current_step": "generate_questions",
            "interview_questions": [q.model_dump() for q in parsed.questions],
        }
    except Exception as exc:
        logger.exception("generate_questions_node failed")
        return {
            "current_step": "generate_questions",
            "errors": [*state["errors"], f"generate_questions failed: {exc}"],
        }


async def _build_report(state: HiringState, rejection: bool) -> dict:
    stance = (
        "Explain why this candidate is likely NOT a good fit and should be rejected for this role."
        if rejection
        else "Explain why this candidate is a good fit and should proceed to interview."
    )
    prompt = (
        f"{stance}\n\n"
        f"Job: {state['jd_data'].get('title')}\n"
        f"Required skills: {', '.join(state['jd_data'].get('required_skills', []))}\n"
        f"Candidate skills: {', '.join(state['resume_data'].get('skills', []))}\n"
        f"Candidate experience: {state['resume_data'].get('experience_years')} years\n"
        f"Match score: {state['match_score']:.2f} (0-1 scale)\n\n"
        "Write a concise summary, list strengths, list concerns, and give a clear recommendation."
    )
    llm, model_name = llm_router.get_llm(TaskComplexity.COMPLEX, estimated_tokens=llm_router.estimate_tokens(prompt))
    structured_llm = llm.with_structured_output(CandidateReport, include_raw=True)
    result = await structured_llm.ainvoke(prompt)
    parsed: CandidateReport = result["parsed"]

    input_tokens, output_tokens = llm_router.extract_usage(result["raw"])
    task_name = "create_rejection_report" if rejection else "create_report"
    await llm_router.log_cost(task_name, model_name, input_tokens, output_tokens)

    return parsed.model_dump()


async def create_report_node(state: HiringState) -> dict:
    if state["errors"]:
        return {}
    try:
        report = await _build_report(state, rejection=False)
        return {"current_step": "create_report", "report": report}
    except Exception as exc:
        logger.exception("create_report_node failed")
        return {"current_step": "create_report", "errors": [*state["errors"], f"create_report failed: {exc}"]}


async def create_rejection_report_node(state: HiringState) -> dict:
    if state["errors"]:
        return {}
    try:
        report = await _build_report(state, rejection=True)
        return {"current_step": "create_rejection_report", "report": report}
    except Exception as exc:
        logger.exception("create_rejection_report_node failed")
        return {
            "current_step": "create_rejection_report",
            "errors": [*state["errors"], f"create_rejection_report failed: {exc}"],
        }


async def error_handler_node(state: HiringState) -> dict:
    logger.error(
        "Pipeline failed for candidate=%s job=%s: %s", state["candidate_id"], state["job_id"], state["errors"]
    )
    return {"current_step": "error"}


# --- Conditional routing -----------------------------------------------------------


def _route_after(next_step: str):
    def _route(state: HiringState) -> str:
        return "error_handler" if state["errors"] else next_step

    return _route


def _route_after_match(state: HiringState) -> str:
    if state["errors"]:
        return "error_handler"
    return "generate_questions" if state["match_score"] > MATCH_SCORE_THRESHOLD else "create_rejection_report"


# --- Graph construction --------------------------------------------------------------

_compiled_graph: CompiledStateGraph | None = None


def build_graph() -> CompiledStateGraph:
    graph = StateGraph(HiringState)

    graph.add_node("parse_resume", parse_resume_node)
    graph.add_node("analyze_jd", analyze_jd_node)
    graph.add_node("match_candidates", match_candidates_node)
    graph.add_node("generate_questions", generate_questions_node)
    graph.add_node("create_report", create_report_node)
    graph.add_node("create_rejection_report", create_rejection_report_node)
    graph.add_node("error_handler", error_handler_node)

    graph.set_entry_point("parse_resume")

    graph.add_conditional_edges("parse_resume", _route_after("analyze_jd"))
    graph.add_conditional_edges("analyze_jd", _route_after("match_candidates"))
    graph.add_conditional_edges("match_candidates", _route_after_match)
    graph.add_conditional_edges("generate_questions", _route_after("create_report"))

    graph.add_edge("create_report", END)
    graph.add_edge("create_rejection_report", END)
    graph.add_edge("error_handler", END)

    return graph.compile()


def get_compiled_graph() -> CompiledStateGraph:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def initial_state(candidate_id: uuid.UUID, job_id: uuid.UUID) -> HiringState:
    return HiringState(
        candidate_id=str(candidate_id),
        job_id=str(job_id),
        resume_data={},
        jd_data={},
        match_score=0.0,
        interview_questions=[],
        report={},
        current_step="start",
        errors=[],
    )
