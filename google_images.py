"""Discover football-player photos through Google Images (CC license filter).

Google is a discovery index, not the rights holder. We only accept Wikimedia
Commons file pages and re-check each actual photo's license metadata before
downloading; this needs no paid Google API key.
"""
from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qs, quote, unquote, urlsplit

import requests

from portraits import _check_commons_file, normalize

SEARCH = "https://www.google.com/search"
FILE_PREFIX = "https://commons.wikimedia.org/wiki/File:"
USER_AGENT = ("Mozilla/5.0 (compatible; ChaoFelicevich/2.0; "
              "+https://github.com/rchiup/futbol-news-bot)")


def commons_filename_from_url(raw: str, subject: str) -> str | None:
    """Return one clearly named Commons image, not an arbitrary image URL."""
    raw = unescape(raw).replace("\\u003d", "=").replace("\\u0026", "&")
    if raw.startswith("/url?"):
        raw = parse_qs(urlsplit("https://www.google.com" + raw).query).get("q", [""])[0]
    raw = unquote(raw).split("#")[0].split("?")[0]
    if not raw.startswith(FILE_PREFIX):
        return None
    filename = unquote(raw[len(FILE_PREFIX):]).replace("_", " ")
    if not filename or "/" in filename or len(filename) > 200:
        return None
    search_words = normalize(subject).split()
    title_words = normalize(filename).split()
    if len(search_words) < 2 or not all(word in title_words for word in search_words):
        return None
    return filename


def find_google_image(subject: str, session=requests) -> dict | None:
    """Use Google Images to find a subject, then verify rights on Commons."""
    if len(normalize(subject).split()) < 2:
        return None
    response = session.get(
        SEARCH,
        params={
            "tbm": "isch",
            "q": f'"{subject}" site:commons.wikimedia.org/wiki/File:',
            "tbs": "il:cl",
            "num": "35",
            "isz": "l",
        },
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.8"},
        timeout=12,
    )
    response.raise_for_status()
    body = unescape(response.text[:1_500_000])
    # Google may link the original Commons file directly or URL-encode it in
    # redirects. The source license is always verified, never assumed.
    links = re.findall(r'https?[^\s"<>]+', body)
    seen = set()
    best = None
    for raw in links[:300]:
        filename = commons_filename_from_url(raw, subject)
        if not filename or filename in seen:
            continue
        seen.add(filename)
        try:
            info = _check_commons_file(subject, "", filename, session)
        except (requests.RequestException, ValueError, KeyError):
            continue
        if info:
            info["photo_provider"] = "Google Images → Wikimedia Commons"
            quality = min(int(info.get("width") or 0), int(info.get("height") or 0))
            if best is None or quality > best[0]:
                best = (quality, info)
            if quality >= 1600:
                break
    return best[1] if best else None
