import logging

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.candidate import Candidate

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


async def generate_embedding(text: str) -> list[float]:
    client = get_openai_client()
    # text-embedding-3-small caps at ~8191 tokens; this char-based cap is a
    # cheap safeguard against pathologically long input, not exact tokenization.
    response = await client.embeddings.create(model=EMBEDDING_MODEL, input=text[:8000])
    return response.data[0].embedding


async def embed_and_store_candidate(session: AsyncSession, candidate: Candidate, text: str) -> None:
    """Generates an embedding for the candidate's resume text and persists it to pgvector."""
    embedding = await generate_embedding(text)
    candidate.resume_embedding = embedding
    await session.commit()
