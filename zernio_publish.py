"""Publish to the owner's connected TikTok and YouTube accounts."""
import os
import requests
import publish_cooldowns as cooldown

BASE = "https://zernio.com/api/v1"

def submit(item, platform, url, caption, session=requests, persist=None):
    key = os.getenv("ZERNIO_API_KEY", "").strip()
    if not key or not cooldown.available("zernio") or not url.startswith("https://"):
        return "not_submitted"
    headers = {"Authorization": "Bearer "+key, "Content-Type": "application/json"}
    try:
        response = session.get(BASE+"/accounts", headers=headers, timeout=20)
        cooldown.observe("zernio",response)
        response.raise_for_status()
        accounts = response.json().get("accounts", [])
        expected = os.getenv("ZERNIO_"+platform.upper()+"_ACCOUNT_ID", "").strip()
        candidates = [a for a in accounts if a.get("platform")==platform and a.get("isActive") is True and a.get("_id")]
        if expected:
            candidates = [a for a in candidates if a["_id"]==expected]
        elif platform=="tiktok":
            candidates = [a for a in candidates if str(a.get("username","")).lower().lstrip("@")=="chaofelicevich"]
        else:
            candidates = [a for a in candidates if any("chaofelicevich" in "".join(str(a.get(field,"")).lower().split()).lstrip("@") for field in ("username","displayName","name"))]
        if len(candidates)!=1:
            print("[ZERNIO] No unique verified "+platform+" account")
            return "not_submitted"
    except Exception as exc:
        print("[ZERNIO] Account lookup unavailable: "+type(exc).__name__)
        return "not_submitted"
    entry = {"platform":platform,"accountId":candidates[0]["_id"]}
    body = {"content":caption[:2100 if platform=="tiktok" else 4900],
            "mediaItems":[{"type":"video","url":url}],"platforms":[entry],"publishNow":True}
    if platform=="youtube":
        entry["platformSpecificData"]={"title":(str(item.get("headline") or "Noticias deportivas")[:91]+" #Shorts")[:100],
            "visibility":"public","madeForKids":False,"categoryId":"17"}
    else:
        body["tiktokSettings"]={"privacy_level":"PUBLIC_TO_EVERYONE","allow_comment":True,
            "allow_duet":True,"allow_stitch":True,"content_preview_confirmed":True,"express_consent_given":True}
    field = "zernio_"+platform
    item[field+"_status"]="submitting"
    if persist:
        persist()
    try:
        response=session.post(BASE+"/posts",headers=headers,json=body,timeout=60)
        if response.status_code in (401,403,402,429):
            cooldown.observe("zernio",response)
            item.pop(field+"_status",None)
            print("[ZERNIO] Rejected before acceptance: "+str(response.status_code))
            return "not_submitted"
        cooldown.observe("zernio",response)
        response.raise_for_status()
        post=response.json().get("post") or {}
        if not post.get("_id"):
            raise RuntimeError("No confirmed post id")
        item[field+"_id"]=str(post["_id"])
        result=next((p for p in post.get("platforms",[]) if p.get("platform")==platform),{})
        item[field+"_status"]=str(result.get("status") or post.get("status") or "accepted")
        if result.get("platformPostUrl"):
            item[field+"_url"]=result["platformPostUrl"]
        if item[field+"_status"] in {"failed","error","rejected"}:
            from buffer_publish import classify_error
            detail=result.get("error") or result.get("errorMessage") or post.get("error")
            item[field+"_error"]=classify_error(detail) if detail else "unknown_failure"
        print("[ZERNIO] "+platform+" "+item[field+"_status"]+" "+item[field+"_id"])
        return "submitted"
    except Exception as exc:
        item[field+"_status"]="check_required"
        print("[ZERNIO] "+platform+" submission uncertain: "+type(exc).__name__)
        return "uncertain"


def refresh(item, platform, session=requests):
    field = "zernio_"+platform
    identifier = item.get(field+"_id")
    key = os.getenv("ZERNIO_API_KEY", "").strip()
    if not key or not cooldown.available("zernio") or not identifier or item.get(field+"_status") not in ("uploading","pending","publishing","processing","accepted","scheduled","sending","check_required"):
        return
    try:
        response = session.get(BASE+"/posts/"+str(identifier), headers={"Authorization":"Bearer "+key}, timeout=20)
        cooldown.observe("zernio",response)
        response.raise_for_status()
        post = response.json().get("post") or {}
        result = next((p for p in post.get("platforms",[]) if p.get("platform")==platform),{})
        status = result.get("status") or post.get("status")
        if status:
            item[field+"_status"] = str(status)
        if result.get("platformPostUrl"):
            item[field+"_url"] = result["platformPostUrl"]
    except Exception as exc:
        print("[ZERNIO] Status lookup unavailable: "+type(exc).__name__)
