"""Platform-native packaging of already validated sports facts. No new factual claims."""
import hashlib
import re
from difflib import SequenceMatcher
from growth import promotion

DEBATE = re.compile(r"\b(?:VAR|árbitr\w*|penal\w*|polémic\w*|expuls\w*|roja|sanci[oó]n|fichaje|traspaso|renovaci[oó]n|derrota|empate|rivalidad)\b", re.I)
SENSITIVE = re.compile(r"\b(?:muerte|fallec\w*|lesi[oó]n|accidente|tragedia|agresi[oó]n|hospital\w*|cirug[ií]a|abus\w*)\b",re.I)

def clean(text):
    return " ".join(re.sub(r"https?://\S+|[@#]\w+", "", str(text or "")).split())

def headline(item):
    return clean(item.get("headline") or item.get("title"))

def facts(item):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean(item.get("caption"))) if s.strip()]

def debate_question(item):
    text=headline(item)+" "+clean(item.get("caption"))
    if SENSITIVE.search(text):
        return ""
    if re.search(r"\b(?:VAR|árbitr\w*|penal\w*|expuls\w*|roja)\b",text,re.I):
        return "¿Te parece correcta la decisión?"
    if re.search(r"\b(?:fichaje|traspaso|renovaci[oó]n)\b",text,re.I):
        return "¿Harías este movimiento en tu equipo?"
    if re.search(r"\b(?:derrota|empate)\b",text,re.I):
        return "¿Qué cambiarías para el próximo partido?"
    return ""

def variant(item):
    return "headline_hook" if int(hashlib.sha256(str(item.get("id","")).encode()).hexdigest()[:8],16)%2==0 else "fact_hook"

def video_script(item):
    # The hook is sourced from the validated headline or first factual sentence.
    h=headline(item)
    fs=facts(item)
    if not fs:
        return h
    first=fs[0]
    use_headline=variant(item)=="headline_hook" and 4<=len(h.split())<=15 and not SENSITIVE.search(h+" "+first) and SequenceMatcher(None,h.casefold(),first.casefold()).ratio()<.65
    script=([h.rstrip(".!?")+"."] if use_headline else [])+fs
    selected=[]
    for part in script:
        if len(" ".join(selected+[part]).split())>68:
            break
        selected.append(part)
    return " ".join(selected) or first

def instagram_caption(item, caption):
    # Add discussion only when the underlying story supports a real decision.
    question=debate_question(item)
    if question:
        return caption.rstrip()+"\n\n"+question
    return caption

def crosspost_caption(item, caption, platform):
    if platform!="tiktok" or not item.get("headline"):
        return caption
    h=headline(item)
    # Search-friendly entities rather than generic #FYP. Preserve attribution.
    tags=" ".join("#"+t for t in promotion(item)["hashtags"][:3] if "#"+t not in caption)
    prefix=h.rstrip(".!?")+".\n\n" if h.casefold() not in caption[:len(h)+8].casefold() else ""
    return prefix+caption.rstrip()+("\n\n"+tags if tags else "")

def carousel_detail(item):
    if item.get("match_result") or SENSITIVE.search(headline(item)+" "+clean(item.get("caption"))):
        return ""
    fs=facts(item)
    if len(fs)<2 or not DEBATE.search(headline(item)+" "+clean(item.get("caption"))):
        return ""
    detail=" ".join(fs[1:])
    return detail if 30<=len(detail)<=115 and detail[-1] in ".!?" else ""
