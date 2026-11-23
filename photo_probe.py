"""Verify real licence-approved portraits from Wikimedia CDN; no IG publishing."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image
from curated_portraits import pick_curated
from portraits import download_portrait, photo_attribution
from graphics import render_card

SAMPLES = (
    ("Gianni Infantino", "Infantino habla del futuro de la FIFA"),
    ("Lionel Messi", "Messi marca otro gol con Argentina"),
    ("Kylian Mbappé", "Mbappé vuelve a marcar con Francia"),
    ("Erling Haaland", "Haaland sigue goleando"),
)
OUT = Path("data/photo_diagnostics.json")
PREVIEWS = Path("output/photo-proof")


def main():
    found = []
    for idx, (subject, title) in enumerate(SAMPLES):
        status = {"name": subject, "valid_metadata": False,
                  "download_ok": False, "render_ok": False}
        try:
            photo = pick_curated("", title, subject)
            if not photo:
                raise ValueError("Not found in curated library")
            status.update({
                "valid_metadata": True, "credit_required": True,
                "filename": photo["commons_filename"],
                "license": photo["license"],
                "artist": photo["photographer"],
            })
            tmp = PREVIEWS / f"{idx}-{subject.replace(' ', '_')}.jpg"
            image = download_portrait(photo, tmp)
            with Image.open(image) as downloaded:
                status["dimensions"] = list(downloaded.size)
            status["download_ok"] = True
            sample = {"id": f"portrait-check-{idx}", "title": title,
                      "headline": title, "category": "ACTUALIDAD"}
            output = PREVIEWS / f"{idx}-{subject.replace(' ', '_')}-graphic.jpg"
            render_card(sample, destination=output, portrait_path=image)
            with Image.open(output) as posted:
                status["render_ok"] = posted.size == (1080, 1350)
            status["has_photographer_attribution"] = subject and bool(photo_attribution(photo))
        except Exception as exc:
            status["error"] = type(exc).__name__
            status["http_status"] = getattr(getattr(exc, "response", None),
                                            "status_code", None)
        found.append(status)
        print("PHOTO CHECK:", subject, status["download_ok"], status["render_ok"])
    data = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "found": sum(1 for x in found if x["download_ok"] and x["render_ok"]),
        "results": found,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Verified real portraits:", data["found"], "/", len(found))


if __name__ == "__main__":
    main()
