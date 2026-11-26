"""Reusable vertical video renderer: local TTS, Pillow captions, FFmpeg H.264."""
from pathlib import Path
import os
import asyncio
import json
import re
import shutil
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageOps, ImageFilter
from graphics import font, _wrap
from platform_strategy import video_script, headline

def narration(item):
    # Use the already validated Spanish caption, never generate additional facts.
    raw = video_script(item) if item.get("video_style") == "tiktok" else str(item.get("caption") or item.get("headline") or "")
    text = re.sub(r"https?://\S+|[@#]\w+", "", raw)
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
    # Short caption chunks; narration is synthesized continuously.
    words=" ".join(selected).split()
    # Prefer complete sentence boundaries, preserving every spoken word.
    chunks=[]
    for sentence in re.split(r"(?<=[.!?])\s+", " ".join(words)):
        tokens=sentence.split()
        while len(tokens)>8:
            size=6 if len(tokens)>10 else len(tokens)//2
            chunks.append(" ".join(tokens[:size]))
            tokens=tokens[size:]
        if tokens:
            chunks.append(" ".join(tokens))
    return chunks

def eligible(item):
    return not item.get("match_result") and bool(item.get("photo_used")) and len(narration(item))>=2

def frame(cover, chunk, item, index, count, destination, brand):
    # Never crop a square editorial card into a vertical video.
    with Image.open(cover) as src:
        photo=ImageOps.exif_transpose(src).convert("RGB")
        if item.get("photo_used") and not item.get("match_result"):
            im=ImageOps.fit(photo,(1080,1920),centering=(0.5,0.30)).convert("RGBA")
        else:
            im=Image.new("RGBA",(1080,1920),(12,22,37,255))
            panel=ImageOps.contain(photo,(840,720))
            im.paste(panel,((960-panel.width)//2,250+(720-panel.height)//2))
    overlay=Image.new("RGBA",im.size)
    d=ImageDraw.Draw(overlay)
    for y in range(1920):
        alpha=int(220*max(0,1-y/430,(y-730)/1190))
        if alpha: d.line((0,y,1080,y),fill=(7,13,21,alpha))
    im=Image.alpha_composite(im,overlay).convert("RGB")
    d=ImageDraw.Draw(im)
    accent=(208,249,92)
    d.rectangle((56,190,70,248),fill=accent)
    d.text((88,190),brand,font=font(37),fill="white")
    d.text((88,245),str(item.get("sport","DEPORTES")).upper()+"  /  NOTICIAS",font=font(26),fill=accent)
    d.rounded_rectangle((54,1000,900,1330),radius=28,fill=(10,18,30),outline=(47,65,79),width=2)
    d.rectangle((78,1030,138,1037),fill=accent)
    if item.get("video_style") == "tiktok":
        d.text((150,1020),"EL DATO" if index==0 else "EN CONTEXTO",font=font(23),fill=accent)
    # Large, central burned-in captions; keep clear of platform controls.
    size=68 if item.get("video_style")=="tiktok" and index==0 else 62
    while size>42:
        lines=_wrap(d,chunk.upper().split(),font(size),760)
        if len(lines)<=3: break
        size-=2
    lines=_wrap(d,chunk.upper().split(),font(size),760)
    line_h=size+12
    y=int(1170-len(lines)*line_h/2)
    for line in lines:
        d.text((477,y),line,font=font(size),fill=accent if index==0 else "white",stroke_width=1,stroke_fill=(8,13,20),anchor="mt")
        y+=line_h
    d.rectangle((60,1390,910,1398),fill=(65,77,79))
    d.rectangle((60,1390,60+850*(index+1)/count,1398),fill=accent)
    d.text((60,1420),("FUENTE: "+str(item.get("source","")).upper())[:55],font=font(24),fill="white")
    im.save(destination)

def command(args,timeout=90,input_text=None):
    return subprocess.run(args,input=input_text,text=True,check=True,capture_output=True,timeout=timeout).stdout

def spoken_text(text):
    """Latin American pronunciation overrides; never modify displayed captions."""
    names = {"PSV": "pe ese ve", "VAR": "var", "FIFA": "fifa", "UEFA": "uefa", "FC": "efe ce"}
    return re.sub(r"\b(?:PSV|VAR|FIFA|UEFA|FC)\b", lambda m: names[m.group(0)], text)


def voice(text,destination):
    """Prefer neural Latin American narration; local Piper is the fallback."""
    text = spoken_text(text)
    async def neural():
        import edge_tts
        audio = destination.with_suffix(".mp3")
        offsets = []
        speech = edge_tts.Communicate(text, os.getenv("REEL_VOICE", "es-MX-JorgeNeural"), rate="+20%", boundary="WordBoundary")
        with audio.open("wb") as f:
            async for event in speech.stream():
                if event["type"] == "audio":
                    f.write(event["data"])
                elif event["type"] == "WordBoundary":
                    offsets.append(event["offset"] / 10_000_000)
        return audio, offsets
    try:
        audio, offsets = asyncio.run(asyncio.wait_for(neural(), timeout=45))
        command(["ffmpeg","-y","-v","error","-i",str(audio),"-af","silenceremove=stop_periods=-1:stop_duration=0.45:stop_threshold=-45dB:stop_silence=0.18",str(destination)])
        return []  # Silence compression changes word offsets; use proportional scene timing.
    except Exception as exc:
        print(f"[REEL] Neural voice unavailable ({type(exc).__name__}); using local voice")
    model=os.getenv("PIPER_MODEL","")
    if not model or not Path(model).is_file() or not shutil.which("piper"):
        raise RuntimeError("Local Spanish voice unavailable")
    command(["piper","--model",model,"--output_file",str(destination)],input_text=text)
    accelerated=destination.with_name("faster.wav")
    command(["ffmpeg","-y","-v","error","-i",str(destination),"-af","atempo=1.18,silenceremove=stop_periods=-1:stop_duration=0.45:stop_threshold=-45dB:stop_silence=0.18",str(accelerated)])
    accelerated.replace(destination)
    return []

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
        wav=root/"narration.wav"
        offsets=voice(" ".join(chunks),wav) or []
        duration=float(command(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(wav)]).strip())
        if not 3<=duration<=90: raise ValueError("Unexpected voice duration")
        word_counts=[len(chunk.split()) for chunk in chunks]
        total=sum(word_counts)
        boundaries=[0.0]
        consumed=0
        for count in word_counts[:-1]:
            consumed+=count
            boundaries.append(offsets[consumed] if len(offsets)==total else duration*consumed/total)
        boundaries.append(duration)
        if any(b<=a for a,b in zip(boundaries,boundaries[1:])):
            boundaries=[duration*sum(word_counts[:i])/total for i in range(len(chunks)+1)]
        frame_bounds=[round(t*30) for t in boundaries]
        for i,chunk in enumerate(chunks):
            png=root/f"{i}.png"; mp4=root/f"{i}.mp4"
            frame(cover,chunk,item,i,len(chunks),png,brand)
            frames=max(1,frame_bounds[i+1]-frame_bounds[i])
            vf=f"scale=2160:3840,zoompan=z='min(1+0.00025*on,1.035)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={frames}:s=1080x1920:fps=30,format=yuv420p"
            command(["ffmpeg","-y","-v","error","-i",str(png),"-vf",vf,"-frames:v",str(frames),"-an","-c:v","libx264","-preset","veryfast","-crf","24","-threads","2",str(mp4)])
            clips.append(mp4)
        manifest=root/"clips.txt"
        manifest.write_text("".join(f"file '{p.name}'\n" for p in clips))
        command(["ffmpeg","-y","-v","error","-f","concat","-safe","0","-i",str(manifest),"-i",str(wav),"-map","0:v:0","-map","1:a:0","-c:v","copy","-af","loudnorm=I=-16:TP=-1.5:LRA=11","-c:a","aac","-ar","44100","-ac","2","-b:a","128k","-movflags","+faststart",str(destination)])
    duration=float(command(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(destination)]).strip())
    if not 3<=duration<=90 or destination.stat().st_size>95_000_000:
        destination.unlink(missing_ok=True)
        raise ValueError("Video outside publishing constraints")
    item["reel_quality"] = validate_video(destination)
    return destination
