"""Corpus integrity tests — run after scripts/build_corpus.py."""

import json

import pytest

from app.config import get_settings

settings = get_settings()

pytestmark = pytest.mark.skipif(
    not settings.corpus_path.exists(),
    reason="corpus.json not built yet (run scripts/build_corpus.py)",
)


@pytest.fixture(scope="module")
def corpus() -> list[dict]:
    return json.loads(settings.corpus_path.read_text(encoding="utf-8"))


def test_counts(corpus):
    by_type = {}
    for d in corpus:
        by_type[d["type"]] = by_type.get(d["type"], 0) + 1
    assert by_type.get("sermon", 0) >= 235, by_type
    assert by_type.get("letter", 0) >= 75, by_type
    assert by_type.get("saying", 0) >= 400, by_type


def test_unique_ids(corpus):
    ids = [d["id"] for d in corpus]
    assert len(ids) == len(set(ids))


def test_required_fields(corpus):
    for d in corpus:
        assert d["id"] and d["ref"] and d["text"], d["id"]
        assert d["type"] in {"sermon", "letter", "saying"}
        assert isinstance(d["number"], int) and d["number"] > 0


def test_no_html_or_escapes_left(corpus):
    for d in corpus:
        assert "<a id=" not in d["text"], d["id"]
        assert "\\." not in d["text"], d["id"]


def test_known_passages_present(corpus):
    docs = {d["id"]: d for d in corpus}
    # Sermon 1 opens with praise of Allah
    assert "Praise is due to Allah" in docs["sermon-1"]["text"]
    # Letter 53 is the famous letter to Malik al-Ashtar
    assert "letter-53" in docs
    # Saying 1 exists and is non-trivial
    assert len(docs["saying-1"]["text"]) > 40
