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
    accent=(205,255,75)
    im=Image.new("RGB",(1080,1920),(9,15,24))
    has_photo=bool(item.get("photo_used") and not item.get("match_result"))
    if has_photo:
        with Image.open(cover) as src:
            im=ImageOps.fit(ImageOps.exif_transpose(src).convert("RGB"),(1080,1920),centering=(.5,.28))
    overlay=Image.new("RGBA",im.size)
    d=ImageDraw.Draw(overlay)
    for y in range(1920):
        alpha=int(min(245,max(0,185*(1-y/380),245*(y-650)/850)))
        d.line((0,y,1080,y),fill=(5,10,18,alpha))
    im=Image.alpha_composite(im.convert("RGBA"),overlay).convert("RGB")
    d=ImageDraw.Draw(im)
    if not has_photo:
        # Native vertical composition: never embed a square headline card.
        for x in range(-1000,1800,110):
            d.line((x,340,x+700,1040),fill=(20,32,44),width=2)
        d.text((70,360),str(item.get("sport","DEPORTES")).upper(),font=font(100),fill=(38,53,65))
        if item.get("match_result"):
            with Image.open(cover) as src:
                panel=ImageOps.contain(src.convert("RGB"),(860,630))
                im.paste(panel,((940-panel.width)//2,350))
        else:
            d.rectangle((72,650,220,662),fill=accent)
            d.text((72,700),"EN DESARROLLO" if index else "ACTUALIDAD",font=font(44),fill=accent)
    d.rounded_rectangle((65,215,129,279),radius=14,fill=accent)
    d.text((97,247),"CF",font=font(32),fill=(9,15,24),anchor="mm")
    d.text((150,219),brand,font=font(35),fill="white")
    d.text((150,263),str(item.get("sport","DEPORTES")).upper(),font=font(25),fill=accent)
    size=84
    while size>44:
        lines=_wrap(d,chunk.upper().split(),font(size),790)
        if len(lines)<=3: break
        size-=2
    lines=_wrap(d,chunk.upper().split(),font(size),790)
    y=1120-len(lines)*(size+10)//2
    for i,line in enumerate(lines):
        d.text((72,y),line,font=font(size),fill=accent if i==0 else "white",stroke_width=2,stroke_fill=(5,10,18))
        y+=size+10
    d.rectangle((72,1350,870,1355),fill=(55,68,77))
    d.rectangle((72,1350,72+798*(index+1)/count,1355),fill=accent)
    d.text((72,1380),str(item.get("source","")).upper()[:50],font=font(24),fill=(180,195,205))
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
