"""Deterministic promotion metadata; never invent Instagram handles."""
import json
import re
import unicodedata
from pathlib import Path

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(s).lower()) if not unicodedata.combining(c))

def mentioned(name, story):
    return bool(re.search(r'(?<!\w)' + re.escape(norm(name)) + r'(?!\w)', norm(story)))

def promotion(item, registry=None):
    story = str(item.get("title","")) + " " + str(item.get("description",""))
    sport = item.get("sport","FUTBOL")
    tags = [{"FUTBOL":"Futbol","TENIS":"Tenis","NBA":"NBA","F1":"Formula1","GOLF":"Golf"}.get(sport,"Deportes")]
    groups = item.get("visual_entities") or {}
    names = []
    for kind in ("personas","clubes","competicion"):
        for name in groups.get(kind,[])[:5]:
            if isinstance(name,str) and len(name)>=4 and mentioned(name,story):
                names.append(name)
    for name in names:
        tag = re.sub(r'[^a-zA-Z0-9]', '', ''.join(c for c in unicodedata.normalize('NFKD',name) if not unicodedata.combining(c)))
        if 4 <= len(tag) <= 35 and tag.lower() not in {t.lower() for t in tags}:
            tags.append(tag)
    if registry is None:
        try:
            registry = json.loads(Path(__file__).with_name("official_handles.json").read_text())
        except (OSError, ValueError):
            registry = {}
    handles = []
    for name in names:
        handle = registry.get(norm(name),"")
        if isinstance(handle,str) and re.fullmatch(r'[A-Za-z0-9_.]{1,30}',handle) and handle not in handles:
            handles.append(handle)
    return {"hashtags":tags[:5], "mentions":handles[:2]}

def append_promotion(caption,item):
    data = promotion(item)
    item["promotion"] = data
    suffix = " ".join(["@"+x for x in data["mentions"]] + ["#"+x for x in data["hashtags"]])
    return caption + "\n\n" + suffix if suffix else caption
