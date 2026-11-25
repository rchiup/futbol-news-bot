"""One-time owner-requested match analysis; independent platform outcomes."""
from pathlib import Path
from PIL import Image, ImageDraw
from graphics import font
import reels
import buffer_publish
from publisher import upload_public_video, publish_reel

ID = "real-psv-analysis-20261124"
HEADLINE = "Real Madrid 5-1 PSV: la clave de la remontada"
CAPTION = ("El Real Madrid goleó cinco a uno al PSV. Tras el gol de Perisic, "
           "Valverde empató al comienzo del segundo tiempo. Bellingham puso al Madrid por delante, "
           "Mbappé anotó dos veces y Vinicius cerró la goleada. La clave fue la reacción "
           "tras el descanso: cinco goles en una sola mitad.")
SOURCE = "Europa Press / UOL"

def run_once(queue, save, reference):
    if any(x.get("id")==ID for x in queue):
        return
    item = {"id":ID,"headline":HEADLINE,"caption":CAPTION,"source":SOURCE,
            "sport":"Fútbol","status":"rendering","published_at":reference.isoformat(),
            "publish_format":"reel","url":"https://www.europapress.es/deportes/estadisticas-deportivas/noticia-real-madrid-psv-eindhoven-resumen-goles-resultado-partido-hoy-20261124225935.html"}
    try:
        root=Path("output/reels")
        root.mkdir(parents=True,exist_ok=True)
        cover=root/(ID+".jpg")
        im=Image.new("RGB",(1080,1920),(12,24,45))
        d=ImageDraw.Draw(im)
        for y in range(1920):
            d.line((0,y,1080,y),fill=(12+y//100,24+y//80,45+y//60))
        d.text((540,480),"CHAMPIONS LEAGUE",font=font(44),fill=(208,249,92),anchor="mm")
        d.text((540,600),"REAL MADRID  ·  PSV",font=font(48),fill="white",anchor="mm")
        d.text((540,800),"5 - 1",font=font(180),fill="white",anchor="mm")
        im.save(cover)
        video=reels.render(item,cover,root/(ID+".mp4"),"CHAO FELICEVICH")
        item["reel_video_url"]=upload_public_video(video,ID)
    except Exception as exc:
        print("[FORCED REEL] Render/upload failed: "+type(exc).__name__)
        return
    queue.append(item)
    save(queue)
    caption=CAPTION+"\n\nFuentes: "+SOURCE+"\n#RealMadrid #ChampionsLeague #Shorts"
    buffer_publish.crosspost(item,item["reel_video_url"],caption,persist=lambda:save(queue))
    item["instagram_reel_status"]="submitting"
    save(queue)
    try:
        item["instagram_media_id"]=publish_reel(video,caption,ID,public_url=item["reel_video_url"])
        item["instagram_reel_status"]="published"
        item["status"]="published"
        item["posted_at"]=reference.isoformat()
    except Exception as exc:
        item["instagram_reel_status"]="check_required"
        item["status"]="publish_error"
        print("[FORCED REEL] Instagram unconfirmed: "+type(exc).__name__)
    save(queue)
    print("[FORCED REEL] Independent platform outcomes saved")
