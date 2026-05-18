from __future__ import annotations
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from config import Config
from agents.scout import ScoutAgent
from agents.analyst import AnalystAgent
from agents.architect import ArchitectAgent
from models.niche_opportunity import ScoutJob, ScoutJobStatus

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent
_OUTPUT_ROOT = _ROOT / "output"


def run_scout_pipeline(
    config: Config,
    triggered_by: str = "scheduler",
    dry_run: bool = False,
    output_root: Path = _OUTPUT_ROOT,
) -> ScoutJob:
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    job = ScoutJob(job_id=job_id, triggered_by=triggered_by)

    logger.info("Scout pipeline started (job=%s, dry_run=%s)", job_id, dry_run)

    scout = ScoutAgent(config)
    job = scout.run(job, dry_run=dry_run)
    logger.info("Scout done: %d signals collected", len(job.signals))

    analyst = AnalystAgent(config)
    job = analyst.run(job, dry_run=dry_run)
    logger.info("Analyst done: %d opportunities ranked", len(job.opportunities))

    _save_report(job, output_root)
    _maybe_export_to_drive(job, config)

    job.status = ScoutJobStatus.AWAITING_APPROVAL
    return job


def approve_niche(
    job: ScoutJob,
    niche_name: str,
    config: Config,
    projects_root: Path = _ROOT / "projects",
) -> str:
    job.approved_niche = niche_name
    architect = ArchitectAgent(config)
    slug = architect.run(job, projects_root=projects_root)
    job.status = ScoutJobStatus.COMPLETED
    logger.info("Architect done: project created at projects/%s/", slug)
    return slug


def _save_report(job: ScoutJob, output_root: Path) -> None:
    reports_dir = output_root / "scout_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{job.job_id}-scout-report.json"
    report_path.write_text(job.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Scout report saved to %s", report_path)


def _maybe_export_to_drive(job: ScoutJob, config: Config) -> None:
    if not config.scout_drive_folder_id:
        return
    from google_drive import upload_file_to_drive
    tmp_path = None
    try:
        content = _format_report_markdown(job)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            tmp_path = f.name
        upload_file_to_drive(
            source_path=tmp_path,
            folder_id=config.scout_drive_folder_id,
            dest_name=f"scout_report_{job.job_id}.md",
            credential_path=config.google_application_credentials or None,
        )
        logger.info("Scout report uploaded to Google Drive")
    except Exception as exc:
        logger.warning("Google Drive export failed: %s", exc)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _format_report_markdown(job: ScoutJob) -> str:
    lines = [f"# Scout Report — {job.job_id}\n", f"Triggered by: {job.triggered_by}\n\n"]
    if not job.opportunities:
        lines.append("No opportunities found in this scan.\n")
        return "".join(lines)
    for i, opp in enumerate(job.opportunities, 1):
        lines.append(f"## {i}. {opp.niche_name} (Score: {opp.reach_score})\n")
        lines.append(f"- **Audience:** {opp.target_audience}\n")
        lines.append(f"- **Platforms:** {', '.join(opp.platforms)}\n")
        lines.append(f"- **Trend:** {opp.trend_direction}\n")
        lines.append(f"- **Formats:** {', '.join(opp.content_formats)}\n")
        lines.append(f"- **Monetization:** {opp.monetization_notes}\n\n")
    return "".join(lines)
