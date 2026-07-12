"""Download the raw Nahjul Balagha sources into data/raw/.

Sources (English translation by Sayyid Ali Raza, freely distributed):
- Sermons + Letters: cleaned markdown from github.com/MonisBana/Nahjul-Balagha
- Sayings: al-islam.org (single page containing all ~480 sayings)
"""

import subprocess
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402

SOURCES = {
    "sermons.md": "https://raw.githubusercontent.com/MonisBana/Nahjul-Balagha/master/Sermons_cleaned.md",
    "letters.md": "https://raw.githubusercontent.com/MonisBana/Nahjul-Balagha/master/Letters_cleaned.md",
    "sayings.html": "https://al-islam.org/nahjul-balagha-part-2-letters-and-sayings/selections-sayings-and-preaching-amir-al-muminin-ali",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}


def main() -> None:
    raw_dir = get_settings().raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True) as client:
        for filename, url in SOURCES.items():
            dest = raw_dir / filename
            if dest.exists() and dest.stat().st_size > 10_000:
                print(f"[skip] {filename} already downloaded ({dest.stat().st_size:,} bytes)")
                continue
            print(f"[get ] {url}")
            try:
                resp = client.get(url)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
            except httpx.HTTPError:
                # Some hosts (al-islam.org) reject Python TLS fingerprints
                # but accept curl, which ships with Windows 10+ and Linux.
                print("[warn] direct fetch failed, retrying via curl ...")
                subprocess.run(
                    ["curl", "-sfL", "-A", HEADERS["User-Agent"], "-o", str(dest), url],
                    check=True,
                )
            print(f"[ok  ] {filename} ({dest.stat().st_size:,} bytes)")

    print(f"\nDone. Raw files in {raw_dir}")


if __name__ == "__main__":
    main()
