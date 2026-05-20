"""
SP-2 IdeaPlanner end-to-end acceptance test.

Covers all 7 requirements from the design spec:
  1. dry-run stores 7 ContentObjects with kind="idea", status="new"
  2. dedup idempotency — second run stores 0, skips 7
  3. status transition — approve flips to "approved" in vault + index
  4. empty KS fallback — no trend signals → still generates 7 ideas
  5. LLM JSON resilience — malformed response → IdeaPlanJob with stored < 7, no crash
  6. digest written with all 7 titles
  7. dashboard list filter — status=new vs status=approved segregation
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from knowledge.embedder import Embedder
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore
from models.idea_plan_job import IdeaPlanJobStatus


@pytest.fixture
def store(tmp_path):
    settings = KnowledgeSettings(root=tmp_path)
    embedder = Embedder("test", embed_fn=lambda texts: [[0.0] * 4 for _ in texts])
    return KnowledgeStore(settings, embedder)


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.openai_api_key = ""
    cfg.openai_agent_model = "gpt-4o-mini"
    return cfg


# ── Requirement 1: dry-run stores 7 ideas ────────────────────────────────────

def test_r1_dry_run_stores_seven_new_ideas(store, config, tmp_path):
    from idea_planner_pipeline import run_idea_planner_pipeline
    job = run_idea_planner_pipeline(
        "nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path
    )
    assert job.status == IdeaPlanJobStatus.COMPLETED
    assert job.ideas_stored == 7
    ideas = store.recent(kind="idea", page="nayzfreedom_fleet")
    assert len(ideas) == 7
    assert all(o.kind == "idea" for o in ideas)
    assert all(o.status == "new" for o in ideas)


# ── Requirement 2: dedup idempotency ─────────────────────────────────────────

def test_r2_dedup_idempotency(store, config, tmp_path):
    from idea_planner_pipeline import run_idea_planner_pipeline
    run_idea_planner_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    job2 = run_idea_planner_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    assert job2.ideas_stored == 0
    assert job2.ideas_skipped == 7


# ── Requirement 3: status transition persists in vault + index ────────────────

def test_r3_approve_persists_in_vault_and_index(store, config, tmp_path):
    from idea_planner_pipeline import run_idea_planner_pipeline
    run_idea_planner_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    ideas = store.recent(kind="idea", page="nayzfreedom_fleet", status="new")
    target = ideas[0]
    store.set_status(target.uid, "approved")

    # Verify index
    from_index = store.get(target.uid)
    assert from_index is not None
    assert from_index.status == "approved"

    # Verify vault is source of truth (rebuild index, then re-read)
    store.rebuild_index()
    from_vault = store.get(target.uid)
    assert from_vault is not None
    assert from_vault.status == "approved"


# ── Requirement 4: empty KS → brand-only context → still 7 ideas ─────────────

def test_r4_empty_ks_fallback_generates_ideas(store, config, tmp_path):
    from idea_planner_pipeline import run_idea_planner_pipeline
    # store is empty (no trend signals added)
    job = run_idea_planner_pipeline(
        "nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path
    )
    assert job.ideas_generated == 7
    assert job.ideas_stored == 7


# ── Requirement 5: LLM JSON resilience ───────────────────────────────────────

def test_r5_malformed_llm_response_no_crash(store, config, tmp_path):
    from agents.idea_planner import IdeaPlannerAgent
    from idea_planner_pipeline import run_idea_planner_pipeline

    with patch.object(IdeaPlannerAgent, "_generate_live", return_value=[]):
        job = run_idea_planner_pipeline(
            "nayzfreedom_fleet", config, store, dry_run=False, output_root=tmp_path
        )
    # Pipeline completes without exception; stored may be 0
    assert job.status == IdeaPlanJobStatus.COMPLETED
    assert job.ideas_stored < 7


# ── Requirement 6: digest file with all 7 titles ─────────────────────────────

def test_r6_digest_written_with_all_titles(store, config, tmp_path):
    from idea_planner_pipeline import run_idea_planner_pipeline
    date_str = datetime.now().strftime("%Y%m%d")
    run_idea_planner_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    digest = tmp_path / "nayzfreedom_fleet" / "ideas" / date_str / "idea_digest.md"
    assert digest.exists()
    content = digest.read_text()
    for title in [
        "Invisible Lip Liner Hack",
        "Quiet Luxury Morning Routine",
        "5 Dupes That Beat the Original",
        "3-Step Kiss-Proof Secret",
        "Get Ready With Me",
        "60-Second Glow Up",
        "Skincare Order Matters",
    ]:
        assert title in content, f"Missing title in digest: {title!r}"


# ── Requirement 7: dashboard list filter by status ────────────────────────────

def test_r7_dashboard_list_filter_by_status(store, config, tmp_path):
    from idea_planner_pipeline import run_idea_planner_pipeline
    run_idea_planner_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    ideas = store.recent(kind="idea", page="nayzfreedom_fleet", status="new")
    assert len(ideas) == 7

    # Approve one
    store.set_status(ideas[0].uid, "approved")

    new_only = store.recent(kind="idea", page="nayzfreedom_fleet", status="new")
    approved_only = store.recent(kind="idea", page="nayzfreedom_fleet", status="approved")
    assert len(new_only) == 6
    assert len(approved_only) == 1
    assert approved_only[0].uid == ideas[0].uid
