from __future__ import annotations

from queue import Queue
from threading import Thread

from coding_agent.safety.approval import ApprovalDecision, ApprovalRequest
from coding_agent.web.approval import ApprovalBroker


def _request() -> ApprovalRequest:
    return ApprovalRequest(
        action="run_command",
        subject="pytest -q",
        summary="run the test suite",
    )


def test_approval_broker_resolves_one_pending_request_once() -> None:
    published: Queue[str] = Queue()
    result: Queue[ApprovalDecision] = Queue()
    broker = ApprovalBroker(on_request=lambda approval_id, _request: published.put(approval_id))
    worker = Thread(target=lambda: result.put(broker.request(_request())))

    worker.start()
    approval_id = published.get(timeout=1)

    assert broker.resolve(approval_id, ApprovalDecision.ALLOW_SESSION) is True
    assert broker.resolve(approval_id, ApprovalDecision.DENY) is False
    worker.join(timeout=1)
    assert worker.is_alive() is False
    assert result.get_nowait() is ApprovalDecision.ALLOW_SESSION
    assert broker.pending_ids == ()


def test_approval_broker_cancel_and_close_deny_waiters() -> None:
    published: Queue[str] = Queue()
    results: Queue[ApprovalDecision] = Queue()
    broker = ApprovalBroker(on_request=lambda approval_id, _request: published.put(approval_id))
    workers = [Thread(target=lambda: results.put(broker.request(_request()))) for _ in range(2)]
    for worker in workers:
        worker.start()
    published.get(timeout=1)
    published.get(timeout=1)

    assert broker.cancel_all() == 2
    for worker in workers:
        worker.join(timeout=1)
    assert [results.get_nowait(), results.get_nowait()] == [
        ApprovalDecision.DENY,
        ApprovalDecision.DENY,
    ]

    broker.close()
    assert broker.request(_request()) is ApprovalDecision.DENY
    assert broker.resolve("missing", ApprovalDecision.ALLOW_ONCE) is False


def test_approval_broker_denies_when_request_publisher_fails() -> None:
    def fail(_approval_id: str, _request: ApprovalRequest) -> None:
        raise RuntimeError("client disconnected")

    broker = ApprovalBroker(on_request=fail)

    assert broker.request(_request()) is ApprovalDecision.DENY
    assert broker.pending_ids == ()
