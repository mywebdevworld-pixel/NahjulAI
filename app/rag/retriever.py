"""Hybrid retrieval: vector search (Chroma) + BM25, fused with Reciprocal Rank
Fusion, plus direct lookup when the user cites a passage by number
("what does Sermon 27 say?")."""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from app.config import Settings
from app.rag.embeddings import embed_query
from app.rag.vectorstore import get_collection

logger = logging.getLogger(__name__)

# "sermon 27", "letter #31", "saying 100", plus common transliterated synonyms
_REF_PATTERN = re.compile(
    r"\b(sermon|khutbah?|letter|epistle|saying|hikmah?|maxim|aphorism)s?\s*(?:#|no\.?|number)?\s*(\d{1,3})\b",
    re.IGNORECASE,
)

_TYPE_ALIASES = {
    "sermon": "sermon", "khutba": "sermon", "khutbah": "sermon",
    "letter": "letter", "epistle": "letter",
    "saying": "saying", "hikma": "saying", "hikmah": "saying",
    "maxim": "saying", "aphorism": "saying",
}

_TOKEN_RE = re.compile(r"[a-z0-9']+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    ref: str
    title: str
    text: str
    chunk_index: int
    score: float


class Retriever:
    """Loads the corpus + index once and serves hybrid queries."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.collection = get_collection(settings.chroma_dir)
        self.documents: dict[str, dict] = {}
        self._chunks: list[dict] = []
        self._bm25: BM25Okapi | None = None
        self._load_corpus(settings.corpus_path)
        self._load_bm25()

    # ── setup ────────────────────────────────────────────────────────────────

    def _load_corpus(self, corpus_path: Path) -> None:
        if not corpus_path.exists():
            logger.warning("Corpus file %s not found — run scripts/build_corpus.py", corpus_path)
            return
        docs = json.loads(corpus_path.read_text(encoding="utf-8"))
        self.documents = {d["id"]: d for d in docs}
        logger.info("Loaded %d corpus documents", len(self.documents))

    def _load_bm25(self) -> None:
        count = self.collection.count()
        if count == 0:
            logger.warning("Vector collection is empty — run scripts/ingest.py")
            return
        data = self.collection.get(include=["documents", "metadatas"])
        self._chunks = [
            {"chunk_id": cid, "text": doc, **meta}
            for cid, doc, meta in zip(data["ids"], data["documents"], data["metadatas"])
        ]
        self._bm25 = BM25Okapi([_tokenize(c["text"]) for c in self._chunks])
        logger.info("BM25 index built over %d chunks", len(self._chunks))

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    # ── public API ───────────────────────────────────────────────────────────

    def get_document(self, doc_type: str, number: int) -> dict | None:
        return self.documents.get(f"{doc_type}-{number}")

    def detect_references(self, query: str) -> list[dict]:
        """Return corpus documents explicitly cited by number in the query."""
        found, seen = [], set()
        for match in _REF_PATTERN.finditer(query):
            doc_type = _TYPE_ALIASES.get(match.group(1).lower().rstrip("s"))
            if not doc_type:
                continue
            doc = self.get_document(doc_type, int(match.group(2)))
            if doc and doc["id"] not in seen:
                seen.add(doc["id"])
                found.append(doc)
        return found

    def search(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        """Hybrid search with Reciprocal Rank Fusion of vector + BM25 rankings."""
        top_k = top_k or self.settings.top_k
        if not self._chunks:
            return []

        pool = min(max(top_k * 4, 20), len(self._chunks))

        # Vector ranking
        query_vec = embed_query(query, self.settings.embedding_model)
        vec_res = self.collection.query(
            query_embeddings=[query_vec], n_results=pool, include=["distances"]
        )
        vec_rank = {cid: rank for rank, cid in enumerate(vec_res["ids"][0])}
        vec_dist = dict(zip(vec_res["ids"][0], vec_res["distances"][0]))

        # BM25 ranking
        bm25_scores = self._bm25.get_scores(_tokenize(query))
        bm25_order = sorted(
            range(len(self._chunks)), key=lambda i: bm25_scores[i], reverse=True
        )[:pool]
        bm25_rank = {
            self._chunks[i]["chunk_id"]: rank
            for rank, i in enumerate(bm25_order)
            if bm25_scores[i] > 0
        }

        # Reciprocal Rank Fusion (k=60 is the standard constant)
        fused: dict[str, float] = {}
        for cid, rank in vec_rank.items():
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (60 + rank)
        for cid, rank in bm25_rank.items():
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (60 + rank)

        by_id = {c["chunk_id"]: c for c in self._chunks}
        top = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]

        results = []
        for cid, score in top:
            chunk = by_id.get(cid)
            if not chunk:
                continue
            results.append(
                RetrievedChunk(
                    chunk_id=cid,
                    doc_id=chunk["doc_id"],
                    ref=chunk["ref"],
                    title=chunk.get("title", ""),
                    text=chunk["text"],
                    chunk_index=int(chunk.get("chunk_index", 0)),
                    score=round(score, 5),
                )
            )
        # Log a relevance hint: cosine distance of the best vector hit
        if vec_dist:
            best = min(vec_dist.values())
            logger.debug("Best vector distance for query %r: %.3f", query[:60], best)
        return results
