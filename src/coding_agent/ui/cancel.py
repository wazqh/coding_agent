from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Callable
from importlib import import_module
from types import TracebackType
from typing import Any, TextIO


class EscapeMonitor:
    """Watch Esc without taking over the terminal or its scrollback."""

    def __init__(
        self,
        cancel_event: threading.Event,
        *,
        enabled: Callable[[], bool] | None = None,
        stream: TextIO | None = None,
    ) -> None:
        self.cancel_event = cancel_event
        self.enabled = enabled or (lambda: True)
        self.stream = stream or sys.stdin
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._fd: int | None = None
        self._terminal_state: list[object] | None = None

    def __enter__(self) -> EscapeMonitor:
        if not self.stream.isatty():
            return self
        target: Callable[[], None]
        if os.name == "nt":
            target = self._watch_windows
        else:
            try:
                termios: Any = import_module("termios")
                tty: Any = import_module("tty")

                self._fd = self.stream.fileno()
                self._terminal_state = termios.tcgetattr(self._fd)
                tty.setcbreak(self._fd)
            except (AttributeError, OSError, ValueError):
                self._fd = None
                self._terminal_state = None
                return self
            target = self._watch_posix
        self._thread = threading.Thread(target=target, name="forge-escape-monitor", daemon=True)
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        if self._fd is not None and self._terminal_state is not None:
            try:
                termios: Any = import_module("termios")

                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._terminal_state)
            except (OSError, ValueError):
                pass

    def feed(self, character: str) -> bool:
        if character != "\x1b" or not self.enabled():
            return False
        self.cancel_event.set()
        self._stop.set()
        return True

    def _watch_windows(self) -> None:
        import msvcrt

        while not self._stop.is_set():
            if not self.enabled() or not msvcrt.kbhit():
                time.sleep(0.05)
                continue
            if self.feed(msvcrt.getwch()):
                return

    def _watch_posix(self) -> None:
        import select

        if self._fd is None:
            return
        while not self._stop.is_set():
            if not self.enabled():
                time.sleep(0.05)
                continue
            readable, _, _ = select.select([self._fd], [], [], 0.1)
            if readable and self.feed(os.read(self._fd, 1).decode(errors="ignore")):
                return
