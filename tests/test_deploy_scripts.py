from __future__ import annotations
import subprocess
from pathlib import Path


def test_backup_and_healthcheck_scripts_parse():
    for path in ("deploy/backup.sh", "deploy/healthcheck.sh", "deploy/restore_smoke.sh"):
        result = subprocess.run(["bash", "-n", path], cwd=Path(__file__).resolve().parents[1])
        assert result.returncode == 0


def test_restore_smoke_logs_history():
    root = Path(__file__).resolve().parents[1]
    text = (root / "deploy" / "restore_smoke.sh").read_text()
    assert "logs/restore_smoke.jsonl" in text
    assert '"state":"Ready"' in text


def test_instagram_queue_systemd_units_exist():
    root = Path(__file__).resolve().parents[1]
    service = root / "deploy" / "nayzfreedom-instagram-queue.service"
    timer = root / "deploy" / "nayzfreedom-instagram-queue.timer"
    assert service.exists()
    assert timer.exists()
    assert "instagram_queue.py" in service.read_text()
    assert "OnUnitActiveSec=5min" in timer.read_text()


def test_production_summary_systemd_units_exist():
    root = Path(__file__).resolve().parents[1]
    service = root / "deploy" / "nayzfreedom-production-summary.service"
    timer = root / "deploy" / "nayzfreedom-production-summary.timer"
    assert service.exists()
    assert timer.exists()
    assert "production_summary.py" in service.read_text()
    assert "00:15:00 UTC" in timer.read_text()


def test_log_retention_systemd_units_exist():
    root = Path(__file__).resolve().parents[1]
    service = root / "deploy" / "nayzfreedom-log-retention.service"
    timer = root / "deploy" / "nayzfreedom-log-retention.timer"
    assert service.exists()
    assert timer.exists()
    assert "ops_retention.py" in service.read_text()
    assert "00:30:00 UTC" in timer.read_text()
    assert "nayzfreedom-log-retention.timer" in (root / "deploy" / "healthcheck.sh").read_text()


def test_ops_report_systemd_units_exist():
    root = Path(__file__).resolve().parents[1]
    service = root / "deploy" / "nayzfreedom-ops-report.service"
    timer = root / "deploy" / "nayzfreedom-ops-report.timer"
    assert service.exists()
    assert timer.exists()
    assert "ops_report.py" in service.read_text()
    assert "00:45:00 UTC" in timer.read_text()
    assert "nayzfreedom-ops-report.timer" in (root / "deploy" / "healthcheck.sh").read_text()


def test_track_scheduler_systemd_units_are_health_checked():
    root = Path(__file__).resolve().parents[1]
    service = root / "deploy" / "nayzfreedom-track-scheduler.service"
    timer = root / "deploy" / "nayzfreedom-track-scheduler.timer"
    assert service.exists()
    assert timer.exists()
    assert "track_scheduler.py" in service.read_text()
    healthcheck = (root / "deploy" / "healthcheck.sh").read_text()
    assert "nayzfreedom-track-scheduler.timer" in healthcheck
    assert "nayzfreedom-track-scheduler.service" in healthcheck


def test_ops_sudoers_limits_allowed_commands():
    root = Path(__file__).resolve().parents[1]
    sudoers = root / "deploy" / "nayzfreedom-ops.sudoers"
    setup = root / "deploy" / "setup.sh"
    update = root / "deploy" / "update.sh"
    text = sudoers.read_text()
    assert "nayzfreedom-backup.service" in text
    assert "nayzfreedom-instagram-queue.service" in text
    assert "nayzfreedom-production-summary.service" in text
    assert "nayzfreedom-ops-report.service" in text
    assert "nayzfreedom-track-scheduler.service" in text
    assert "nayzfreedom-dashboard.service" in text
    assert "NOPASSWD: ALL" not in text
    assert "/etc/sudoers.d/nayzfreedom-ops" in setup.read_text()
    assert "/etc/sudoers.d/nayzfreedom-ops" in update.read_text()


def test_update_script_repairs_wrong_ownership_before_pull():
    root = Path(__file__).resolve().parents[1]
    update = (root / "deploy" / "update.sh").read_text()
    assert "[preflight] Checking deploy ownership" in update
    assert "ownership_warning=" in update
    assert "chown -R \"$SERVICE_USER:$SERVICE_USER\" \"$INSTALL_DIR\"" in update
    assert update.index("[preflight] Checking deploy ownership") < update.index("[1/3] Pulling latest code")
