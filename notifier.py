"""notifier.py — sends scheduler and report alerts."""

from __future__ import annotations

import logging
import os
import sys
from html import escape

import requests

logger = logging.getLogger(__name__)


def _post_slack(message: str, missing_label: str) -> bool:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return False

    try:
        with requests.post(url, json={"text": message}, timeout=10) as resp:
            if not (200 <= resp.status_code < 300):
                print(
                    f"WARNING: Slack {missing_label} webhook returned status {resp.status_code}.",
                    file=sys.stderr,
                )
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: Failed to send Slack {missing_label}: {exc}", file=sys.stderr)
    return True


def _post_telegram(message: str, missing_label: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False

    try:
        with requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "disable_web_page_preview": True,
            },
            timeout=10,
        ) as resp:
            if not (200 <= resp.status_code < 300):
                print(
                    f"WARNING: Telegram {missing_label} returned status {resp.status_code}.",
                    file=sys.stderr,
                )
    except Exception:  # noqa: BLE001
        print(f"WARNING: Failed to send Telegram {missing_label}.", file=sys.stderr)
    return True


def _send_alert(message: str, missing_label: str) -> None:
    if _post_slack(message, missing_label):
        return
    if _post_telegram(message, missing_label):
        return
    print(
        f"WARNING: SLACK_WEBHOOK_URL or TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set — "
        f"skipping {missing_label}.",
        file=sys.stderr,
    )


def send_slack_alert(
    failures: list[dict],
    run_date: str,
    total: int,
    dry_run: bool = False,
) -> None:
    """Send a Slack alert summarising failed pipeline jobs.

    Args:
        failures: List of failure dicts with keys: project, brief, content_type,
                  exit_code (int or None for timeout).
        run_date: Human-readable date string for the run (e.g. "2026-05-13").
        total:    Total number of jobs attempted in the run.
        dry_run:  If True, print the message to stdout instead of posting.
    """
    n = len(failures)
    lines = [
        f":rotating_light: NayzFreedom Scheduler — {n}/{total} jobs failed ({run_date})",
        "",
    ]
    for f in failures:
        label = "timeout" if f["exit_code"] is None else f"exit {f['exit_code']}"
        lines.append(f"• {f['project']} | {f['brief']} | {f['content_type']} → {label}")

    message = "\n".join(lines)

    if dry_run:
        print(message)
        return

    _send_alert(message, "scheduler alert")


def send_weekly_report(lines: list[str], dry_run: bool = False) -> None:
    """Send a weekly performance report to Slack.

    Args:
        lines:   Lines of the report message to join and send.
        dry_run: If True, print the message to stdout instead of posting.
    """
    message = "\n".join(lines)

    if dry_run:
        print(message)
        return

    _send_alert(message, "weekly report")


def send_healthcheck_alert(message: str, dry_run: bool = False) -> None:
    """Send a production health-check alert."""
    if dry_run:
        print(message)
        return

    _send_alert(message, "health-check alert")


def send_telegram_scout_report(config, job) -> None:
    """Send top 3 scout opportunities to Telegram with Approve/Skip buttons."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("Telegram not configured — skipping scout report notification")
        return

    top3 = job.opportunities[:3]
    lines = [f"🔍 <b>Scout Report</b> — {job.job_id}\n"]
    for i, opp in enumerate(top3, 1):
        lines.append(
            f"{i}. <b>{escape(opp.niche_name)}</b> — Score: {opp.reach_score:.0f}\n"
            f"   {escape(opp.target_audience)} | {escape(opp.trend_direction)} | "
            f"{escape(', '.join(opp.platforms))}\n"
        )
    if not top3:
        lines.append("No opportunities found in this scan.\n")
    lines.append("\nApprove a niche to generate project files:")

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": f"✅ {opp.niche_name}"[:64],
                    "callback_data": f"scout_approve:{job.job_id}:{opp.niche_name[:30]}",
                }
            ]
            for opp in top3
        ]
        + [
            [
                {
                    "text": "⏭ Skip this report",
                    "callback_data": f"scout_skip:{job.job_id}",
                }
            ]
        ]
    }

    try:
        from telegram_bot import _api

        _api(
            token,
            "sendMessage",
            chat_id=chat_id,
            text="".join(lines),
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception as exc:
        logger.warning("send_telegram_scout_report failed: %s", exc)
