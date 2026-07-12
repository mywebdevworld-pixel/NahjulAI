"""Chunk the corpus and index it into ChromaDB with fastembed embeddings.

Re-runnable: rebuilds the collection from scratch each time.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402
from app.rag.embeddings import embed_passages  # noqa: E402
from app.rag.vectorstore import reset_collection  # noqa: E402

CHUNK_TARGET = 1500   # characters per chunk (~350 tokens)
CHUNK_MIN = 200       # merge tiny trailing chunks into the previous one


def chunk_document(doc: dict) -> list[dict]:
    """Pack paragraphs into ~CHUNK_TARGET-char chunks with 1-paragraph overlap."""
    paragraphs = [p.strip() for p in doc["text"].split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[list[str]] = []
    current: list[str] = []
    size = 0
    for para in paragraphs:
        # Split single paragraphs that are longer than the target on sentences.
        while len(para) > CHUNK_TARGET * 1.5:
            cut = para.rfind(". ", 0, CHUNK_TARGET)
            cut = cut + 1 if cut > CHUNK_MIN else CHUNK_TARGET
            head, para = para[:cut].strip(), para[cut:].strip()
            if size:
                chunks.append(current)
                current, size = [], 0
            chunks.append([head])
        if size and size + len(para) > CHUNK_TARGET:
            chunks.append(current)
            current = [current[-1]] if len(current[-1]) < 400 else []  # overlap
            size = sum(len(p) for p in current)
        current.append(para)
        size += len(para)
    if current:
        if chunks and size < CHUNK_MIN:
            chunks[-1].extend(current)
        else:
            chunks.append(current)

    out = []
    for i, parts in enumerate(chunks):
        out.append({
            "chunk_id": f"{doc['id']}#{i}",
            "text": "\n\n".join(parts),
            "metadata": {
                "doc_id": doc["id"],
                "ref": doc["ref"],
                "title": doc.get("title", ""),
                "type": doc["type"],
                "number": doc["number"],
                "chunk_index": i,
            },
        })
    return out


def main() -> None:
    settings = get_settings()
    corpus = json.loads(settings.corpus_path.read_text(encoding="utf-8"))

    all_chunks = []
    for doc in corpus:
        all_chunks.extend(chunk_document(doc))
    print(f"{len(corpus)} documents -> {len(all_chunks)} chunks")

    collection = reset_collection(settings.chroma_dir)

    batch_size = 64
    for start in range(0, len(all_chunks), batch_size):
        batch = all_chunks[start:start + batch_size]
        texts = [c["text"] for c in batch]
        vectors = embed_passages(texts, settings.embedding_model)
        collection.add(
            ids=[c["chunk_id"] for c in batch],
            documents=texts,
            embeddings=vectors,
            metadatas=[c["metadata"] for c in batch],
        )
        done = min(start + batch_size, len(all_chunks))
        print(f"  indexed {done}/{len(all_chunks)}", end="\r")

    print(f"\nDone. Collection now holds {collection.count()} chunks "
          f"in {settings.chroma_dir}")


if __name__ == "__main__":
    main()
