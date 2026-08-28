from __future__ import annotations

from typing import Any

from scripts.check_coverage import evaluate


def _summary(covered: int, possible: int) -> dict[str, int]:
    return {
        "covered_lines": covered,
        "num_statements": possible,
        "covered_branches": 0,
        "num_branches": 0,
    }


def test_high_risk_coverage_gate_accepts_and_rejects() -> None:
    payload: dict[str, Any] = {
        "files": {
            "src\\coding_agent\\controller.py": {"summary": _summary(96, 100)},
            "src/coding_agent/memory.py": {"summary": _summary(100, 100)},
            "src/coding_agent/safety/paths.py": {"summary": _summary(95, 100)},
        }
    }
    results, failures = evaluate(payload)
    assert not failures
    assert dict(results)["coding_agent.safety"] == 95

    payload["files"]["src/coding_agent/memory.py"]["summary"] = _summary(94, 100)
    payload["files"]["src/coding_agent/safety/paths.py"]["summary"] = _summary(50, 100)
    _, failures = evaluate(payload)
    assert any("memory.py" in failure for failure in failures)
    assert any("safety" in failure for failure in failures)
