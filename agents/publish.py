from __future__ import annotations
import logging
import re
import time
from datetime import datetime, timezone
import requests
from pathlib import Path
from urllib.parse import quote
from agents.base_agent import BaseAgent
from models.content_job import ContentJob, ContentType
from track_queue import enqueue_track_snapshots

_META_GRAPH_BASE = "https://graph.facebook.com/v19.0"
_TIKTOK_BASE = "https://open.tiktokapis.com/v2"
_TIKTOK_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB
_TIKTOK_POLL_INTERVAL = 5
_TIKTOK_POLL_TIMEOUT = 300
_IG_CONTAINER_POLL_INTERVAL = 5
_IG_CONTAINER_POLL_TIMEOUT = 300
_YOUTUBE_UPLOAD_BASE = "https://www.googleapis.com/upload/youtube/v3"
_YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
logger = logging.getLogger(__name__)
_SECRET_PATTERNS = [
    re.compile(r"(access_token=)[^&\s]+", re.IGNORECASE),
    re.compile(r"(Authorization:\s*(?:Bearer|OAuth)\s+)[^\s,}]+", re.IGNORECASE),
    re.compile(r"((?:Bearer|OAuth)\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
]


class MetaAPIError(RuntimeError):
    def __init__(self, message: str, meta_error: dict[str, object] | None = None):
        super().__init__(message)
        self.meta_error = meta_error or {}


def has_publish_failures(result: dict | None) -> bool:
    if not result:
        return False
    platform_results = [v for v in result.values() if isinstance(v, dict)]
    return any(item.get("status") == "failed" for item in platform_results)


def sanitize_error_text(text: str, limit: int = 500) -> str:
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(r"\1<redacted>", redacted)
    return redacted[:limit]


def _safe_meta_error(response: requests.Response) -> dict[str, object]:
    body = ""
    try:
        body = response.text
    except Exception:  # noqa: BLE001
        body = ""
    data = {}
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error", payload)
            if isinstance(error, dict):
                data = {
                    key: sanitize_error_text(error[key]) if isinstance(error[key], str) else error[key]
                    for key in ("message", "type", "code", "error_subcode", "fbtrace_id")
                    if key in error
                }
    except Exception:  # noqa: BLE001
        data = {}
    if body:
        data["body"] = sanitize_error_text(body)
    return data


def _raise_for_status_with_body(response: requests.Response, context: str) -> None:
    try:
        response.raise_for_status()
    except Exception as exc:
        meta_error = _safe_meta_error(response)
        body = meta_error.get("body", "")
        if body:
            raise MetaAPIError(f"{context}: {exc}; body={body}", meta_error) from exc
        raise MetaAPIError(f"{context}: {exc}", meta_error) from exc


class PublishAgent(BaseAgent):
    def run_dry(self, job: ContentJob, **kwargs) -> ContentJob:
        job.publish_result = {"dry_run": True, "platforms": job.platforms}
        job.stage = "publish_done"
        return job

    def run_live(self, job: ContentJob, **kwargs) -> ContentJob:
        schedule: bool = kwargs.get("schedule", False)
        target_platforms = kwargs.get("target_platforms")
        requested_platforms = list(target_platforms or job.platforms)
        effective_platforms = [
            p for p in requested_platforms
            if not (job.content_type == ContentType.ARTICLE and p in ("instagram", "tiktok", "youtube"))
        ]
        if job.content_type != ContentType.ARTICLE:
            media_path = job.video_path if job.content_type == ContentType.VIDEO else job.image_path
            if not media_path:
                raise ValueError(
                    f"PublishAgent: no media file on job {job.id} "
                    f"(content_type={job.content_type})"
                )
            if not Path(media_path).exists():
                raise ValueError(
                    f"PublishAgent: media file not found: {media_path} (job {job.id})"
                )
        scheduled_time = self._scheduled_unix_ts(job) if schedule else None
        caption = self._build_caption(job)
        result: dict = dict(job.publish_result or {}) if target_platforms else {}
        for platform in effective_platforms:
            try:
                if platform == "facebook":
                    post_result = self._post_facebook(job, caption, scheduled_time)
                elif platform == "instagram":
                    if scheduled_time:
                        result[platform] = self._queue_instagram(job, caption, scheduled_time)
                        continue
                    post_result = self._post_instagram(job, caption, None)
                elif platform == "tiktok":
                    post_result = self._post_tiktok(job, caption)
                    if post_result.get("status") == "skipped":
                        result[platform] = post_result
                        continue
                elif platform == "youtube":
                    post_result = self._post_youtube(job, caption, scheduled_time)
                    if post_result.get("status") == "skipped":
                        result[platform] = post_result
                        continue
                else:
                    result[platform] = {"status": "skipped", "error": f"unsupported platform: {platform}"}
                    continue
                status = "published" if platform == "instagram" else "scheduled" if scheduled_time else "published"
                result[platform] = {"status": status, **post_result}
            except Exception as e:
                failure = {"status": "failed", "error": str(e)}
                meta_error = getattr(e, "meta_error", None)
                if meta_error:
                    failure["meta_error"] = meta_error
                result[platform] = failure
        job.publish_result = result
        job.stage = "publish_done"

        _published_statuses = {"published", "scheduled", "pending_queue"}
        any_published = any(
            isinstance(v, dict) and v.get("status") in _published_statuses
            for v in result.values()
        )
        if any_published:
            job.published_at = (
                datetime.fromtimestamp(scheduled_time, tz=timezone.utc)
                if scheduled_time else datetime.now(timezone.utc)
            )
            enqueue_track_snapshots(job)

        return job

    def _queue_instagram(self, job: ContentJob, caption: str, scheduled_time: int) -> dict:
        from datetime import datetime, timezone
        return {
            "status": "pending_queue",
            "scheduled_publish_time": scheduled_time,
            "due_at": datetime.fromtimestamp(scheduled_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "caption": caption,
            "reason": "Instagram Graph scheduling is unavailable for this Meta account; queued for just-in-time publish.",
        }

    def _build_caption(self, job: ContentJob) -> str:
        if job.growth_strategy is None:
            return ""
        tags = " ".join(job.growth_strategy.hashtags)
        return f"{job.growth_strategy.caption}\n\n{tags}"

    def _scheduled_unix_ts(self, job: ContentJob) -> int | None:
        if job.growth_strategy is None:
            return None
        from datetime import datetime, timezone, timedelta
        try:
            hh, mm = job.growth_strategy.best_post_time_utc.split(":")
            now = datetime.now(timezone.utc)
            scheduled = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            if scheduled <= now:
                scheduled += timedelta(days=1)
            return int(scheduled.timestamp())
        except Exception:
            logger.warning(
                "PublishAgent: could not parse best_post_time_utc=%r for job %s — "
                "falling back to immediate publish",
                job.growth_strategy.best_post_time_utc,
                job.id,
            )
            return None

    def _auth_headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _post_tiktok(self, job: ContentJob, caption: str) -> dict:
        if not self.config.tiktok_access_token:
            return {"status": "skipped", "reason": "TIKTOK_ACCESS_TOKEN not configured"}
        if job.content_type != ContentType.VIDEO:
            return {"status": "skipped", "reason": "image carousel requires public URL hosting"}
        token = self.config.tiktok_access_token
        return self._post_tiktok_video(job, caption, token)

    def _post_tiktok_video(self, job: ContentJob, caption: str, token: str) -> dict:
        if not job.video_path:
            raise ValueError(f"PublishAgent: video_path is None for job {job.id}")
        headers = self._auth_headers(token)
        file_size = Path(job.video_path).stat().st_size
        if file_size == 0:
            raise ValueError(f"PublishAgent: video file is empty: {job.video_path}")
        total_chunk_count = (file_size + _TIKTOK_CHUNK_SIZE - 1) // _TIKTOK_CHUNK_SIZE
        init_resp = requests.post(
            f"{_TIKTOK_BASE}/post/publish/video/init/",
            headers={**headers, "Content-Type": "application/json; charset=UTF-8"},
            json={
                "post_info": {
                    "title": caption,
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": file_size,
                    "chunk_size": _TIKTOK_CHUNK_SIZE,
                    "total_chunk_count": total_chunk_count,
                },
            },
        )
        init_resp.raise_for_status()
        init_data = init_resp.json()["data"]
        publish_id = init_data["publish_id"]
        upload_url = init_data["upload_url"]
        with open(job.video_path, "rb") as f:
            for chunk_index in range(total_chunk_count):
                chunk = f.read(_TIKTOK_CHUNK_SIZE)
                start = chunk_index * _TIKTOK_CHUNK_SIZE
                end = start + len(chunk) - 1
                requests.put(
                    upload_url,
                    headers={
                        "Content-Range": f"bytes {start}-{end}/{file_size}",
                        "Content-Type": "video/mp4",
                    },
                    data=chunk,
                ).raise_for_status()
        elapsed = 0
        while elapsed < _TIKTOK_POLL_TIMEOUT:
            status_resp = requests.post(
                f"{_TIKTOK_BASE}/post/publish/status/fetch/",
                headers={**headers, "Content-Type": "application/json; charset=UTF-8"},
                json={"publish_id": publish_id},
            )
            status_resp.raise_for_status()
            status_data = status_resp.json().get("data", {})
            status = status_data.get("status")
            if status == "PUBLISH_COMPLETE":
                return {"publish_id": publish_id, "status_code": "PUBLISH_COMPLETE"}
            if status == "FAILED":
                fail_reason = status_data.get("fail_reason", "unknown")
                raise RuntimeError(f"TikTok publish failed: {fail_reason}")
            time.sleep(_TIKTOK_POLL_INTERVAL)
            elapsed += _TIKTOK_POLL_INTERVAL
        raise TimeoutError(
            f"timed out waiting for TikTok processing after {_TIKTOK_POLL_TIMEOUT}s"
        )

    def _post_youtube(self, job: ContentJob, caption: str, scheduled_time: int | None) -> dict:
        if not self.config.youtube_client_id or not self.config.youtube_refresh_token:
            return {"status": "skipped", "reason": "YouTube OAuth credentials not configured"}
        if job.content_type != ContentType.VIDEO:
            return {"status": "skipped", "reason": "YouTube only supports video uploads"}
        token = self._youtube_access_token(self.config)
        return self._post_youtube_video(job, caption, scheduled_time, token)

    def _youtube_access_token(self, config) -> str:
        resp = requests.post(
            _YOUTUBE_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": config.youtube_client_id,
                "client_secret": config.youtube_client_secret,
                "refresh_token": config.youtube_refresh_token,
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _post_youtube_video(
        self, job: ContentJob, caption: str, scheduled_time: int | None, token: str
    ) -> dict:
        if not job.video_path:
            raise ValueError(f"PublishAgent: video_path is None for job {job.id}")
        file_size = Path(job.video_path).stat().st_size
        if file_size == 0:
            raise ValueError(f"PublishAgent: video file is empty: {job.video_path}")
        tags = job.growth_strategy.hashtags if job.growth_strategy else []
        status_body: dict = {"privacyStatus": "private" if scheduled_time else "public"}
        if scheduled_time:
            status_body["publishAt"] = self._youtube_scheduled_iso(scheduled_time)
        init_resp = requests.post(
            f"{_YOUTUBE_UPLOAD_BASE}/videos?uploadType=resumable",
            headers={
                **self._auth_headers(token),
                "Content-Type": "application/json",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(file_size),
            },
            json={
                "snippet": {
                    "title": caption,
                    "description": caption,
                    "tags": tags,
                    "categoryId": "22",
                },
                "status": status_body,
            },
        )
        init_resp.raise_for_status()
        upload_uri = init_resp.headers["Location"]
        with open(job.video_path, "rb") as f:
            upload_resp = requests.put(
                upload_uri,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(file_size),
                },
                data=f,
            )
        upload_resp.raise_for_status()
        resp_data = upload_resp.json()
        if "id" not in resp_data:
            raise RuntimeError(
                f"YouTube upload did not return a video id "
                f"(status {upload_resp.status_code}): {resp_data}"
            )
        return {"id": resp_data["id"], "status_code": "uploaded"}

    def _youtube_scheduled_iso(self, scheduled_time: int) -> str:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(scheduled_time, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _post_facebook(self, job: ContentJob, caption: str, scheduled_time: int | None) -> dict:
        token = self.config.meta_access_token
        page_id = self.config.meta_page_id
        headers = self._auth_headers(token)
        if job.content_type == ContentType.ARTICLE:
            url = f"{_META_GRAPH_BASE}/{page_id}/feed"
            data: dict = {"message": caption}
            if scheduled_time:
                data["scheduled_publish_time"] = str(scheduled_time)
                data["published"] = "false"
            resp = requests.post(url, data=data, headers=headers)
            _raise_for_status_with_body(resp, "Facebook feed publish failed")
            return resp.json()
        media_path = job.image_path if job.content_type != ContentType.VIDEO else job.video_path
        if not media_path:
            raise ValueError(f"PublishAgent: media_path is None for job {job.id}")
        if job.content_type == ContentType.VIDEO:
            url = f"{_META_GRAPH_BASE}/{page_id}/videos"
            caption_key = "description"
        else:
            url = f"{_META_GRAPH_BASE}/{page_id}/photos"
            caption_key = "caption"
        data = {caption_key: caption}
        if scheduled_time:
            data["scheduled_publish_time"] = str(scheduled_time)
            data["published"] = "false"
        with open(media_path, "rb") as f:
            resp = requests.post(url, data=data, files={"source": f}, headers=headers)
        _raise_for_status_with_body(resp, "Facebook media publish failed")
        return resp.json()

    def _post_instagram(self, job: ContentJob, caption: str, scheduled_time: int | None) -> dict:
        token = self.config.meta_access_token
        ig_user_id = self.config.meta_ig_user_id
        if job.content_type == ContentType.VIDEO:
            return self._post_ig_reel(job, caption, scheduled_time, token, ig_user_id)
        return self._post_ig_image(job, caption, scheduled_time, token, ig_user_id)

    def _post_ig_image(
        self,
        job: ContentJob,
        caption: str,
        scheduled_time: int | None,
        token: str,
        ig_user_id: str,
    ) -> dict:
        if not job.image_path:
            raise ValueError(f"PublishAgent: image_path is None for job {job.id}")
        headers = self._auth_headers(token)
        url = f"{_META_GRAPH_BASE}/{ig_user_id}/media"
        data: dict = {"caption": caption}
        if scheduled_time:
            data["scheduled_publish_time"] = str(scheduled_time)
        try:
            with open(job.image_path, "rb") as f:
                resp = requests.post(url, data=data, files={"source": f}, headers=headers)
            _raise_for_status_with_body(resp, "Instagram image container creation failed")
            container_id = resp.json()["id"]
            upload_mode = "source"
        except Exception as source_error:
            image_url = self._public_media_url(job, job.image_path)
            if not image_url:
                raise source_error
            fallback_data = {**data, "image_url": image_url}
            resp = requests.post(url, data=fallback_data, headers=headers)
            _raise_for_status_with_body(resp, "Instagram image_url container creation failed")
            container_id = resp.json()["id"]
            upload_mode = "image_url"
        pub_url = f"{_META_GRAPH_BASE}/{ig_user_id}/media_publish"
        pub_resp = requests.post(pub_url, data={"creation_id": container_id}, headers=headers)
        _raise_for_status_with_body(pub_resp, "Instagram image publish failed")
        return {**pub_resp.json(), "upload_mode": upload_mode}

    def _public_media_url(self, job: ContentJob, media_path: str) -> str:
        base_url = getattr(self.config, "public_base_url", "") or ""
        if not base_url:
            return ""
        path = Path(str(media_path))
        filename = quote(path.name)
        return f"{base_url.rstrip().rstrip('/')}/media/public/{quote(job.id)}/{filename}"

    def _post_ig_reel(
        self,
        job: ContentJob,
        caption: str,
        scheduled_time: int | None,
        token: str,
        ig_user_id: str,
    ) -> dict:
        if not job.video_path:
            raise ValueError(f"PublishAgent: video_path is None for job {job.id}")
        headers = self._auth_headers(token)
        file_size = Path(job.video_path).stat().st_size
        url = f"{_META_GRAPH_BASE}/{ig_user_id}/media"
        init_data: dict = {
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption,
        }
        if scheduled_time:
            init_data["scheduled_publish_time"] = str(scheduled_time)
        init_resp = requests.post(
            url,
            data=init_data,
            headers={**headers, "file_size": str(file_size), "file_type": "video/mp4"},
        )
        _raise_for_status_with_body(init_resp, "Instagram Reel container creation failed")
        init_json = init_resp.json()
        container_id = init_json["id"]
        upload_uri = init_json.get(
            "uri",
            f"https://rupload.facebook.com/video-upload/v19.0/{container_id}",
        )
        with open(job.video_path, "rb") as f:
            upload_resp = requests.post(
                upload_uri,
                headers={
                    "Authorization": f"OAuth {token}",
                    "offset": "0",
                    "file_size": str(file_size),
                },
                data=f,
            )
        _raise_for_status_with_body(upload_resp, "Instagram Reel upload failed")
        self._wait_for_ig_container(container_id, token)
        pub_url = f"{_META_GRAPH_BASE}/{ig_user_id}/media_publish"
        pub_resp = requests.post(pub_url, data={"creation_id": container_id}, headers=headers)
        _raise_for_status_with_body(pub_resp, "Instagram Reel publish failed")
        return pub_resp.json()

    def _wait_for_ig_container(self, container_id: str, token: str) -> None:
        url = f"{_META_GRAPH_BASE}/{container_id}"
        headers = self._auth_headers(token)
        elapsed = 0
        last_status = "unknown"
        while elapsed < _IG_CONTAINER_POLL_TIMEOUT:
            resp = requests.get(
                url,
                params={"fields": "status_code"},
                headers=headers,
            )
            _raise_for_status_with_body(resp, "Instagram container status check failed")
            last_status = resp.json().get("status_code", "unknown")
            if last_status == "FINISHED":
                return
            if last_status in {"ERROR", "EXPIRED"}:
                raise RuntimeError(f"Instagram container processing failed: {last_status}")
            time.sleep(_IG_CONTAINER_POLL_INTERVAL)
            elapsed += _IG_CONTAINER_POLL_INTERVAL
        raise TimeoutError(
            f"timed out waiting for Instagram container {container_id} "
            f"to finish processing; last status: {last_status}"
        )
