"""Optional clearly marked AI football illustrations (Replicate).

Disabled by default. Unlike factual photographs, these are creative magazine
illustrations: never claim to portray actual match footage or documentary events.
Replicate is usage-billed; requires explicit ENABLE_AI_ART=true and secret token.
"""
from __future__ import annotations

import io
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
from PIL import Image, ImageOps

API = "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions"
ALLOWED_IMAGE_HOSTS = {"replicate.delivery"}


def safe_output_url(value: str) -> bool:
    url = urlsplit(str(value))
    host = (url.hostname or "").lower()
    return url.scheme == "https" and (
        host in ALLOWED_IMAGE_HOSTS or host.endswith(".replicate.delivery")
    )


def build_prompt(item: dict) -> str:
    subject = re.sub(r"[^A-Za-zÀ-ÿ \-'.]", "", str(item.get("visual_subject", "")))[:65].strip()
    # Real news must use real photographic evidence; the fallback is art, not a fake news photo.
    person = (
        f"stylized artistic magazine portrait of footballer {subject}"
        if len(subject.split()) >= 2
        else "anonymous footballer silhouette with ball in stadium"
    )
    return (
        f"Premium South American football magazine cover illustration of {person}. "
        "Highly artistic digital illustration, clearly NOT a photograph. "
        "Bold painterly brush strokes, dramatic stadium floodlights, cinematic dark navy "
        "with electric green and warm gold accents, dynamic magazine composition, "
        "sport editorial art direction, 4:5 portrait framing, open negative space "
        "in lower half for a separately overlaid Spanish headline. "
        "No logos, no badges, no text, no watermarks, no scores, "
        "no depiction of a specific real-world sporting event. "
    )


def generate_illustration(item: dict, path: Path, session=requests) -> Path:
    token = os.getenv("REPLICATE_API_TOKEN", "").strip()
    if not token or os.getenv("ENABLE_AI_ART", "").lower() != "true":
        raise RuntimeError("AI art is disabled or Replicate token is missing")
    headers = {"Authorization": f"Bearer {token}", "Prefer": "wait=35"}
    response = session.post(
        API, headers=headers,
        json={"input": {"prompt": build_prompt(item),
                        "aspect_ratio": "4:5", "output_format": "webp",
                        "num_outputs": 1, "num_inference_steps": 4,
                        "disable_safety_checker": False}},
        timeout=50,
    )
    response.raise_for_status()
    prediction = response.json()
    for _ in range(6):
        if prediction.get("status") == "succeeded" or prediction.get("output"):
            break
        if prediction.get("status") in {"failed", "canceled"}:
            raise RuntimeError("AI illustration generation failed")
        pred_id = str(prediction.get("id", ""))
        if not re.fullmatch(r"[a-zA-Z0-9]{10,50}", pred_id):
            raise RuntimeError("Missing valid AI prediction ID")
        time.sleep(2)
        status = session.get(f"https://api.replicate.com/v1/predictions/{pred_id}",
                             headers={"Authorization": f"Bearer {token}"}, timeout=25)
        status.raise_for_status()
        prediction = status.json()
    output = prediction.get("output")
    if isinstance(output, list):
        output = output[0] if output else ""
    if not safe_output_url(output):
        raise RuntimeError("AI provider did not return an accepted output URL")
    downloaded = session.get(output, timeout=25)
    downloaded.raise_for_status()
    if len(downloaded.content) > 9_000_000:
        raise ValueError("AI output is too large")
    with Image.open(io.BytesIO(downloaded.content)) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
        if min(image.size) < 500:
            raise ValueError("AI output resolution too low")
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, format="JPEG", quality=88, optimize=True)
    return path
