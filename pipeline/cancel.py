from __future__ import annotations

import signal
import sys
import threading
import time
from contextlib import contextmanager
from types import FrameType
from typing import Iterator


class PipelineCancelled(KeyboardInterrupt):
    """Raised when the current pipeline run is cancelled by the user."""


_cancel_event = threading.Event()
_keyboard_thread: threading.Thread | None = None
_keyboard_thread_lock = threading.Lock()


def cancel(reason: str = "cancelled") -> None:
    _cancel_event.set()


def reset_cancel() -> None:
    _cancel_event.clear()


def is_cancelled() -> bool:
    return _cancel_event.is_set()


def raise_if_cancelled() -> None:
    if is_cancelled():
        raise PipelineCancelled()


def interruptible_sleep(seconds: float, *, step: float = 0.1) -> None:
    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        raise_if_cancelled()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(step, remaining))


def wait_event(event: threading.Event, timeout: float | None = None, *, step: float = 0.1) -> bool:
    if timeout is None:
        while not event.wait(step):
            raise_if_cancelled()
        return True

    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        raise_if_cancelled()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return event.is_set()
        if event.wait(min(step, remaining)):
            return True


def _start_escape_listener() -> None:
    if not sys.stdin.isatty() or sys.platform != "win32":
        return

    global _keyboard_thread
    with _keyboard_thread_lock:
        if _keyboard_thread is not None and _keyboard_thread.is_alive():
            return

        def watch_escape() -> None:
            try:
                import msvcrt

                while True:
                    if msvcrt.kbhit():
                        key = msvcrt.getwch()
                        if key == "\x1b":
                            print("\n[info] 用户中断 (Esc)，正在退出…", flush=True)
                            cancel("escape")
                            return
                    time.sleep(0.05)
            except Exception:
                return

        _keyboard_thread = threading.Thread(
            target=watch_escape,
            name="pipeline-escape-listener",
            daemon=True,
        )
        _keyboard_thread.start()


@contextmanager
def cancellation_context() -> Iterator[None]:
    reset_cancel()
    _start_escape_listener()

    previous_int = signal.getsignal(signal.SIGINT)
    previous_term = signal.getsignal(signal.SIGTERM) if hasattr(signal, "SIGTERM") else None

    def handle_signal(signum: int, frame: FrameType | None) -> None:
        cancel(signal.Signals(signum).name)
        raise PipelineCancelled()

    signal.signal(signal.SIGINT, handle_signal)
    if previous_term is not None:
        signal.signal(signal.SIGTERM, handle_signal)

    try:
        yield
        raise_if_cancelled()
    finally:
        signal.signal(signal.SIGINT, previous_int)
        if previous_term is not None:
            signal.signal(signal.SIGTERM, previous_term)
