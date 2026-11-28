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
    "match": ("victoria", "derrota", "golea", "golazo", "goal", "scores", "scored", "defeat", "won ",
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
    # A single surname (e.g. "Sinner") still identifies the protagonist when it
    # appears in the original title; otherwise the same story slips through twice.
    for token in named.split()[-1:]:
        if len(token) >= 5 and phrase(str(item.get("title") or ""), token):
            out.add("surname:" + norm(token))
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


# Distinctive names and event anchors, including cross-language synonyms.
STOPWORDS = frozenset("the and for with from after before into about that this will were have has says said could would their they are was news football soccer futbol para como desde hasta sobre entre esta este esto estos estas del las los una uno por con que sus tras ante fue sera partido jugadores equipo today ayer hoy".split())
ANCHORS = {
    "badger_hole": ("badger hole", "madriguera", "badger sett"),
    "ferrari_pair": ("hamilton", "leclerc"),
    "ponzio": ("ponzio",),
    "libertadores_final": ("libertadores", "final"),
}
def event_anchors(item):
    title = " ".join(str(item.get(k) or "") for k in ("title","headline"))
    text = norm(title)
    out = set()
    for label, terms in ANCHORS.items():
        if label == "badger_hole":
            if any(phrase(text,t) for t in terms): out.add(label)
        elif all(phrase(text,t) for t in terms):
            if label != "libertadores_final" or any(phrase(text,t) for t in ("estudiantes","palmeiras")):
                out.add(label)
    return out

def lead_tokens(item):
    # Original and generated titles only: shared article boilerplate is noisy.
    return set(re.findall(r"[a-z0-9]{4,}", norm(" ".join(str(item.get(k) or "") for k in ("title","headline"))))) - STOPWORDS

def shared_protagonist(candidate: dict, existing: dict) -> bool:
    """Protagonist named by one item and mentioned by surname in the other, same kind of event."""
    for one, other in ((candidate, existing), (existing, candidate)):
        named = str(one.get("visual_subject") or "").split()
        if named and len(named[-1]) >= 5:
            other_text = " ".join(str(other.get(k) or "") for k in ("title", "headline"))
            if phrase(other_text, named[-1]):
                groups_a, groups_b = event_group(candidate), event_group(existing)
                if not (groups_a and groups_b and groups_a.isdisjoint(groups_b)):
                    return True
    return False


def same_story(candidate: dict, existing: dict, reference: datetime | None = None) -> bool:
    if candidate.get("id") and existing.get("id") == candidate["id"]:
        return False
    if candidate.get("source_url") and candidate["source_url"] == existing.get("source_url"):
        return True
    reference = reference or datetime.now(timezone.utc)
    first, second = story_time(candidate), story_time(existing)
    if first and second and abs((first - second).total_seconds()) > COOLDOWN_HOURS * 3600:
        return False
    # A completed elimination is distinct from a pre-match preview or a testimonial.
    # Keep ordinary deduplication for other reports of the same elimination.
    def mls_elimination(item):
        t = norm(" ".join(str(item.get(k) or "") for k in ("title","headline","description")))
        return ("columbus" in t and "miami" in t and any(w in t for w in ("eliminad","elimination","ousted","knocked out","eliminacion")))
    def clearly_other_event(item):
        t = norm(" ".join(str(item.get(k) or "") for k in ("title","headline")))
        return ("tevez" in t and any(w in t for w in ("despedida","testimonial","homenaje"))) or ("columbus" in t and "miami" in t and any(w in t for w in ("en vivo","live","arranco","previa","preview","busca victoria")))
    if (mls_elimination(candidate) and clearly_other_event(existing) and not mls_elimination(existing)) or (mls_elimination(existing) and clearly_other_event(candidate) and not mls_elimination(candidate)):
        return False
    # Checked before the sport guard: general feeds (e.g. Olé) tag tennis news as FUTBOL.
    if shared_protagonist(candidate, existing):
        return True
    if str(candidate.get("sport", "FUTBOL")) != str(existing.get("sport", "FUTBOL")):
        return False
    if event_anchors(candidate) & event_anchors(existing):
        return True
    tokens_a, tokens_b = lead_tokens(candidate), lead_tokens(existing)
    shared = tokens_a & tokens_b
    if len(shared) >= 3 and len(shared) / max(1, min(len(tokens_a), len(tokens_b))) >= 0.55:
        return True
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
