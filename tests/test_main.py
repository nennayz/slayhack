from lock_utils import LockAcquisitionError
import main as main_module


def test_main_lock_recovers_stale_pid(monkeypatch, tmp_path):
    lock_file = tmp_path / "pipeline.lock"
    monkeypatch.setattr(main_module, "_LOCK_FILE", lock_file)
    monkeypatch.delenv(main_module._SKIP_LOCK_ENV, raising=False)
    monkeypatch.setattr(main_module, "acquire_pid_lock", lambda path: (True, 12345, True))

    assert main_module._acquire_lock() is True


def test_main_lock_raises_when_active(monkeypatch, tmp_path):
    lock_file = tmp_path / "pipeline.lock"
    monkeypatch.setattr(main_module, "_LOCK_FILE", lock_file)
    monkeypatch.delenv(main_module._SKIP_LOCK_ENV, raising=False)
    monkeypatch.setattr(main_module, "acquire_pid_lock", lambda path: (False, 4321, False))

    try:
        main_module._acquire_lock()
        raised = False
    except LockAcquisitionError as exc:
        raised = True
        assert "4321" in str(exc)

    assert raised is True
