from __future__ import annotations

import pytest

import coding_agent.tokens as tokens


def test_token_count_falls_back_when_encoding_cannot_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tokens._load_encoding.cache_clear()

    def fail_import(_name: str) -> None:
        raise RuntimeError("offline")

    monkeypatch.setattr(tokens.importlib, "import_module", fail_import)
    assert tokens.count_tokens("abcdefgh") == 2
    assert tokens.count_tokens("abcd") == 1
    tokens._load_encoding.cache_clear()
