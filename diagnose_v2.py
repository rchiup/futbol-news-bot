"""Write redacted results of unit tests to a GitHub-readable JSON report."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

result = subprocess.run(
    ["python", "-m", "unittest", "discover", "-s", "tests", "-v"],
    capture_output=True, text=True, timeout=240,
)
output = Path("data/health_v2.json")
output.parent.mkdir(parents=True, exist_ok=True)
content = {
    "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    "tests_ok": result.returncode == 0,
    "exit_code": result.returncode,
    "output_tail": (result.stdout + "\n" + result.stderr)[-3000:],
}
output.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("Tests:", "PASS" if content["tests_ok"] else "FAIL")
if result.returncode:
    print(content["output_tail"])
raise SystemExit(result.returncode)
