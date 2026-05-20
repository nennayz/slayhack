from __future__ import annotations

import os

OPS_PUBLIC_BASE_URL = os.environ.get("OPS_PUBLIC_BASE_URL", "https://fleet.nayzfreedom.cloud").rstrip("/")
OPS_UNITS = [
    "nayzfreedom-dashboard.service",
    "nayzfreedom-bot.service",
    "nayzfreedom-scheduler.timer",
    "nayzfreedom-reporter.timer",
    "nayzfreedom-instagram-queue.timer",
    "nayzfreedom-backup.timer",
    "nayzfreedom-healthcheck.timer",
    "nayzfreedom-production-summary.timer",
    "nayzfreedom-log-retention.timer",
    "nayzfreedom-ops-report.timer",
    "nayzfreedom-track-scheduler.timer",
]
OPS_ACTIONS = {
    "backup": {
        "label": "Run backup now",
        "unit": "nayzfreedom-backup.service",
        "verb": "start",
    },
    "instagram_queue": {
        "label": "Run due Instagram queue now",
        "unit": "nayzfreedom-instagram-queue.service",
        "verb": "start",
    },
    "production_summary": {
        "label": "Run production summary now",
        "unit": "nayzfreedom-production-summary.service",
        "verb": "start",
    },
    "ops_report": {
        "label": "Send Ops report now",
        "unit": "nayzfreedom-ops-report.service",
        "verb": "start",
    },
    "track_scheduler": {
        "label": "Run tracking queue now",
        "unit": "nayzfreedom-track-scheduler.service",
        "verb": "start",
    },
    "restart_dashboard": {
        "label": "Restart dashboard",
        "unit": "nayzfreedom-dashboard.service",
        "verb": "restart",
        "delayed": True,
    },
}

OPTIONAL_SERVICE_ENV = {
    "nayzfreedom-bot.service": ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"),
    "nayzfreedom-comment-reply-bot.service": ("COMMENT_BOT_TOKEN", "GEMINI_API_KEY"),
}
