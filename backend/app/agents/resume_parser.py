import logging
from io import BytesIO

import fitz  # PyMuPDF
from docx import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.schemas.resume import ResumeData

logger = logging.getLogger(__name__)

# Resumes are short (typically 1-3 pages); a hard character cap comfortably
# covers that without needing a full map-reduce chunking pipeline.
MAX_RESUME_CHARS = 12000

_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an expert resume parser. Extract structured candidate data from the resume "
            "text below. If a field is not present in the resume, leave it null or an empty list. "
            "Estimate total_years_exp from the experience entries if it isn't stated explicitly.",
        ),
        ("human", "{resume_text}"),
    ]
)


class ResumeParserAgent:
    """Extracts structured candidate data from PDF/DOCX resumes using an LLM."""

    def __init__(self, model: str = "gpt-4o") -> None:
        llm = ChatOpenAI(model=model, temperature=0, api_key=settings.OPENAI_API_KEY)
        self._chain = _EXTRACTION_PROMPT | llm.with_structured_output(ResumeData)

    @staticmethod
    def extract_text(file_bytes: bytes, filename: str) -> str:
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        if ext == "pdf":
            return ResumeParserAgent._extract_pdf_text(file_bytes)
        if ext in ("docx", "doc"):
            return ResumeParserAgent._extract_docx_text(file_bytes)
        raise ValueError(f"Unsupported resume file type: .{ext}")

    @staticmethod
    def _extract_pdf_text(file_bytes: bytes) -> str:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            return "\n".join(page.get_text() for page in doc).strip()

    @staticmethod
    def _extract_docx_text(file_bytes: bytes) -> str:
        document = Document(BytesIO(file_bytes))
        return "\n".join(p.text for p in document.paragraphs if p.text.strip()).strip()

    @staticmethod
    def _prepare_for_extraction(text: str) -> str:
        """Keeps the LLM input bounded while preserving head (contact info,
        most recent experience) and tail (often education) for long resumes."""
        if len(text) <= MAX_RESUME_CHARS:
            return text
        head_budget = int(MAX_RESUME_CHARS * 0.85)
        tail_budget = MAX_RESUME_CHARS - head_budget
        return f"{text[:head_budget]}\n...\n{text[-tail_budget:]}"

    async def parse(self, file_bytes: bytes, filename: str) -> tuple[str, ResumeData]:
        """Extracts text then runs LLM structured extraction.

        Returns (raw_extracted_text, structured ResumeData).
        """
        raw_text = self.extract_text(file_bytes, filename)
        if not raw_text:
            raise ValueError("No extractable text found in resume")

        prepared_text = self._prepare_for_extraction(raw_text)
        result: ResumeData = await self._chain.ainvoke({"resume_text": prepared_text})
        return raw_text, result
