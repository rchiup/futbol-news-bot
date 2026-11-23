"""Cross-feed, cross-language novelty and one-protagonist cooling period.

URL/title equality alone misses headlines about the SAME story rewritten by
different outlets or translated by AI. Be conservative: one lead subject per
36h, unless a human editor deliberately approves another angle.

This never creates new stories or verifies factual claims: RSS articles are
required independently by the editorial pipeline.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime, timezone, timedelta
from curated_portraits import LIBRARY

COOLDOWN_HOURS = 36
ACTIVE = frozenset({"published", "draft", "awaiting_ai", "publish_error", "publishing"})
SPANISH_CHILE = (
    "universidad de chile", "colo colo", "cobreloa", "eduardo vargas",
    "seleccion chilena", "la roja de chile", "campeonato nacional", "huachipato", "copa chile",
    "palestino", "santiago wanderers",
)
EVENT_TERMS = {
    "injury": ("lesion", "baja", "dolencia", "molestia", "tobillo", "injur", "ankle",
               "sidelined", "out for", "miss ", "hospital", "operacion", "cirugia"),
    "match": ("victoria", "derrota", "golea", "golazo", "defeat", "won ",
              "beat ", "lost ", "loss ", "thrash", "aplasta", "4 0", "4-0"),
    "transfer": ("fichaj", "traspas", "negocia", "transfer", "signing", "rumor",
                 "renew", "renueva", "contrato", "loan"),
    "discipline": ("expulsion", "tarjeta roja", "red card", "appeal", "apelar"),
    "tournament": ("sede", "world cup", "mundial", "host ", "fifa", "2035", "2031"),
}


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def phrase(haystack: str, needle: str) -> bool:
    value = norm(haystack)
    key = norm(needle)
    return bool(key and re.search(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])", value))


def story_subjects(item: dict) -> set[str]:
    title = " ".join(str(item.get(k) or "") for k in ("title", "headline", "description"))
    out = set()
    named = str(item.get("visual_subject") or "").strip()
    # Do not let the AI inject an absent person: their name must occur in RSS source.
    if len(named.split()) >= 2 and (
            phrase(str(item.get("title") or "") + " " + str(item.get("description") or ""), named)):
        out.add(norm(named))
    for full, record in LIBRARY.items():
        aliases = [full, *record.get("aliases", [])]
        # Short surnames are too ambiguous unless a full name is in article data.
        for alias in aliases:
            key = norm(alias)
            if len(key) < 5:
                continue
            if key == "paredes" and not phrase(title, "boca"):
                continue
            if phrase(title, alias):
                out.add(norm(full))
                break
    # Poch is the familiar shorthand for Pochettino in many English headlines.
    if phrase(title, "poch") and any(phrase(title, word) for word in
                                     ("united", "liverpool", "man utd", "manchester")):
        out.add(norm("Mauricio Pochettino"))
    return out


def event_group(item: dict) -> set[str]:
    title = " ".join(str(item.get(k) or "") for k in ("title", "headline"))
    normed = norm(title)
    return {kind for kind, words in EVENT_TERMS.items()
            if any(norm(w) in normed for w in words)}


def story_time(item: dict) -> datetime | None:
    for field in ("posted_at", "published_at", "queued_at"):
        raw = item.get(field)
        if not raw:
            continue
        try:
            d = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def same_story(candidate: dict, existing: dict, reference: datetime | None = None) -> bool:
    if candidate.get("id") and existing.get("id") == candidate["id"]:
        return False
    if candidate.get("source_url") and candidate["source_url"] == existing.get("source_url"):
        return True
    if str(candidate.get("sport", "FUTBOL")) != str(existing.get("sport", "FUTBOL")):
        return False
    reference = reference or datetime.now(timezone.utc)
    first, second = story_time(candidate), story_time(existing)
    if first and second and abs((first - second).total_seconds()) > COOLDOWN_HOURS * 3600:
        return False
    # The same main protagonist within 36h: avoid repeatedly posting the same
    # news just because the outlet changed or the headline was rewritten.
    leads_a, leads_b = story_subjects(candidate), story_subjects(existing)
    if leads_a & leads_b:
        # A player's injury and a later match-winning goal are genuinely
        # different stories; don't silence important new events about one star.
        groups_a, groups_b = event_group(candidate), event_group(existing)
        if groups_a and groups_b and groups_a.isdisjoint(groups_b):
            return False
        return True
    text_a = norm(" ".join(str(candidate.get(k) or "") for k in ("title", "headline")))
    text_b = norm(" ".join(str(existing.get(k) or "") for k in ("title", "headline")))
    if len(text_a) > 22 and len(text_b) > 22:
        if SequenceMatcher(None, text_a, text_b).ratio() >= 0.80:
            return True
    # Tournament announcements: year + FIFA/world cup make an unambiguous
    # event, regardless of English/Spanish headline wording.
    for year in ("2031", "2035", "2026", "2030"):
        if year in text_a.split() and year in text_b.split():
            terms_a, terms_b = event_group(candidate), event_group(existing)
            if "tournament" in terms_a and "tournament" in terms_b:
                return True
    return False


def duplicate_reason(item: dict, queue: list[dict], reference: datetime | None = None) -> str:
    for existing in reversed(queue[-1000:]):
        if existing is item or existing.get("id") == item.get("id"):
            continue
        if existing.get("status") not in ACTIVE:
            continue
        if same_story(item, existing, reference):
            return f"same_story_as:{existing.get('id', 'unknown')}"
    return ""


def novelty_priority(item: dict, reference: datetime) -> tuple:
    """Fresh major news first; portrait availability is NOT the first key."""
    when = story_time(item)
    hours = max(0.0, (reference - when).total_seconds() / 3600) if when else 99.0
    story = norm(item.get("title", "") + " " + item.get("headline", ""))
    chile = int(any(phrase(story, k) for k in SPANISH_CHILE if len(norm(k)) >= 5))
    urgent = int(hours <= 4)
    injury = int("injury" in event_group(item))
    score = int(item.get("score") or 0)
    return (urgent, chile, score, injury, -hours)
