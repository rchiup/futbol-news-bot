"""Fair, FREE-ONLY comparison: same real RSS source, one call/provider.

This does not publish, modify the queue, or pretend a readability heuristic
checks facts. Human editorial review is still required for real accuracy.
"""
from __future__ import annotations
import json
import time
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
                    started = time.monotonic()
                    data = free_llm.one(
                        name, messages, session=requests,
                        validator=lambda result: editorial.validate_llm_copy(result, source),
                        usage_path=ROOT / "data" / "llm_free_usage.json",
                    )
                    entry.update({
                        "status": "ok",
                        "latency_ms": int((time.monotonic() - started) * 1000),
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
    # Only rank models after several independent samples; readability is
    # heuristic and human review is needed before making editorial changes.
    rank = {}
    for name in free_llm.KEYS:
        samples = [
            row for run in history[-60:]
            for row in run.get("results", [])
            if row.get("provider") == name
        ]
        good = [x for x in samples if x.get("status") == "ok"]
        if good:
            mean_quality = round(sum(x["readability_score"] for x in good)/len(good), 1)
            mean_latency = round(sum(x.get("latency_ms", 0) for x in good)/len(good))
        else:
            mean_quality, mean_latency = None, None
        rank[name] = {
            "sample_count": len(samples), "successful_samples": len(good),
            "readability_avg": mean_quality, "latency_avg_ms": mean_latency,
            "conclusion": "early_sample" if len(samples) < 3 else "can_compare",
        }
    (ROOT / "data" / "llm_ranking.json").write_text(
        json.dumps({"checked_at_utc": now, "providers": rank,
                    "warning": "Readability scores are not factual accuracy; review copies manually."},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    HISTORY.write_text(json.dumps(history[-60:], indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    print("Free-only LLM benchmark:", report["status"],
          {r["provider"]: r["status"] for r in report["results"]})


if __name__ == "__main__":
    run()
