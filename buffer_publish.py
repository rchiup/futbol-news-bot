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

def crosspost(item, video_url, caption, session=requests):
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
    try:
        result = submit_tiktok(video_url, caption, session=session, channel=channel)
        item["buffer_tiktok_id"] = result["id"]
        item["buffer_tiktok_status"] = result["status"]
        print("[BUFFER] TikTok accepted post "+result["id"])
    except Exception as exc:
        item["buffer_tiktok_status"] = "check_required"
        item["buffer_tiktok_error"] = type(exc).__name__
        print("[BUFFER] TikTok submission unconfirmed: "+type(exc).__name__)
