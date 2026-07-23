FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# torch is only used here for CPU inference (sentence-transformers cross-encoder,
# Module 3) — installing it from PyPI's default index on Linux pulls ~1.5GB of
# NVIDIA CUDA libraries as separate wheel dependencies that are never used. The
# CPU-only index avoids that; `pip install -r requirements.txt` below then finds
# torch==2.13.0 already satisfied and skips reinstalling it.
RUN pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
