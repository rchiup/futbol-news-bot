"""Optional original editorial illustrations via Cloudflare Workers AI.

Uses Cloudflare's recurring free daily Neurons first, with strictly opt-in
fallbacks. All outputs are validated and saved as 4:5 JPEG with no paid
Replicate dependence. A generated scene is not real match photography.
"""
from __future__ import annotations

import base64
import binascii
import io
import os
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, ImageOps

MAX_IMAGE_BYTES = 9_000_000
CF_MODEL = "@cf/black-forest-labs/flux-1-schnell"
HF_MODEL = "black-forest-labs/FLUX.1-schnell"
TARGET_SIZE = (864, 1080)


def enabled_providers() -> list[str]:
    """Enabled in order; Hugging Face requires explicit opt-in as it isn't free."""
    allowed = ("cloudflare", "pollinations", "huggingface")
    order = os.getenv("AI_IMAGE_PROVIDER_ORDER", "cloudflare,pollinations,huggingface")
    requested = [n.strip().lower() for n in order.split(",")]
    available = {
        "cloudflare": bool(os.getenv("CF_ACCOUNT_ID", "").strip()
                           and os.getenv("CF_API_TOKEN", "").strip()),
        "pollinations": os.getenv("ENABLE_POLLINATIONS", "false").lower() == "true",
        "huggingface": (os.getenv("ENABLE_HF_IMAGE", "false").lower() == "true"
                        and bool(os.getenv("HF_TOKEN", "").strip())),
    }
    return list(dict.fromkeys(n for n in requested if n in allowed and available[n]))


def ai_image_provider_configured() -> bool:
    return bool(enabled_providers())


def build_prompt(item: dict) -> str:
    subject = re.sub(r"[^A-Za-zÀ-ÿ \-'.]", "", str(item.get("visual_subject", "")))[:65].strip()
    # Never generate fake evidence of a match or pretend that an AI scene
    # depicts the reported facts. This is always CLEARLY LABELLED editorial art.
    sport = str(item.get("sport", "FUTBOL")).upper()
    props = {
        "FUTBOL": "abstract football pitch floodlights and an expressive football",
        "TENIS": "tennis racket, dramatic tennis court lighting and green tennis ball",
        "GOLF": "golf ball, distant flag and dramatic golf-course landscape",
        "F1": "abstract racing car silhouette, track kerbs and dynamic speed streaks",
        "NBA": "basketball, hardwood arena and glowing hoop",
    }
    motif = props.get(sport, props["FUTBOL"])
    person = (
        f"stylized hand-painted editorial portrait of athlete {subject}"
        if len(subject.split()) >= 2
        else f"symbolic artistic composition of {motif}"
    )
    return (
        f"Premium South American sports news magazine digital illustration of {person}. "
        f"Sports category: {sport}. Clearly stylized painting, NOT a photograph, NOT documentary photography. "
        "High-end sports editorial art direction, rich navy shadows, cinematic light, "
        "dynamic color gradients, bold expressive brush strokes, tasteful neon accents. "
        "4:5 vertical portrait layout, open negative space in lower half for separately overlaid headline. "
        "No text, no logos, no numbers, no badges, no watermarks, no fake photojournalism, "
        "no precise depicted injury, no invented celebration, no real-world match reconstruction. "
    )



def _decode_response_image(response) -> bytes:
    """Decode common API responses; reject non-images and oversized payloads."""
    status = getattr(response, "status_code", 200)
    if status != 200:
        raise RuntimeError(f"HTTP {status}")
    content = response.content
    if len(content) > MAX_IMAGE_BYTES * 2:
        raise ValueError("AI image response is too large")
    ctype = str(getattr(response, "headers", {}).get("content-type", "")).lower()
    if ctype.startswith("image/") or content.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"RIFF")):
        return content
    try:
        obj = response.json()
        if obj.get("success") is False:
            raise ValueError("Provider returned no successful image")
        payload = obj.get("result", obj)
        encoded = payload.get("image") if isinstance(payload, dict) else None
        if not isinstance(encoded, str):
            raise ValueError("No base64 image in JSON")
        if encoded.startswith("data:image/"):
            encoded = encoded.split(",", 1)[-1]
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, KeyError, TypeError) as exc:
        raise ValueError("Invalid base64 image") from exc


def _cloudflare(prompt: str, session) -> bytes:
    account = os.getenv("CF_ACCOUNT_ID", "").strip()
    token = os.getenv("CF_API_TOKEN", "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{32}", account):
        raise ValueError("Cloudflare Account ID missing or malformed")
    # Model is fixed to a known free-tier eligible image model.
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{CF_MODEL}"
    response = session.post(
        endpoint,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"prompt": prompt[:2048], "steps": 4},
        timeout=(10, 60),
    )
    return _decode_response_image(response)


def _huggingface(prompt: str, session) -> bytes:
    # Paid/credit-dependent provider: disabled unless explicitly opted in.
    model = os.getenv("HF_IMAGE_MODEL", HF_MODEL)
    if not re.fullmatch(r"[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+", model):
        raise ValueError("Invalid Hugging Face model ID")
    response = session.post(
        f"https://router.huggingface.co/hf-inference/models/{model}",
        headers={"Authorization": f"Bearer {os.environ['HF_TOKEN']}",
                 "Accept": "image/*"},
        json={"inputs": prompt,
              "parameters": {"width": 864, "height": 1080,
                             "num_inference_steps": 4}},
        timeout=(10, 70),
    )
    return _decode_response_image(response)


def _pollinations(prompt: str, session) -> bytes:
    # Optional provider; legacy no-key endpoint may be discontinued.
    response = session.get(
        "https://image.pollinations.ai/prompt/" + quote(prompt, safe=""),
        params={"model": "flux", "width": 864, "height": 1080, "nologo": "true"},
        headers={"Accept": "image/*"},
        timeout=(10, 45),
    )
    return _decode_response_image(response)


def _save_jpeg(raw_bytes: bytes, path: Path) -> Path:
    if len(raw_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("AI output too large")
    with Image.open(io.BytesIO(raw_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.load()
        if min(image.size) < 500:
            raise ValueError("AI output resolution too low")
        image = ImageOps.fit(image, TARGET_SIZE, method=Image.Resampling.LANCZOS)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, format="JPEG", quality=88, optimize=True)
    return path


def generate_illustration(item: dict, path: Path, session=requests) -> Path:
    if os.getenv("ENABLE_AI_ART", "").lower() != "true":
        raise RuntimeError("AI art disabled")
    providers = enabled_providers()
    if not providers:
        raise RuntimeError("No configured image providers")
    prompt = build_prompt(item)
    for name in providers:
        try:
            raw = {
                "cloudflare": _cloudflare,
                "pollinations": _pollinations,
                "huggingface": _huggingface,
            }[name](prompt, session)
            output = _save_jpeg(raw, path)
            item["ai_art_provider"] = name
            print(f"[ART] Generated original illustration with {name}")
            return output
        except (requests.RequestException, ValueError, OSError, RuntimeError) as exc:
            # Never print credentials or raw HTTP response URLs/bodies.
            detail = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
            print(f"[ART] {name} unavailable: {detail[:65]}")
    raise RuntimeError("All configured image providers failed")
