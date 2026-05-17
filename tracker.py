from __future__ import annotations
import logging
from datetime import datetime, timezone
import requests
from config import Config
from models.content_job import ContentJob, PostPerformance

_META_GRAPH_BASE = "https://graph.facebook.com/v19.0"
_TIKTOK_BASE = "https://open.tiktokapis.com/v2"
_TIKTOK_MATCH_WINDOW = 3600

logger = logging.getLogger(__name__)


def track_job(job: ContentJob, config: Config) -> ContentJob:
    if not job.publish_result:
        return job
    for platform, result in job.publish_result.items():
        if result.get("status") != "published":
            continue
        try:
            perf = _fetch_platform_metrics(platform, result, job, config)
            if perf:
                job.performance.append(perf)
        except Exception as e:
            logger.warning("Could not fetch metrics for %s: %s", platform, e)
    return job


def _fetch_platform_metrics(
    platform: str, result: dict, job: ContentJob, config: Config
) -> PostPerformance | None:
    if platform == "facebook":
        post_id = result.get("id")
        if not post_id:
            logger.warning("facebook publish result missing 'id', skipping metrics")
            return None
        return _fetch_facebook(post_id, config)
    if platform == "instagram":
        media_id = result.get("id")
        if not media_id:
            logger.warning("instagram publish result missing 'id', skipping metrics")
            return None
        return _fetch_instagram(media_id, config)
    if platform == "tiktok":
        return _fetch_tiktok(result, job, config)
    return None


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _fetch_facebook(post_id: str, config: Config) -> PostPerformance:
    resp = requests.get(
        f"{_META_GRAPH_BASE}/{post_id}",
        params={"fields": "likes.summary(true),shares,insights.metric(post_impressions_unique)"},
        headers=_auth_headers(config.meta_access_token),
    )
    resp.raise_for_status()
    data = resp.json()
    likes = data.get("likes", {}).get("summary", {}).get("total_count")
    shares = data.get("shares", {}).get("count")
    reach = None
    insights = data.get("insights", {}).get("data", [])
    if insights:
        values = insights[0].get("values", [])
        if values:
            reach = values[0].get("value")
    return PostPerformance(
        platform="facebook",
        likes=likes,
        reach=reach,
        shares=shares,
        recorded_at=datetime.now(timezone.utc),
    )


def _fetch_instagram(media_id: str, config: Config) -> PostPerformance:
    resp = requests.get(
        f"{_META_GRAPH_BASE}/{media_id}",
        params={"fields": "like_count,reach,saved"},
        headers=_auth_headers(config.meta_access_token),
    )
    resp.raise_for_status()
    data = resp.json()
    return PostPerformance(
        platform="instagram",
        likes=data.get("like_count"),
        reach=data.get("reach"),
        saves=data.get("saved"),
        recorded_at=datetime.now(timezone.utc),
    )


def _fetch_tiktok(result: dict, job: ContentJob, config: Config) -> PostPerformance | None:
    token = config.tiktok_access_token
    headers = _auth_headers(token)
    video_id = result.get("video_id")
    if video_id:
        query_resp = requests.post(
            f"{_TIKTOK_BASE}/video/query/",
            params={"fields": "id,like_count,view_count,share_count"},
            headers={**headers, "Content-Type": "application/json; charset=UTF-8"},
            json={"filters": {"video_ids": [video_id]}},
        )
        query_resp.raise_for_status()
        videos = (query_resp.json().get("data") or {}).get("videos") or []
        matched = videos[0] if videos else None
        if not matched:
            return None
    else:
        list_resp = requests.post(
            f"{_TIKTOK_BASE}/video/list/",
            params={"fields": "id,create_time,like_count,view_count,share_count"},
            headers={**headers, "Content-Type": "application/json; charset=UTF-8"},
            json={"max_count": 10},
        )
        list_resp.raise_for_status()
        videos = (list_resp.json().get("data") or {}).get("videos") or []
        job_ts = _job_publish_time(job)
        matched = next(
            (v for v in videos if abs(v.get("create_time", 0) - job_ts) <= _TIKTOK_MATCH_WINDOW),
            None,
        )
        if not matched:
            logger.warning(
                "TikTok: could not match video for job %s within ±%ds window",
                job.id,
                _TIKTOK_MATCH_WINDOW,
            )
            return None
        video_id = matched["id"]
        result["video_id"] = video_id
    return PostPerformance(
        platform="tiktok",
        likes=matched.get("like_count"),
        reach=matched.get("view_count"),
        shares=matched.get("share_count"),
        recorded_at=datetime.now(timezone.utc),
    )


def _job_publish_time(job: ContentJob) -> int:
    if job.published_at is not None:
        return int(job.published_at.timestamp())
    try:
        dt = datetime.strptime(job.id[:15], "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (ValueError, AttributeError):
        return int(datetime.now(timezone.utc).timestamp())
