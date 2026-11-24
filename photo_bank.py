"""Persistent, rights-checked image metadata for named people and clubs."""
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from portraits import normalize, _get_json, _check_commons_file, WIKIDATA_API, COMMONS_API
import requests

BANK = Path(__file__).parent / "data/photo_bank.json"
CLUBS = {"Liverpool": "Q1130849", "Manchester United": "Q18656", "Arsenal": "Q9617", "Chelsea": "Q9616", "Real Madrid": "Q8682", "Barcelona": "Q7156", "Bayern Munich": "Q15789", "Boca Juniors": "Q12131", "River Plate": "Q12203"}
SPORT_WORDS = ("football", "soccer", "tennis", "basketball", "golfer", "racing driver", "formula one", "futbol", "tenista", "baloncesto")

def mentioned(name, story):
    key = normalize(name)
    return bool(key and len(key) >= 4 and re.search(r"(?<!\w)" + re.escape(key) + r"(?!\w)", normalize(story)))

def entities(item, output=None):
    output = output or item
    story = str(item.get("title","")) + " " + str(item.get("description",""))
    result = {}
    for key in ("personas", "clubes", "competicion", "ciudad"):
        raw = output.get(key, [])
        if isinstance(raw, str):
            raw = [raw]
        result[key] = list(dict.fromkeys(x.strip() for x in raw[:8] if isinstance(x,str) and len(x)<=75 and mentioned(x,story))) if isinstance(raw,list) else []
    subject = output.get("visual_subject","")
    if isinstance(subject,str) and len(subject.split())>=2 and mentioned(subject,story):
        result["personas"] = list(dict.fromkeys([subject]+result["personas"]))
    result["clubes"] = list(dict.fromkeys(result["clubes"]+[c for c in CLUBS if mentioned(c,story)]))
    return result

def load_bank():
    try:
        data=json.loads(BANK.read_text())
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):
        return {}

def save_bank(bank):
    BANK.parent.mkdir(parents=True,exist_ok=True)
    tmp=BANK.with_suffix(".tmp")
    tmp.write_text(json.dumps(bank,ensure_ascii=False,indent=2)+"\n")
    tmp.replace(BANK)

def claims_for(qid, session):
    return _get_json(session,WIKIDATA_API,{"action":"wbgetentities","ids":qid,"props":"claims"}).get("entities",{}).get(qid,{}).get("claims",{})

def values(claims, prop):
    return [s.get("mainsnak",{}).get("datavalue",{}).get("value") for s in claims.get(prop,[]) if s.get("rank")!="deprecated"]

def resolve(name, kind, session):
    found=_get_json(session,WIKIDATA_API,{"action":"wbsearchentities","search":name,"language":"en","type":"item","limit":7})
    rows=[r for r in found.get("search",[]) if normalize(r.get("label",""))==normalize(name) and any(w in r.get("description","").lower() for w in (SPORT_WORDS if kind=="person" else ("football club","soccer club","football team","basketball team")))]
    return rows[0]["id"] if len(rows)==1 and re.fullmatch(r"Q\d+",rows[0].get("id","")) else None

def find_entity_photo(name, kind, session=requests):
    qid=resolve(name,kind,session)
    if not qid:
        return None
    claims=claims_for(qid,session)
    if kind=="club":
        venues=[v["id"] for v in values(claims,"P115") if isinstance(v,dict) and re.fullmatch(r"Q\d+",v.get("id",""))]
        if len(set(venues))!=1:
            return None
        claims=claims_for(venues[0],session)
        image_qid=venues[0]
    else:
        image_qid=qid
    files=[v for v in values(claims,"P18") if isinstance(v,str)]
    if kind=="person":
        cats=[v for v in values(claims,"P373") if isinstance(v,str)]
        if cats:
            data=_get_json(session,COMMONS_API,{"action":"query","list":"categorymembers","cmtitle":"Category:"+cats[0],"cmtype":"file","cmlimit":12})
            files += [r["title"][5:] for r in data.get("query",{}).get("categorymembers",[]) if r.get("title","").startswith("File:") and mentioned(name,r["title"])]
    candidates=[]
    for filename in list(dict.fromkeys(files))[:4]:
        photo=_check_commons_file(name,image_qid,filename,session)
        if photo:
            candidates.append(photo)
    if not candidates:
        return None
    photo=max(candidates,key=lambda p:min(p.get("width",0),p.get("height",0)))
    photo.update(entity_kind=kind,entity_qid=qid,photo_provider="Wikidata photo bank",verified_at=datetime.now(timezone.utc).isoformat())
    return photo

def choose_photo(item, network=False, session=requests):
    bank=load_bank()
    groups=entities(item,item.get("visual_entities") or item)
    for kind,names in (("person",groups["personas"]),("club",groups["clubes"])):
        for name in names[:3]:
            key=kind+":"+normalize(name)
            cached=bank.get(key)
            if isinstance(cached,dict) and cached.get("image_url"):
                return cached
    if network:
        for kind,names in (("person",groups["personas"]),("club",groups["clubes"])):
            for name in names[:2]:
                try:
                    photo=find_entity_photo(name,kind,session)
                    if photo:
                        bank[kind+":"+normalize(name)]=photo
                        save_bank(bank)
                        return photo
                except (requests.RequestException,ValueError,KeyError,TypeError):
                    continue
    return None
