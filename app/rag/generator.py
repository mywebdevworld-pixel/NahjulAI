"""Answer generation: builds a grounded prompt from retrieved passages and
streams a response from any OpenAI-compatible LLM endpoint (Ollama, Groq,
OpenRouter, vLLM, ...). Falls back to an extractive answer when no LLM is
reachable so the app remains useful out of the box."""

import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.config import Settings
from app.models import ChatMessage
from app.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are Nahj AI, a knowledgeable and respectful assistant for Nahjul Balagha — \
the collection of sermons, letters, and sayings of Imam Ali ibn Abi Talib (peace \
be upon him), compiled by al-Sharif al-Radi. The English translation provided is \
by Sayyid Ali Raza.

Rules:
1. Ground every answer in the CONTEXT passages provided. Do not invent quotes, \
sermon numbers, or attributions.
2. Cite passages inline using square brackets exactly as referenced, e.g. \
[Sermon 27], [Letter 31], [Saying 100].
3. If the context does not contain enough information to answer, say so plainly \
and suggest what the user might ask instead. Never fabricate.
4. When quoting, quote exactly from the context.
5. Be respectful of the religious significance of the text. Present scholarly \
context neutrally when relevant.
6. Answer in the same language the user writes in.
7. Keep answers focused and well-structured; use short paragraphs or bullet \
points where it helps readability.
"""


def build_context_block(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for c in chunks:
        header = c.ref if not c.title else f"{c.ref} — {c.title}"
        parts.append(f"[{c.ref}] ({header})\n{c.text}")
    return "\n\n---\n\n".join(parts)


def build_messages(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[ChatMessage],
    max_history: int,
) -> list[dict]:
    context = build_context_block(chunks) if chunks else "(no passages retrieved)"
    user_block = (
        f"CONTEXT — passages from Nahjul Balagha:\n\n{context}\n\n"
        f"QUESTION: {question}"
    )
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history[-max_history:]:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": user_block})
    return messages


async def llm_reachable(settings: Settings) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"{settings.llm_base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            )
            return resp.status_code < 500
    except httpx.HTTPError:
        return False


async def stream_llm_answer(
    messages: list[dict], settings: Settings
) -> AsyncIterator[str]:
    """Stream tokens from an OpenAI-compatible /chat/completions endpoint."""
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "stream": True,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}

    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode(errors="replace")[:500]
                raise RuntimeError(f"LLM returned {resp.status_code}: {body}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"]
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                token = delta.get("content")
                if token:
                    yield token


def extractive_answer(question: str, chunks: list[RetrievedChunk]) -> str:
    """No-LLM fallback: present the most relevant passages directly."""
    if not chunks:
        return (
            "I could not find relevant passages in Nahjul Balagha for that "
            "question. Try rephrasing, or ask about a specific sermon, letter, "
            "or saying by number."
        )
    lines = [
        "*(No language model is currently configured — showing the most "
        "relevant passages retrieved from Nahjul Balagha. Set up Ollama or a "
        "free API key in `.env` to get synthesized answers.)*",
        "",
    ]
    for c in chunks[:3]:
        title = f" — {c.title}" if c.title else ""
        lines.append(f"**[{c.ref}]{title}**")
        text = c.text if len(c.text) <= 900 else c.text[:900].rsplit(" ", 1)[0] + " …"
        lines.append(f"> {text}")
        lines.append("")
    return "\n".join(lines)
