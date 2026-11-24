"""Final scores from ESPN scoreboard; no LLM score inference."""
from datetime import timedelta
from io import BytesIO
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageOps
from graphics import font, _original_background

def results(reference, session=requests):
    day = reference.strftime("%Y%m%d")
    response = session.get("https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/scoreboard", params={"dates":day}, timeout=12)
    response.raise_for_status()
    out = []
    for event in response.json().get("events", []):
        for comp in event.get("competitions", []):
            if comp.get("status", {}).get("type", {}).get("name") != "STATUS_FULL_TIME":
                continue
            teams = sorted(comp.get("competitors", []), key=lambda x:x.get("homeAway")!="home")
            if len(teams)!=2 or any(not str(t.get("score","")).isdigit() for t in teams):
                continue
            rows = [{"name":t["team"]["displayName"],"abbr":t["team"].get("abbreviation",""),"logo":t["team"].get("logo",""),"score":int(t["score"])} for t in teams]
            label = f"{rows[0]['name']} {rows[0]['score']}-{rows[1]['score']} {rows[1]['name']}"
            scorers = []
            for detail in comp.get("details", []):
                if detail.get("scoringPlay"):
                    for athlete in detail.get("athletesInvolved", []):
                        if athlete.get("displayName"):
                            scorers.append(athlete["displayName"]+" "+detail.get("clock",{}).get("displayValue",""))
            caption = "Resultado final de la Champions League: "+label+"."
            if scorers: caption += " Goles: "+", ".join(scorers)+"."
            out.append({"id":"ucl-final-"+str(event["id"]), "title":label,"headline":label,"description":caption,"caption":caption+" Datos: ESPN.","score":1000,"sport":"FUTBOL","category":"PARTIDOS","source":"ESPN","published_at":reference.isoformat(),"status":"draft","match_result":rows})
    return out

def render(item, destination, brand):
    im = _original_background((88,212,234)).convert("RGB")
    d = ImageDraw.Draw(im)
    d.text((60,65),brand,font=font(40),fill="white")
    d.text((540,245),"CHAMPIONS LEAGUE",font=font(54),fill="white",anchor="mm")
    d.text((540,325),"RESULTADO FINAL",font=font(32),fill=(88,212,234),anchor="mm")
    for x,t in zip((255,825),item["match_result"]):
        logo=t["logo"]
        try:
            if not logo.startswith("https://a.espncdn.com/"): raise ValueError("unknown crest host")
            r=requests.get(logo,timeout=8,allow_redirects=False)
            r.raise_for_status()
            pic=ImageOps.contain(Image.open(BytesIO(r.content)).convert("RGBA"),(230,230))
            im.paste(pic,(x-pic.width//2,490-pic.height//2),pic)
        except (requests.RequestException,ValueError,OSError):
            d.text((x,490),t["abbr"],font=font(70),fill="white",anchor="mm")
        d.text((x,800),t["abbr"],font=font(48),fill="white",anchor="mm")
    a,b=item["match_result"]
    d.text((540,665),f"{a['score']} - {b['score']}",font=font(150),fill="white",anchor="mm")
    d.line((60,1120,1020,1120),fill=(88,212,234),width=3)
    d.text((60,1170),"INFORMACIÓN DEPORTIVA  /  ESPN",font=font(26),fill="white")
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    im.save(destination,quality=94)
    return destination
