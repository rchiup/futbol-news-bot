"""Rights-aware, identity-aware football portraits.

Never reuse arbitrary Google/agency photos. Resolve a precise football-person
entity on Wikidata; use its primary Wikimedia Commons portrait ONLY when
machine-readable license metadata identifies CC0, public domain, CC BY or CC BY-SA.
Credited photographs need the author, license and file links; ShareAlike
adaptations are shared under that same CC BY-SA license.
If any validation is uncertain, the caller gets None and renders custom art.
"""
from __future__ import annotations

import io
import re
from html import unescape
from urllib.parse import quote, urlsplit
import unicodedata
from pathlib import Path

import requests
from PIL import Image, ImageOps

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "ChaoFelicevichFootballBot/2.0 (educational automated newsroom; GitHub rchiup/futbol-news-bot)"
ALLOWED_LICENSES = {"cc0", "public domain", "public domain mark"}
ATTRIBUTION_LICENSES = {"cc by 4.0", "cc by 3.0", "cc by 2.0",
                        "cc by sa 4.0", "cc by sa 3.0", "cc by sa 2.0"}
FOOTBALL_DESCRIPTIONS = ("football", "soccer", "futbolista", "fútbol", "footballer",
                         "football manager", "football coach", "futebolista")
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", text))


def name_in_story(name: str, title: str, summary: str) -> bool:
    """LLM-proposed subject must occur verbatim in source context."""
    norm = normalize(name)
    if not norm or len(norm.split()) < 2 or len(norm) < 6 or len(norm) > 70:
        return False
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(norm) + r"(?![a-z0-9])",
                          normalize(title + " " + summary)))


def _get_json(session, endpoint: str, params: dict) -> dict:
    response = session.get(endpoint, params={**params, "format": "json"},
                           headers={"User-Agent": USER_AGENT}, timeout=13)
    response.raise_for_status()
    return response.json()


def _check_commons_file(subject: str, qid: str, filename: str, session=requests) -> dict | None:
    """Check the exact Commons file's machine-readable metadata and credits."""
    if not filename or len(filename) > 200 or "/" in filename or "|" in filename:
        return None
    commons = _get_json(session, COMMONS_API, {
        "action": "query", "prop": "imageinfo", "titles": "File:" + filename,
        "iiprop": "url|size|mime|extmetadata", "iiurlwidth": "1200",
    })
    for page in commons.get("query", {}).get("pages", {}).values():
        for record in page.get("imageinfo", []):
            meta = record.get("extmetadata", {})
            license_name = str(meta.get("LicenseShortName", {}).get("value", "")).strip().lower()
            license_url = str(meta.get("LicenseUrl", {}).get("value", ""))
            rights = str(meta.get("Copyrighted", {}).get("value", "")).strip().lower()
            normalized_license = re.sub(r"\s+", " ", license_name.replace("-", " ").replace("_", " "))
            public_domain = normalized_license in ALLOWED_LICENSES
            credited = normalized_license in ATTRIBUTION_LICENSES
            if not (public_domain or credited):
                continue
            artist_html = str(meta.get("Artist", {}).get("value", ""))
            artist = " ".join(unescape(re.sub(r"<[^>]+>", " ", artist_html)).split())[:95]
            share_alike = normalized_license.startswith("cc by sa ")
            if credited:
                expected = "by-sa" if share_alike else "by"
                version = normalized_license.split()[-1]
                if len(artist) < 3:
                    continue
                if not license_url.startswith(f"https://creativecommons.org/licenses/{expected}/{version}/"):
                    continue
            elif normalized_license != "cc0" and rights not in {"false", "0"}:
                continue
            if record.get("mime", "") not in {"image/jpeg", "image/png", "image/webp"}:
                continue
            if int(record.get("width", 0)) < 400 or int(record.get("height", 0)) < 400:
                continue
            url = record.get("thumburl") or record.get("url") or ""
            if not url.startswith("https://upload.wikimedia.org/"):
                continue
            return {
                "subject": subject, "wikidata_id": qid,
                "image_url": url, "license": license_name,
                "license_url": license_url, "commons_filename": filename,
                "photographer": artist if credited else "",
                "credit_required": credited, "share_alike": share_alike,
                "file_page": "https://commons.wikimedia.org/wiki/File:" + quote(filename.replace(" ", "_")),
            }
    return None


def find_portrait(subject: str, session=requests) -> dict | None:
    """Find a verified football-person portrait, with wider Commons photo coverage."""
    search = _get_json(session, WIKIDATA_API, {
        "action": "wbsearchentities", "search": subject,
        "language": "en", "uselang": "en", "type": "item", "limit": 7,
    })
    exact = [
        row for row in search.get("search", [])
        if normalize(row.get("label", "")) == normalize(subject)
        and any(w in row.get("description", "").lower() for w in FOOTBALL_DESCRIPTIONS)
    ]
    if len(exact) != 1:
        return None
    qid = exact[0].get("id", "")
    if not re.fullmatch(r"Q[0-9]{1,12}", qid):
        return None
    details = _get_json(session, WIKIDATA_API, {
        "action": "wbgetentities", "ids": qid, "props": "claims",
    })
    claims = details.get("entities", {}).get(qid, {}).get("claims", {})
    statements = claims.get("P18", [])
    if statements:
        filename = statements[0].get("mainsnak", {}).get("datavalue", {}).get("value", "")
        photo = _check_commons_file(subject, qid, filename, session)
        if photo:
            return photo

    # When Wikidata's profile photo has incompatible rights, search the Commons
    # file index for alternative portraits explicitly naming this same person.
    # Never search for random football images or rely on a Google thumbnail.
    found = _get_json(session, COMMONS_API, {
        "action": "query", "list": "search",
        "srsearch": f'intitle:"{subject}"', "srnamespace": "6", "srlimit": "12",
        "srprop": "",
    })
    subject_words = normalize(subject).split()
    alternatives = []
    for result in found.get("query", {}).get("search", []):
        title = str(result.get("title", ""))
        if not title.startswith("File:"):
            continue
        filename = title[5:]
        name_words = normalize(filename).split()
        if all(word in name_words for word in subject_words):
            alternatives.append(filename)
    for filename in alternatives[:5]:
        photo = _check_commons_file(subject, qid, filename, session)
        if photo:
            return photo
    return None


def photo_attribution(info: dict | None) -> str:
    """Return legally required image credit, not a news-source attribution."""
    if not info or not info.get("credit_required"):
        return ""
    author = str(info.get("photographer", "")).strip()
    license_name = str(info.get("license", "")).strip().upper()
    page = str(info.get("file_page", "")).strip()
    license_url = str(info.get("license_url", "")).strip()
    if not author or not (page.startswith("https://commons.wikimedia.org/wiki/File:") or
                          page.startswith("https://www.flickr.com/photos/")):
        raise ValueError("Licensed photo is missing attribution details")
    if not license_url.startswith("https://creativecommons.org/licenses/by"):
        raise ValueError("Licensed photo is missing Creative Commons license URL")
    extra = (" · Gráfica adaptada bajo la misma licencia CC BY-SA."
             if info.get("share_alike") else "")
    provider = "Wikimedia Commons" if "wikimedia.org" in page else "Flickr (Openverse)"
    return f"📷 Foto: {author} · {license_name} · {provider} (recorte y edición). {page} · {license_url}{extra}"


def photo_attribution_compact(info: dict | None) -> str:
    """Short public credit; full source/licence record remains attached to media.

    CC-licensed photos must still identify their creator and licence, note
    adaptations, and preserve the original-file and licence links elsewhere in
    the public post metadata. Never present unattributed stock photographs.
    """
    if not info or not info.get("credit_required"):
        return ""
    # Validate and retain the full rights trail instead of simply dropping it.
    photo_attribution(info)
    author = " ".join(str(info.get("photographer", "")).split())
    licence = str(info.get("license", "")).upper()
    note = " · editada" if info.get("share_alike") else ""
    return f"📷 Foto: {author} · {licence}{note}"


def download_portrait(info: dict, destination: Path, session=requests) -> Path:
    """Download licence-verified Commons photo with layered public CDN fallback.

    Referer avoids a known Wikimedia third-party 429 policy. Thumbnail and
    proxy paths are only built from Wikimedia Commons upload URLs; never
    process private data or arbitrary external URLs.
    """
    url = str(info.get("image_url", ""))
    if not url.startswith("https://upload.wikimedia.org/wikipedia/commons/"):
        raise ValueError("Untrusted Commons upload host")
    parsed = urlsplit(url)
    bits = parsed.path.removeprefix("/wikipedia/commons/").split("/")
    thumb = ""
    if len(bits) == 3 and bits[0] and bits[1] and bits[2]:
        thumb = ("https://thumb.wikimedia.org/wikipedia/commons/thumb/"
                 + "/".join(bits) + "/960px-" + bits[2])
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://commons.wikimedia.org/",
        "Accept": "image/jpeg,image/png,image/webp,*/*;q=0.8",
    }
    response = None
    # The original and preview CDNs are separate; the preview saves bandwidth.
    for candidate in [url, thumb]:
        if not candidate:
            continue
        try:
            attempt = session.get(candidate, headers=headers, timeout=14)
            status = getattr(attempt, "status_code", 200)
            if status in (429, 502, 503, 504, 404):
                continue
            attempt.raise_for_status()
            response = attempt
            break
        except requests.RequestException:
            continue
    if response is None:
        response = session.get(
            "https://wsrv.nl/",
            params={"url": url, "w": 1100, "output": "jpg", "q": 85},
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        response.raise_for_status()
    if len(response.content) > MAX_DOWNLOAD_BYTES:
        raise ValueError("Portrait is too large")
    with Image.open(io.BytesIO(response.content)) as source:
        if source.width < 400 or source.height < 400:
            raise ValueError("Portrait resolution too low")
        img = ImageOps.exif_transpose(source).convert("RGB")
        img.thumbnail((1600, 1600))
        destination.parent.mkdir(parents=True, exist_ok=True)
        img.save(destination, "JPEG", quality=89, optimize=True)
    return destination
