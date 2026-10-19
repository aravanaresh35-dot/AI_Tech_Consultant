#!/usr/bin/env python3
"""Reproducible evaluation runner (offline, deterministic, DEMO mode). Writes reports/eval_results.json.

MEASURED here: pytest pass counts per task, and the rule-based classifier's accuracy on the 56-email dataset.
NOT measured here (need live credentials): Claude draft quality, token usage, cost -> see benchmark_models.py.
"""
import json, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ["task1-knowledge-brain", "task2-inbox-agent", "task3-meeting-to-sow"]
env = {**os.environ, "DEMO_MODE": "true"}
results = {"mode": "DEMO (deterministic, no model calls)", "tasks": {}, "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

for t in TASKS:
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT / t, env=env, capture_output=True, text=True)
    out = p.stdout + p.stderr
    passed = int((re.search(r"(\d+) passed", out) or [0, 0])[1]); failed = int((re.search(r"(\d+) failed", out) or [0, 0])[1])
    err = int((re.search(r"(\d+) error", out) or [0, 0])[1])
    results["tasks"][t] = {"passed": passed, "failed": failed, "errors": err, "pass_rate": round(passed / max(passed + failed + err, 1), 3),
                           "seconds": round(time.perf_counter() - t0, 2)}
    print(f"{t}: {passed} passed, {failed} failed, {err} errors")

sys.path.insert(0, str(ROOT / "shared")); sys.path.insert(0, str(ROOT / "task2-inbox-agent"))
from app.classifier import classify  # noqa: E402

data = json.loads((ROOT / "task2-inbox-agent/data/sample_emails.json").read_text())
wrong = []
for e in data:
    got = classify(e["subject"], e["body"], bool(e.get("previous_conversation")))["category"]
    if got != e["expected_category"]:
        wrong.append({"id": e["id"], "expected": e["expected_category"], "got": got})
results["classification"] = {"classifier": "rule-based keyword (demo path)", "n": len(data), "correct": len(data) - len(wrong),
                             "accuracy": round(1 - len(wrong) / len(data), 3), "misclassified": wrong,
                             "note": "Labels were written by the project author with the dataset; not an independent benchmark."}
results["unavailable"] = {"claude_draft_quality": "needs ANTHROPIC_API_KEY + ANTHROPIC_MODEL", "token_usage": "no live calls made",
                          "estimated_cost": "no live calls made", "model_comparison": "pending - run scripts/benchmark_models.py with two models"}
print(f"classification accuracy: {results['classification']['accuracy']} ({len(data) - len(wrong)}/{len(data)})")
(ROOT / "reports").mkdir(exist_ok=True)
(ROOT / "reports" / "eval_results.json").write_text(json.dumps(results, indent=2))
sys.exit(1 if any(v["failed"] or v["errors"] for v in results["tasks"].values()) else 0)
