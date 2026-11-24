"""Openverse fallback for clearly identified footballer photos.

Openverse indexes Creative Commons photos on Flickr and other providers.
Never use image search as proof of identity. Require a complete exact name
in the indexed photo title and an explicit photograph category, reject
mural/poster/jersey imagery, and restrict download hosts and licences.
"""
from __future__ import annotations

import io
import re
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit

import requests
from PIL import Image, ImageOps
from portraits import normalize

SEARCH_API = "https://api.openverse.org/v1/images/"
ALLOWED_PHOTO_HOSTS = {"live.staticflickr.com", "upload.wikimedia.org"}
ALLOWED_LICENSES = {"by", "by-sa", "cc0", "pdm"}
MAX_BYTES = 8_000_000


def verified_photo_host(value: str) -> bool:
    url = urlsplit(value)
    return url.scheme == "https" and url.hostname in ALLOWED_PHOTO_HOSTS


def title_matches_person(title: str, subject: str) -> bool:
    norm, person = normalize(title), normalize(subject)
    if len(person.split()) < 2 or len(person) < 6:
        return False
    if not re.search(r"(?<![a-z0-9])" + re.escape(person) + r"(?![a-z0-9])", norm):
        return False
    bad = {"mural", "statue", "painting", "illustration", "drawing",
           "fan art", "wax", "poster", "jersey", "shirt", "shirtless",
           "card", "game", "cover", "graffiti", "lookalike"}
    return not any(re.search(r"\b" + re.escape(word) + r"\b", norm) for word in bad)


def find_openverse_photo(subject: str, session=requests, kind="person", sport="FUTBOL") -> dict | None:
    sport_query = {"FUTBOL":"football", "TENIS":"tennis", "NBA":"basketball", "F1":"formula one", "GOLF":"golf"}.get(sport,"sports")
    res = session.get(
        SEARCH_API,
        params={"q": subject + (" stadium" if kind == "club" else " " + sport_query), "license_type": "commercial,modification",
                "page_size": 12},
        headers={"User-Agent": "ChaoFelicevichFootballBot/2.1 (open photos; contact via GitHub)"},
        timeout=12,
    )
    res.raise_for_status()
    results = res.json().get("results", [])
    # Rank suitable player photographs by available resolution, not API order.
    results = sorted(results, key=lambda row: min(int(row.get("width") or 0), int(row.get("height") or 0)), reverse=True)
    for row in results:
        title = str(row.get("title") or "")
        if kind == "club":
            norm, club = normalize(title), normalize(subject)
            if len(club) < 4 or not re.search(r"(?<!\w)" + re.escape(club) + r"(?!\w)", norm):
                continue
            if not any(w in norm for w in ("stadium", "estadio", "arena", "ground", "stade")):
                continue
            if any(w in norm for w in ("model", "render", "illustration", "logo", "drawing")):
                continue
        elif not title_matches_person(title, subject):
            continue
        if str(row.get("category", "")).lower() != "photograph":
            continue
        if row.get("mature", False):
            continue
        if int(row.get("width") or 0) < 500 or int(row.get("height") or 0) < 500:
            continue
        url = str(row.get("url", ""))
        if not verified_photo_host(url):
            continue
        license_name = str(row.get("license") or "").lower()
        license_version = str(row.get("license_version") or "")
        if license_name not in ALLOWED_LICENSES:
            continue
        credit = license_name in {"by", "by-sa"}
        author = " ".join(unescape(re.sub(r"<[^>]+>", " ", str(row.get("creator") or ""))).split())[:95]
        if credit and len(author) < 3:
            continue
        if credit and license_version not in {"2.0", "3.0", "4.0"}:
            continue
        license_url = str(row.get("license_url") or "")
        if credit and not license_url.startswith(
            f"https://creativecommons.org/licenses/{license_name}/{license_version}/"
        ):
            continue
        page = str(row.get("foreign_landing_url") or "")
        if not (page.startswith("https://www.flickr.com/photos/") or
                page.startswith("https://commons.wikimedia.org/wiki/File:")):
            continue
        return {
            "subject": subject, "image_url": url,
            "width": int(row.get("width") or 0), "height": int(row.get("height") or 0), "license": (
                "CC " + license_name.upper().replace("-", "-") + " " + license_version
                if credit else license_name.upper()
            ),
            "license_url": license_url, "commons_filename": title,
            "photographer": author if credit else "",
            "credit_required": credit, "share_alike": license_name == "by-sa",
            "file_page": page, "photo_provider": "Openverse", "entity_kind": kind,
        }
    return None


def download_openverse_photo(info: dict, dest: Path, session=requests) -> Path:
    url = str(info.get("image_url", ""))
    if not verified_photo_host(url):
        raise ValueError("Untrusted image host")
    response = session.get(url, timeout=18)
    response.raise_for_status()
    if len(response.content) > MAX_BYTES:
        raise ValueError("Photo exceeds maximum size")
    with Image.open(io.BytesIO(response.content)) as source:
        if source.width < 500 or source.height < 500:
            raise ValueError("Photo resolution too low")
        photo = ImageOps.exif_transpose(source).convert("RGB")
        photo.thumbnail((1920, 1920))
        dest.parent.mkdir(parents=True, exist_ok=True)
        photo.save(dest, "JPEG", quality=89, optimize=True)
    return dest
