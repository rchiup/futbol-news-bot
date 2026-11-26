"""Upload original JPEG to Cloudinary, then publish via Meta's official Graph API.

Supports professional-account Instagram Login (default) and Facebook Login.
Set IG_USER_ID, IG_ACCESS_TOKEN, CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY,
CLOUDINARY_API_SECRET in GitHub Actions Secrets. Never expose credentials in Git.
"""
import hashlib
import os
import time
from pathlib import Path

import requests


def require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing secret: {name}")
    return value


def upload_public_image(path: Path, identifier: str, session=requests) -> str:
    cloud = require("CLOUDINARY_CLOUD_NAME")
    key = require("CLOUDINARY_API_KEY")
    secret = require("CLOUDINARY_API_SECRET")
    params = {
        "folder": "football-news-bot",
        "public_id": identifier,
        "timestamp": str(int(time.time())),
    }
    signature_base = "&".join(f"{k}={params[k]}" for k in sorted(params))
    signature = hashlib.sha1((signature_base + secret).encode()).hexdigest()
    data = {**params, "api_key": key, "signature": signature}
    with path.open("rb") as image_file:
        response = session.post(
            f"https://api.cloudinary.com/v1_1/{cloud}/image/upload",
            data=data, files={"file": (path.name, image_file, "image/jpeg")}, timeout=40,
        )
    response.raise_for_status()
    url = response.json().get("secure_url", "")
    if not url.startswith("https://"):
        raise RuntimeError("Cloudinary did not return a public HTTPS media URL")
    return url


def instagram_api_settings() -> tuple[str, str, str, str]:
    ig_id = require("IG_USER_ID")
    token = require("IG_ACCESS_TOKEN")
    mode = os.getenv("META_AUTH_MODE", "facebook").strip().lower()
    if mode not in {"instagram", "facebook"}:
        raise ValueError("Invalid META_AUTH_MODE")
    version = os.getenv("META_GRAPH_VERSION", "v27.0")
    if not version.startswith("v") or "/" in version:
        raise ValueError("Invalid META_GRAPH_VERSION")
    host = "graph.facebook.com" if mode == "facebook" else "graph.instagram.com"
    return ig_id, token, mode, f"https://{host}/{version}"


def available_instagram_slots(session=requests, fallback_slots: int = 0) -> int:
    """Check Instagram's account-specific rolling publishing limit.

    Fail closed to the caller-supplied conservative number if Meta's usage
    endpoint is unavailable. Quota is account-wide, not just this bot's posts.
    """
    try:
        ig_id, token, _, root = instagram_api_settings()
        response = session.get(
            f"{root}/{ig_id}/content_publishing_limit",
            params={"fields": "config,quota_usage"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        records = payload.get("data", [])
        entry = records[0] if isinstance(records, list) and records else payload
        usage = int(entry["quota_usage"])
        config = entry.get("config") or {}
        total = int(config["quota_total"])
        if total <= 0 or usage < 0:
            raise ValueError("Invalid publishing quota")
        remaining = max(0, total - usage)
        print(f"[META] Account publishing quota: {usage}/{total}; remaining {remaining}")
        return remaining
    except (requests.RequestException, ValueError, TypeError, KeyError, IndexError) as exc:
        print(f"[META] Publishing quota unavailable; conservative fallback: {type(exc).__name__}")
        return max(0, fallback_slots)


def verify_instagram_account(session=requests) -> dict:
    """Read-only guard: never post into a different professional Instagram account."""
    ig_id, token, mode, root = instagram_api_settings()
    headers = {"Authorization": f"Bearer {token}"}
    # A Facebook User Token with valid Instagram Graph permissions can access
    # the linked Instagram account directly, even when
    # /me/assigned_instagram_accounts returns []. This was blocking all posts
    # after the owner rotated the token to add insights permissions.
    # Verify the *exact* account ID and username through the same token used
    # for publishing; NEVER fall back to a different account.
    response = session.get(
        f"{root}/{ig_id}",
        params={"fields": "id,username"},
        headers=headers, timeout=30,
    )
    if getattr(response, "status_code", 200) >= 400:
        try:
            err = response.json().get("error", {})
            code = err.get("code")
            subcode = err.get("error_subcode")
            token_hint = "token_invalid_or_expired" if code == 190 else "review_permissions_or_auth_mode"
            print(f"[META_AUTH] Account check HTTP {response.status_code}; graph_code={code}; subcode={subcode}; hint={token_hint}")
        except (ValueError, AttributeError):
            print(f"[META_AUTH] Account check HTTP {response.status_code}; no structured error")
    response.raise_for_status()
    accounts = [response.json()]
    matched = next((item for item in accounts if str(item.get("id")) == ig_id), None)
    if not matched:
        raise RuntimeError("Target Instagram account ID is not assigned to this token")
    expected = os.getenv("EXPECTED_IG_USERNAME", "chaofelicevich").lstrip("@").lower()
    username = str(matched.get("username") or "").lstrip("@").lower()
    if not username or username != expected:
        raise RuntimeError("Instagram account username does not match the expected destination")
    return {"id": ig_id, "username": username, "mode": mode}


def publish_image(path: Path, caption: str, identifier: str, session=requests) -> str:
    verified = verify_instagram_account(session=session)
    ig_id, token, _, root = instagram_api_settings()
    if verified["id"] != ig_id:
        raise RuntimeError("Instagram target verification mismatch")
    image_url = upload_public_image(path, identifier, session=session)
    auth_headers = {"Authorization": f"Bearer {token}"}

    response = session.post(
        f"{root}/{ig_id}/media",
        data={"image_url": image_url, "caption": caption}, headers=auth_headers,
        timeout=35,
    )
    response.raise_for_status()
    creation_id = response.json().get("id")
    if not creation_id:
        raise RuntimeError("Instagram did not return a creation ID")

    # Meta must finish fetching the image before it can be published.
    for _ in range(8):
        status_response = session.get(
            f"{root}/{creation_id}",
            params={"fields": "status_code"}, headers=auth_headers,
            timeout=25,
        )
        status_response.raise_for_status()
        status = status_response.json().get("status_code")
        if status == "FINISHED":
            break
        if status in {"ERROR", "EXPIRED"}:
            raise RuntimeError(f"Meta media container status: {status}")
        time.sleep(3)
    else:
        raise RuntimeError("Meta media container is not ready; verify before retrying")

    response = session.post(
        f"{root}/{ig_id}/media_publish",
        data={"creation_id": creation_id}, headers=auth_headers, timeout=35,
    )
    response.raise_for_status()
    media_id = response.json().get("id")
    if not media_id:
        raise RuntimeError("Meta did not confirm Instagram publication")
    return str(media_id)


def upload_public_video(path: Path, identifier: str, session=requests) -> str:
    cloud = require("CLOUDINARY_CLOUD_NAME")
    key = require("CLOUDINARY_API_KEY")
    secret = require("CLOUDINARY_API_SECRET")
    params = {"folder": "football-news-bot/reels", "public_id": identifier,
              "timestamp": str(int(time.time()))}
    signature = hashlib.sha1(("&".join(f"{k}={params[k]}" for k in sorted(params)) + secret).encode()).hexdigest()
    with path.open("rb") as video:
        response = session.post(
            f"https://api.cloudinary.com/v1_1/{cloud}/video/upload",
            data={**params, "api_key": key, "signature": signature},
            files={"file": (path.name, video, "video/mp4")}, timeout=120)
    response.raise_for_status()
    url = response.json().get("secure_url", "")
    if not url.startswith("https://"):
        raise RuntimeError("Cloudinary did not return a public video URL")
    return url


def publish_reel(path: Path, caption: str, identifier: str, session=requests, public_url=None) -> str:
    verified = verify_instagram_account(session=session)
    ig_id, token, _, root = instagram_api_settings()
    if verified["id"] != ig_id:
        raise RuntimeError("Instagram target verification mismatch")
    url = public_url or upload_public_video(path, identifier, session=session)
    headers = {"Authorization": f"Bearer {token}"}
    response = session.post(f"{root}/{ig_id}/media",
        data={"media_type":"REELS","video_url":url,"caption":caption,"share_to_feed":"true"},
        headers=headers, timeout=35)
    response.raise_for_status()
    creation_id = response.json().get("id")
    if not creation_id:
        raise RuntimeError("Instagram did not return a Reel container")
    for _ in range(24):
        response = session.get(f"{root}/{creation_id}", params={"fields":"status_code"},
                               headers=headers, timeout=20)
        response.raise_for_status()
        status = response.json().get("status_code")
        if status == "FINISHED":
            break
        if status in {"ERROR","EXPIRED","PUBLISHED"}:
            raise RuntimeError(f"Reel container status: {status}")
        time.sleep(5)
    else:
        raise RuntimeError("Reel container still processing; check before retrying")
    response = session.post(f"{root}/{ig_id}/media_publish",
        data={"creation_id":creation_id},headers=headers,timeout=35)
    response.raise_for_status()
    media_id = response.json().get("id")
    if not media_id:
        raise RuntimeError("Meta did not confirm Reel publication")
    return str(media_id)

class CarouselPreparationError(RuntimeError):
    """No parent publish request has been sent; a single-image fallback is safe."""

def publish_carousel(paths, caption, identifier, session=requests):
    if not 2 <= len(paths) <= 10:
        raise CarouselPreparationError("Invalid carousel length")
    try:
        verified=verify_instagram_account(session=session)
        ig_id, token, _, root=instagram_api_settings()
        if verified["id"]!=ig_id:
            raise RuntimeError("Instagram target verification mismatch")
        headers={"Authorization":f"Bearer {token}"}
        children=[]
        for n,path in enumerate(paths):
            url=upload_public_image(path,identifier+"-slide-"+str(n+1),session=session)
            res=session.post(f"{root}/{ig_id}/media",data={"image_url":url,"is_carousel_item":"true"},headers=headers,timeout=35)
            res.raise_for_status()
            child=res.json().get("id")
            if not child:
                raise RuntimeError("Missing carousel child")
            children.append(child)
        res=session.post(f"{root}/{ig_id}/media",data={"media_type":"CAROUSEL","children":",".join(children),"caption":caption},headers=headers,timeout=35)
        res.raise_for_status()
        parent=res.json().get("id")
        if not parent:
            raise RuntimeError("Missing carousel parent")
        for _ in range(8):
            status=session.get(f"{root}/{parent}",params={"fields":"status_code"},headers=headers,timeout=25)
            status.raise_for_status()
            value=status.json().get("status_code")
            if value=="FINISHED":
                break
            if value in {"ERROR","EXPIRED","PUBLISHED"}:
                raise RuntimeError("Invalid carousel status")
            time.sleep(3)
        else:
            raise RuntimeError("Carousel not ready")
    except Exception as exc:
        raise CarouselPreparationError(type(exc).__name__) from exc
    # Once publication is attempted, never fallback on an ambiguous result.
    res=session.post(f"{root}/{ig_id}/media_publish",data={"creation_id":parent},headers=headers,timeout=35)
    res.raise_for_status()
    media_id=res.json().get("id")
    if not media_id:
        raise RuntimeError("No carousel publication confirmation")
    return str(media_id)
