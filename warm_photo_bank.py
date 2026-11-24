"""Bounded, rotating SPARQL roster warmup plus recent newsroom entities."""
import json
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit
import requests
from photo_bank import entities, load_bank, save_bank, find_entity_photo
from portraits import normalize, _check_commons_file, USER_AGENT

# League IDs resolved by exact labels through Wikidata, not guessed identifiers.
LEAGUES = ("Premier League", "La Liga", "Serie A", "Primera División de Chile",
           "Argentine Primera División", "NBA")
SPORTS = ("Formula One", "tennis")
CURSOR = Path("data/photo_bank_cursor.json")

def discover_roster(league, offset=0, session=requests):
    # League membership and active team statements. Exclude ended player spells.
    search=session.get("https://www.wikidata.org/w/api.php",params={"action":"wbsearchentities","search":league,"language":"en","format":"json","limit":8},headers={"User-Agent":USER_AGENT},timeout=15)
    search.raise_for_status()
    candidates=[r for r in search.json().get("search",[]) if normalize(r.get("label",""))==normalize(league) and any(w in r.get("description","").lower() for w in ("league","football division","basketball league","racing","sport"))]
    if len(candidates)!=1:
        return []
    qid=candidates[0].get("id","")
    import re
    if not re.fullmatch(r"Q\d+",qid):
        return []
    query="""SELECT DISTINCT ?person ?personLabel ?photo WHERE {
      ?team wdt:P118 wd:%s.
      ?person p:P54 ?membership; wdt:P18 ?photo.
      ?membership ps:P54 ?team.
      FILTER NOT EXISTS { ?membership pq:P582 ?end. FILTER(?end <= NOW()) }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
    } ORDER BY ?person ?photo LIMIT 40 OFFSET %d""" % (qid,offset)
    response=session.get("https://query.wikidata.org/sparql",params={"query":query,"format":"json"},headers={"User-Agent":USER_AGENT,"Accept":"application/sparql-results+json"},timeout=40)
    response.raise_for_status()
    return response.json().get("results",{}).get("bindings",[])

def warm_rosters(bank):
    try:
        cursor=json.loads(CURSOR.read_text())
    except (OSError,ValueError):
        cursor={}
    league=LEAGUES[int(cursor.get("league",0))%len(LEAGUES)]
    offset=int(cursor.get(league,0))
    try:
        rows=discover_roster(league,offset)
        for row in rows:
            name=row["personLabel"]["value"]
            qid=row["person"]["value"].rsplit("/",1)[-1]
            filename=unquote(urlsplit(row["photo"]["value"]).path.rsplit("/",1)[-1])
            key="person:"+normalize(name)
            if key in bank or not name or name==qid:
                continue
            try:
                photo=_check_commons_file(name,qid,filename)
                if photo:
                    photo.update(entity_kind="person",entity_qid=qid,photo_provider="Wikidata roster")
                    bank[key]=photo
                    save_bank(bank)
            except (requests.RequestException,ValueError,KeyError,TypeError):
                pass
            time.sleep(0.5)
        cursor[league]=offset+40 if len(rows)==40 else 0
    except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
        print("[BANK] Roster discovery unavailable:",type(exc).__name__)
    cursor["league"]=(int(cursor.get("league",0))+1)%len(LEAGUES)
    CURSOR.parent.mkdir(parents=True,exist_ok=True)
    CURSOR.write_text(json.dumps(cursor,indent=2)+"\n")

def main():
    bank=load_bank()
    warm_rosters(bank)
    queue=json.loads(Path("data/queue.json").read_text())
    attempted=0
    seen=set()
    for item in reversed(queue):
        groups=entities(item,item.get("visual_entities") or item)
        for kind,names in (("person",groups["personas"]),("club",groups["clubes"])):
            for name in names:
                key=kind+":"+normalize(name)
                if key in bank or key in seen:
                    continue
                if attempted>=15:
                    return
                seen.add(key)
                attempted+=1
                try:
                    photo=find_entity_photo(name,kind)
                    if photo:
                        bank[key]=photo
                        save_bank(bank)
                except (requests.RequestException,ValueError,KeyError,TypeError):
                    pass
                time.sleep(1)

if __name__=="__main__":
    main()
