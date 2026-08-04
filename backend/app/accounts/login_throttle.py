"""In-process brute-force throttle for /auth/login.

Tracks failed attempts per normalized username in memory. This is
per-process state: correct for the single-replica SQLite deployments this
app targets, and a best-effort mitigation (not a hard guarantee) on a
multi-replica Postgres deployment, since each replica throttles
independently.
"""

import threading
import time

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60
LOCKOUT_SECONDS = 15 * 60

_lock = threading.Lock()
_failures: dict[str, list[float]] = {}
_locked_until: dict[str, float] = {}


def seconds_until_unlocked(key: str) -> float:
    now = time.monotonic()
    with _lock:
        unlock_at = _locked_until.get(key)
        if unlock_at is None:
            return 0.0
        if now >= unlock_at:
            _locked_until.pop(key, None)
            _failures.pop(key, None)
            return 0.0
        return unlock_at - now


def record_failure(key: str) -> None:
    now = time.monotonic()
    with _lock:
        attempts = [
            attempt for attempt in _failures.get(key, [])
            if now - attempt < WINDOW_SECONDS
        ]
        attempts.append(now)
        _failures[key] = attempts
        if len(attempts) >= MAX_ATTEMPTS:
            _locked_until[key] = now + LOCKOUT_SECONDS


def record_success(key: str) -> None:
    with _lock:
        _failures.pop(key, None)
        _locked_until.pop(key, None)


def reset() -> None:
    """Clear all throttle state. Test-only."""
    with _lock:
        _failures.clear()
        _locked_until.clear()
