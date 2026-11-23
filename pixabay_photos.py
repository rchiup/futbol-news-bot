"""Pixabay fallback for exact-subject, free-to-use sports photos.

Pixabay search is free but requires an API key. Only accept photo results
whose tags include the complete named subject; never pass generic stock
imagery off as evidence of a current event.
"""
from __future__ import annotations

import io
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import requests
from PIL import Image, ImageOps

SEARCH_API = "https://pixabay.com/api/"
MAX_BYTES = 8_000_000


def safe_pixabay_url(value: str) -> bool:
    url = urlsplit(str(value))
    host = (url.hostname or "").lower()
    return url.scheme == "https" and (host == "pixabay.com" or host.endswith(".pixabay.com"))


def tags_match_subject(tags: str, subject: str) -> bool:
    wanted = re.findall(r"[a-z0-9]+", subject.casefold())
    available = set(re.findall(r"[a-z0-9]+", str(tags).casefold()))
    return len(wanted) >= 2 and all(word in available for word in wanted)


def find_pixabay_photo(subject: str, session=requests) -> dict | None:
    key = os.getenv("PIXABAY_API_KEY", "").strip()
    if not key or len(subject.split()) < 2:
        return None
    response = session.get(
        SEARCH_API,
        params={"key": key, "q": subject, "image_type": "photo",
                "safesearch": "true", "per_page": 30, "order": "popular"},
        headers={"User-Agent": "ChaoFelicevichFootballBot/2.2 (free image search; GitHub)"},
        timeout=15,
    )
    response.raise_for_status()
    hits = sorted(
        response.json().get("hits", []),
        key=lambda row: min(int(row.get("imageWidth") or 0),
                            int(row.get("imageHeight") or 0)),
        reverse=True,
    )
    for row in hits:
        if not tags_match_subject(row.get("tags", ""), subject):
            continue
        url = str(row.get("largeImageURL") or "")
        if not safe_pixabay_url(url):
            continue
        width, height = int(row.get("imageWidth") or 0), int(row.get("imageHeight") or 0)
        if min(width, height) < 500:
            continue
        page = str(row.get("pageURL") or "")
        if not page.startswith("https://pixabay.com/photos/"):
            continue
        return {
            "subject": subject, "image_url": url, "width": width, "height": height,
            "license": "Pixabay Content License",
            "license_url": "https://pixabay.com/service/license-summary/",
            "photographer": " ".join(str(row.get("user") or "").split())[:95],
            "credit_required": False, "share_alike": False,
            "file_page": page, "photo_provider": "Pixabay",
        }
    return None


def download_pixabay_photo(info: dict, dest: Path, session=requests) -> Path:
    url = str(info.get("image_url") or "")
    if not safe_pixabay_url(url):
        raise ValueError("Untrusted Pixabay image host")
    response = session.get(url, timeout=20)
    response.raise_for_status()
    if len(response.content) > MAX_BYTES:
        raise ValueError("Pixabay photo exceeds maximum size")
    with Image.open(io.BytesIO(response.content)) as source:
        if source.width < 500 or source.height < 500:
            raise ValueError("Pixabay photo resolution too low")
        photo = ImageOps.exif_transpose(source).convert("RGB")
        photo.thumbnail((1920, 1920))
        dest.parent.mkdir(parents=True, exist_ok=True)
        photo.save(dest, "JPEG", quality=89, optimize=True)
    return dest
