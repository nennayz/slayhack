from __future__ import annotations

import os
from pathlib import Path


class LockAcquisitionError(RuntimeError):
    def __init__(self, lock_file: Path, pid: int | None = None):
        self.lock_file = lock_file
        self.pid = pid
        pid_hint = f" (PID {pid})" if pid else ""
        super().__init__(
            f"another pipeline instance is already running{pid_hint}. "
            f"If no pipeline is running, delete {lock_file} manually."
        )


def pid_is_running(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_lock_pid(lock_file: Path) -> int | None:
    try:
        return int(lock_file.read_text().strip())
    except (OSError, ValueError):
        return None


def acquire_pid_lock(lock_file: Path) -> tuple[bool, int | None, bool]:
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    stale_removed = False

    for _ in range(2):
        try:
            fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
                os.close(fd)
            return True, os.getpid(), stale_removed
        except FileExistsError:
            pid = read_lock_pid(lock_file)
            if pid_is_running(pid):
                return False, pid, stale_removed
            lock_file.unlink(missing_ok=True)
            stale_removed = True

    pid = read_lock_pid(lock_file)
    return False, pid, stale_removed
