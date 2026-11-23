"""Collect football RSS headlines without automatically publishing."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import feedparser

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
OUT = DATA / "news.json"
FEEDS = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))

def main():
    existing = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    seen = {item["id"] for item in existing}
    added = 0
    for source in FEEDS:
        url = source.get("url", "") if isinstance(source, dict) else source
        if not url:
            continue
        feed = feedparser.parse(url, request_headers={"User-Agent": "FootballNewsBot/1.0"})
        if feed.bozo:
            print(f"Warning parsing {url}: {feed.bozo_exception}")
        for entry in feed.entries:
            link = entry.get("link", "")
            title = entry.get("title", "").strip()
            if not link or not title:
                continue
            identifier = hashlib.sha256(link.encode()).hexdigest()
            if identifier in seen:
                continue
            existing.append({"id": identifier, "title": title, "url": link,
                             "source": feed.feed.get("title", url),
                             "collected_at": datetime.now(timezone.utc).isoformat(),
                             "status": "pending_review"})
            seen.add(identifier)
            added += 1
    OUT.write_text(json.dumps(existing[-2000:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Added {added} headlines. Total retained: {min(len(existing), 2000)}")

if __name__ == "__main__":
    main()
