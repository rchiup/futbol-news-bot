"""One requested breaking-news story, gated on the completed MLS result."""
from datetime import datetime, timezone, timedelta
import requests

ID="manual-messi-mls-20261127"
MATCH_URL="https://www.mlssoccer.com/playoffs/2026/news/columbus-crew-oust-leo-messi-inter-miami-in-playoff-shocker"
API="https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard"

def verified_story(reference, session=requests):
    if not datetime(2026,11,28,1,tzinfo=timezone.utc)<=reference<=datetime(2026,11,28,16,tzinfo=timezone.utc):
        return None
    response=session.get(API,params={"dates":"20261127-20261128"},timeout=12)
    response.raise_for_status()
    for event in response.json().get("events",[]):
        for comp in event.get("competitions",[]):
            status=comp.get("status",{}).get("type",{})
            if not status.get("completed") or status.get("state")!="post":
                continue
            teams=comp.get("competitors",[])
            if len(teams)!=2:
                continue
            def name(t):
                return str(t.get("team",{}).get("displayName","")).lower()
            crew=next((t for t in teams if "columbus crew" in name(t)),None)
            miami=next((t for t in teams if "inter miami" in name(t)),None)
            if not crew or not miami or crew.get("winner") is not True:
                continue
            date=datetime.fromisoformat(str(event.get("date","")).replace("Z","+00:00"))
            if not datetime(2026,11,28,0,tzinfo=timezone.utc)<=date<datetime(2026,11,28,6,tzinfo=timezone.utc):
                continue
            a,b=crew.get("score"),miami.get("score")
            if not str(a).isdigit() or not str(b).isdigit() or int(a)<=int(b):
                continue  # Avoid guessing a shootout score from ordinary goals.
            result=f"{a}-{b}"
            headline="¡PAPELÓN! Messi eliminado en primera ronda"
            description=f"Columbus Crew venció {result} a Inter Miami en el segundo partido de la primera ronda de los playoffs de la MLS. Columbus ya había ganado el primer encuentro por 3-0."
            caption=f"¡PAPELÓN EN LA MLS! Messi y el vigente campeón, eliminados en primera ronda: 0-3 y 0-1 ante Columbus Crew. Dos derrotas y ni un gol. ¿El mayor fracaso de Messi en Miami? Debate abierto."
            return {"id":ID,"title":"Lionel Messi e Inter Miami eliminados por Columbus Crew en los playoffs de la MLS","source_url":MATCH_URL,"source":"ESPN / MLS","description":description,"headline":headline,"caption":caption,"published_at":reference.isoformat(),"queued_at":reference.isoformat(),"status":"draft","sport":"FUTBOL","category":"ACTUALIDAD","score":1000,"visual_subject":"Lionel Messi","visual_entities":{"personas":["Lionel Messi"],"clubes":["Inter Miami","Columbus Crew"],"competicion":["MLS"],"ciudad":[]},"llm_provider":"manual_verified","manual_requested":True}
    return None
