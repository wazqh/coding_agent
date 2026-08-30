from __future__ import annotations

from coding_agent.web.auth import LaunchAuth


def test_launch_capability_is_single_use_and_cookie_authorizes_exact_origin() -> None:
    auth = LaunchAuth(host="127.0.0.1:43125", origin="http://127.0.0.1:43125")

    session_token = auth.exchange(
        auth.capability,
        host="127.0.0.1:43125",
        origin="http://127.0.0.1:43125",
    )

    assert session_token is not None
    assert (
        auth.exchange(
            auth.capability,
            host="127.0.0.1:43125",
            origin="http://127.0.0.1:43125",
        )
        is None
    )
    assert auth.authorize(
        session_token,
        host="127.0.0.1:43125",
        origin="http://127.0.0.1:43125",
    )
    assert not auth.authorize(
        session_token,
        host="evil.example",
        origin="http://127.0.0.1:43125",
    )
    assert not auth.authorize(
        session_token,
        host="127.0.0.1:43125",
        origin="http://evil.example",
    )


def test_launch_auth_rejects_wrong_capability_and_allows_one_controller() -> None:
    auth = LaunchAuth(host="127.0.0.1:43125", origin="http://127.0.0.1:43125")
    assert (
        auth.exchange(
            "wrong-token",
            host="127.0.0.1:43125",
            origin="http://127.0.0.1:43125",
        )
        is None
    )
    token = auth.exchange(
        auth.capability,
        host="127.0.0.1:43125",
        origin="http://127.0.0.1:43125",
    )
    assert token is not None

    assert auth.claim_controller(token) is True
    assert auth.claim_controller(token) is False
    auth.release_controller(token)
    assert auth.claim_controller(token) is True
    auth.revoke()
    assert not auth.authorize(
        token,
        host="127.0.0.1:43125",
        origin="http://127.0.0.1:43125",
    )
