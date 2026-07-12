"""Scrape al-islam.org for the complete Letters (1-79) and any sermons missing
from the markdown source. Produces:

  data/raw/alislam_letters.json   [{number, title, text}, ...]
  data/raw/alislam_sermons.json   [{number, title, text}, ...]

Uses curl for fetching (al-islam.org rejects Python TLS fingerprints) with a
polite delay between requests. Re-runnable: already-fetched pages are cached in
data/raw/alislam_pages/.
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402

BASE = "https://al-islam.org"
TOC_SERMONS = f"{BASE}/nahjul-balagha-part-1-sermons"
TOC_LETTERS = f"{BASE}/nahjul-balagha-part-2-letters-and-sayings"

# Sermons known to be absent from the markdown source
MISSING_SERMONS = [24, 240, 241]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

DELAY_SECONDS = 0.4


def fetch(url: str, cache_dir: Path, cache_key: str) -> str:
    cached = cache_dir / f"{cache_key}.html"
    if cached.exists() and cached.stat().st_size > 5_000:
        return cached.read_text(encoding="utf-8", errors="replace")
    result = subprocess.run(
        ["curl", "-sfL", "-A", UA, url],
        capture_output=True, check=True,
    )
    html = result.stdout.decode("utf-8", errors="replace")
    cached.write_text(html, encoding="utf-8")
    time.sleep(DELAY_SECONDS)
    return html


def extract_links(toc_html: str, kind: str) -> dict[int, str]:
    """Map number -> absolute URL for sermon-N-... / letter-N-... links."""
    pattern = re.compile(rf'href="(/nahjul-balagha[^"#]*/{kind}-(\d+)-[^"#]*)"')
    links: dict[int, str] = {}
    for m in pattern.finditer(toc_html):
        links.setdefault(int(m.group(2)), BASE + m.group(1))
    return links


_ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿ]")


def _mostly_arabic(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    arabic = sum(1 for c in letters if _ARABIC_RE.match(c))
    return arabic / len(letters) > 0.5


def parse_page(html: str, kind: str, number: int) -> dict | None:
    soup = BeautifulSoup(html, "lxml")

    title = ""
    label = kind.title()
    for h in soup.find_all(["h1", "h2"]):
        text = h.get_text(" ", strip=True)
        m = re.match(rf"{label}\s+{number}\s*:?\s*(.*)", text, re.IGNORECASE)
        if m:
            title = m.group(1).strip()
            break

    items = soup.select("div.field-item")
    if not items:
        return None
    body = max(items, key=lambda el: len(el.get_text()))
    paragraphs = [p.get_text(" ", strip=True) for p in body.find_all("p")]
    paragraphs = [re.sub(r"\s+", " ", p) for p in paragraphs if p and len(p) > 1]
    # The pages are bilingual; keep only the English translation (drop
    # paragraphs that are predominantly Arabic script).
    paragraphs = [p for p in paragraphs if not _mostly_arabic(p)]
    if not paragraphs:
        return None

    return {
        "number": number,
        "title": title,
        "text": "\n\n".join(paragraphs),
    }


def scrape(kind: str, toc_url: str, numbers: list[int] | None, raw_dir: Path) -> list[dict]:
    cache_dir = raw_dir / "alislam_pages"
    cache_dir.mkdir(parents=True, exist_ok=True)

    toc = fetch(toc_url, cache_dir, f"toc_{kind}")
    links = extract_links(toc, kind)
    targets = sorted(links) if numbers is None else [n for n in numbers if n in links]
    absent = [] if numbers is None else [n for n in numbers if n not in links]
    if absent:
        print(f"[warn] {kind}s not found in TOC: {absent}")

    docs = []
    for n in targets:
        html = fetch(links[n], cache_dir, f"{kind}-{n}")
        doc = parse_page(html, kind, n)
        if doc:
            docs.append(doc)
            print(f"[ok  ] {kind} {n}: {len(doc['text']):,} chars")
        else:
            print(f"[FAIL] {kind} {n}: could not parse {links[n]}")
    return docs


def main() -> None:
    raw_dir = get_settings().raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)

    letters = scrape("letter", TOC_LETTERS, None, raw_dir)  # all letters
    (raw_dir / "alislam_letters.json").write_text(
        json.dumps(letters, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Saved {len(letters)} letters")

    sermons = scrape("sermon", TOC_SERMONS, MISSING_SERMONS, raw_dir)
    (raw_dir / "alislam_sermons.json").write_text(
        json.dumps(sermons, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Saved {len(sermons)} supplementary sermons")


if __name__ == "__main__":
    main()
