from __future__ import annotations

from evals.run_eval import (
    DEFAULT_CASES,
    RunMetrics,
    _event_metrics,
    load_cases,
    parse_events,
    summarize,
)


def test_eval_manifest_has_five_valid_cases() -> None:
    cases = load_cases(DEFAULT_CASES)
    assert len(cases) == 5
    assert len({case.id for case in cases}) == 5
    assert all(case.fixture.is_dir() and case.verify for case in cases)


def test_event_and_summary_metrics() -> None:
    events = parse_events(
        "\n".join(
            [
                "not json",
                '{"kind":"tool_call","data":{"id":"1","name":"read_file","arguments":{}}}',
                '{"kind":"tool_result","data":{"id":"1","name":"read_file","result":{"ok":false}}}',
                '{"kind":"tool_result","data":{"id":"2","name":"read_file","result":{"ok":true}}}',
                '{"kind":"usage","data":{"total_tokens":12}}',
                '{"kind":"skill","data":{"name":"wrong"}}',
            ]
        )
    )
    values = _event_metrics(events, ("expected",))
    assert values["tool_calls"] == 2
    assert values["tool_successes"] == 1
    assert values["self_corrections"] == 1
    assert values["false_skill_activations"] == 1
    run = RunMetrics(
        case_id="case",
        repetition=1,
        passed=True,
        agent_exit_code=0,
        verification_exit_code=0,
        latency_seconds=2.0,
        tool_calls=2,
        tool_successes=2,
        self_corrections=1,
        total_tokens=12,
        false_skill_activations=0,
        skill_activations=1,
        memory_pollution=0,
        dangerous_command_leaks=0,
    )
    summary = summarize([run])
    assert summary["task_pass_rate"] == 1
    assert summary["tool_success_rate"] == 1
    assert summary["average_latency_seconds"] == 2
