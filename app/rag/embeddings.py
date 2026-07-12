"""Embedding model wrapper built on fastembed (ONNX, CPU-friendly, no torch)."""

import logging

from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

_model: TextEmbedding | None = None
_model_name: str | None = None


def get_embedder(model_name: str) -> TextEmbedding:
    """Lazily load (and cache) the embedding model."""
    global _model, _model_name
    if _model is None or _model_name != model_name:
        logger.info("Loading embedding model %s ...", model_name)
        _model = TextEmbedding(model_name=model_name)
        _model_name = model_name
        logger.info("Embedding model ready.")
    return _model


def embed_passages(texts: list[str], model_name: str) -> list[list[float]]:
    model = get_embedder(model_name)
    return [vec.tolist() for vec in model.passage_embed(texts)]


def embed_query(text: str, model_name: str) -> list[float]:
    model = get_embedder(model_name)
    return next(iter(model.query_embed([text]))).tolist()
