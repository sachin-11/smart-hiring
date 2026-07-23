import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.schemas.job import JDAnalysis

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
    """Extracts structured requirements from a job description using an LLM."""

    def __init__(self, model: str = "gpt-4o") -> None:
        llm = ChatOpenAI(model=model, temperature=0, api_key=settings.OPENAI_API_KEY)
        self._chain = _EXTRACTION_PROMPT | llm.with_structured_output(JDAnalysis)

    async def analyze(self, jd_text: str) -> JDAnalysis:
        if not jd_text.strip():
            raise ValueError("Job description text is empty")
        result: JDAnalysis = await self._chain.ainvoke({"jd_text": jd_text})
        return result
