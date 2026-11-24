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


# Deterministic corrections for notorious RSS/LLM metadata mistakes.
# Prefer editorial's source-validated visual_subject when it is available.
KNOWN_ATHLETES = (
    ("sinner", "Jannik Sinner", "TENIS"),
    ("alcaraz", "Carlos Alcaraz", "TENIS"),
    ("djokovic", "Novak Djokovic", "TENIS"),
    ("swiatek", "Iga Świątek", "TENIS"),
    ("verstappen", "Max Verstappen", "F1"),
    ("leclerc", "Charles Leclerc", "F1"),
    ("hamilton", "Lewis Hamilton", "F1"),
    ("mbapp", "Kylian Mbappé", "FUTBOL"),
    ("messi", "Lionel Messi", "FUTBOL"),
    ("ronaldo", "Cristiano Ronaldo", "FUTBOL"),
    ("haaland", "Erling Haaland", "FUTBOL"),
    ("yamal", "Lamine Yamal", "FUTBOL"),
)

SPORT_SCENES = {
    "FUTBOL": "association football player in a soccer kit, realistic football pitch, football boots",
    "TENIS": "professional tennis player in a tennis shirt, hard-court tennis arena, tennis net and racket",
    "GOLF": "professional golfer in golf attire on a golf course, a golf club in hand",
    "F1": "professional Formula One racing driver in a race suit, pit lane and racing car",
    "NBA": "professional basketball player in basketball kit, indoor basketball court and hoop",
}

SPORT_EXCLUSIONS = {
    "FUTBOL": "No tennis rackets, no basketball hoops.",
    "TENIS": "No soccer ball, no football field, no soccer goals, no football floodlight stadium.",
    "GOLF": "No soccer ball, no football field, no tennis court.",
    "F1": "No soccer ball, no football field, no tennis court.",
    "NBA": "No soccer ball, no football field, no tennis court.",
}


def _named_person(subject: str) -> bool:
    return len(re.findall(r"[A-Za-zÀ-ÿ]+", subject)) >= 2


def resolve_athlete(item: dict) -> tuple[str, str]:
    """Resolve athlete and sport from story, not an unreliable default sport.

    No anonymous football-ball illustration when an athlete is named.
    """
    title = str(item.get("title") or "")
    headline = str(item.get("headline") or "")
    summary = str(item.get("description") or "")
    story = (title + " " + headline + " " + summary).casefold()
    subject = re.sub(r"[^A-Za-zÀ-ÿ \-'.]", "", str(item.get("visual_subject") or "")).strip()[:70]
    sport = str(item.get("sport") or "").upper().strip()
    for term, full, identified_sport in KNOWN_ATHLETES:
        if re.search(r"(?<![a-zà-ÿ])" + re.escape(term) + r"(?![a-zà-ÿ])", story):
            # If the model named a different person, prefer the name present in
            # the reported story; known names are only used for exact-word matches.
            if not _named_person(subject) or full.casefold() in subject.casefold():
                subject = full
                sport = identified_sport
                break
    if sport not in SPORT_SCENES:
        sport = "FUTBOL"
    if "australian open" in story or "atp " in story or "wta " in story:
        sport = "TENIS"
    if "grand prix" in story or "formula 1" in story or "fórmula 1" in story:
        sport = "F1"
    return subject, sport


def build_prompt(item: dict) -> str:
    """Symbolic sports backdrop only; never invent an athlete's likeness."""
    _, sport = resolve_athlete(item)
    scenes = {
        "FUTBOL": "empty football pitch at dusk, a football on grass",
        "TENIS": "empty tennis court, tennis racket and tennis ball",
        "F1": "empty racing circuit with track kerbs",
        "NBA": "empty basketball arena with hoop and basketball",
        "GOLF": "empty golf course with flag and golf ball",
    }
    return ("Original clearly illustrated editorial sports backdrop, NOT a documentary photograph. "
            + scenes[sport] + ". No people, no faces, no athletes, no logos, no words. "
            "Vertical 4:5, premium cinematic lighting, dark lower third for headline. "
            "No recognizable real venue or reconstruction of a specific event.")


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
