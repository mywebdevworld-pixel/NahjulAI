FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY scripts/ scripts/
COPY frontend/ frontend/

# Build the corpus + index at image build time (bakes data into the image).
# Comment these out if you prefer mounting a prebuilt ./data volume instead.
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    python scripts/download_data.py && \
    python scripts/scrape_alislam.py && \
    python scripts/build_corpus.py && \
    python scripts/ingest.py

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
