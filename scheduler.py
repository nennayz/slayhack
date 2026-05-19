from __future__ import annotations
import logging
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import yaml
from activity_logger import log_action, log_command
from project_loader import list_project_slugs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent

_KEY_TO_CONTENT_TYPE: dict[str, str] = {
    "short_video_1": "video",
    "short_video_2": "video",
    "long_video": "video",
    "article_1": "article",
    "article_2": "article",
    "infographic_1": "infographic",
    "infographic_2": "infographic",
}

_BRIEF_KEYS = list(_KEY_TO_CONTENT_TYPE.keys())
_LOCK_FILE = Path("/tmp/nayz_pipeline.lock")
_SKIP_LOCK_ENV = "NAYZ_SKIP_PIPELINE_LOCK"


def send_slack_alert(
    failures: list[dict],
    run_date: str,
    total_jobs: int,
    dry_run: bool = False,
) -> None:
    import importlib

    notifier = importlib.import_module("notifier")
    notifier.send_slack_alert(failures, run_date, total_jobs, dry_run=dry_run)


def _today_name() -> str:
    return datetime.now().strftime("%A").lower()


def _video_generation_available() -> bool:
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        return False
    credentials = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    if credentials:
        return Path(credentials).expanduser().exists()
    return (Path.home() / ".config/gcloud/application_default_credentials.json").exists()


def _scheduler_lock_file(root: Path | None) -> Path:
    if root is None:
        return _LOCK_FILE
    return root / "output" / "nayz_pipeline.lock"


def _acquire_scheduler_lock(root: Path | None) -> tuple[Path, bool]:
    lock_file = _scheduler_lock_file(root)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    if lock_file.exists():
        try:
            pid = int(lock_file.read_text().strip())
        except (ValueError, OSError):
            pid = None
        pid_hint = f" (PID {pid})" if pid else ""
        logger.error(
            "another pipeline instance is already running%s; delete %s manually if stale",
            pid_hint,
            lock_file,
        )
        return lock_file, False
    lock_file.write_text(str(os.getpid()))
    return lock_file, True


def _run_job(cmd: list[str], cwd: Path, project_slug: str, key: str, content_type: str) -> dict:
    """Run a single pipeline job subprocess and return a result dict."""
    try:
        env = os.environ.copy()
        env[_SKIP_LOCK_ENV] = "1"
        result = subprocess.run(cmd, cwd=cwd, timeout=1800, env=env)
        if result.returncode != 0:
            logger.error("FAILED: project=%s key=%s", project_slug, key)
            return {"project": project_slug, "brief": key, "content_type": content_type,
                    "exit_code": result.returncode, "failed": True}
        logger.info("OK: project=%s key=%s", project_slug, key)
        return {"project": project_slug, "brief": key, "content_type": content_type, "failed": False}
    except subprocess.TimeoutExpired as exc:
        proc = getattr(exc, "process", None)
        if proc:
            proc.kill()
            proc.communicate()
        logger.error("TIMEOUT: project=%s key=%s", project_slug, key)
        return {"project": project_slug, "brief": key, "content_type": content_type,
                "exit_code": None, "failed": True}


def _run_daily_scout(dry_run: bool = False) -> None:
    if not os.environ.get("BRAVE_SEARCH_API_KEY"):
        logger.debug("BRAVE_SEARCH_API_KEY not set — skipping daily scout")
        return
    try:
        import importlib

        from config import Config

        scout_pipeline = importlib.import_module("scout_pipeline")
        notifier = importlib.import_module("notifier")
        cfg = Config.from_env()
        job = scout_pipeline.run_scout_pipeline(cfg, triggered_by="scheduler", dry_run=dry_run)
        notifier.send_telegram_scout_report(cfg, job)
    except Exception as exc:
        logger.error("Daily scout failed: %s", exc)


def _run_daily_trend_scan(
    active_slugs: list[str],
    dry_run: bool = False,
    root: Path | None = None,
) -> None:
    try:
        from config import Config
        from knowledge.embedder import Embedder, openai_embed_fn
        from knowledge.settings import KnowledgeSettings
        from knowledge.store import KnowledgeStore
        from trend_scout_pipeline import run_trend_scout_pipeline

        cfg = Config.from_env()
        settings_root = root if root is not None else _ROOT
        settings = KnowledgeSettings.from_env(settings_root)
        api_key = os.getenv("OPENAI_API_KEY", "")
        embed_fn = openai_embed_fn(settings.embed_model, api_key)
        store = KnowledgeStore(settings, Embedder(settings.embed_model, embed_fn=embed_fn))
        output_root = root / "output" if root is not None else None

        for slug in active_slugs:
            try:
                if output_root is None:
                    job = run_trend_scout_pipeline(slug, cfg, store, dry_run=dry_run)
                else:
                    job = run_trend_scout_pipeline(slug, cfg, store, dry_run=dry_run, output_root=output_root)
                logger.info(
                    "Trend scan done: page=%s found=%d stored=%d skipped=%d",
                    slug,
                    job.signals_found,
                    job.signals_stored,
                    job.signals_skipped,
                )
            except Exception as exc:
                logger.error("Trend scan failed for %s: %s", slug, exc)
    except Exception as exc:
        logger.error("Daily trend scan setup failed: %s", exc)


def run_scheduler(
    dry_run: bool = False,
    root: Path | None = None,
    max_workers: int = 3,
    safe_prep: bool = False,
    run_scout: bool | None = None,
) -> int:
    _root = root if root is not None else _ROOT
    active_slugs = list_project_slugs(_root)
    calendars = [
        _root / "projects" / slug / "weekly_calendar.yaml"
        for slug in active_slugs
        if (_root / "projects" / slug / "weekly_calendar.yaml").exists()
    ]
    if not calendars and not active_slugs:
        calendars = sorted(_root.glob("projects/*/weekly_calendar.yaml"))
    if not calendars:
        logger.warning("No weekly_calendar.yaml found under projects/")
        return 0

    today = _today_name()
    run_date = datetime.now().strftime("%Y-%m-%d")
    failures: list[dict] = []

    log_action("scheduler_start", {"run_date": run_date, "dry_run": dry_run})
    should_run_scout = root is None if run_scout is None else run_scout
    if should_run_scout:
        _run_daily_scout(dry_run=dry_run)
        _run_daily_trend_scan(active_slugs, dry_run=dry_run, root=root)

    # Collect all jobs to run today across all projects
    pending: list[tuple[list[str], str, str, str]] = []  # (cmd, project_slug, key, content_type)
    for calendar_path in calendars:
        project_slug = calendar_path.parent.name
        with open(calendar_path) as f:
            calendar: dict = yaml.safe_load(f) or {}

        day_entry: dict = calendar.get(today, {})
        if not day_entry:
            logger.warning("No calendar entry for %s in %s — skipping", today, calendar_path)
            continue

        for key in _BRIEF_KEYS:
            brief = day_entry.get(key, "")
            if not brief:
                logger.warning("Blank brief for key=%s project=%s — skipping", key, project_slug)
                continue

            content_type = _KEY_TO_CONTENT_TYPE[key]
            if root is None and not dry_run and content_type == "video" and not _video_generation_available():
                logger.warning(
                    "Skipping video job because Google video credentials are not configured: "
                    "project=%s key=%s",
                    project_slug,
                    key,
                )
                continue

            cmd = [
                sys.executable, "main.py",
                "--project", project_slug,
                "--brief", brief,
                "--content-type", content_type,
                "--schedule",
                "--unattended",
            ]
            if dry_run:
                cmd.append("--dry-run")
            if safe_prep:
                cmd.append("--safe-prep")

            log_command("scheduler_run_command", {
                "project": project_slug,
                "key": key,
                "content_type": content_type,
                "cmd": cmd,
                "dry_run": dry_run,
                "safe_prep": safe_prep,
            })
            pending.append((cmd, project_slug, key, content_type))

    total = len(pending)
    logger.info("Scheduler: %d jobs to run with max_workers=%d", total, max_workers)

    lock_file, lock_acquired = _acquire_scheduler_lock(root)
    if not lock_acquired:
        return 1
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_meta = {
                executor.submit(_run_job, cmd, _root, proj, key, ct): (proj, key)
                for cmd, proj, key, ct in pending
            }
            for future in as_completed(future_to_meta):
                job_result = future.result()
                if job_result["failed"]:
                    failures.append({k: v for k, v in job_result.items() if k != "failed"})
    finally:
        lock_file.unlink(missing_ok=True)

    if failures:
        send_slack_alert(failures, run_date, total, dry_run=dry_run)
    log_action("scheduler_complete", {
        "run_date": run_date,
        "total": total,
        "failures": len(failures),
    })

    return 1 if failures else 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="NayzFreedom daily content scheduler")
    parser.add_argument("--dry-run", action="store_true", help="Pass --dry-run to each main.py call")
    parser.add_argument(
        "--safe-prep",
        action="store_true",
        help="Pass --safe-prep to each main.py call so jobs stop before external publish APIs",
    )
    args = parser.parse_args()
    sys.exit(run_scheduler(dry_run=args.dry_run, safe_prep=args.safe_prep))
