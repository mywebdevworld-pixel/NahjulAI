"""Parse the raw sources into a normalized corpus: data/corpus.json.

Each document: {id, type, number, ref, title, text}
  e.g. {"id": "sermon-27", "type": "sermon", "number": 27,
        "ref": "Sermon 27", "title": "...", "text": "..."}
"""

import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402

ANCHOR_RE = re.compile(r"<a id=\"[^\"]*\"></a>")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿ]")


def _mostly_arabic(text: str) -> bool:
    """True when a paragraph is predominantly Arabic script (the al-islam.org
    pages are bilingual; the corpus keeps the English translation only)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    arabic = sum(1 for c in letters if _ARABIC_RE.match(c))
    return arabic / len(letters) > 0.5


def clean_markdown(text: str) -> str:
    text = ANCHOR_RE.sub("", text)
    # Unescape markdown backslash escapes: \( \) \. \- \' etc.
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!'\"<>])", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_markdown_sections(md: str, doc_type: str) -> list[dict]:
    """Split on '**Sermon N**' / '**Letter N**' markers."""
    label = doc_type.title()  # Sermon / Letter
    marker = re.compile(rf"^\*\*{label} (\d+)\*\*\s*$", re.MULTILINE)
    matches = list(marker.finditer(md))
    docs = []
    for i, m in enumerate(matches):
        number = int(m.group(1))
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        body = md[m.end():end].strip()

        # First bold line right after the marker is the descriptor/title.
        title = ""
        title_match = re.match(r"\s*\*\*(.+?)\*\*", body, re.DOTALL)
        if title_match:
            candidate = " ".join(title_match.group(1).split())
            if len(candidate) < 300:
                title = candidate.strip(" :")
                body = body[title_match.end():]

        text = clean_markdown(BOLD_RE.sub(r"\1", body))
        if not text:
            continue
        docs.append({
            "id": f"{doc_type}-{number}",
            "type": doc_type,
            "number": number,
            "ref": f"{label} {number}",
            "title": clean_markdown(title),
            "text": text,
        })
    return docs


def parse_sayings_html(html: str) -> list[dict]:
    """Extract numbered sayings ('1. ...') from the al-islam.org page."""
    soup = BeautifulSoup(html, "lxml")
    # The article body is the region containing the vast majority of <p> tags.
    main = soup.find("main") or soup.find("article") or soup.body
    paragraphs = [p.get_text(" ", strip=True) for p in main.find_all("p")]

    docs: list[dict] = []
    current_num: int | None = None
    current_parts: list[str] = []
    # Separator varies in the source: "262." / "262-" / "472 ."
    num_re = re.compile(r"^(\d{1,3})\s*[.\-–]\s*(.*)", re.DOTALL)

    def flush():
        if current_num is None:
            return
        text = re.sub(r"\s+", " ", " ".join(current_parts)).strip()
        if text:
            docs.append({
                "id": f"saying-{current_num}",
                "type": "saying",
                "number": current_num,
                "ref": f"Saying {current_num}",
                "title": "",
                "text": text,
            })

    for para in paragraphs:
        if not para or _mostly_arabic(para):
            continue
        m = num_re.match(para)
        # Only accept a number as a new saying if it moves the sequence forward
        # (guards against numbers appearing inside commentary text).
        if m and (current_num is None or current_num < int(m.group(1)) <= current_num + 25):
            flush()
            current_num = int(m.group(1))
            current_parts = [m.group(2)]
        elif current_num is not None:
            # Continuation of the current saying (commentary, notes, etc.)
            # Skip obvious footer/navigation noise.
            if len(para) > 2 and not para.lower().startswith(("«", "»", "share", "tags")):
                current_parts.append(para)
    flush()

    # Deduplicate by number, keep first occurrence
    seen: set[int] = set()
    unique = []
    for d in docs:
        if d["number"] not in seen:
            seen.add(d["number"])
            unique.append(d)
    return unique


def load_alislam(raw: Path, filename: str, doc_type: str) -> list[dict]:
    """Load documents scraped from al-islam.org (scripts/scrape_alislam.py)."""
    path = raw / filename
    if not path.exists():
        return []
    label = doc_type.title()
    return [
        {
            "id": f"{doc_type}-{d['number']}",
            "type": doc_type,
            "number": d["number"],
            "ref": f"{label} {d['number']}",
            "title": d.get("title", ""),
            "text": d["text"].strip(),
        }
        for d in json.loads(path.read_text(encoding="utf-8"))
        if d.get("text", "").strip()
    ]


def merge(primary: list[dict], secondary: list[dict]) -> list[dict]:
    """Combine two doc lists; primary wins on duplicate ids."""
    seen = {d["id"] for d in primary}
    merged = primary + [d for d in secondary if d["id"] not in seen]
    return sorted(merged, key=lambda d: d["number"])


def main() -> None:
    settings = get_settings()
    raw = settings.raw_dir

    sermons_md = parse_markdown_sections(
        (raw / "sermons.md").read_text(encoding="utf-8"), "sermon")
    sermons = merge(sermons_md, load_alislam(raw, "alislam_sermons.json", "sermon"))

    # Letters: the al-islam.org scrape is complete (79); the markdown source
    # is missing 24 letters, so it only serves as a fallback.
    letters_alislam = load_alislam(raw, "alislam_letters.json", "letter")
    letters_md = parse_markdown_sections(
        (raw / "letters.md").read_text(encoding="utf-8"), "letter")
    letters = merge(letters_alislam, letters_md)

    sayings = parse_sayings_html(
        (raw / "sayings.html").read_text(encoding="utf-8", errors="replace"))

    corpus = sermons + letters + sayings
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.corpus_path.write_text(
        json.dumps(corpus, ensure_ascii=False, indent=1), encoding="utf-8")

    total_chars = sum(len(d["text"]) for d in corpus)
    print(f"Sermons: {len(sermons)}  Letters: {len(letters)}  Sayings: {len(sayings)}")
    print(f"Total documents: {len(corpus)}  ({total_chars:,} characters)")
    print(f"Wrote {settings.corpus_path}")


if __name__ == "__main__":
    main()
