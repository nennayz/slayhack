from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast


SNAPSHOT_DIR = Path("output") / "slayobjects_metrics"
SNAPSHOT_FILE = SNAPSHOT_DIR / "snapshots.jsonl"


PLATFORMS = {
    "tiktok": {
        "label": "TikTok",
        "url": "https://www.tiktok.com/@slayobjects",
        "handle": "@slayobjects",
        "required_env": ("TIKTOK_ACCESS_TOKEN",),
        "primary_metric": "views",
    },
    "instagram": {
        "label": "Instagram",
        "url": "https://www.instagram.com/slayobjects/",
        "handle": "@slayobjects",
        "required_env": ("META_ACCESS_TOKEN", "META_IG_USER_ID"),
        "primary_metric": "reach",
    },
    "facebook": {
        "label": "Facebook",
        "url": "https://facebook.com/slayobjects",
        "handle": "facebook.com/slayobjects",
        "required_env": ("META_ACCESS_TOKEN", "META_PAGE_ID"),
        "primary_metric": "reach",
    },
}


METRIC_KEYS = ("views", "reach", "likes", "comments", "saves", "shares", "followers")


@dataclass(frozen=True)
class SlayObjectsSnapshot:
    platform: str
    captured_at: datetime
    source: str = "manual"
    content_url: str = ""
    note: str = ""
    views: int = 0
    reach: int = 0
    likes: int = 0
    comments: int = 0
    saves: int = 0
    shares: int = 0
    followers: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "SlayObjectsSnapshot":
        captured_raw = str(data.get("captured_at") or "").strip()
        captured_at = _parse_time(captured_raw) or datetime.now(timezone.utc)
        platform = _clean_platform(str(data.get("platform") or ""))
        values = {key: _to_int(data.get(key)) for key in METRIC_KEYS}
        return cls(
            platform=platform,
            captured_at=captured_at,
            source=str(data.get("source") or "manual"),
            content_url=str(data.get("content_url") or ""),
            note=str(data.get("note") or ""),
            **values,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "captured_at": self.captured_at.astimezone(timezone.utc).isoformat(),
            "source": self.source,
            "content_url": self.content_url,
            "note": self.note,
            **{key: getattr(self, key) for key in METRIC_KEYS},
        }


def record_manual_snapshot(
    root: Path,
    *,
    platform: str,
    content_url: str = "",
    note: str = "",
    views: object = 0,
    reach: object = 0,
    likes: object = 0,
    comments: object = 0,
    saves: object = 0,
    shares: object = 0,
    followers: object = 0,
) -> SlayObjectsSnapshot:
    snapshot = SlayObjectsSnapshot(
        platform=_clean_platform(platform),
        captured_at=datetime.now(timezone.utc),
        source="manual",
        content_url=content_url.strip(),
        note=note.strip(),
        views=_to_int(views),
        reach=_to_int(reach),
        likes=_to_int(likes),
        comments=_to_int(comments),
        saves=_to_int(saves),
        shares=_to_int(shares),
        followers=_to_int(followers),
    )
    path = _snapshot_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(snapshot.to_dict(), sort_keys=True) + "\n")
    return snapshot


def read_slayobjects_snapshots(root: Path, limit: int = 300) -> list[SlayObjectsSnapshot]:
    path = _snapshot_path(root)
    if not path.exists():
        return []
    snapshots: list[SlayObjectsSnapshot] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            snapshots.append(SlayObjectsSnapshot.from_dict(json.loads(line)))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return sorted(snapshots, key=lambda item: item.captured_at, reverse=True)[:limit]


def build_slayobjects_live_dashboard(root: Path) -> dict[str, object]:
    snapshots = read_slayobjects_snapshots(root)
    by_platform: dict[str, list[SlayObjectsSnapshot]] = {
        key: [item for item in snapshots if item.platform == key]
        for key in PLATFORMS
    }
    platform_rows = [
        _platform_row(platform, platform_snapshots)
        for platform, platform_snapshots in by_platform.items()
    ]
    latest = [cast(dict[str, object], row["latest_snapshot"]) for row in platform_rows if row["latest_snapshot"]]
    top_content = sorted(
        latest,
        key=lambda item: (
            _to_int(item.get("views")) + _to_int(item.get("reach")),
            _to_int(item.get("shares")) * 3 + _to_int(item.get("saves")) * 2 + _to_int(item.get("comments")),
        ),
        reverse=True,
    )[:6]
    return {
        "identity": {
            "name": "SlayObjects",
            "project": "SlayHack",
            "handle": "@slayobjects",
            "website": "slayhack.com",
        },
        "platforms": platform_rows,
        "summary": _summary(platform_rows),
        "top_content": top_content,
        "captain_actions": _captain_actions(platform_rows, top_content),
        "snapshot_count": len(snapshots),
    }


def _snapshot_path(root: Path) -> Path:
    return root / SNAPSHOT_FILE


def _clean_platform(value: str) -> str:
    platform = value.strip().lower()
    if platform not in PLATFORMS:
        raise ValueError(f"Unsupported SlayObjects platform: {value}")
    return platform


def _platform_row(platform: str, snapshots: list[SlayObjectsSnapshot]) -> dict[str, object]:
    config = PLATFORMS[platform]
    latest = snapshots[0] if snapshots else None
    previous = snapshots[1] if len(snapshots) > 1 else None
    env_ready = all(os.getenv(name) for name in config["required_env"])
    primary_metric = str(config["primary_metric"])
    latest_value = getattr(latest, primary_metric, 0) if latest else 0
    previous_value = getattr(previous, primary_metric, 0) if previous else 0
    delta = latest_value - previous_value if latest and previous else None
    return {
        "platform": platform,
        "label": config["label"],
        "handle": config["handle"],
        "url": config["url"],
        "primary_metric": primary_metric,
        "latest_value": latest_value,
        "delta": delta,
        "api_state": "API ready" if env_ready else "Manual-ready",
        "state": _row_state(latest, env_ready),
        "latest_snapshot": _snapshot_view(latest, platform) if latest else None,
        "snapshot_count": len(snapshots),
    }


def _snapshot_view(snapshot: SlayObjectsSnapshot | None, platform: str) -> dict[str, object] | None:
    if snapshot is None:
        return None
    config = PLATFORMS[platform]
    interactions = snapshot.likes + snapshot.comments + snapshot.saves + snapshot.shares
    denominator = snapshot.views or snapshot.reach or 0
    engagement_rate = round((interactions / denominator) * 100, 2) if denominator else 0
    return {
        "platform": platform,
        "platform_label": config["label"],
        "captured_at": snapshot.captured_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": snapshot.source,
        "content_url": snapshot.content_url,
        "note": snapshot.note,
        "views": snapshot.views,
        "reach": snapshot.reach,
        "likes": snapshot.likes,
        "comments": snapshot.comments,
        "saves": snapshot.saves,
        "shares": snapshot.shares,
        "followers": snapshot.followers,
        "interactions": interactions,
        "engagement_rate": engagement_rate,
    }


def _summary(platform_rows: list[dict[str, object]]) -> dict[str, int]:
    snapshots = [cast(dict[str, object], row["latest_snapshot"]) for row in platform_rows if row["latest_snapshot"]]
    return {
        "platforms_tracked": len(snapshots),
        "total_views": sum(_to_int(item.get("views")) for item in snapshots),
        "total_reach": sum(_to_int(item.get("reach")) for item in snapshots),
        "total_interactions": sum(_to_int(item.get("interactions")) for item in snapshots),
    }


def _captain_actions(
    platform_rows: list[dict[str, object]],
    top_content: list[dict[str, object]],
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    missing = [str(row["label"]) for row in platform_rows if not row["latest_snapshot"]]
    if missing:
        actions.append({
            "state": "missing",
            "label": "Record first snapshot",
            "detail": f"Add manual/API proof for {', '.join(missing)} so Slay can compare the full @slayobjects footprint.",
        })
    if top_content:
        winner = top_content[0]
        actions.append({
            "state": "ready",
            "label": "Scale winning signal",
            "detail": f"{winner['platform_label']} is the current strongest proof. Turn this angle into the next content or e-book funnel test.",
        })
    if not actions:
        actions.append({
            "state": "ready",
            "label": "Connect metric source",
            "detail": "Dashboard shell is ready. Add API tokens or record a manual snapshot to start the learning loop.",
        })
    actions.append({
        "state": "ready",
        "label": "Keep live publish locked",
        "detail": "This dashboard measures and recommends next actions only; it does not auto-post.",
    })
    return actions


def _row_state(snapshot: SlayObjectsSnapshot | None, env_ready: bool) -> str:
    if snapshot:
        return "tracking"
    if env_ready:
        return "api_ready"
    return "needs_snapshot"


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    cleaned = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _to_int(value: object) -> int:
    if value is None:
        return 0
    try:
        return max(0, int(str(value).replace(",", "").strip() or "0"))
    except ValueError:
        return 0
