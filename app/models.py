"""Pydantic schemas shared by the API layer."""

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=40)


class Source(BaseModel):
    ref: str                  # e.g. "Sermon 27"
    title: str
    text: str                 # the retrieved chunk
    doc_id: str               # e.g. "sermon-27"
    chunk_index: int
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[Source]


class PassageResponse(BaseModel):
    ref: str
    title: str
    text: str


class HealthResponse(BaseModel):
    status: str
    corpus_documents: int
    indexed_chunks: int
    llm_reachable: bool
    llm_model: str
