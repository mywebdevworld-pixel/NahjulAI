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

# Corpus + vector index are pre-built and committed (see scripts/), not
# regenerated at image-build time: al-islam.org blocks scraping from cloud
# hosting IP ranges (Render, HF Spaces, Cloud Run all hit this).
COPY --chown=appuser:appuser data/corpus.json data/corpus.json
COPY --chown=appuser:appuser data/chroma/ data/chroma/

RUN chown -R appuser:appuser /app

USER appuser
ENV HOME=/home/appuser

EXPOSE 8000

# Honor the PORT env var set by hosts like Render / Cloud Run; default 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
