from __future__ import annotations
import hashlib

import pytest
from unittest.mock import MagicMock
from knowledge.embedder import Embedder
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore
from models.trend_scan_job import TrendScanJobStatus


@pytest.fixture
def store(tmp_path):
    def fake_embed(texts):
        vectors = []
        for text in texts:
            idx = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:2], 16) % 64
            vector = [0.0] * 64
            vector[idx] = 1.0
            vectors.append(vector)
        return vectors

    settings = KnowledgeSettings(root=tmp_path)
    return KnowledgeStore(settings, Embedder("test-model", embed_fn=fake_embed))


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.brave_search_api_key = ""
    cfg.reddit_client_id = ""
    return cfg


def test_dry_run_stores_five_objects(store, config, tmp_path):
    from trend_scout_pipeline import run_trend_scout_pipeline
    job = run_trend_scout_pipeline(
        "nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path
    )
    assert job.status == TrendScanJobStatus.COMPLETED
    assert job.signals_found == 5
    assert job.signals_stored == 5
    assert job.signals_skipped == 0


def test_stored_objects_have_correct_kind(store, config, tmp_path):
    from trend_scout_pipeline import run_trend_scout_pipeline
    run_trend_scout_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    recent = store.recent(kind="trend_signal", page="nayzfreedom_fleet", limit=10)
    assert len(recent) == 5
    assert all(obj.kind == "trend_signal" for obj in recent)


def test_dedup_idempotency(store, config, tmp_path):
    from trend_scout_pipeline import run_trend_scout_pipeline
    run_trend_scout_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    job2 = run_trend_scout_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    assert job2.signals_stored == 0
    assert job2.signals_skipped == 5


def test_no_seed_topics_returns_completed_immediately(store, config, tmp_path):
    from trend_scout_pipeline import run_trend_scout_pipeline
    # "unknown_page" has no brand.yaml → load_scout_seed_topics returns []
    job = run_trend_scout_pipeline("unknown_page", config, store, dry_run=True, output_root=tmp_path)
    assert job.status == TrendScanJobStatus.COMPLETED
    assert job.signals_found == 0
    assert job.signals_stored == 0
