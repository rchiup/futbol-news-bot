"""Upload original JPEG to Cloudinary, then publish via Meta's official Graph API.

Supports Instagram's Facebook-Login professional-account flow.
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


def publish_image(path: Path, caption: str, identifier: str, session=requests) -> str:
    ig_id = require("IG_USER_ID")
    token = require("IG_ACCESS_TOKEN")
    version = os.getenv("META_GRAPH_VERSION", "v24.0")
    if not version.startswith("v") or "/" in version:
        raise ValueError("Invalid META_GRAPH_VERSION")
    root = f"https://graph.facebook.com/{version}"
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
