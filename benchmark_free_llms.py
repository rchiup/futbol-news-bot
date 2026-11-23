"""Fair, FREE-ONLY comparison: same real RSS source, one call/provider.

This does not publish, modify the queue, or pretend a readability heuristic
checks facts. Human editorial review is still required for real accuracy.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import requests
import editorial
import free_llm

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "data" / "llm_benchmark.json"
HISTORY = ROOT / "data" / "llm_benchmark_history.json"


def choose_story():
    queue = editorial.load_queue()
    candidates = [
        row for row in queue
        if row.get("title") and len(str(row.get("description", ""))) >= 65
        and row.get("published_at")
    ]
    candidates.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return candidates[0] if candidates else None


def run():
    now = datetime.now(timezone.utc).isoformat()
    source = choose_story()
    providers = free_llm.providers()
    report = {"checked_at_utc": now, "method": "same dated RSS title and summary",
              "readability_is_not_fact_checking": True,
              "configured_free_providers": providers, "results": []}
    if not source:
        report["status"] = "no_suitable_source"
    else:
        messages = editorial.ai_messages(source)
        report["source_title"] = source["title"]
        report["sport"] = source.get("sport", "FUTBOL")
        for name in free_llm.KEYS:
            entry = {"provider": name, "model": free_llm.MODELS[name]}
            if name not in providers:
                entry["status"] = "not_configured"
            else:
                try:
                    data = free_llm.one(
                        name, messages, session=requests,
                        validator=lambda result: editorial.validate_llm_copy(result, source),
                        usage_path=ROOT / "data" / "llm_free_usage.json",
                    )
                    entry.update({
                        "status": "ok",
                        "headline": data["headline"], "caption": data["caption"],
                        "readability_score": free_llm.score_text(data),
                    })
                except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                    entry.update({"status": "failed", "reason": free_llm.safe_error(exc)})
            report["results"].append(entry)
        report["status"] = "complete"
    report["usage_summary"] = free_llm.summary(ROOT / "data" / "llm_free_usage.json")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    try:
        history = json.loads(HISTORY.read_text(encoding="utf-8"))
        if not isinstance(history, list):
            history = []
    except (OSError, ValueError):
        history = []
    history.append(report)
    HISTORY.write_text(json.dumps(history[-60:], indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    print("Free-only LLM benchmark:", report["status"],
          {r["provider"]: r["status"] for r in report["results"]})


if __name__ == "__main__":
    run()
