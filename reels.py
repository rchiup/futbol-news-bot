"""Reusable vertical video renderer: local TTS, Pillow captions, FFmpeg H.264."""
from pathlib import Path
import os
import json
import re
import shutil
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageOps, ImageFilter
from graphics import font, _wrap

def narration(item):
    # Use the already validated Spanish caption, never generate additional facts.
    text = re.sub(r"https?://\S+|[@#]\w+", "", str(item.get("caption") or item.get("headline") or ""))
    text = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    selected=[]
    for sentence in sentences:
        if not sentence.strip(): continue
        if len((" ".join(selected+[sentence])).split()) > 68:
            break
        selected.append(sentence)
    if not selected:
        selected=[str(item.get("headline") or "").strip()]
    # Short caption chunks; the same chunks are spoken, so timing is exact.
    words=" ".join(selected).split()
    return [" ".join(words[i:i+6]) for i in range(0,len(words),6)]

def eligible(item):
    return not item.get("match_result") and bool(item.get("photo_used")) and len(narration(item))>=2

def frame(cover, chunk, item, index, count, destination, brand):
    # Raw athlete photography, not a still of the feed card.
    with Image.open(cover) as src:
        photo=ImageOps.exif_transpose(src).convert("RGB")
        zoom=1.0+0.035*(index%4)
        w,h=photo.size
        if zoom>1:
            nw,nh=int(w/zoom),int(h/zoom)
            x=(w-nw)//2; y=int((h-nh)*0.25)
            photo=photo.crop((x,y,x+nw,y+nh))
        im=ImageOps.fit(photo,(1080,1920),centering=(0.5,0.30)).convert("RGBA")
    overlay=Image.new("RGBA",im.size)
    d=ImageDraw.Draw(overlay)
    for y in range(1920):
        alpha=int(220*max(0,1-y/430,(y-730)/1190))
        if alpha: d.line((0,y,1080,y),fill=(7,13,21,alpha))
    im=Image.alpha_composite(im,overlay).convert("RGB")
    d=ImageDraw.Draw(im)
    accent=(208,249,92)
    d.rectangle((56,110,70,168),fill=accent)
    d.text((88,110),brand,font=font(37),fill="white")
    d.text((88,165),str(item.get("sport","DEPORTES")).upper()+"  /  NOTICIAS",font=font(26),fill=accent)
    # Large, central burned-in captions; keep clear of platform controls.
    size=76
    while size>42:
        lines=_wrap(d,chunk.upper().split(),font(size),820)
        if len(lines)<=3: break
        size-=2
    lines=_wrap(d,chunk.upper().split(),font(size),820)
    line_h=size+12
    y=int(1190-len(lines)*line_h/2)
    for line in lines:
        d.text((485,y),line,font=font(size),fill="white",stroke_width=4,stroke_fill=(8,13,20),anchor="mt")
        y+=line_h
    d.rectangle((60,1480,910,1488),fill=(65,77,79))
    d.rectangle((60,1480,60+850*(index+1)/count,1488),fill=accent)
    d.text((60,1520),("FUENTE: "+str(item.get("source","")).upper())[:55],font=font(24),fill="white")
    im.save(destination)

def command(args,timeout=90,input_text=None):
    return subprocess.run(args,input=input_text,text=True,check=True,capture_output=True,timeout=timeout).stdout

def voice(text,destination):
    model=os.getenv("PIPER_MODEL","")
    if not model or not Path(model).is_file() or not shutil.which("piper"):
        raise RuntimeError("Local Spanish voice unavailable")
    command(["piper","--model",model,"--output_file",str(destination)],input_text=text)

def validate_video(path):
    """Reject missing, silent or truncated audio and static video before upload."""
    probe=json.loads(command(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(path)]))
    streams=probe.get("streams",[])
    video=next((x for x in streams if x.get("codec_type")=="video"),{})
    audio=next((x for x in streams if x.get("codec_type")=="audio"),{})
    duration=float(probe["format"]["duration"])
    if (video.get("width"),video.get("height"))!=(1080,1920) or audio.get("codec_name")!="aac":
        raise ValueError("Reel missing vertical video or AAC narration")
    if float(audio.get("duration") or 0)<duration-0.6 or not 3<=duration<=90:
        raise ValueError("Reel audio is truncated")
    result=subprocess.run(["ffmpeg","-hide_banner","-i",str(path),"-vn","-af","volumedetect","-f","null","-"],capture_output=True,text=True,check=True,timeout=90)
    match=re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB",result.stderr)
    if not match or float(match.group(1)) < -40:
        raise ValueError("Reel narration is silent")
    # Scene subtitles must visibly change. Compare decoded frames in the
    # caption band, not just file size or the existence of an audio track.
    with tempfile.TemporaryDirectory() as tmp:
        for i,t in enumerate((duration*0.15,duration*0.55,duration*0.85)):
            command(["ffmpeg","-y","-v","error","-ss",str(t),"-i",str(path),"-frames:v","1","-vf","crop=900:400:35:980,scale=225:100",str(Path(tmp)/f"{i}.png")])
        from PIL import ImageChops, ImageStat
        with Image.open(Path(tmp)/"0.png") as a, Image.open(Path(tmp)/"1.png") as b, Image.open(Path(tmp)/"2.png") as c:
            if max(sum(ImageStat.Stat(ImageChops.difference(a.convert("RGB"),x.convert("RGB"))).mean)/3 for x in (b,c))<2:
                raise ValueError("Reel caption scenes do not change")
    return {"version":2,"duration":round(duration,2),"mean_db":float(match.group(1))}

def render(item,cover,destination,brand):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg unavailable")
    chunks=narration(item)
    if len(chunks)<2: raise ValueError("Insufficient narration")
    destination=Path(destination).resolve()
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        clips=[]
        for i,chunk in enumerate(chunks):
            png=root/f"{i}.png"; wav=root/f"{i}.wav"; mp4=root/f"{i}.mp4"
            frame(cover,chunk,item,i,len(chunks),png,brand)
            voice(chunk,wav)
            duration=float(command(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(wav)]).strip())+0.18
            if not 0.4<=duration<=20: raise ValueError("Unexpected voice duration")
            frames=max(1,round(duration*30))
            # Subtle camera push on each scene, safe margins for vertical UI.
            vf=f"scale=2160:3840,zoompan=z='min(1+0.00025*on,1.035)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={frames}:s=1080x1920:fps=30,format=yuv420p"
            command(["ffmpeg","-y","-v","error","-i",str(png),"-i",str(wav),"-vf",vf,"-map","0:v:0","-map","1:a:0","-af","loudnorm=I=-16:TP=-1.5:LRA=11,apad","-t",str(duration),"-c:v","libx264","-preset","veryfast","-crf","24","-threads","2","-c:a","aac","-ar","44100","-ac","2","-b:a","128k",str(mp4)])
            clips.append(mp4)
        manifest=root/"clips.txt"
        manifest.write_text("".join(f"file '{p.name}'\n" for p in clips))
        command(["ffmpeg","-y","-v","error","-f","concat","-safe","0","-i",str(manifest),"-c","copy","-movflags","+faststart",str(destination)])
    duration=float(command(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(destination)]).strip())
    if not 3<=duration<=90 or destination.stat().st_size>95_000_000:
        destination.unlink(missing_ok=True)
        raise ValueError("Video outside publishing constraints")
    item["reel_quality"] = validate_video(destination)
    return destination
