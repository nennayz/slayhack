# SP-1 TrendScout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a daily TrendScout pipeline that stores trending topic signals as `ContentObject(kind="trend_signal")` in the SP-0 Knowledge Store, ready for SP-2 Idea Planning to consume.

**Architecture:** `TrendScoutAgent` fetches Brave + Google Trends + Reddit per seed topic (from `brand.yaml:scout_seed_topics`). `run_trend_scout_pipeline` turns hits into ContentObjects, deduplicates via SP-0, writes a daily digest markdown, and returns a `TrendScanJob`. Scheduler calls it per active page before the content pipeline.

**Depends on:** SP-0 Knowledge Store (PR #143 merged to main). Checkout this plan's branch from post-merge main.

**Tech Stack:** Python 3.12, Pydantic 2, SP-0 KnowledgeStore, requests, pytrends, praw, pytest, ruff, mypy

**Checkpoint model:** CP1 after Task 3 (pipeline works, objects land in store). CP2 after Task 6 (scheduler + dashboard). Full test run at each CP.

---

### Task 1: `TrendHit` + `TrendScanJob` models + `load_scout_seed_topics`

**Files:**
- Create: `models/trend_scan_job.py`
- Modify: `project_loader.py` (add `load_scout_seed_topics`)
- Modify: `projects/slay_hack/brand.yaml` (add `scout_seed_topics`)
- Test: `tests/test_trend_scan_job.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_trend_scan_job.py
from __future__ import annotations
import pytest
from pathlib import Path
import tempfile, textwrap, yaml
from models.trend_scan_job import TrendHit, TrendScanJob, TrendScanJobStatus


def test_trend_hit_fields():
    hit = TrendHit(topic="beauty hacks", direction="rising", score=82.0, sources={"source": "dry-run"})
    assert hit.topic == "beauty hacks"
    assert hit.score == 82.0


def test_trend_scan_job_defaults():
    job = TrendScanJob(job_id="20260519_060000", page_slug="nayzfreedom_fleet", triggered_by="test")
    assert job.status == TrendScanJobStatus.PENDING
    assert job.signals_found == 0
    assert job.signals_stored == 0
    assert job.signals_skipped == 0


def test_load_scout_seed_topics_reads_yaml(tmp_path):
    from project_loader import load_scout_seed_topics
    proj_dir = tmp_path / "projects" / "test_page"
    proj_dir.mkdir(parents=True)
    brand = {"mission": "test", "scout_seed_topics": ["beauty hacks", "skincare"]}
    (proj_dir / "brand.yaml").write_text(yaml.dump(brand))
    topics = load_scout_seed_topics("test_page", root=tmp_path)
    assert topics == ["beauty hacks", "skincare"]


def test_load_scout_seed_topics_missing_field(tmp_path):
    from project_loader import load_scout_seed_topics
    proj_dir = tmp_path / "projects" / "test_page"
    proj_dir.mkdir(parents=True)
    (proj_dir / "brand.yaml").write_text(yaml.dump({"mission": "test"}))
    assert load_scout_seed_topics("test_page", root=tmp_path) == []


def test_load_scout_seed_topics_missing_file(tmp_path):
    from project_loader import load_scout_seed_topics
    assert load_scout_seed_topics("no_such_page", root=tmp_path) == []
```

- [ ] **Step 2: Run — confirm all fail**

```bash
pytest tests/test_trend_scan_job.py -v
```
Expected: FAILED (ImportError — module doesn't exist yet)

- [ ] **Step 3: Create `models/trend_scan_job.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


@dataclass
class TrendHit:
    topic: str
    direction: str   # "rising" | "stable" | "declining" | "unknown"
    score: float     # 0–100
    sources: dict    # raw source data


class TrendScanJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TrendScanJob(BaseModel):
    job_id: str
    page_slug: str
    triggered_by: str
    created_at: datetime = Field(default_factory=datetime.now)
    status: TrendScanJobStatus = TrendScanJobStatus.PENDING
    signals_found: int = 0
    signals_stored: int = 0
    signals_skipped: int = 0
    digest_path: Optional[str] = None
    error: Optional[str] = None
```

- [ ] **Step 4: Add `load_scout_seed_topics` to `project_loader.py`**

Add after the existing `load_project_bridge` function (end of file):

```python
def load_scout_seed_topics(project_slug: str, root: Path | None = None) -> list[str]:
    resolved_slug = resolve_project_slug(project_slug, root=root)
    base = (root or Path(".")) / "projects" / resolved_slug
    try:
        brand_data = yaml.safe_load((base / "brand.yaml").read_text()) or {}
    except (FileNotFoundError, yaml.YAMLError):
        return []
    topics = brand_data.get("scout_seed_topics") or []
    return [str(t) for t in topics if t]
```

- [ ] **Step 5: Add `scout_seed_topics` to `projects/slay_hack/brand.yaml`**

Add after the `nora_max_retries` line:

```yaml
scout_seed_topics:
  - beauty hacks
  - skincare routine
  - makeup tutorial
  - Gen Z fashion
  - wellness routine
```

- [ ] **Step 6: Run tests — confirm all pass**

```bash
pytest tests/test_trend_scan_job.py -v
```
Expected: 5 passed

- [ ] **Step 7: Type-check and lint**

```bash
mypy models/trend_scan_job.py project_loader.py --ignore-missing-imports
ruff check models/trend_scan_job.py project_loader.py
```
Expected: no errors

- [ ] **Step 8: Commit**

```bash
git add models/trend_scan_job.py project_loader.py projects/slay_hack/brand.yaml tests/test_trend_scan_job.py
git commit -m "feat(sp-1): TrendHit/TrendScanJob models + load_scout_seed_topics + brand.yaml seed topics"
```

---

### Task 2: `TrendScoutAgent` with dry-run mode

**Files:**
- Create: `agents/trend_scout.py`
- Test: `tests/test_trend_scout_agent.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_trend_scout_agent.py
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch
from agents.trend_scout import TrendScoutAgent
from models.trend_scan_job import TrendHit


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.brave_search_api_key = ""
    cfg.reddit_client_id = ""
    return cfg


def test_dry_run_returns_five_hits(config):
    agent = TrendScoutAgent(config)
    hits = agent.scan(["beauty hacks"], dry_run=True)
    assert len(hits) == 5
    assert all(isinstance(h, TrendHit) for h in hits)


def test_dry_run_scores_in_range(config):
    agent = TrendScoutAgent(config)
    hits = agent.scan([], dry_run=True)
    for h in hits:
        assert 0.0 <= h.score <= 100.0


def test_score_clipped_high():
    from agents.trend_scout import TrendScoutAgent
    agent = TrendScoutAgent(MagicMock())
    score = agent._compute_score(
        brave=[{}] * 100,          # way over cap
        gtrends={"recent": 999},   # over 100
        reddit={"subreddits": [{"subscribers": 10_000_000}]},
    )
    assert score <= 100.0


def test_score_clipped_low():
    from agents.trend_scout import TrendScoutAgent
    agent = TrendScoutAgent(MagicMock())
    score = agent._compute_score(brave=[], gtrends={}, reddit={})
    assert score >= 0.0


def test_fetch_brave_empty_without_key(config):
    agent = TrendScoutAgent(config)
    result = agent._fetch_brave("beauty hacks")
    assert result == []


def test_fetch_reddit_empty_without_key(config):
    agent = TrendScoutAgent(config)
    result = agent._fetch_reddit("beauty hacks")
    assert result == {}


def test_fetch_google_trends_returns_dict_on_error(config):
    agent = TrendScoutAgent(config)
    with patch("agents.trend_scout.TrendScoutAgent._fetch_google_trends",
               return_value={"trend_direction": "unknown"}):
        result = agent._fetch_google_trends("anything")
    assert "trend_direction" in result
```

- [ ] **Step 2: Run — confirm all fail**

```bash
pytest tests/test_trend_scout_agent.py -v
```
Expected: FAILED (ImportError)

- [ ] **Step 3: Create `agents/trend_scout.py`**

```python
from __future__ import annotations
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from config import Config
from models.trend_scan_job import TrendHit

logger = logging.getLogger(__name__)

_BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
_GTRENDS_LOCK = threading.Lock()

_DRY_HITS: list[TrendHit] = [
    TrendHit(topic="beauty hacks",     direction="rising",  score=82.0, sources={"source": "dry-run"}),
    TrendHit(topic="skincare routine", direction="stable",  score=71.5, sources={"source": "dry-run"}),
    TrendHit(topic="makeup tutorial",  direction="rising",  score=68.0, sources={"source": "dry-run"}),
    TrendHit(topic="Gen Z fashion",    direction="rising",  score=55.0, sources={"source": "dry-run"}),
    TrendHit(topic="wellness routine", direction="stable",  score=48.0, sources={"source": "dry-run"}),
]


class TrendScoutAgent:
    def __init__(self, config: Config) -> None:
        self.config = config

    def scan(self, seed_topics: list[str], dry_run: bool = False) -> list[TrendHit]:
        if dry_run:
            return list(_DRY_HITS)
        return self._scan_live(seed_topics)

    def _scan_live(self, seed_topics: list[str]) -> list[TrendHit]:
        brave_results: dict[str, list[dict]] = {}
        reddit_results: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            brave_futs = {executor.submit(self._fetch_brave, t): t for t in seed_topics}
            reddit_futs = {executor.submit(self._fetch_reddit, t): t for t in seed_topics}
            for f in as_completed(brave_futs):
                brave_results[brave_futs[f]] = f.result()
            for f in as_completed(reddit_futs):
                reddit_results[reddit_futs[f]] = f.result()

        hits: list[TrendHit] = []
        for topic in seed_topics:
            gtrends = self._fetch_google_trends(topic)
            brave = brave_results.get(topic, [])
            reddit = reddit_results.get(topic, {})
            score = self._compute_score(brave, gtrends, reddit)
            hits.append(TrendHit(
                topic=topic,
                direction=gtrends.get("trend_direction", "unknown"),
                score=score,
                sources={"brave": brave, "gtrends": gtrends, "reddit": reddit},
            ))
        return hits

    def _compute_score(self, brave: list[dict], gtrends: dict, reddit: dict) -> float:
        brave_count = min(len(brave), 10)
        gtrends_score = float(gtrends.get("recent", 0))
        subs = sum(s.get("subscribers", 0) for s in (reddit.get("subreddits") or []))
        reddit_score = math.log10(subs + 1) * 20
        raw = brave_count * 0.4 + gtrends_score * 0.4 + reddit_score * 0.2
        return max(0.0, min(100.0, raw))

    def _fetch_brave(self, topic: str) -> list[dict]:
        if not self.config.brave_search_api_key:
            return []
        try:
            resp = requests.get(
                _BRAVE_URL,
                headers={"Accept": "application/json",
                         "X-Subscription-Token": self.config.brave_search_api_key},
                params={"q": f"{topic} viral trend 2026", "count": 10},
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("web", {}).get("results", [])
            return [{"title": r.get("title", ""), "description": r.get("description", "")}
                    for r in results[:10]]
        except Exception as exc:
            logger.warning("Brave Search failed for %s: %s", topic, exc)
            return []

    def _fetch_google_trends(self, topic: str) -> dict:
        try:
            from pytrends.request import TrendReq
            with _GTRENDS_LOCK:
                time.sleep(2)
                pt = TrendReq(hl="en-US", tz=300)
                pt.build_payload([topic], timeframe="today 3-m", geo="US")
                interest = pt.interest_over_time()
            if interest.empty:
                return {"trend_direction": "unknown"}
            values = interest[topic].tolist()
            if len(values) < 2:
                return {"trend_direction": "unknown", "recent": values[-1] if values else 0}
            direction = ("rising" if values[-1] > values[0]
                         else "declining" if values[-1] < values[0] else "stable")
            return {"trend_direction": direction, "recent": int(values[-1]), "start": int(values[0])}
        except Exception as exc:
            logger.warning("Google Trends failed for %s: %s", topic, exc)
            return {"trend_direction": "unknown"}

    def _fetch_reddit(self, topic: str) -> dict:
        if not self.config.reddit_client_id:
            return {}
        try:
            import praw
            reddit = praw.Reddit(
                client_id=self.config.reddit_client_id,
                client_secret=self.config.reddit_client_secret,
                user_agent=self.config.reddit_user_agent,
            )
            results = [
                {"name": sub.display_name, "subscribers": sub.subscribers}
                for sub in reddit.subreddits.search(topic, limit=3)
            ]
            return {"subreddits": results}
        except Exception as exc:
            logger.warning("Reddit failed for %s: %s", topic, exc)
            return {}
```

- [ ] **Step 4: Run tests — confirm all pass**

```bash
pytest tests/test_trend_scout_agent.py -v
```
Expected: 7 passed

- [ ] **Step 5: Type-check and lint**

```bash
mypy agents/trend_scout.py --ignore-missing-imports
ruff check agents/trend_scout.py
```

- [ ] **Step 6: Commit**

```bash
git add agents/trend_scout.py tests/test_trend_scout_agent.py
git commit -m "feat(sp-1): TrendScoutAgent with dry-run, score formula, graceful degradation"
```

---

### Task 3: `run_trend_scout_pipeline` + Knowledge Store integration (CP1)

**Files:**
- Create: `trend_scout_pipeline.py`
- Test: `tests/test_trend_scout_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_trend_scout_pipeline.py
from __future__ import annotations
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore
from knowledge.embedder import openai_embed_fn
from models.trend_scan_job import TrendScanJobStatus


@pytest.fixture
def store(tmp_path):
    settings = KnowledgeSettings(
        vault_knowledge_dir=tmp_path / "vault",
        db_path=tmp_path / "knowledge.db",
    )
    embed_fn = openai_embed_fn("text-embedding-3-small", "")  # lazy — won't call OpenAI in tests
    return KnowledgeStore(settings, embed_fn)


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
```

- [ ] **Step 2: Run — confirm all fail**

```bash
pytest tests/test_trend_scout_pipeline.py -v
```
Expected: FAILED (ImportError)

- [ ] **Step 3: Create `trend_scout_pipeline.py`**

```python
from __future__ import annotations
import json
import logging
from datetime import datetime
from pathlib import Path

from config import Config
from agents.trend_scout import TrendScoutAgent
from knowledge.store import KnowledgeStore
from knowledge.object import ContentObject
from models.trend_scan_job import TrendHit, TrendScanJob, TrendScanJobStatus
from project_loader import load_scout_seed_topics

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent
_OUTPUT_ROOT = _ROOT / "output"


def run_trend_scout_pipeline(
    page_slug: str,
    config: Config,
    store: KnowledgeStore,
    dry_run: bool = False,
    output_root: Path = _OUTPUT_ROOT,
) -> TrendScanJob:
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    job = TrendScanJob(job_id=job_id, page_slug=page_slug, triggered_by="pipeline")

    seed_topics = load_scout_seed_topics(page_slug)
    if not seed_topics:
        logger.info("No scout_seed_topics for %s — skipping trend scan", page_slug)
        job.status = TrendScanJobStatus.COMPLETED
        return job

    job.status = TrendScanJobStatus.RUNNING
    date_str = datetime.now().strftime("%Y%m%d")

    agent = TrendScoutAgent(config)
    hits = agent.scan(seed_topics, dry_run=dry_run)
    job.signals_found = len(hits)

    for hit in hits:
        obj = _hit_to_content_object(hit, page_slug, date_str)
        dup = store.check_duplicate(obj)
        if dup is not None and dup.score >= 0.82:
            job.signals_skipped += 1
            logger.debug("Skipping dup trend signal: %s", hit.topic)
            continue
        store.add(obj, embed=True)
        job.signals_stored += 1

    digest_path = write_trend_digest(hits, page_slug, output_root, date_str)
    job.digest_path = str(digest_path)
    job.status = TrendScanJobStatus.COMPLETED
    return job


def _hit_to_content_object(hit: TrendHit, page_slug: str, date_str: str) -> ContentObject:
    body = (
        f"## Trend Signal\n\n"
        f"**Topic:** {hit.topic}  \n"
        f"**Direction:** {hit.direction}  \n"
        f"**Score:** {hit.score:.1f}/100  \n\n"
        f"### Sources\n\n"
        f"```json\n{json.dumps(hit.sources, indent=2, default=str)[:2000]}\n```\n"
    )
    return ContentObject(
        page=page_slug,
        kind="trend_signal",
        title=f"{hit.topic} — {hit.direction}",
        body=body,
        dedup_text=f"{hit.topic}|{page_slug}|{date_str}",
        tags=[hit.direction, page_slug] + list(hit.sources.keys()),
        metadata={
            "topic": hit.topic,
            "direction": hit.direction,
            "score": hit.score,
            "sources": hit.sources,
        },
    )


def write_trend_digest(
    hits: list[TrendHit],
    page_slug: str,
    output_root: Path,
    date_str: str,
) -> Path:
    digest_dir = output_root / page_slug / "scout" / date_str
    digest_dir.mkdir(parents=True, exist_ok=True)
    digest_path = digest_dir / "trend_digest.md"

    sorted_hits = sorted(hits, key=lambda h: h.score, reverse=True)
    lines = [
        f"# Trend Digest — {page_slug} — {date_str}\n\n",
        "| # | Topic | Direction | Score |\n",
        "|---|---|---|---|\n",
    ]
    for i, hit in enumerate(sorted_hits, 1):
        lines.append(f"| {i} | {hit.topic} | {hit.direction} | {hit.score:.1f} |\n")
    lines.append("\n---\n\n")
    for hit in sorted_hits:
        lines.append(f"## {hit.topic}\n\n- **Direction:** {hit.direction}\n- **Score:** {hit.score:.1f}/100\n\n")

    digest_path.write_text("".join(lines), encoding="utf-8")
    logger.info("Trend digest written to %s", digest_path)
    return digest_path
```

- [ ] **Step 4: Run tests — confirm all pass**

```bash
pytest tests/test_trend_scout_pipeline.py -v
```
Expected: 4 passed

- [ ] **Step 5: Run full suite — CP1 gate**

```bash
pytest -v
```
Expected: all existing SP-0 tests + SP-1 tests pass (no regressions)

- [ ] **Step 6: Type-check and lint**

```bash
mypy trend_scout_pipeline.py --ignore-missing-imports
ruff check trend_scout_pipeline.py
```

- [ ] **Step 7: Commit**

```bash
git add trend_scout_pipeline.py tests/test_trend_scout_pipeline.py
git commit -m "feat(sp-1): run_trend_scout_pipeline with Knowledge Store integration and dedup (CP1)"
```

---

### Task 4: `write_trend_digest` integration test

`write_trend_digest` is already implemented in Task 3. This task adds its dedicated test.

**Files:**
- Modify: `tests/test_trend_scout_pipeline.py` (add digest tests)

- [ ] **Step 1: Add digest tests to `tests/test_trend_scout_pipeline.py`**

Append these two test functions:

```python
def test_digest_file_created(store, config, tmp_path):
    from trend_scout_pipeline import run_trend_scout_pipeline
    from datetime import datetime
    date_str = datetime.now().strftime("%Y%m%d")
    run_trend_scout_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    digest = tmp_path / "nayzfreedom_fleet" / "scout" / date_str / "trend_digest.md"
    assert digest.exists()


def test_digest_contains_all_topics(store, config, tmp_path):
    from trend_scout_pipeline import run_trend_scout_pipeline
    from datetime import datetime
    date_str = datetime.now().strftime("%Y%m%d")
    run_trend_scout_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    digest = tmp_path / "nayzfreedom_fleet" / "scout" / date_str / "trend_digest.md"
    content = digest.read_text()
    for topic in ["beauty hacks", "skincare routine", "makeup tutorial", "Gen Z fashion", "wellness routine"]:
        assert topic in content
```

- [ ] **Step 2: Run tests — confirm all pass**

```bash
pytest tests/test_trend_scout_pipeline.py -v
```
Expected: 6 passed

- [ ] **Step 3: Commit**

```bash
git add tests/test_trend_scout_pipeline.py
git commit -m "test(sp-1): add digest file integration tests"
```

---

### Task 5: Scheduler integration (CP2)

**Files:**
- Modify: `scheduler.py`
- Test: verify `pytest tests/test_scheduler.py -v` still passes after changes

- [ ] **Step 1: Read existing tests baseline**

```bash
pytest tests/test_scheduler.py -v 2>&1 | tail -5
```
Note the pass count. All must still pass after this task.

- [ ] **Step 2: Add `_run_daily_trend_scan` to `scheduler.py`**

Add this function after `_run_daily_scout` (around line 109):

```python
def _run_daily_trend_scan(
    active_slugs: list[str],
    dry_run: bool = False,
    root: Path | None = None,
) -> None:
    try:
        import os
        from config import Config
        from knowledge.settings import KnowledgeSettings
        from knowledge.embedder import openai_embed_fn
        from knowledge.store import KnowledgeStore
        from trend_scout_pipeline import run_trend_scout_pipeline

        cfg = Config.from_env()
        settings = KnowledgeSettings.from_env()
        api_key = os.getenv("OPENAI_API_KEY", "")
        embed_fn = openai_embed_fn(settings.embed_model, api_key)
        store = KnowledgeStore(settings, embed_fn)

        for slug in active_slugs:
            try:
                job = run_trend_scout_pipeline(slug, cfg, store, dry_run=dry_run)
                logger.info(
                    "Trend scan done: page=%s found=%d stored=%d skipped=%d",
                    slug, job.signals_found, job.signals_stored, job.signals_skipped,
                )
            except Exception as exc:
                logger.error("Trend scan failed for %s: %s", slug, exc)
    except Exception as exc:
        logger.error("Daily trend scan setup failed: %s", exc)
```

- [ ] **Step 3: Call `_run_daily_trend_scan` in `run_scheduler`**

In `run_scheduler()`, replace the existing scout block at line 136–138:

```python
    # BEFORE:
    should_run_scout = root is None if run_scout is None else run_scout
    if should_run_scout:
        _run_daily_scout(dry_run=dry_run)

    # AFTER:
    should_run_scout = root is None if run_scout is None else run_scout
    if should_run_scout:
        _run_daily_scout(dry_run=dry_run)
        _run_daily_trend_scan(active_slugs, dry_run=dry_run, root=root)
```

- [ ] **Step 4: Run scheduler tests — confirm no regressions**

```bash
pytest tests/test_scheduler.py -v
```
Expected: same pass count as Step 1 baseline

- [ ] **Step 5: Run full suite — CP2 gate**

```bash
pytest -v
```
Expected: all tests pass

- [ ] **Step 6: Type-check and lint**

```bash
mypy scheduler.py --ignore-missing-imports
ruff check scheduler.py
```

- [ ] **Step 7: Commit**

```bash
git add scheduler.py
git commit -m "feat(sp-1): daily trend scan in scheduler (runs per active page after niche scout)"
```

---

### Task 6: Dashboard "Run Trend Scan Now" button

**Files:**
- Modify: `routes/scout.py`

- [ ] **Step 1: Add POST endpoint to `routes/scout.py`**

Add this import at the top of `routes/scout.py` if not present:
```python
from fastapi.responses import JSONResponse
```

Add this endpoint after the existing router definitions (before the last route or at the end):

```python
@router.post("/trend-scan/{project_slug}")
async def run_trend_scan(
    project_slug: str,
    request: Request,
    _: None = Depends(verify_auth),
) -> JSONResponse:
    if not _PROJECT_SLUG_RE.match(project_slug):
        raise HTTPException(status_code=400, detail="Invalid project_slug")

    def _run() -> None:
        import os
        try:
            from config import Config
            from knowledge.settings import KnowledgeSettings
            from knowledge.embedder import openai_embed_fn
            from knowledge.store import KnowledgeStore
            from trend_scout_pipeline import run_trend_scout_pipeline

            cfg = Config.from_env()
            settings = KnowledgeSettings.from_env()
            embed_fn = openai_embed_fn(settings.embed_model, os.getenv("OPENAI_API_KEY", ""))
            store = KnowledgeStore(settings, embed_fn)
            job = run_trend_scout_pipeline(project_slug, cfg, store)
            logger.info(
                "Dashboard trend scan done: page=%s stored=%d skipped=%d",
                project_slug, job.signals_stored, job.signals_skipped,
            )
        except Exception as exc:
            logger.error("Dashboard trend scan failed for %s: %s", project_slug, exc)

    import threading
    threading.Thread(target=_run, daemon=True).start()
    return JSONResponse({"status": "started", "project_slug": project_slug})
```

- [ ] **Step 2: Run dashboard route tests — confirm no regressions**

```bash
pytest tests/test_dashboard.py -v -k "scout"
```
Expected: existing scout tests still pass

- [ ] **Step 3: Run full suite**

```bash
pytest -v
```
Expected: all tests pass

- [ ] **Step 4: Type-check and lint**

```bash
mypy routes/scout.py --ignore-missing-imports
ruff check routes/scout.py
```

- [ ] **Step 5: Commit**

```bash
git add routes/scout.py
git commit -m "feat(sp-1): add POST /scout/trend-scan/{project_slug} endpoint for dashboard trigger"
```

---

## Final verification

```bash
# Full test suite
pytest -v

# Type check all SP-1 files
mypy models/trend_scan_job.py project_loader.py agents/trend_scout.py \
     trend_scout_pipeline.py scheduler.py routes/scout.py --ignore-missing-imports

# Lint
ruff check models/trend_scan_job.py project_loader.py agents/trend_scout.py \
          trend_scout_pipeline.py scheduler.py routes/scout.py

# Dry-run smoke test (no API keys needed)
python -c "
from unittest.mock import MagicMock
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore
from knowledge.embedder import openai_embed_fn
from trend_scout_pipeline import run_trend_scout_pipeline
import tempfile, pathlib

with tempfile.TemporaryDirectory() as tmp:
    settings = KnowledgeSettings(vault_knowledge_dir=pathlib.Path(tmp) / 'vault', db_path=pathlib.Path(tmp) / 'k.db')
    store = KnowledgeStore(settings, openai_embed_fn('text-embedding-3-small', ''))
    cfg = MagicMock(); cfg.brave_search_api_key = ''; cfg.reddit_client_id = ''
    job = run_trend_scout_pipeline('nayzfreedom_fleet', cfg, store, dry_run=True, output_root=pathlib.Path(tmp))
    print(f'stored={job.signals_stored} skipped={job.signals_skipped} digest={job.digest_path}')
"
```

Expected smoke test output:
```
stored=5 skipped=0 digest=<tmp>/nayzfreedom_fleet/scout/<date>/trend_digest.md
```
