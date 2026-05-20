from __future__ import annotations
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from models.content_job import (
    BrandProfile, ContentJob, PMProfile, PostPerformance, VisualIdentity, JobStatus,
)


def _make_pm(page_name: str = "Slayhack") -> PMProfile:
    brand = BrandProfile(
        mission="m", visual=VisualIdentity(colors=[], style=""), platforms=[],
        tone="", target_audience="", script_style="", nora_max_retries=2,
    )
    return PMProfile(name="Test PM", page_name=page_name, persona="", brand=brand)


def _make_job(job_id: str, brief: str = "test brief", performance=None, page_name: str = "Slayhack") -> ContentJob:
    job = ContentJob(
        id=job_id,
        project="nayzfreedom_fleet",
        pm=_make_pm(page_name),
        brief=brief,
        platforms=["facebook"],
        status=JobStatus.COMPLETED,
    )
    if performance is not None:
        job.performance = performance
    return job


def _write_job(tmp_path: Path, job: ContentJob) -> None:
    page_name = job.pm.page_name
    job_dir = tmp_path / "output" / page_name / job.id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "job.json").write_text(job.model_dump_json())


TODAY = date(2026, 5, 13)
IN_WINDOW_ID = "20260510_060000"   # 3 days ago — inside window
OUT_WINDOW_ID = "20260505_060000"  # 8 days ago — outside window


def test_reporter_aggregates_jobs_in_window(tmp_path):
    job_in = _make_job(IN_WINDOW_ID, performance=[
        PostPerformance(platform="facebook", reach=1000, likes=50, saves=10, shares=5),
    ])
    job_out = _make_job(OUT_WINDOW_ID, performance=[
        PostPerformance(platform="facebook", reach=999, likes=1, saves=1, shares=1),
    ])
    _write_job(tmp_path, job_in)
    _write_job(tmp_path, job_out)

    from reporter import collect_week_data
    data = collect_week_data(tmp_path, TODAY)

    assert "Slayhack" in data
    assert data["Slayhack"]["facebook"].job_count == 1
    assert data["Slayhack"]["facebook"].total_reach == 1000


def test_reporter_aggregates_metrics_by_platform(tmp_path):
    job1 = _make_job("20260511_060000", brief="brief1", performance=[
        PostPerformance(platform="facebook", reach=1000, likes=50, saves=10, shares=5),
    ])
    job2 = _make_job("20260512_060000", brief="brief2", performance=[
        PostPerformance(platform="facebook", reach=2000, likes=100, saves=20, shares=10),
    ])
    _write_job(tmp_path, job1)
    _write_job(tmp_path, job2)

    from reporter import collect_week_data
    data = collect_week_data(tmp_path, TODAY)

    stats = data["Slayhack"]["facebook"]
    assert stats.job_count == 2
    assert stats.total_reach == 3000
    assert stats.total_likes == 150
    assert stats.total_saves == 30
    assert stats.total_shares == 15


def test_reporter_identifies_top_job_by_reach(tmp_path):
    job1 = _make_job("20260511_060000", brief="low reach post", performance=[
        PostPerformance(platform="facebook", reach=500, likes=10, saves=2, shares=1),
    ])
    job2 = _make_job("20260512_060000", brief="high reach post", performance=[
        PostPerformance(platform="facebook", reach=3000, likes=100, saves=20, shares=10),
    ])
    _write_job(tmp_path, job1)
    _write_job(tmp_path, job2)

    from reporter import collect_week_data
    data = collect_week_data(tmp_path, TODAY)

    stats = data["Slayhack"]["facebook"]
    assert stats.top_job_id == "20260512_060000"
    assert stats.top_job_brief == "high reach post"
    assert stats.top_job_reach == 3000


def test_reporter_uses_latest_snapshot_per_platform(tmp_path):
    older = PostPerformance(
        platform="facebook", reach=500, likes=10, saves=2, shares=1,
        recorded_at=datetime(2026, 5, 11, 6, 0),
    )
    newer = PostPerformance(
        platform="facebook", reach=800, likes=20, saves=5, shares=3,
        recorded_at=datetime(2026, 5, 12, 6, 0),
    )
    job = _make_job("20260511_060000", brief="snapshot test", performance=[older, newer])
    _write_job(tmp_path, job)

    from reporter import collect_week_data
    data = collect_week_data(tmp_path, TODAY)

    stats = data["Slayhack"]["facebook"]
    assert stats.total_reach == 800  # only the newer snapshot counted


def test_reporter_skips_jobs_outside_window(tmp_path):
    job = _make_job(OUT_WINDOW_ID, performance=[
        PostPerformance(platform="facebook", reach=999),
    ])
    _write_job(tmp_path, job)

    from reporter import collect_week_data
    data = collect_week_data(tmp_path, TODAY)

    assert data == {}


def test_reporter_skips_jobs_with_no_performance(tmp_path):
    job = _make_job(IN_WINDOW_ID, performance=[])
    _write_job(tmp_path, job)

    from reporter import collect_week_data
    data = collect_week_data(tmp_path, TODAY)

    assert data == {}


def test_reporter_skips_corrupt_job_file(tmp_path):
    page_dir = tmp_path / "output" / "Slayhack" / IN_WINDOW_ID
    page_dir.mkdir(parents=True)
    (page_dir / "job.json").write_text("not valid json {{{")

    from reporter import collect_week_data
    data = collect_week_data(tmp_path, TODAY)  # must not raise

    assert data == {}


def test_reporter_top_job_set_when_only_one_job(tmp_path):
    job = _make_job(IN_WINDOW_ID, brief="only post", performance=[
        PostPerformance(platform="facebook", reach=0, likes=0, saves=0, shares=0),
    ])
    _write_job(tmp_path, job)

    from reporter import collect_week_data
    data = collect_week_data(tmp_path, TODAY)

    stats = data["Slayhack"]["facebook"]
    assert stats.top_job_id == IN_WINDOW_ID
    assert stats.top_job_brief == "only post"


def test_reporter_top_job_tiebreaker_earlier_id_wins(tmp_path):
    job1 = _make_job("20260511_060000", brief="earlier post", performance=[
        PostPerformance(platform="facebook", reach=1000),
    ])
    job2 = _make_job("20260512_060000", brief="later post", performance=[
        PostPerformance(platform="facebook", reach=1000),
    ])
    _write_job(tmp_path, job1)
    _write_job(tmp_path, job2)

    from reporter import collect_week_data
    data = collect_week_data(tmp_path, TODAY)

    assert data["Slayhack"]["facebook"].top_job_id == "20260511_060000"


def test_reporter_aggregates_multi_platform_job(tmp_path):
    job = _make_job(IN_WINDOW_ID, brief="multi platform", performance=[
        PostPerformance(platform="facebook", reach=1000, likes=50, saves=10, shares=5),
        PostPerformance(platform="instagram", reach=2000, likes=100, saves=20, shares=10),
    ])
    _write_job(tmp_path, job)

    from reporter import collect_week_data
    data = collect_week_data(tmp_path, TODAY)

    assert data["Slayhack"]["facebook"].total_reach == 1000
    assert data["Slayhack"]["instagram"].total_reach == 2000


def test_reporter_output_dir_missing_returns_empty(tmp_path):
    from reporter import collect_week_data
    data = collect_week_data(tmp_path, TODAY)

    assert data == {}


def test_reporter_none_recorded_at_snapshot_not_preferred_over_dated(tmp_path):
    dated = PostPerformance(
        platform="facebook", reach=800, likes=20, saves=5, shares=3,
        recorded_at=datetime(2026, 5, 12, 6, 0),
    )
    undated = PostPerformance(
        platform="facebook", reach=300, likes=5, saves=1, shares=1,
        recorded_at=None,
    )
    # undated appears after dated — should not replace it
    job = _make_job(IN_WINDOW_ID, brief="none recorded_at test", performance=[dated, undated])
    _write_job(tmp_path, job)

    from reporter import collect_week_data
    data = collect_week_data(tmp_path, TODAY)

    assert data["Slayhack"]["facebook"].total_reach == 800


def test_reporter_writes_markdown_file(tmp_path):
    today_id = date.today().strftime("%Y%m%d") + "_060000"
    job = _make_job(today_id, brief="quiet luxury brands", performance=[
        PostPerformance(platform="facebook", reach=3200, likes=80, saves=15, shares=7),
    ])
    _write_job(tmp_path, job)

    with patch("reporter.send_weekly_report"):
        from reporter import run_reporter
        run_reporter(dry_run=True, root=tmp_path)

    report_path = tmp_path / "output" / "Slayhack" / f"weekly_report_{date.today()}.md"
    assert report_path.exists()
    content = report_path.read_text()
    assert "Weekly Report" in content
    assert "3,200" in content
    assert "quiet luxury brands" in content


def test_reporter_no_data_sends_no_data_message(tmp_path):
    (tmp_path / "output").mkdir(parents=True)

    with patch("reporter.send_weekly_report") as mock_alert:
        from reporter import run_reporter
        run_reporter(dry_run=True, root=tmp_path)

    mock_alert.assert_called_once()
    lines = mock_alert.call_args.args[0]
    assert any("no performance data" in line.lower() for line in lines)


def test_reporter_calls_send_weekly_report_with_bar_chart(tmp_path):
    today_id = date.today().strftime("%Y%m%d") + "_060000"
    job = _make_job(today_id, brief="test", performance=[
        PostPerformance(platform="facebook", reach=1000, likes=30, saves=5, shares=2),
    ])
    _write_job(tmp_path, job)

    with patch("reporter.send_weekly_report") as mock_send:
        from reporter import run_reporter
        run_reporter(dry_run=False, root=tmp_path)

    mock_send.assert_called()
    lines = mock_send.call_args.args[0]
    assert any(":bar_chart:" in line for line in lines)
