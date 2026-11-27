"""Conservative pre-publication checks for factual scores and photo identity."""
import re
import unicodedata

SCORE = re.compile(r"(?<!\d)(\d{1,2})\s*[-–—‑−:]\s*(\d{1,2})(?!\d)")
DECISIVE = re.compile(r"\b(?:cay[oó]|cayeron|perdi[oó]|perdieron|derrot[oó]|derrotaron|venci[oó]|vencieron|gole[oó]|golearon|gan[oó]|ganaron|se impuso|fue derrotad[oa]|fue vencid[oa])\b",re.I)
DRAW = re.compile(r"\b(?:empat[oó]|empataron|igual[oó]|igualaron|empate)\b",re.I)

def norm(value):
    return " ".join(re.findall(r"[a-z0-9]+", "".join(c for c in unicodedata.normalize("NFKD", str(value).casefold()) if not unicodedata.combining(c))))

def scores(text):
    return [(int(a), int(b)) for a,b in SCORE.findall(text)]

def mentioned_team(team, story):
    name = norm(team.get("name",""))
    abbr = norm(team.get("abbr",""))
    aliases = [name, abbr]
    if name.startswith("as "):
        aliases.append(name[3:])
    if name == "paris saint germain":
        aliases += ["psg", "paris saint germain"]
    if name == "internazionale":
        aliases += ["inter de milan", "inter milan", "inter"]
    if name == "bayern munich":
        aliases.append("bayern")
    return any(len(alias)>=3 and (" "+alias+" ") in (" "+story+" ") for alias in aliases)

def score_error(item, queue=()):
    if item.get("sport","FUTBOL") != "FUTBOL":
        return ""
    raw = " ".join(str(item.get(k) or "") for k in ("title","description","article_context"))
    copy = " ".join(str(item.get(k) or "") for k in ("headline","caption"))
    # Check each sentence/line: a draw cannot itself be a defeat or victory.
    for part in re.split(r"[.!?;\n]", copy):
        for match in SCORE.finditer(part):
            a,b = map(int,match.groups())
            # Nearby verbs only, not a separate historical result in another clause.
            nearby = part[max(0,match.start()-85):match.end()+45]
            if a==b and DECISIVE.search(nearby) and not re.search(r"\b(?:penales|penaltis|tanda)\b",nearby,re.I):
                return "draw_described_as_win_or_loss"
            if a!=b and DRAW.search(nearby):
                return "unequal_score_described_as_draw"
    if item.get("match_result"):
        rows=item["match_result"]
        if len(rows)==2 and all(isinstance(t,dict) and isinstance(t.get("score"),int) for t in rows):
            expected=(rows[0]["score"],rows[1]["score"])
            if expected not in scores(copy):
                return "structured_score_missing_or_wrong"
        return ""
    # A numeric match result must be grounded in the actual source or a
    # structured scoreboard for both teams, not invented by the language model.
    reported=scores(copy)
    if not reported:
        return ""
    supported={tuple(sorted(pair)) for pair in scores(raw)}
    story=norm(raw)
    for other in queue:
        rows=other.get("match_result")
        if other.get("sport")!="FUTBOL" or not isinstance(rows,list) or len(rows)!=2:
            continue
        if all(isinstance(t,dict) and isinstance(t.get("score"),int) and mentioned_team(t,story) for t in rows):
            supported.add(tuple(sorted(t["score"] for t in rows)))
    if any(tuple(sorted(pair)) not in supported for pair in reported):
        return "unverified_numeric_score"
    return ""

def photo_safe(info, item):
    if not isinstance(info,dict) or not info.get("image_url") or info.get("reference_only"):
        return False
    subject=norm(info.get("subject",""))
    filename=norm(info.get("commons_filename",""))
    identity=str(info.get("entity_qid") or info.get("wikidata_id") or "")
    # Known homonym: Luis Enrique Ponce, not the current PSG coach.
    if identity=="Q222789" or "luis enrique ponce" in filename:
        return False
    # Ambiguous given-name-only identities require a manually reviewed photo.
    if subject=="luis enrique" and info.get("photo_provider")!="Curated Commons":
        return False
    story=norm(" ".join(str(item.get(k) or "") for k in ("title","description")))
    if info.get("photo_provider")!="Curated Commons" and (not subject or (" "+subject+" ") not in (" "+story+" ")):
        return False
    # Historical photos cannot illustrate a current story unless the source
    # actually discusses that historical period.
    if any(1900<=int(y)<1980 and y not in story.split() for y in re.findall(r"\b(?:19\d{2})\b",filename)):
        return False
    return True


def identity_error(item):
    raw=" ".join(str(item.get(k) or "") for k in ("title","description","article_context"))
    copy=" ".join(str(item.get(k) or "") for k in ("headline","caption"))
    # Preserve source spelling of full personal names, including common translated given names.
    aliases={"alexander":{"alejandro","alexandre","alessandro"},"arthur":{"arturo"},"john":{"juan"},"james":{"jaime","santiago"},"michael":{"miguel"},"william":{"guillermo"},"charles":{"carlos"},"george":{"jorge"},"peter":{"pedro"},"louis":{"luis"},"harry":{"enrique"},"robert":{"roberto"},"thomas":{"tomas"}}
    source=norm(raw)
    output=norm(copy)
    for given,translations in aliases.items():
        for surname in re.findall(r"\b"+given+r" ([a-z]{3,})\b",source):
            if any(re.search(r"\b"+a+" "+surname+r"\b",output) and not re.search(r"\b"+a+" "+surname+r"\b",source) for a in translations):
                return "translated_person_name"
    if item.get("sport")=="TENIS":
        # Team elimination is not an individual singles defeat.
        h=norm(item.get("headline",""))
        c=norm(item.get("caption",""))
        if re.search(r"\b(?:davis cup|copa davis|billie jean king)\b",source+" "+c) and re.search(r"\b(?:gano|vencio|se impuso)\b.{0,65}\b(?:singles|individual|individuales)\b",c) and re.search(r"\b(?:cae|cayo|pierde|perdio|derrotado|eliminado)\b",h):
            for name in re.findall(r"\b([A-ZÁÉÍÓÚ][a-záéíóú]+ [A-ZÁÉÍÓÚ][a-záéíóú]+)\b",raw):
                surname=norm(name).split()[-1]
                if re.search(r"\b"+surname+r"\s+(?:cae|cayo|pierde|perdio|queda eliminado)\b",h) and re.search(r"\b"+surname+r"\s+(?:gano|vencio|se impuso)\b",c):
                    return "individual_win_misrepresented_as_loss"
    return ""
