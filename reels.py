"""Reusable vertical video renderer: local TTS, Pillow captions, FFmpeg H.264."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageOps
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
    return [" ".join(words[i:i+11]) for i in range(0,len(words),11)]

def eligible(item):
    return not item.get("match_result") and bool(item.get("photo_used")) and len(narration(item))>=2

def frame(cover, chunk, item, index, count, destination, brand):
    im=Image.new("RGB",(1080,1920),(8,16,27))
    d=ImageDraw.Draw(im)
    accent=(88,212,234)
    d.rectangle((0,0,1080,12),fill=accent)
    d.text((64,105),brand,font=font(40),fill="white")
    d.text((64,172),str(item.get("sport","DEPORTES")).upper()+"  /  ACTUALIDAD",font=font(27),fill=accent)
    with Image.open(cover) as src:
        pic=ImageOps.contain(src.convert("RGB"),(900,1125))
        im.paste(pic,((1080-pic.width)//2,240))
    d.rounded_rectangle((50,1390,960,1640),radius=24,fill=(21,35,49))
    size=52
    while size>30:
        lines=_wrap(d,chunk.split(),font(size),820)
        if len(lines)<=3: break
        size-=2
    lines=_wrap(d,chunk.split(),font(size),820)
    y=1515-len(lines)*(size+9)/2
    for line in lines:
        d.text((505,y),line,font=font(size),fill="white",anchor="mt")
        y+=size+9
    d.rectangle((64,1685,960,1692),fill=(43,58,71))
    d.rectangle((64,1685,64+896*(index+1)/count,1692),fill=accent)
    source=str(item.get("source") or "").strip()
    if source:
        d.text((64,1720),("FUENTE: "+source.upper())[:70],font=font(22),fill=(170,190,200))
    im.save(destination)

def command(args,timeout=90,input_text=None):
    return subprocess.run(args,input=input_text,text=True,check=True,capture_output=True,timeout=timeout).stdout

def voice(text,destination):
    model=os.getenv("PIPER_MODEL","")
    if not model or not Path(model).is_file() or not shutil.which("piper"):
        raise RuntimeError("Local Spanish voice unavailable")
    command(["piper","--model",model,"--output_file",str(destination)],input_text=text)

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
            command(["ffmpeg","-y","-v","error","-i",str(png),"-i",str(wav),"-vf",vf,"-af","apad","-t",str(duration),"-c:v","libx264","-preset","veryfast","-crf","24","-threads","2","-c:a","aac","-ar","44100","-ac","2","-b:a","128k",str(mp4)])
            clips.append(mp4)
        manifest=root/"clips.txt"
        manifest.write_text("".join(f"file '{p.name}'\n" for p in clips))
        command(["ffmpeg","-y","-v","error","-f","concat","-safe","0","-i",str(manifest),"-c","copy","-movflags","+faststart",str(destination)])
    duration=float(command(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(destination)]).strip())
    if not 3<=duration<=90 or destination.stat().st_size>95_000_000:
        destination.unlink(missing_ok=True)
        raise ValueError("Video outside publishing constraints")
    return destination
