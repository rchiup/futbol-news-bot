"""Free-only sports-news LLM router. Never uses paid OpenAI or paid models.

OpenRouter always routes to openrouter/free. Gemini and Cerebras additionally
require confirmation that their projects are on the unbilled FREE plan.
The local request caps protect free quotas; hitting one skips that provider.
"""
from __future__ import annotations
import json, os, re, time
from pathlib import Path
from datetime import datetime, timezone
import requests

ROOT = Path(__file__).resolve().parent
USAGE = ROOT / "data" / "llm_free_usage.json"
KEYS = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY",
        "cerebras": "CEREBRAS_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
CAPS = {"groq": 75, "gemini": 20, "cerebras": 35, "openrouter": 40}
MODELS = {"groq": "openai/gpt-oss-120b",
          "gemini": "gemini-3.1-flash-lite",
          "cerebras": "gpt-oss-120b", "openrouter": "openrouter/free"}
ENDPOINTS = {"groq": "https://api.groq.com/openai/v1/chat/completions",
             "cerebras": "https://api.cerebras.ai/v1/chat/completions",
             "openrouter": "https://openrouter.ai/api/v1/chat/completions"}


def providers(env=None):
    env = os.environ if env is None else env
    wanted = env.get("FREE_LLM_ORDER", "groq,gemini,cerebras,openrouter").split(",")
    result = []
    for raw in wanted:
        name = raw.strip().lower()
        if name not in KEYS or name in result or not env.get(KEYS[name], "").strip():
            continue
        if name in ("gemini", "cerebras") and env.get(
                name.upper() + "_FREE_TIER_CONFIRMED", "").lower() != "true":
            continue
        if name == "groq" and env.get("GROQ_FREE_TIER_CONFIRMED", "true").lower() != "true":
            continue
        result.append(name)
    return result


def state(path=USAGE):
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        result = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        result = {}
    if not isinstance(result, dict) or result.get("date_utc") != today:
        return {"date_utc": today, "providers": {}, "last_success": None}
    return result


def save(data, path=USAGE):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def unfence(raw):
    if not isinstance(raw, str):
        raise ValueError("Non-text LLM response")
    raw = raw.strip()
    if raw.startswith(chr(96)*3):
        raw = re.sub(r"^" + chr(96)*3 + r"(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(chr(96)*3 + r"\s*$", "", raw)
    data = json.loads(raw.strip())
    if not isinstance(data, dict):
        raise ValueError("Not an LLM JSON object")
    return data


def score_text(data):
    """Readability heuristic only, not independent fact checking."""
    h = str(data.get("headline", ""))
    c = str(data.get("caption", ""))
    score = 100
    if not 25 <= len(h) <= 75: score -= 15
    if not 45 <= len(c) <= 360: score -= 15
    if len(h.split()) > 13: score -= 10
    if any(s in h.lower() for s in ("sin rebote", "da que hablar", "medita su futuro")):
        score -= 20
    if "http" in c.lower() or "fuente:" in c.lower(): score -= 20
    return max(0, score)


def safe_error(e):
    if isinstance(e, requests.HTTPError):
        code = getattr(getattr(e, "response", None), "status_code", None)
        return "http_" + str(code) if isinstance(code, int) else "http_error"
    if isinstance(e, requests.Timeout): return "timeout"
    if isinstance(e, requests.ConnectionError): return "connection"
    return "invalid_output"


def ask_one(name, messages, session=requests, env=None):
    env = os.environ if env is None else env
    key = env[KEYS[name]].strip()
    model = MODELS[name]  # Fixed free-only model selection.
    if name == "gemini":
        endpoint = ("https://generativelanguage.googleapis.com/v1beta/models/"
                    + model + ":generateContent")
        headers = {"x-goog-api-key": key}
        payload = {
            "systemInstruction": {"parts": [{"text": messages[0]["content"]}]},
            "contents": [{"role": "user", "parts": [{"text": messages[1]["content"]}]}],
            "generationConfig": {"temperature": 0.35, "maxOutputTokens": 1600,
                                 "responseMimeType": "application/json"},
        }
    else:
        endpoint = ENDPOINTS[name]
        headers = {"Authorization": "Bearer " + key}
        payload = {"model": model, "temperature": 0.35, "messages": messages}
        if name == "groq":
            payload["response_format"] = {"type": "json_object"}
        if name == "cerebras":
            payload["max_completion_tokens"] = 800
    response = session.post(endpoint, headers=headers, json=payload, timeout=38)
    response.raise_for_status()
    data = response.json()
    if name == "gemini":
        raw = "".join(p.get("text", "")
                      for candidate in data.get("candidates", [])
                      for p in candidate.get("content", {}).get("parts", []))
    else:
        raw = data["choices"][0]["message"]["content"]
    return unfence(raw)


def one(name, messages, session=requests, env=None, validator=None,
        usage_path=None):
    env = os.environ if env is None else env
    if name not in providers(env):
        raise ValueError("Free-tier provider is not configured")
    path = Path(usage_path) if usage_path else USAGE
    stats = state(path)
    values = stats["providers"].setdefault(
        name, {"attempts": 0, "success": 0, "failures": 0,
               "latencies_ms": [], "quality": []})
    if values["attempts"] >= CAPS[name]:
        raise ValueError("Local free-tier daily limit")
    if values.get("blocked_until_utc", 0) > time.time():
        raise ValueError("Provider temporarily unavailable; respecting retry cooldown")
    values["attempts"] += 1
    save(stats, path)  # Failed requests also consume a provider quota.
    start = time.monotonic()
    try:
        data = ask_one(name, messages, session=session, env=env)
        if validator:
            data = validator(data)
        values["success"] += 1
        values["latencies_ms"] = (values["latencies_ms"] +
                                 [int((time.monotonic()-start)*1000)])[-30:]
        values["quality"] = (values["quality"] + [score_text(data)])[-30:]
        stats["last_success"] = name
        return data
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        values["failures"] += 1
        values["last_error"] = safe_error(exc)  # Never leak prompts/tokens.
        if isinstance(exc, requests.HTTPError):
            response = getattr(exc, "response", None)
            code = getattr(response, "status_code", None)
            if code in (401, 403, 429):
                # Do not burn the remaining daily quota retrying unusable keys.
                # The state is persisted across runs when the workflow commits it.
                cooldown = 86400 if code in (401, 403) else 3600
                retry = getattr(response, "headers", {}).get("Retry-After", "")
                if code == 429 and str(retry).strip().isdigit():
                    cooldown = max(60, min(86400, int(retry)))
                values["blocked_until_utc"] = int(time.time()) + cooldown
        raise
    finally:
        save(stats, path)


def generate(messages, session=requests, env=None, validator=None,
             usage_path=None):
    options = providers(env)
    if not options:
        return None
    errors = []
    for name in options:
        try:
            return one(name, messages, session=session, env=env,
                       validator=validator, usage_path=usage_path), name
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            errors.append(name + ":" + safe_error(exc))
    # Never use a paid service as rescue.
    raise ValueError("Free LLMs unavailable: " + ", ".join(errors))


def summary(usage_path=None):
    data = state(Path(usage_path) if usage_path else USAGE)
    out = {"date_utc": data["date_utc"], "last_success": data.get("last_success"),
           "providers": {}}
    for name, values in data["providers"].items():
        times = values.get("latencies_ms", [])
        qualities = values.get("quality", [])
        out["providers"][name] = {
            "attempts": values.get("attempts", 0),
            "success": values.get("success", 0),
            "failures": values.get("failures", 0),
            "avg_latency_ms": round(sum(times)/len(times)) if times else None,
            "avg_readability": round(sum(qualities)/len(qualities), 1) if qualities else None,
            "last_error": values.get("last_error"),
        }
    return out
