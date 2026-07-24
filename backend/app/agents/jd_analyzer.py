import logging

from langchain_core.prompts import ChatPromptTemplate

from app.schemas.job import JDAnalysis
from app.services import guardrails, llm_router
from app.services.llm_router import TaskComplexity

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an expert technical recruiter. Extract structured data from the job "
            "description text below: title, required_skills (must-haves only), nice_to_have "
            "skills, min_experience (years, as a number), responsibilities, and seniority_level. "
            "If a field isn't present in the text, leave it null or an empty list.",
        ),
        ("human", "{jd_text}"),
    ]
)


class JDAnalyzerAgent:
    """Extracts structured requirements from a job description using an LLM.

    Routed through llm_router (task-complexity-based model choice, cost
    logging, and automatic cross-provider fallback) rather than hardcoding
    a single OpenAI client — this used to be the one agent in the codebase
    with no fallback if OpenAI had an outage.
    """

    async def analyze(self, jd_text: str) -> JDAnalysis:
        if not jd_text.strip():
            raise ValueError("Job description text is empty")
        guardrails.guard_input(jd_text, context="jd_analysis")
        messages = _EXTRACTION_PROMPT.format_messages(jd_text=guardrails.wrap_untrusted(jd_text, "job_description"))
        result: JDAnalysis = await llm_router.invoke_structured_with_fallback(
            TaskComplexity.COMPLEX, "analyze_job_description", messages, JDAnalysis
        )
        return result
