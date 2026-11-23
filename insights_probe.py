"""Read-only Instagram Graph API Insights capability probe.

Uses only the token already stored in GitHub Actions Secrets. It does NOT post,
comment, modify metadata or output access tokens. Errors are redacted to stable
HTTP / Meta error codes. Missing insights are 'unavailable', never a fake zero.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

OUTPUT = Path("data/ig_insights_probe.json")
ACCOUNT_METRICS = {
    "reach": {"period": "day"},
    "views": {"period": "day", "metric_type": "total_value"},
    "total_interactions": {"period": "day", "metric_type": "total_value"},
    "follower_count": {"period": "day"},
}
MEDIA_METRICS = ("views", "reach", "shares", "saved", "likes", "comments", "follows")
SAFE_KINDS = {"IMAGE", "CAROUSEL_ALBUM", "VIDEO"}


def safe_get(session, root, path, token, params):
    try:
        response = session.get(
            f"{root}/{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        body = response.json()
        if not isinstance(body, dict):
            return {"ok": False, "status": "invalid_body", "http": response.status_code}
        if response.status_code >= 400 or "error" in body:
            err = body.get("error", {})
            return {
                "ok": False, "status": "denied", "http": response.status_code,
                "meta_code": err.get("code") if isinstance(err, dict) else None,
                "meta_subcode": err.get("error_subcode") if isinstance(err, dict) else None,
                "error_type": str(err.get("type", ""))[:60] if isinstance(err, dict) else "",
            }
        return {"ok": True, "data": body}
    except (requests.RequestException, ValueError):
        return {"ok": False, "status": "network_error"}


def extract_metric(reply, metric):
    if not reply.get("ok"):
        return {k: v for k, v in reply.items() if k != "data"}
    items = reply["data"].get("data", [])
    if not isinstance(items, list) or not items:
        return {"ok": True, "status": "empty", "value": None}
    picked = next((x for x in items if x.get("name") == metric), items[0])
    total = picked.get("total_value")
    if isinstance(total, dict) and isinstance(total.get("value"), (int, float)):
        return {"ok": True, "status": "available", "value": total["value"]}
    values = picked.get("values", [])
    if isinstance(values, list) and values and isinstance(values[-1].get("value"), (int, float)):
        return {"ok": True, "status": "available", "value": values[-1]["value"]}
    return {"ok": True, "status": "empty", "value": None}


def probe(session=requests):
    token, ig = os.getenv("IG_ACCESS_TOKEN", "").strip(), os.getenv("IG_USER_ID", "").strip()
    mode = os.getenv("META_AUTH_MODE", "facebook").lower()
    version = os.getenv("META_GRAPH_VERSION", "v27.0")
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "auth_mode": mode, "api_version": version,
        "read_only": True, "account": {}, "account_insights": {},
        "media_insights": {}, "basic_media_counters": {},
        "conclusion": "unverified",
    }
    if not token or not ig:
        report["conclusion"] = "missing_secrets"
        return report
    if mode not in {"instagram", "facebook"} or not version.startswith("v"):
        report["conclusion"] = "invalid_api_configuration"
        return report
    host = "graph.facebook.com" if mode == "facebook" else "graph.instagram.com"
    root = f"https://{host}/{version}"

    profile = safe_get(session, root, ig, token,
                       {"fields": "id,username,followers_count,media_count"})
    if not profile["ok"]:
        report["account"] = profile
        report["conclusion"] = "profile_unavailable"
        return report

    profile_data = profile["data"]
    username = str(profile_data.get("username", "")).lstrip("@").lower()
    # Safety: enforce original destination. No querying another user's insights.
    if username != "chaofelicevich" or str(profile_data.get("id")) != ig:
        report["conclusion"] = "account_mismatch"
        return report
    report["account"] = {
        "username": username,
        "followers_count": profile_data.get("followers_count"),
        "media_count": profile_data.get("media_count"),
    }
    for metric, settings in ACCOUNT_METRICS.items():
        response = safe_get(session, root, f"{ig}/insights", token,
                            {"metric": metric, **settings})
        report["account_insights"][metric] = extract_metric(response, metric)

    media = safe_get(session, root, f"{ig}/media", token, {
        "fields": "id,media_type,media_product_type,timestamp,permalink",
        "limit": 5,
    })
    if not media["ok"]:
        report["media_lookup"] = media
    else:
        rows = media["data"].get("data", [])
        item = next((m for m in rows if m.get("media_type") in SAFE_KINDS), None)
        if item is not None:
            # Store no private image URLs, token, user IDs or comments.
            report["sample_media"] = {
                "media_type": item.get("media_type"),
                "media_product_type": item.get("media_product_type"),
                "timestamp": item.get("timestamp"),
                "permalink": item.get("permalink", ""),
            }
            for metric in MEDIA_METRICS:
                response = safe_get(session, root, f"{item['id']}/insights",
                                    token, {"metric": metric})
                report["media_insights"][metric] = extract_metric(response, metric)
            # Basic media fields can sometimes be read even without the
            # instagram_manage_insights permission; probe independently.
            for fieldset in ("like_count,comments_count", "saved_count,shares_count,reposts_count"):
                response = safe_get(session, root, item["id"], token, {"fields": fieldset})
                if response.get("ok"):
                    report["basic_media_counters"].update({
                        k: v for k, v in response["data"].items()
                        if k != "id" and isinstance(v, (int, float))
                    })
                else:
                    report["basic_media_counters"][fieldset] = {
                        k: v for k, v in response.items() if k != "data"
                    }
    accepted = [
        name for name, obj in {**report["account_insights"], **report["media_insights"]}.items()
        if obj.get("ok")
    ]
    report["conclusion"] = (
        "insights_accessible" if accepted else "insights_permission_or_metric_unavailable"
    )
    return report


def main():
    result = probe()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Read-only Meta insights probe:", result["conclusion"])
    print("Account metric status:", {k: v.get("status", "denied")
          for k, v in result["account_insights"].items()})
    print("Media metric status:", {k: v.get("status", "denied")
          for k, v in result["media_insights"].items()})
    print("Basic media fields:", {
        k: "available" if isinstance(v, (int, float)) else "denied"
        for k, v in result["basic_media_counters"].items()
    })


if __name__ == "__main__":
    main()
