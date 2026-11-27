"""Separate platform pacing and explicit delivery state."""
from datetime import datetime, timedelta, timezone
PLATFORMS=("youtube","tiktok")
TERMINAL_FAILURE={"error","failed","rejected","cancelled"}
def timestamp(value):
    try:
        d=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError,ValueError):
        return None
def pending_platform(item,platform):
    # Unknown or accepted submissions must not be automatically duplicated.
    return not any(item.get(p+"_"+platform+"_status") for p in ("buffer","zernio"))
def due(queue,platform,reference,minutes=15):
    for item in queue:
        stamp=item.get(platform+"_attempt_at")
        if not stamp and any(item.get(p+"_"+platform+"_status") for p in ("buffer","zernio")):
            stamp=item.get("crosspost_attempt_at")
        when=timestamp(stamp)
        if when and reference-timedelta(minutes=minutes)<when<=reference:
            return False
    # A confirmed daily limit is an external quota, not a retryable transient.
    # Probe no more than hourly using the newest known attempt on this platform.
    attempts=[]
    for item in queue:
        stamp=item.get(platform+"_attempt_at")
        if not stamp and any(item.get(p+"_"+platform+"_status") for p in ("buffer","zernio")):
            stamp=item.get("crosspost_attempt_at")
        when=timestamp(stamp)
        if when and when<=reference:
            attempts.append((when,item))
    if attempts:
        when,last=max(attempts,key=lambda pair:pair[0])
        if any(last.get(p+"_"+platform+"_error")=="daily_limit" for p in ("buffer","zernio")) and reference-when<timedelta(hours=1):
            return False
    return True
def safe_existing_video(item):
    return bool(item.get("reel_video_url") and (item.get("reel_quality") or {}).get("version")==2)
