"""API routes: chat (SSE streaming), search, direct passage lookup, health."""

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.models import (
    ChatRequest,
    HealthResponse,
    PassageResponse,
    SearchResponse,
    Source,
)
from app.rag import generator
from app.rag.retriever import RetrievedChunk, Retriever
from app.ratelimit import chat_limiter, search_limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def get_retriever(request: Request) -> Retriever:
    return request.app.state.retriever


def _chunk_to_source(c: RetrievedChunk) -> Source:
    return Source(
        ref=c.ref,
        title=c.title,
        text=c.text,
        doc_id=c.doc_id,
        chunk_index=c.chunk_index,
        score=c.score,
    )


def _sse(event: str, data: dict | list) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    """Stream a grounded answer. SSE events: `sources`, `token`, `done`, `error`."""
    chat_limiter.check(request)
    settings = get_settings()
    retriever = get_retriever(request)

    # Retrieval: explicit references (e.g. "Sermon 27") are pinned first,
    # then hybrid search fills the remaining slots.
    pinned: list[RetrievedChunk] = []
    for doc in retriever.detect_references(payload.message)[:2]:
        text = doc["text"]
        pinned.append(
            RetrievedChunk(
                chunk_id=f"{doc['id']}#full",
                doc_id=doc["id"],
                ref=doc["ref"],
                title=doc.get("title", ""),
                text=text if len(text) <= 6000 else text[:6000] + " …",
                chunk_index=0,
                score=1.0,
            )
        )
    searched = retriever.search(payload.message)
    pinned_docs = {c.doc_id for c in pinned}
    chunks = pinned + [c for c in searched if c.doc_id not in pinned_docs]
    chunks = chunks[: settings.top_k]

    messages = generator.build_messages(
        payload.message, chunks, payload.history, settings.max_history_messages
    )

    async def event_stream():
        yield _sse("sources", [ _chunk_to_source(c).model_dump() for c in chunks ])
        try:
            got_tokens = False
            async for token in generator.stream_llm_answer(messages, settings):
                got_tokens = True
                yield _sse("token", {"t": token})
            if not got_tokens:
                yield _sse("token", {"t": generator.extractive_answer(payload.message, chunks)})
        except Exception as exc:  # LLM unreachable / errored → extractive fallback
            logger.warning("LLM generation failed (%s); using extractive fallback", exc)
            yield _sse("token", {"t": generator.extractive_answer(payload.message, chunks)})
        yield _sse("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/search", response_model=SearchResponse)
async def search(q: str, request: Request, k: int = 6) -> SearchResponse:
    search_limiter.check(request)
    if not q.strip():
        raise HTTPException(status_code=422, detail="Query must not be empty")
    retriever = get_retriever(request)
    results = retriever.search(q.strip(), top_k=min(max(k, 1), 20))
    return SearchResponse(query=q, results=[_chunk_to_source(c) for c in results])


@router.get("/passage/{doc_type}/{number}", response_model=PassageResponse)
async def passage(doc_type: str, number: int, request: Request) -> PassageResponse:
    doc_type = doc_type.lower().rstrip("s")
    if doc_type not in {"sermon", "letter", "saying"}:
        raise HTTPException(status_code=404, detail="Type must be sermon, letter, or saying")
    doc = get_retriever(request).get_document(doc_type, number)
    if not doc:
        raise HTTPException(status_code=404, detail=f"{doc_type.title()} {number} not found")
    return PassageResponse(ref=doc["ref"], title=doc.get("title", ""), text=doc["text"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = get_settings()
    retriever = get_retriever(request)
    return HealthResponse(
        status="ok",
        corpus_documents=len(retriever.documents),
        indexed_chunks=retriever.chunk_count,
        llm_reachable=await generator.llm_reachable(settings),
        llm_model=settings.llm_model,
    )
