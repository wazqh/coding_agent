from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CORE_THRESHOLDS = {
    "src/coding_agent/controller.py": 95.0,
    "src/coding_agent/memory.py": 95.0,
}
SAFETY_PREFIX = "src/coding_agent/safety/"
SAFETY_THRESHOLD = 95.0


def _points(summary: dict[str, Any]) -> tuple[int, int]:
    covered = int(summary.get("covered_lines", 0)) + int(summary.get("covered_branches", 0))
    possible = int(summary.get("num_statements", 0)) + int(summary.get("num_branches", 0))
    return covered, possible


def evaluate(payload: dict[str, Any]) -> tuple[list[tuple[str, float]], list[str]]:
    files = {
        name.replace("\\", "/"): value for name, value in dict(payload.get("files", {})).items()
    }
    results: list[tuple[str, float]] = []
    failures: list[str] = []
    for name, threshold in CORE_THRESHOLDS.items():
        if name not in files:
            failures.append(f"coverage data is missing {name}")
            continue
        covered, possible = _points(files[name]["summary"])
        percent = covered * 100 / possible if possible else 100.0
        results.append((name, percent))
        if percent < threshold:
            failures.append(f"{name} coverage {percent:.2f}% is below {threshold:.0f}%")

    safety_covered = 0
    safety_possible = 0
    for name, value in files.items():
        if name.startswith(SAFETY_PREFIX):
            covered, possible = _points(value["summary"])
            safety_covered += covered
            safety_possible += possible
    safety_percent = safety_covered * 100 / safety_possible if safety_possible else 0.0
    results.append(("coding_agent.safety", safety_percent))
    if safety_percent < SAFETY_THRESHOLD:
        failures.append(
            f"coding_agent.safety coverage {safety_percent:.2f}% is below {SAFETY_THRESHOLD:.0f}%"
        )
    return results, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce coverage for high-risk modules.")
    parser.add_argument("coverage_json", type=Path, nargs="?", default=Path("coverage.json"))
    args = parser.parse_args()
    try:
        payload = json.loads(args.coverage_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"cannot read coverage data: {exc}")
    results, failures = evaluate(payload)
    for name, percent in results:
        print(f"{name}: {percent:.2f}%")
    for failure in failures:
        print(f"error: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
