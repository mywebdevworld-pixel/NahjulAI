"""API tests — require a built corpus + index (run the ingestion scripts first)."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings

settings = get_settings()

pytestmark = pytest.mark.skipif(
    not settings.corpus_path.exists(),
    reason="corpus/index not built yet",
)


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["corpus_documents"] > 700
    assert body["indexed_chunks"] > 1000


def test_passage_lookup(client):
    resp = client.get("/api/passage/sermon/1")
    assert resp.status_code == 200
    assert "Praise is due to Allah" in resp.json()["text"]


def test_passage_404(client):
    assert client.get("/api/passage/sermon/9999").status_code == 404
    assert client.get("/api/passage/poem/1").status_code == 404


def test_search(client):
    resp = client.get("/api/search", params={"q": "patience and gratitude", "k": 5})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 5
    assert all(r["text"] for r in results)


def test_chat_streams_sources_and_answer(client):
    with client.stream(
        "POST", "/api/chat", json={"message": "What is said about patience?"}
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    assert "event: sources" in body
    assert "event: token" in body
    assert "event: done" in body


def test_frontend_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Nahj AI" in resp.text
