from __future__ import annotations

import importlib
from functools import cache
from typing import Protocol, cast


class _TokenEncoder(Protocol):
    def encode(self, text: str) -> list[int]: ...


@cache
def _load_encoding() -> _TokenEncoder | None:
    """Load the optional tokenizer once without making it a runtime requirement."""
    try:
        module = importlib.import_module("tiktoken")
        return cast(_TokenEncoder, module.get_encoding("cl100k_base"))
    except Exception:
        # A first run may be offline before tiktoken has cached its vocabulary.
        return None


def count_tokens(text: str) -> int:
    encoder = _load_encoding()
    if encoder is None:
        return max(1, len(text) // 4)
    return len(encoder.encode(text))
