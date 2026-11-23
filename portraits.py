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
from urllib.parse import quote
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


def find_portrait(subject: str, session=requests) -> dict | None:
    """Find a verified person portrait and safe license, or return None."""
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
        return None  # ambiguous or no exact football entity: no photo
    qid = exact[0].get("id", "")
    if not re.fullmatch(r"Q[0-9]{1,12}", qid):
        return None
    details = _get_json(session, WIKIDATA_API, {
        "action": "wbgetentities", "ids": qid, "props": "claims",
    })
    statements = details.get("entities", {}).get(qid, {}).get("claims", {}).get("P18", [])
    if not statements:
        return None
    filename = statements[0].get("mainsnak", {}).get("datavalue", {}).get("value", "")
    if not filename or len(filename) > 200 or "/" in filename:
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
            normalized_license = license_name.replace("-", " ").replace("_", " ").strip()
            is_public_domain = normalized_license in ALLOWED_LICENSES
            requires_credit = normalized_license in ATTRIBUTION_LICENSES
            if not (is_public_domain or requires_credit):
                return None
            artist_html = str(meta.get("Artist", {}).get("value", ""))
            artist = " ".join(unescape(re.sub(r"<[^>]+>", " ", artist_html)).split())[:95]
            if requires_credit:
                # Never take an attributed photo when the author or license is absent.
                if len(artist) < 3 or len(artist) > 95:
                    return None
                expected_kind = "by-sa" if " by sa " in (" " + normalized_license + " ") else "by"
                expected_url = f"https://creativecommons.org/licenses/{expected_kind}/{normalized_license.split()[-1]}/"
                if not license_url.startswith(expected_url):
                    return None
            elif normalized_license not in {"cc0", "public domain", "public domain mark"} or (
                    normalized_license != "cc0" and rights not in {"false", "0"}):
                return None
            if record.get("mime", "") not in {"image/jpeg", "image/png", "image/webp"}:
                return None
            if int(record.get("width", 0)) < 400 or int(record.get("height", 0)) < 400:
                return None
            url = record.get("thumburl") or record.get("url") or ""
            if not url.startswith("https://upload.wikimedia.org/"):
                return None
            return {
                "subject": subject, "wikidata_id": qid,
                "image_url": url, "license": license_name,
                "license_url": license_url, "commons_filename": filename,
                "photographer": artist if requires_credit else "",
                "credit_required": requires_credit,
                "share_alike": " by sa " in (" " + normalized_license + " "),
                "file_page": "https://commons.wikimedia.org/wiki/File:" + quote(filename.replace(" ", "_")),
            }
    return None


def photo_attribution(info: dict | None) -> str:
    """Return legally required image credit, not a news-source attribution."""
    if not info or not info.get("credit_required"):
        return ""
    author = str(info.get("photographer", "")).strip()
    license_name = str(info.get("license", "")).strip().upper()
    page = str(info.get("file_page", "")).strip()
    license_url = str(info.get("license_url", "")).strip()
    if not author or not page.startswith("https://commons.wikimedia.org/wiki/File:"):
        raise ValueError("Licensed photo is missing attribution details")
    if not license_url.startswith("https://creativecommons.org/licenses/by"):
        raise ValueError("Licensed photo is missing Creative Commons license URL")
    extra = (" · Gráfica adaptada bajo la misma licencia CC BY-SA."
             if info.get("share_alike") else "")
    return f"📷 Foto: {author} · {license_name} · Wikimedia Commons (recorte y edición). {page} · {license_url}{extra}"


def download_portrait(info: dict, destination: Path, session=requests) -> Path:
    url = str(info.get("image_url", ""))
    if not url.startswith("https://upload.wikimedia.org/"):
        raise ValueError("Untrusted portrait host")
    response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=18)
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
