"""Read-only photo availability probe; never downloads or publishes photos."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from portraits import find_portrait

SUBJECTS = ["Gianni Infantino", "Lionel Messi", "Cristiano Ronaldo", "Chloe Mustaki"]
RESULT_PATH = Path("data/photo_diagnostics.json")


def main():
    results = []
    for name in SUBJECTS:
        try:
            photo = find_portrait(name)
            results.append({
                "name": name,
                "found": photo is not None,
                "license": (photo or {}).get("license"),
                "filename": (photo or {}).get("commons_filename"),
                "credit_required": (photo or {}).get("credit_required", False),
            })
        except Exception as exc:
            # Never put a remote response body, token or URL in public diagnostics.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            results.append({"name": name, "found": False, "error": type(exc).__name__,
                            "http_status": status})
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "results": results}
    RESULT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    main()
