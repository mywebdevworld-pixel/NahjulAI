# Nahj AI 🕌

A production-quality, fully open-source **RAG chatbot for Nahjul Balagha** — the
sermons, letters, and sayings of Imam Ali ibn Abi Talib (peace be upon him),
compiled by al-Sharif al-Radi. English translation by Sayyid Ali Raza.

Every answer is grounded in retrieved passages and cited inline
(`[Sermon 27]`, `[Letter 31]`, `[Saying 100]`) — click any citation to read the
full original passage.

## Architecture

```
Browser ──► FastAPI ──► Hybrid Retriever ──► ChromaDB (vectors, embedded)
 (SSE          │              │        └────► BM25 (lexical)
  stream)      │              └── Reciprocal Rank Fusion + direct-reference pinning
               └────► Any OpenAI-compatible LLM (Ollama local / Groq / OpenRouter)
```

| Component  | Technology | Cost |
|---|---|---|
| Corpus | Sayyid Ali Raza translation (241 sermons, 79 letters, ~480 sayings) | Free |
| Embeddings | `fastembed` (ONNX, `BAAI/bge-small-en-v1.5`) — no GPU, no torch | Free |
| Vector DB | ChromaDB (embedded, persistent) | Free |
| Lexical search | BM25 (`rank-bm25`), fused with vectors via RRF | Free |
| LLM | Ollama (local) by default; any OpenAI-compatible API via `.env` | Free |
| Backend | FastAPI + SSE streaming | Free |
| Frontend | Vanilla HTML/CSS/JS (zero dependencies, dark-mode aware) | Free |

## Quick start

```bash
# 1. Install dependencies (Python 3.11+)
python -m venv .venv
.venv\Scripts\activate          # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt

# 2. Build the knowledge base (downloads sources, parses, chunks, embeds)
python scripts/download_data.py     # sermons/letters markdown + sayings page
python scripts/scrape_alislam.py    # complete letters 1-79 + missing sermons
python scripts/build_corpus.py      # parse + merge -> data/corpus.json
python scripts/ingest.py            # chunk + embed -> data/chroma/

# 3. Configure the LLM
copy .env.example .env           # then edit if needed (defaults to local Ollama)

# 4. Run
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** and start asking.

### LLM options (pick one)

1. **Ollama (local, private, free)** — install from [ollama.com](https://ollama.com), then
   `ollama pull llama3.1:8b`. The default `.env` already points at it.
2. **Groq (hosted, free tier, very fast)** — get a key at
   [console.groq.com](https://console.groq.com) and set in `.env`:
   ```
   LLM_BASE_URL=https://api.groq.com/openai/v1
   LLM_MODEL=llama-3.3-70b-versatile
   LLM_API_KEY=gsk_...
   ```
3. **OpenRouter free models** — [openrouter.ai](https://openrouter.ai).

**No LLM configured?** The app still works: it falls back to *extractive mode*,
returning the most relevant passages verbatim with citations.

## API

| Endpoint | Description |
|---|---|
| `POST /api/chat` | Streamed chat (SSE events: `sources`, `token`, `done`) |
| `GET /api/search?q=...&k=6` | Hybrid semantic + lexical passage search |
| `GET /api/passage/{type}/{number}` | Full text of a sermon / letter / saying |
| `GET /api/health` | Corpus size, index size, LLM reachability |

Interactive docs at `/docs` (Swagger UI).

## How retrieval works

1. **Direct references** — if the question names a passage ("what does *Letter 31*
   say?"), that document is fetched directly and pinned to the top of the context.
2. **Hybrid search** — the query is embedded (`bge-small-en-v1.5`) and searched in
   ChromaDB; in parallel a BM25 lexical search runs over all chunks. The two
   rankings are merged with Reciprocal Rank Fusion.
3. **Grounded generation** — the top passages are placed in the prompt with strict
   instructions: quote exactly, cite every claim, refuse to fabricate.

## Docker

```bash
docker compose up --build
docker compose exec ollama ollama pull llama3.1:8b   # one-time model download
```

App on `http://localhost:8000`, with Ollama running as a sidecar container.

## Tests

```bash
pytest        # corpus integrity + API tests (needs the index built first)
```

## Project layout

```
app/
  main.py            FastAPI app: lifespan, CORS, static frontend
  config.py          Settings (env / .env)
  models.py          Pydantic schemas
  api/routes.py      /api/chat /api/search /api/passage /api/health
  rag/
    embeddings.py    fastembed wrapper
    vectorstore.py   ChromaDB persistent collection
    retriever.py     hybrid retrieval (vector + BM25 + RRF + reference pinning)
    generator.py     prompt building, SSE LLM streaming, extractive fallback
scripts/
  download_data.py   fetch raw sources → data/raw/
  scrape_alislam.py  complete letters 1-79 + missing sermons from al-islam.org
  build_corpus.py    parse + merge → data/corpus.json (~800 documents)
  ingest.py          chunk + embed → data/chroma/
frontend/            zero-dependency chat UI (streaming, citations, passage modal)
tests/               corpus integrity + API tests
```

## Content note

The translation used is the widely-distributed English rendering by Sayyid Ali
Raza. Answers are AI-generated and should always be verified against the cited
passages — the passage viewer exists precisely for that.
