from __future__ import annotations

import os


AUTO_POSTING_DISABLED_ENV = "NAYZ_AUTO_POSTING_DISABLED"
_TRUTHY = {"1", "true", "yes", "on", "locked", "disabled"}


class AutoPostingDisabledError(RuntimeError):
    pass


def auto_posting_disabled() -> bool:
    value = os.getenv(AUTO_POSTING_DISABLED_ENV, "").strip().lower()
    return value in _TRUTHY


def ensure_auto_posting_enabled(action: str = "publish") -> None:
    if auto_posting_disabled():
        raise AutoPostingDisabledError(
            f"{action} blocked: {AUTO_POSTING_DISABLED_ENV}=1"
        )
