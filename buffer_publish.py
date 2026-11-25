"""Cross-publish original vertical videos via Buffer's official GraphQL API."""
import json
import os
import requests

_resolved_channel = None

def configured():
    return bool(os.getenv("BUFFER_API_KEY","").strip())

def graphql(query, session=requests):
    key = os.environ["BUFFER_API_KEY"].strip()
    response = session.post("https://api.buffer.com", json={"query":query},
        headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"}, timeout=45)
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        messages = [str(x.get("message", ""))[:160] for x in payload["errors"]]
        raise RuntimeError("Buffer GraphQL: " + "; ".join(messages))
    return payload.get("data") or {}

def resolve_channel(session=requests):
    global _resolved_channel
    explicit = os.getenv("BUFFER_TIKTOK_CHANNEL_ID","").strip()
    if explicit:
        return explicit
    if _resolved_channel:
        return _resolved_channel
    account = graphql("query { account { organizations { id } } }", session)
    expected = os.getenv("BUFFER_TIKTOK_USERNAME","chaofelicevich").strip().lstrip("@").lower()
    channels = []
    for org in (account.get("account") or {}).get("organizations", []):
        query = "query { channels(input: { organizationId: %s }) { id name displayName service isQueuePaused isDisconnected isLocked } }" % json.dumps(org["id"])
        channels.extend(graphql(query, session).get("channels") or [])
    matches = [c for c in channels if c.get("service","").lower()=="tiktok" and
               c.get("name","").strip().lstrip("@").lower()==expected and
               not any(c.get(k) for k in ("isQueuePaused","isDisconnected","isLocked"))]
    if len(matches)!=1:
        print("[BUFFER] Expected TikTok channel @"+expected+" not uniquely available")
        return None
    _resolved_channel = matches[0]["id"]
    print("[BUFFER] Verified TikTok channel @"+expected)
    return _resolved_channel

def submit_tiktok(video_url, caption, session=requests, channel=None):
    key = os.environ["BUFFER_API_KEY"].strip()
    channel = channel or resolve_channel(session)
    if not key or not channel or not video_url.startswith("https://"):
        raise ValueError("Buffer credentials or HTTPS video missing")
    # Only publish to the explicitly configured channel. Buffer handles OAuth.
    literal = lambda v: json.dumps(v, ensure_ascii=False)
    query = """mutation {
      createPost(input: {
        text: %s
        channelId: %s
        schedulingType: automatic
        mode: shareNow
        aiAssisted: true
        needsApproval: false
        metadata: { tiktok: { isAiGenerated: true } }
        assets: [{video: {url: %s}}]
      }) {
        ... on PostActionSuccess { post { id status } }
        ... on MutationError { message }
      }
    }""" % (literal(caption[:2100]), literal(channel), literal(video_url))
    response = session.post("https://api.buffer.com", json={"query":query},
        headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"}, timeout=45)
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError("Buffer GraphQL rejected request")
    result = (payload.get("data") or {}).get("createPost") or {}
    post = result.get("post") or {}
    if not post.get("id"):
        raise RuntimeError("Buffer did not accept the TikTok post")
    return {"id":str(post["id"]),"status":str(post.get("status") or "accepted")}

def buffer_tiktok(item, video_url, caption, session=requests, persist=None):
    if not configured() or item.get("buffer_tiktok_status"):
        return
    try:
        channel = resolve_channel(session)
    except Exception as exc:
        print("[BUFFER] Channel discovery failed: "+type(exc).__name__)
        return
    if not channel:
        return
    # Keep platform state independent of Instagram. Uncertain network errors
    # require inspection, rather than automatically creating duplicates.
    item["buffer_tiktok_status"] = "submitting"
    if persist:
        persist()
    try:
        result = submit_tiktok(video_url, caption, session=session, channel=channel)
        item["buffer_tiktok_id"] = result["id"]
        item["buffer_tiktok_status"] = result["status"]
        print("[BUFFER] TikTok accepted post "+result["id"])
    except Exception as exc:
        item["buffer_tiktok_status"] = "check_required"
        item["buffer_tiktok_error"] = type(exc).__name__
        print("[BUFFER] TikTok submission unconfirmed: "+type(exc).__name__)


def recover_original_video(identifier, session=requests):
    """Look up a previously uploaded original; no Instagram re-encoding."""
    from urllib.parse import quote
    cloud = os.environ["CLOUDINARY_CLOUD_NAME"]
    auth = (os.environ["CLOUDINARY_API_KEY"], os.environ["CLOUDINARY_API_SECRET"])
    for public_id in ("football-news-bot/reels/"+identifier, identifier):
        response = session.get("https://api.cloudinary.com/v1_1/"+quote(cloud,safe="")+
            "/resources/video/upload/"+quote(public_id,safe=""), auth=auth, timeout=25)
        if response.status_code == 404:
            continue
        response.raise_for_status()
        data = response.json()
        url = data.get("secure_url","")
        if data.get("public_id")==public_id and url.startswith("https://"):
            return url
    return None

def buffer_youtube(item, video_url, caption, session=requests, persist=None):
    if not configured() or item.get("buffer_youtube_status"):
        return
    channel = os.getenv("BUFFER_YOUTUBE_CHANNEL_ID", "").strip()
    if not channel:
        return
    item["buffer_youtube_status"] = "submitting"
    if persist:
        persist()
    literal = lambda v: json.dumps(v, ensure_ascii=False)
    title = (str(item.get("headline") or "Noticias deportivas")[:91] + " #Shorts")[:100]
    query = """mutation { createPost(input: {
      text: %s channelId: %s schedulingType: automatic mode: shareNow
      aiAssisted: true needsApproval: false
      metadata: { youtube: { title: %s categoryId: "17" madeForKids: false } }
      assets: [{video: {url: %s}}]
    }) { ... on PostActionSuccess { post { id status } } ... on MutationError { message } } }""" % (
        literal(caption[:4900]),literal(channel),literal(title),literal(video_url))
    try:
        data = graphql(query, session)
        post = (data.get("createPost") or {}).get("post") or {}
        if not post.get("id"):
            raise RuntimeError("Buffer rejected YouTube post")
        item["buffer_youtube_id"] = str(post["id"])
        item["buffer_youtube_status"] = str(post.get("status") or "accepted")
        print("[BUFFER] YouTube accepted " + item["buffer_youtube_id"])
    except Exception as exc:
        item["buffer_youtube_status"] = "check_required"
        print("[BUFFER] YouTube unconfirmed: " + type(exc).__name__)

def crosspost(item, video_url, caption, session=requests, persist=None):
    # Keep each platform and provider independent; never retry an ambiguous POST.
    import zernio_publish
    for platform, fallback in (("tiktok", buffer_tiktok), ("youtube", buffer_youtube)):
        if item.get("buffer_"+platform+"_status") or item.get("zernio_"+platform+"_status"):
            continue
        try:
            outcome = zernio_publish.submit(item, platform, video_url, caption, session, persist)
            if outcome == "not_submitted":
                fallback(item, video_url, caption, session, persist)
        except Exception as exc:
            item.setdefault("crosspost_"+platform+"_error", type(exc).__name__)
            item.setdefault("zernio_"+platform+"_status", "check_required")
            print("[CROSSPOST] "+platform+" requires verification: "+type(exc).__name__)
        if persist:
            persist()
