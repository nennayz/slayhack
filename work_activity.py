from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORK_ACTIVITY_LOG = Path("logs") / "work_activity.jsonl"
VALID_EVENT_TYPES = {
    "terminal_command",
    "design_decision",
    "implementation_step",
    "test_result",
    "deploy_step",
    "production_smoke",
    "blocker",
    "next_recommendation",
}
SECRET_ENV_KEYS = (
    "META_ACCESS_TOKEN",
    "META_APP_SECRET",
    "DASHBOARD_PASSWORD",
    "TELEGRAM_BOT_TOKEN",
    "GITHUB_TOKEN",
    "GH_TOKEN",
)


def _work_activity_path(root: Path) -> Path:
    return root / WORK_ACTIVITY_LOG


def _sanitize_text(value: object, max_length: int = 2000) -> str:
    text = str(value or "")
    secret_values = sorted(
        (os.environ.get(key, "") for key in SECRET_ENV_KEYS),
        key=len,
        reverse=True,
    )
    for secret_value in secret_values:
        if secret_value:
            text = text.replace(secret_value, "<redacted>")
    return text[:max_length]


def _sanitize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_json(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return _sanitize_text(value) if isinstance(value, str) else value
    return _sanitize_text(value)


def write_work_activity(
    root: Path,
    event_type: str,
    summary: str,
    *,
    actor: str = "codex",
    command: str | None = None,
    files: list[str] | None = None,
    result: str | None = None,
    next_action: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid work activity event type: {event_type}")
    cleaned_summary = _sanitize_text(summary, max_length=500).strip()
    if not cleaned_summary:
        raise ValueError("Work activity summary is required")

    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "actor": _sanitize_text(actor, max_length=80).strip() or "codex",
        "event_type": event_type,
        "summary": cleaned_summary,
    }
    if command:
        record["command"] = _sanitize_text(command, max_length=1000)
    if files:
        record["files"] = [_sanitize_text(item, max_length=240) for item in files if str(item).strip()]
    if result:
        record["result"] = _sanitize_text(result, max_length=1000)
    if next_action:
        record["next_action"] = _sanitize_text(next_action, max_length=500)
    if metadata:
        record["metadata"] = _sanitize_json(metadata)

    path = _work_activity_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def read_recent_work_activity(root: Path, limit: int = 8) -> list[dict[str, Any]]:
    path = _work_activity_path(root)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append({
            "timestamp": str(item.get("timestamp", "")),
            "actor": str(item.get("actor", "")),
            "event_type": str(item.get("event_type", "")),
            "summary": _sanitize_text(item.get("summary", ""), max_length=500),
            "command": _sanitize_text(item.get("command", ""), max_length=1000),
            "result": _sanitize_text(item.get("result", ""), max_length=1000),
            "next_action": _sanitize_text(item.get("next_action", ""), max_length=500),
            "files": item.get("files", []) if isinstance(item.get("files", []), list) else [],
            "metadata": _sanitize_json(item.get("metadata", {})) if isinstance(item.get("metadata", {}), dict) else {},
        })
    return list(reversed(rows))


def work_activity_status(root: Path) -> dict[str, object]:
    path = _work_activity_path(root)
    archive_dir = root / "logs" / "archive"
    archive_count = len(list(archive_dir.glob("work_activity-*.jsonl"))) if archive_dir.exists() else 0
    if not path.exists():
        return {
            "state": "Missing",
            "detail": "work_activity.jsonl not created yet",
            "size_bytes": 0,
            "line_count": 0,
            "archive_count": archive_count,
        }
    try:
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        size = path.stat().st_size
    except OSError as exc:
        return {"state": "Failed", "detail": str(exc), "size_bytes": 0, "line_count": 0, "archive_count": archive_count}
    size_kb = size / 1024
    return {
        "state": "Ready",
        "detail": f"{line_count} entries - {size_kb:.1f} KB - {archive_count} archives",
        "size_bytes": size,
        "line_count": line_count,
        "archive_count": archive_count,
    }
