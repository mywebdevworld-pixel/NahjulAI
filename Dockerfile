FROM python:3.12-slim

# Hugging Face Spaces (and good practice generally): run as UID 1000
RUN useradd -m -u 1000 appuser

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser app/ app/
COPY --chown=appuser:appuser scripts/ scripts/
COPY --chown=appuser:appuser frontend/ frontend/

USER appuser
ENV HOME=/home/appuser

# Build the corpus + index at image build time (bakes data into the image).
# Runs as appuser so the embedding-model cache is reusable at runtime.
RUN python scripts/download_data.py && \
    python scripts/scrape_alislam.py && \
    python scripts/build_corpus.py && \
    python scripts/ingest.py

EXPOSE 8000

# Honor the PORT env var set by hosts like Render / Cloud Run; default 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
