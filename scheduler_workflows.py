from __future__ import annotations

import logging
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


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

def _run_daily_idea_planner(
    active_slugs: list[str],
    dry_run: bool = False,
    root: Path | None = None,
) -> None:
    try:
        from config import Config
        from idea_planner_pipeline import run_idea_planner_pipeline
        from knowledge.embedder import Embedder, openai_embed_fn
        from knowledge.settings import KnowledgeSettings
        from knowledge.store import KnowledgeStore

        cfg = Config.from_env()
        settings_root = root if root is not None else _ROOT
        settings = KnowledgeSettings.from_env(settings_root)
        api_key = os.getenv("OPENAI_API_KEY", "")
        embed_fn = openai_embed_fn(settings.embed_model, api_key)
        store = KnowledgeStore(settings, Embedder(settings.embed_model, embed_fn=embed_fn))
        output_root = root / "output" if root is not None else None

        for slug in active_slugs:
            try:
                kwargs: dict = {"dry_run": dry_run}
                if output_root is not None:
                    kwargs["output_root"] = output_root
                job = run_idea_planner_pipeline(slug, cfg, store, **kwargs)
                logger.info(
                    "Idea planner done: page=%s generated=%d stored=%d skipped=%d",
                    slug,
                    job.ideas_generated,
                    job.ideas_stored,
                    job.ideas_skipped,
                )
            except Exception as exc:
                logger.error("Idea planner failed for %s: %s", slug, exc)
    except Exception as exc:
        logger.error("Daily idea planner setup failed: %s", exc)

def _run_daily_production_loop(
    active_slugs: list[str],
    dry_run: bool = False,
    root: Path | None = None,
) -> None:
    try:
        import os
        from config import Config
        from knowledge.embedder import Embedder, openai_embed_fn
        from knowledge.settings import KnowledgeSettings
        from knowledge.store import KnowledgeStore
        from production_loop import run_production_loop

        cfg = Config.from_env()
        settings_root = root if root is not None else _ROOT
        settings = KnowledgeSettings.from_env(settings_root)
        api_key = os.getenv("OPENAI_API_KEY", "")
        embed_fn = openai_embed_fn(settings.embed_model, api_key)
        store = KnowledgeStore(settings, Embedder(settings.embed_model, embed_fn=embed_fn))
        output_root = root / "output" if root is not None else None

        for slug in active_slugs:
            try:
                kwargs: dict = {"dry_run": dry_run}
                if output_root is not None:
                    kwargs["output_root"] = output_root
                result = run_production_loop(slug, cfg, store, **kwargs)
                logger.info(
                    "Production loop done: page=%s found=%d started=%d completed=%d failed=%d",
                    slug, result.ideas_found, result.jobs_started,
                    result.jobs_completed, result.jobs_failed,
                )
            except Exception as exc:
                logger.error("Production loop failed for %s: %s", slug, exc)
    except Exception as exc:
        logger.error("Daily production loop setup failed: %s", exc)

def _run_daily_social_packaging(
    active_slugs: list[str],
    dry_run: bool = False,
    root: Path | None = None,
) -> None:
    try:
        import os
        from knowledge.embedder import Embedder, openai_embed_fn
        from knowledge.settings import KnowledgeSettings
        from knowledge.store import KnowledgeStore
        from social_packaging import run_social_packaging

        settings_root = root if root is not None else _ROOT
        settings = KnowledgeSettings.from_env(settings_root)
        api_key = os.getenv("OPENAI_API_KEY", "")
        embed_fn = openai_embed_fn(settings.embed_model, api_key)
        store = KnowledgeStore(settings, Embedder(settings.embed_model, embed_fn=embed_fn))

        for slug in active_slugs:
            try:
                result = run_social_packaging(slug, store, root=settings_root, dry_run=dry_run)
                logger.info(
                    "Social packaging done: page=%s found=%d packaged=%d queued=%d skipped=%d failed=%d",
                    slug, result.jobs_found, result.packages_created,
                    result.queue_entries_created, result.jobs_skipped, result.jobs_failed,
                )
            except Exception as exc:
                logger.error("Social packaging failed for %s: %s", slug, exc)
    except Exception as exc:
        logger.error("Daily social packaging setup failed: %s", exc)
