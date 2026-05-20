from __future__ import annotations
import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from models.content_job import ContentJob, PostPerformance
from notifier import send_weekly_report

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent


@dataclass
class PlatformStats:
    job_count: int = 0
    total_reach: int = 0
    total_likes: int = 0
    total_saves: int = 0
    total_shares: int = 0
    top_job_id: str = ""
    top_job_brief: str = ""
    top_job_reach: int = 0


def _in_window(job_id: str, today: date) -> bool:
    try:
        job_date = date(int(job_id[:4]), int(job_id[4:6]), int(job_id[6:8]))
        return (today - timedelta(days=6)) <= job_date <= today
    except (ValueError, IndexError):
        return False


def _latest_perf_per_platform(performances: list[PostPerformance]) -> dict[str, PostPerformance]:
    latest: dict[str, PostPerformance] = {}
    for p in performances:
        if p.platform not in latest:
            latest[p.platform] = p
        else:
            existing = latest[p.platform]
            if p.recorded_at is not None and (
                existing.recorded_at is None or p.recorded_at > existing.recorded_at
            ):
                latest[p.platform] = p
    return latest


def collect_week_data(root: Path, today: date) -> dict[str, dict[str, PlatformStats]]:
    output_dir = root / "output"
    if not output_dir.exists():
        return {}

    result: dict[str, dict[str, PlatformStats]] = {}

    for job_file in output_dir.glob("*/*/job.json"):
        page_name = job_file.parent.parent.name
        try:
            job = ContentJob.model_validate_json(job_file.read_text())
        except Exception as exc:
            logger.warning("Skipping corrupt job file %s: %s", job_file, exc)
            continue

        if not _in_window(job.id, today):
            continue

        if not job.performance:
            continue

        latest = _latest_perf_per_platform(job.performance)

        if page_name not in result:
            result[page_name] = {}

        for platform, perf in latest.items():
            if platform not in result[page_name]:
                result[page_name][platform] = PlatformStats()
            stats = result[page_name][platform]
            stats.job_count += 1
            reach = perf.reach or 0
            stats.total_reach += reach
            stats.total_likes += perf.likes or 0
            stats.total_saves += perf.saves or 0
            stats.total_shares += perf.shares or 0
            if (not stats.top_job_id) or reach > stats.top_job_reach or (
                reach == stats.top_job_reach and job.id < stats.top_job_id
            ):
                stats.top_job_id = job.id
                stats.top_job_brief = job.brief
                stats.top_job_reach = reach

    return result


def _format_markdown(
    page_name: str,
    data: dict[str, PlatformStats],
    start_date: date,
    end_date: date,
) -> str:
    lines = [
        f"# Weekly Report — {page_name} ({start_date} → {end_date})",
        "",
    ]
    if not data:
        lines.append("No performance data found for this period.")
    else:
        for platform, stats in sorted(data.items()):
            lines += [
                f"## {platform}",
                f"- Jobs tracked: {stats.job_count}",
                f"- Total reach: {stats.total_reach:,}",
                f"- Total likes: {stats.total_likes:,}",
                f"- Total saves: {stats.total_saves:,}",
                f"- Total shares: {stats.total_shares:,}",
            ]
            if stats.top_job_id:
                lines.append(
                    f'- Top post: {stats.top_job_id} — "{stats.top_job_brief}"'
                    f" (reach: {stats.top_job_reach:,})"
                )
            lines.append("")
    lines += ["---", f"Generated: {end_date}"]
    return "\n".join(lines)


def _format_slack(
    page_name: str,
    data: dict[str, PlatformStats],
    start_date: date,
    end_date: date,
) -> list[str]:
    lines = [f":bar_chart: Weekly Report — {page_name} ({start_date} → {end_date})", ""]
    if not data:
        lines.append("No performance data found for this period.")
    else:
        for platform, stats in sorted(data.items()):
            lines.append(f"{platform} — {stats.job_count} jobs")
            lines.append(
                f"  reach: {stats.total_reach:,} | likes: {stats.total_likes:,}"
                f" | saves: {stats.total_saves:,} | shares: {stats.total_shares:,}"
            )
            if stats.top_job_id:
                lines.append(
                    f'  Top: {stats.top_job_id} — "{stats.top_job_brief}"'
                    f" (reach {stats.top_job_reach:,})"
                )
            lines.append("")
    return lines


def run_reporter(dry_run: bool = False, root: Path | None = None) -> int:
    _root = root if root is not None else _ROOT
    today = date.today()
    start_date = today - timedelta(days=6)

    all_data = collect_week_data(_root, today)

    if not all_data:
        logger.warning("No performance data found for any page in the last 7 days.")
        send_weekly_report(
            [f":bar_chart: Weekly Report — no performance data found for {start_date} → {today}."],
            dry_run=dry_run,
        )
        return 0

    for page_name, page_data in sorted(all_data.items()):
        md = _format_markdown(page_name, page_data, start_date, today)
        out_path = _root / "output" / page_name / f"weekly_report_{today}.md"
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(md)
            logger.info("Report written to %s", out_path)
        except OSError as exc:
            logger.error("Failed to write report for %s: %s", page_name, exc)

        slack_lines = _format_slack(page_name, page_data, start_date, today)
        send_weekly_report(slack_lines, dry_run=dry_run)

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NayzFreedom weekly performance reporter")
    parser.add_argument("--dry-run", action="store_true", help="Print Slack message to stdout instead of posting")
    args = parser.parse_args()
    sys.exit(run_reporter(dry_run=args.dry_run))
