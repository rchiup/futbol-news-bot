"""Cross-publish original vertical videos via Buffer's official GraphQL API."""
import json
import os
import requests

def configured():
    return bool(os.getenv("BUFFER_API_KEY","").strip() and os.getenv("BUFFER_TIKTOK_CHANNEL_ID","").strip())

def submit_tiktok(video_url, caption, session=requests):
    key = os.environ["BUFFER_API_KEY"].strip()
    channel = os.environ["BUFFER_TIKTOK_CHANNEL_ID"].strip()
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

def crosspost(item, video_url, caption, session=requests):
    if not configured() or item.get("buffer_tiktok_status"):
        return
    # Keep platform state independent of Instagram. Uncertain network errors
    # require inspection, rather than automatically creating duplicates.
    item["buffer_tiktok_status"] = "submitting"
    try:
        result = submit_tiktok(video_url, caption, session=session)
        item["buffer_tiktok_id"] = result["id"]
        item["buffer_tiktok_status"] = result["status"]
        print("[BUFFER] TikTok accepted post "+result["id"])
    except Exception as exc:
        item["buffer_tiktok_status"] = "check_required"
        item["buffer_tiktok_error"] = type(exc).__name__
        print("[BUFFER] TikTok submission unconfirmed: "+type(exc).__name__)
