"""ChromaDB persistent vector store wrapper."""

import logging
from pathlib import Path

import chromadb

logger = logging.getLogger(__name__)

COLLECTION_NAME = "nahjul_balagha"


def get_client(chroma_dir: Path) -> chromadb.ClientAPI:
    chroma_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(chroma_dir))


def get_collection(chroma_dir: Path) -> chromadb.Collection:
    client = get_client(chroma_dir)
    # We supply our own embeddings, so disable Chroma's default embedder.
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=None,
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection(chroma_dir: Path) -> chromadb.Collection:
    client = get_client(chroma_dir)
    try:
        client.delete_collection(COLLECTION_NAME)
        logger.info("Deleted existing collection %s", COLLECTION_NAME)
    except Exception:
        pass
    return get_collection(chroma_dir)
