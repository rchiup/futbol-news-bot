"""Verified portrait starter library: no live search API required.

Each Commons file was checked against its public file description and licence.
Attribution is added by the existing photo_attribution() function. New images
must be reviewed for identity and commercial/editorial reuse before adding.
"""
from __future__ import annotations
import hashlib
import re
from urllib.parse import quote
from portraits import normalize

# Official Wikimedia Commons file pages and CC BY-SA grants verified 2026-11-23.
# Some photos are archival. They illustrate the person, NOT the current event.
LIBRARY = {
    "Lionel Messi": {
        "filename": "Lionel Messi Argentina v Spain 19 July 2026-222.jpg",
        "author": "Bryan Berlin", "version": "4.0",
        "aliases": ["messi", "lionel messi"],
    },
    "Gianni Infantino": {
        "filename": "Gianni Infantino - 55062516828.jpg",
        "author": "Ricardo Stuckert", "version": "4.0",
        "aliases": ["infantino", "gianni infantino"],
    },
    "Cristiano Ronaldo": {
        "filename": "Cristiano Ronaldo (2).jpg",
        "author": "Jan S0L0", "version": "2.0",
        "aliases": ["cristiano ronaldo", "cr7"],
    },
    "Erling Haaland": {
        "filename": "Erling Haaland 2023.jpg",
        "author": "Jacek Stanislawek", "version": "4.0",
        "aliases": ["haaland", "erling haaland", "erling braut haaland"],
    },
    "Kylian Mbappé": {
        "filename": "Kylian Mbappe France v Senegal 16 June 2026-391 (cropped 2).jpg",
        "author": "Bryan Berlin / WikiPortraits", "version": "4.0",
        "aliases": ["mbappe", "kylian mbappe"],
    },
    "Arturo Vidal": {
        "filename": "Arturo Vidal Copiapó v Colo-Colo 20241110 25.jpg",
        "author": "Carlos Figueroa Rojas", "version": "4.0",
        "aliases": ["arturo vidal"],
    },
    "Alexis Sánchez": {
        "filename": "Alexis Sánchez 2016.jpg",
        "author": "Agencia de Noticias ANDES", "version": "4.0",
        "aliases": ["alexis sanchez"],
    },
}

def _contains_phrase(text: str, phrase: str) -> bool:
    words = normalize(text)
    key = normalize(phrase)
    return bool(key and re.search(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])", words))


def pick_curated(subject: str, title: str, summary: str = "") -> dict | None:
    """Use a photographer-verified file ONLY for a clearly named person.

    Exact full names in article text are preferred; a globally distinctive
    surname may match the title, but ambiguous names never do.
    """
    story = title + " " + summary
    for full_name, record in LIBRARY.items():
        if subject and normalize(subject) not in {"", normalize(full_name)}:
            continue
        if _contains_phrase(story, full_name) or any(
            _contains_phrase(title, alias)
            for alias in record["aliases"]
            if alias not in {"arturo vidal", "alexis sanchez"} or _contains_phrase(title, full_name)
        ):
            filename = record["filename"]
            clean_name = filename.replace(" ", "_")
            digest = hashlib.md5(clean_name.encode("utf-8")).hexdigest()
            url = ("https://upload.wikimedia.org/wikipedia/commons/"
                   + digest[0] + "/" + digest[:2] + "/" + quote(clean_name, safe="()"))
            version = record["version"]
            return {
                "subject": full_name,
                "image_url": url,
                "license": "CC BY-SA " + version,
                "license_url": f"https://creativecommons.org/licenses/by-sa/{version}/",
                "commons_filename": filename,
                "photographer": record["author"],
                "credit_required": True,
                "share_alike": True,
                "file_page": "https://commons.wikimedia.org/wiki/File:"
                             + quote(clean_name, safe="()"),
                "photo_provider": "Curated Commons",
                "verified": "2026-11-23",
            }
    return None
