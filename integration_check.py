"""Check Meta and Cloudinary credentials without publishing on Instagram."""
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image
from publisher import verify_instagram_account, upload_public_image

OUTPUT = Path("data/integration_status.json")


def sanitize(error: Exception) -> str:
    status = getattr(getattr(error, "response", None), "status_code", None)
    if status:
        return f"{type(error).__name__}: HTTP {status}"
    if isinstance(error, RuntimeError) and str(error).startswith("Missing secret:"):
        return str(error)
    if isinstance(error, RuntimeError) and ("Instagram" in str(error) or "Cloudinary" in str(error)):
        return str(error)[:140]
    return type(error).__name__


def main() -> bool:
    result = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "instagram": {"ok": False},
        "cloudinary": {"ok": False},
    }
    try:
        account = verify_instagram_account()
        result["instagram"] = {"ok": True, "username": account["username"],
                               "account_id": account["id"], "auth_mode": account["mode"]}
    except Exception as exc:
        result["instagram"]["error"] = sanitize(exc)

    try:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.jpg"
            Image.new("RGB", (160, 160), "#0a1727").save(path, "JPEG")
            url = upload_public_image(path, "integration-check", session=requests)
            if not url.startswith("https://"):
                raise RuntimeError("Cloudinary returned an invalid HTTPS URL")
        result["cloudinary"] = {"ok": True}
    except Exception as exc:
        result["cloudinary"]["error"] = sanitize(exc)

    result["all_ok"] = bool(result["instagram"]["ok"] and result["cloudinary"]["ok"])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Instagram verification:", "OK" if result["instagram"]["ok"] else result["instagram"].get("error"))
    print("Cloudinary upload:", "OK" if result["cloudinary"]["ok"] else result["cloudinary"].get("error"))
    print("All integrations:", "READY" if result["all_ok"] else "NOT READY")
    return result["all_ok"]


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
