from __future__ import annotations
from unittest.mock import patch, MagicMock

from models.niche_opportunity import NicheOpportunity, ScoutJob
from notifier import send_healthcheck_alert, send_slack_alert, send_telegram_scout_report, send_weekly_report


FAILURES_ONE = [
    {"project": "nayzfreedom_fleet", "brief": "article_1", "content_type": "article", "exit_code": 1},
]
FAILURES_TIMEOUT = [
    {"project": "nayzfreedom_fleet", "brief": "short_video_1", "content_type": "video", "exit_code": None},
]
FAILURES_TWO = FAILURES_ONE + FAILURES_TIMEOUT


def test_send_slack_alert_dry_run_prints_message(capsys, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/fake")
    send_slack_alert(FAILURES_ONE, "2026-05-13", total=7, dry_run=True)
    out = capsys.readouterr().out
    assert "1/7 jobs failed" in out
    assert "nayzfreedom_fleet" in out
    assert "article_1" in out
    assert "article" in out
    assert "exit 1" in out


def test_send_slack_alert_posts_to_webhook(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/fake")
    mock_post = MagicMock()
    mock_post.return_value.__enter__ = lambda s: mock_post.return_value
    mock_post.return_value.__exit__ = MagicMock(return_value=False)
    mock_post.return_value.status_code = 200
    with patch("notifier.requests.post", mock_post):
        send_slack_alert(FAILURES_ONE, "2026-05-13", total=7, dry_run=False)
    mock_post.assert_called_once()
    assert mock_post.call_args.args[0] == "https://hooks.slack.com/fake"
    assert "1/7 jobs failed" in mock_post.call_args.kwargs["json"]["text"]
    assert "nayzfreedom_fleet" in mock_post.call_args.kwargs["json"]["text"]


def test_send_slack_alert_missing_env_skips(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    mock_post = MagicMock()
    with patch("notifier.requests.post", mock_post):
        send_slack_alert(FAILURES_ONE, "2026-05-13", total=7, dry_run=False)
    mock_post.assert_not_called()


def test_send_slack_alert_non_2xx_does_not_raise(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/fake")
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: mock_resp
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.status_code = 500
    with patch("notifier.requests.post", return_value=mock_resp):
        send_slack_alert(FAILURES_ONE, "2026-05-13", total=7, dry_run=False)  # must not raise


def test_send_slack_alert_timeout_label_text(capsys, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/fake")
    send_slack_alert(FAILURES_TIMEOUT, "2026-05-13", total=7, dry_run=True)
    out = capsys.readouterr().out
    assert "timeout" in out


def test_send_slack_alert_two_failures(capsys, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/fake")
    send_slack_alert(FAILURES_TWO, "2026-05-13", total=7, dry_run=True)
    out = capsys.readouterr().out
    assert "2/7 jobs failed" in out
    assert "exit 1" in out
    assert "timeout" in out


def test_send_slack_alert_request_exception_does_not_raise(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/fake")
    with patch("notifier.requests.post", side_effect=Exception("network error")):
        send_slack_alert(FAILURES_ONE, "2026-05-13", total=7, dry_run=False)  # must not raise


def test_send_weekly_report_dry_run_prints(capsys, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/fake")
    send_weekly_report([":bar_chart: Weekly Report", "", "Facebook — 3 jobs"], dry_run=True)
    out = capsys.readouterr().out
    assert ":bar_chart: Weekly Report" in out
    assert "Facebook — 3 jobs" in out


def test_send_weekly_report_posts_to_webhook(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/fake")
    mock_post = MagicMock()
    mock_post.return_value.__enter__ = lambda s: mock_post.return_value
    mock_post.return_value.__exit__ = MagicMock(return_value=False)
    mock_post.return_value.status_code = 200
    with patch("notifier.requests.post", mock_post):
        send_weekly_report([":bar_chart: Weekly Report", "Facebook — 3 jobs"], dry_run=False)
    mock_post.assert_called_once()
    assert ":bar_chart: Weekly Report" in mock_post.call_args.kwargs["json"]["text"]


def test_send_weekly_report_missing_env_skips(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    mock_post = MagicMock()
    with patch("notifier.requests.post", mock_post):
        send_weekly_report([":bar_chart: Weekly Report"], dry_run=False)
    mock_post.assert_not_called()


def test_send_weekly_report_non_2xx_does_not_raise(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/fake")
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: mock_resp
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.status_code = 500
    with patch("notifier.requests.post", return_value=mock_resp):
        send_weekly_report([":bar_chart: Weekly Report"], dry_run=False)  # must not raise


def test_send_weekly_report_request_exception_does_not_raise(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/fake")
    with patch("notifier.requests.post", side_effect=Exception("network error")):
        send_weekly_report([":bar_chart: Weekly Report"], dry_run=False)  # must not raise


def test_send_slack_alert_uses_telegram_fallback(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")
    mock_post = MagicMock()
    mock_post.return_value.__enter__ = lambda s: mock_post.return_value
    mock_post.return_value.__exit__ = MagicMock(return_value=False)
    mock_post.return_value.status_code = 200
    with patch("notifier.requests.post", mock_post):
        send_slack_alert(FAILURES_ONE, "2026-05-13", total=7, dry_run=False)
    mock_post.assert_called_once()
    assert mock_post.call_args.args[0] == "https://api.telegram.org/bottelegram-token/sendMessage"
    assert "1/7 jobs failed" in mock_post.call_args.kwargs["json"]["text"]


def test_send_weekly_report_uses_telegram_fallback(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")
    mock_post = MagicMock()
    mock_post.return_value.__enter__ = lambda s: mock_post.return_value
    mock_post.return_value.__exit__ = MagicMock(return_value=False)
    mock_post.return_value.status_code = 200
    with patch("notifier.requests.post", mock_post):
        send_weekly_report([":bar_chart: Weekly Report"], dry_run=False)
    mock_post.assert_called_once()
    assert mock_post.call_args.args[0] == "https://api.telegram.org/bottelegram-token/sendMessage"
    assert ":bar_chart: Weekly Report" in mock_post.call_args.kwargs["json"]["text"]


def test_send_healthcheck_alert_dry_run_prints(capsys, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/fake")
    send_healthcheck_alert("health failed", dry_run=True)
    out = capsys.readouterr().out
    assert "health failed" in out


def test_send_healthcheck_alert_uses_telegram_fallback(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")
    mock_post = MagicMock()
    mock_post.return_value.__enter__ = lambda s: mock_post.return_value
    mock_post.return_value.__exit__ = MagicMock(return_value=False)
    mock_post.return_value.status_code = 200
    with patch("notifier.requests.post", mock_post):
        send_healthcheck_alert("health failed")
    mock_post.assert_called_once()
    assert mock_post.call_args.args[0] == "https://api.telegram.org/bottelegram-token/sendMessage"
    assert "health failed" in mock_post.call_args.kwargs["json"]["text"]


def _scout_job(opportunities: list[NicheOpportunity] | None = None) -> ScoutJob:
    return ScoutJob(
        job_id="20260518_010203",
        triggered_by="telegram",
        opportunities=opportunities or [],
    )


def _opportunity(name: str, score: float = 91.0) -> NicheOpportunity:
    return NicheOpportunity(
        niche_name=name,
        target_audience="Women USA 25-40",
        platforms=["instagram", "tiktok"],
        reach_score=score,
        trend_direction="rising",
        content_formats=["reel"],
        monetization_notes="Low-ticket guide candidate",
        signals={"source": "dry-run"},
    )


def test_send_telegram_scout_report_sends_top_three(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")
    mock_api = MagicMock()

    job = _scout_job(
        [
            _opportunity("clean beauty", 91),
            _opportunity("quiet luxury", 85),
            _opportunity("finance for women", 79),
            _opportunity("extra niche", 70),
        ]
    )

    with patch("telegram_bot._api", mock_api):
        send_telegram_scout_report(None, job)

    mock_api.assert_called_once()
    kwargs = mock_api.call_args.kwargs
    assert kwargs["chat_id"] == "123456"
    assert "Scout Report" in kwargs["text"]
    assert "clean beauty" in kwargs["text"]
    assert "extra niche" not in kwargs["text"]
    assert kwargs["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == (
        "scout_approve:20260518_010203:clean beauty"
    )
    assert kwargs["reply_markup"]["inline_keyboard"][-1][0]["callback_data"] == "scout_skip:20260518_010203"


def test_send_telegram_scout_report_handles_no_opportunities(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")
    mock_api = MagicMock()

    with patch("telegram_bot._api", mock_api):
        send_telegram_scout_report(None, _scout_job())

    kwargs = mock_api.call_args.kwargs
    assert "No opportunities found" in kwargs["text"]
    assert kwargs["reply_markup"]["inline_keyboard"] == [
        [{"text": "⏭ Skip this report", "callback_data": "scout_skip:20260518_010203"}]
    ]


def test_send_telegram_scout_report_missing_env_skips(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with patch("telegram_bot._api") as mock_api:
        send_telegram_scout_report(None, _scout_job([_opportunity("clean beauty")]))

    mock_api.assert_not_called()
