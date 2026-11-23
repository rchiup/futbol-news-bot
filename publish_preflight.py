"""Read-only diagnostic for Instagram photo publishing readiness.

No posting, uploading, token values, profile IDs, or raw error messages exposed.
Run with GitHub Secrets IG_ACCESS_TOKEN, IG_USER_ID and other bool-only credentials.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT = Path("data/publish_preflight.json")


def check(session=requests):
    token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    ig = os.getenv("IG_USER_ID", "").strip()
    version = os.getenv("META_GRAPH_VERSION", "v27.0")
    result = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True, "account_match": None,
        "graph_ig_profile": None, "assigned_account": None,
        "quota": None, "credentials_present": {},
    }
    for name in ("IG_USER_ID", "IG_ACCESS_TOKEN",
                 "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
                 "CLOUDINARY_API_SECRET", "GROQ_API_KEY"):
        result["credentials_present"][name] = bool(os.getenv(name, "").strip())
    if not token or not ig:
        result["status"] = "missing_token_or_id"
        return result
    if not version.startswith("v") or not version[1:].replace(".", "").isdigit():
        result["status"] = "invalid_graph_version"
        return result
    root = f"https://graph.facebook.com/{version}"
    headers = {"Authorization": "Bearer " + token}
    def get(path, params):
        try:
            response = session.get(root + path, headers=headers, params=params, timeout=17)
            data = response.json()
            if response.status_code >= 400 or data.get("error"):
                error = data.get("error", {})
                return {"ok": False, "http": response.status_code,
                        "meta_code": error.get("code"), "meta_subcode": error.get("error_subcode"),
                        "error_type": str(error.get("type") or "")[:45]}
            return {"ok": True, "data": data}
        except (requests.RequestException, ValueError, AttributeError):
            return {"ok": False, "status": "network_error"}

    own = get("/" + ig, {"fields": "id,username"})
    if not own.get("ok"):
        result["graph_ig_profile"] = own
    else:
        name = str(own["data"].get("username", "")).lower()
        matches = name == "chaofelicevich" and str(own["data"].get("id")) == ig
        result["graph_ig_profile"] = {"ok": True, "username_matches": matches}
        result["account_match"] = matches

    assigned = get("/me/assigned_instagram_accounts", {"fields": "id,username", "limit": 100})
    if not assigned.get("ok"):
        result["assigned_account"] = assigned
    else:
        rows = assigned["data"].get("data", [])
        match = any(str(row.get("id")) == ig and
                    str(row.get("username", "")).lower() == "chaofelicevich"
                    for row in rows)
        result["assigned_account"] = {"ok": True, "target_found": match,
                                      "number_of_assigned_accounts": len(rows)}

    limit = get("/" + ig + "/content_publishing_limit", {"fields": "config,quota_usage"})
    if not limit.get("ok"):
        result["quota"] = limit
    else:
        content = limit["data"]
        entries = content.get("data", [])
        record = entries[0] if isinstance(entries, list) and entries else content
        config = record.get("config") or {}
        result["quota"] = {"ok": True, "quota_usage": record.get("quota_usage"),
                           "quota_total": config.get("quota_total")}
    result["status"] = (
        "ready" if result["account_match"] and
                   result["assigned_account"].get("target_found") else
        "publishing_auth_problem"
    )
    return result


def main():
    r = check()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Publishing preflight status:", r["status"])
    print("Read-only, no secret values have been logged.")


if __name__ == "__main__":
    main()
