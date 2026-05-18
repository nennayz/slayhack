# Scout Pipeline Implementation Plan

> **For agentic workers:** Follow `CLAUDE.md` first, then implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 3-agent niche discovery pipeline (Scout → Analyst → Architect) that scans 4 data sources daily, delivers a ranked opportunity report to Telegram/Dashboard/Google Drive, and generates Fleet project files upon Captain approval.

**Architecture:** Scout fetches raw signals from Brave Search, Google Trends, Reddit, and Meta Ads Library in parallel; Analyst uses OpenAI to score and rank top 5 niches by reach potential; Architect generates `projects/<slug>/` YAML files after Captain approves via Telegram or Dashboard. The pipeline runs independently from Aurora content production but shares Config, scheduler, Telegram bot, and Google Drive infrastructure.

**Tech Stack:** Python 3.12+, Pydantic v2, pytrends, praw, FastAPI, Jinja2, existing OpenAI + Brave Search + Telegram + Google Drive clients

**Spec:** `docs/superpowers/specs/2026-05-17-scout-pipeline-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `requirements.txt` | Modify | Add pytrends, praw |
| `models/niche_opportunity.py` | Create | NicheSignal, NicheOpportunity, ScoutJob models |
| `config.py` | Modify | Scout config vars (timezone, seed categories, Reddit creds) |
| `agents/scout.py` | Create | Fetch raw signals from 4 sources |
| `agents/analyst.py` | Create | Score & rank NicheSignal → top 5 NicheOpportunity via OpenAI |
| `agents/architect.py` | Create | Generate projects/<slug>/ YAML files |
| `scout_pipeline.py` | Create | Orchestrate Scout → Analyst → report output → optional Architect |
| `tools/agent_tools.py` | Modify | Add scout pipeline tool definitions |
| `scheduler.py` | Modify | Add daily 08:00 scout trigger |
| `telegram_bot.py` | Modify | Add /scout command + approve/skip callback handler |
| `routes/scout.py` | Create | Dashboard /scout endpoints |
| `templates/scout.html` | Create | Scout report UI with niche cards |
| `tests/test_niche_opportunity.py` | Create | Model tests |
| `tests/test_scout_agent.py` | Create | Scout agent tests |
| `tests/test_analyst_agent.py` | Create | Analyst agent tests |
| `tests/test_architect_agent.py` | Create | Architect agent tests |
| `tests/test_scout_pipeline.py` | Create | Pipeline integration tests |

---

## Task 1: Add Dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add pytrends and praw**

Open `requirements.txt` and append:

```
pytrends>=4.9.0
praw>=7.7.0
```

- [ ] **Step 2: Install**

```bash
pip install pytrends praw
```

Expected: both install without errors.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add pytrends and praw for scout pipeline"
```

---

## Task 2: Data Models

**Files:**
- Create: `models/niche_opportunity.py`
- Create: `tests/test_niche_opportunity.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_niche_opportunity.py`:

```python
from __future__ import annotations
from datetime import datetime
from models.niche_opportunity import NicheSignal, NicheOpportunity, ScoutJob, ScoutJobStatus


def test_niche_signal_stores_raw_data():
    sig = NicheSignal(niche_name="clean beauty", raw_data={"brave": ["result1"]})
    assert sig.niche_name == "clean beauty"
    assert sig.raw_data["brave"] == ["result1"]


def test_niche_opportunity_reach_score_bounds():
    opp = NicheOpportunity(
        niche_name="clean beauty",
        target_audience="Women USA 25-35",
        platforms=["instagram", "tiktok"],
        reach_score=85.0,
        trend_direction="rising",
        content_formats=["reel", "infographic"],
        monetization_notes="High affiliate potential",
        signals={"google_trends": "rising"},
    )
    assert 0 <= opp.reach_score <= 100
    assert opp.trend_direction == "rising"


def test_scout_job_defaults():
    job = ScoutJob(job_id="20260517_080000", triggered_by="scheduler")
    assert job.status == ScoutJobStatus.PENDING
    assert job.opportunities == []
    assert job.approved_niche is None


def test_scout_job_serializes_to_json():
    job = ScoutJob(job_id="20260517_080000", triggered_by="telegram")
    data = job.model_dump_json()
    assert "job_id" in data
    assert "opportunities" in data
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_niche_opportunity.py -v
```

Expected: `ModuleNotFoundError: No module named 'models.niche_opportunity'`

- [ ] **Step 3: Create the models**

Create `models/niche_opportunity.py`:

```python
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ScoutJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    AWAITING_APPROVAL = "awaiting_approval"


class NicheSignal(BaseModel):
    niche_name: str
    raw_data: dict


class NicheOpportunity(BaseModel):
    niche_name: str
    target_audience: str
    platforms: list[str]
    reach_score: float          # 0-100
    trend_direction: str        # "rising" | "stable" | "declining"
    content_formats: list[str]
    monetization_notes: str
    signals: dict


class ScoutJob(BaseModel):
    job_id: str
    triggered_by: str           # "scheduler" | "telegram" | "dashboard"
    created_at: datetime = Field(default_factory=datetime.now)
    status: ScoutJobStatus = ScoutJobStatus.PENDING
    opportunities: list[NicheOpportunity] = Field(default_factory=list)
    approved_niche: Optional[str] = None
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/test_niche_opportunity.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add models/niche_opportunity.py tests/test_niche_opportunity.py
git commit -m "feat: add NicheSignal, NicheOpportunity, ScoutJob models"
```

---

## Task 3: Config Updates

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Add scout fields to the Config dataclass**

In `config.py`, add these fields to the `Config` dataclass (after `youtube_refresh_token`):

```python
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "nayzfreedom-scout/1.0"
    scout_timezone: str = "America/New_York"
    scout_seed_categories: list = Field(default_factory=list)
    scout_drive_folder_id: str = ""
```

Because `Config` is a plain `dataclass` (not Pydantic), use a regular default. Replace `Field(default_factory=list)` with just `= None` and handle in `from_env`. Apply the change as:

```python
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "nayzfreedom-scout/1.0"
    scout_timezone: str = "America/New_York"
    scout_seed_categories: str = ""   # comma-separated, parsed at use time
    scout_drive_folder_id: str = ""
```

- [ ] **Step 2: Add to `from_env()`**

Inside `cls(...)` call in `from_env`, add:

```python
            reddit_client_id=os.getenv("REDDIT_CLIENT_ID", ""),
            reddit_client_secret=os.getenv("REDDIT_CLIENT_SECRET", ""),
            reddit_user_agent=os.getenv("REDDIT_USER_AGENT", "nayzfreedom-scout/1.0"),
            scout_timezone=os.getenv("SCOUT_TIMEZONE", "America/New_York"),
            scout_seed_categories=os.getenv(
                "SCOUT_SEED_CATEGORIES",
                "clean beauty,quiet luxury,wellness,self care,personal finance for women,"
                "home aesthetic,sustainable fashion,mental health,career growth",
            ),
            scout_drive_folder_id=os.getenv("SCOUT_DRIVE_FOLDER_ID", ""),
```

- [ ] **Step 3: Verify existing tests still pass**

```bash
pytest tests/ -v --tb=short
```

Expected: all existing tests PASS (no regression).

- [ ] **Step 4: Commit**

```bash
git add config.py
git commit -m "feat: add scout config vars to Config (Reddit, timezone, seed categories)"
```

---

## Task 4: Scout Agent

**Files:**
- Create: `agents/scout.py`
- Create: `tests/test_scout_agent.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_scout_agent.py`:

```python
from __future__ import annotations
from unittest.mock import MagicMock, patch
from config import Config
from models.niche_opportunity import NicheSignal, ScoutJob, ScoutJobStatus


def _make_config() -> Config:
    return Config(
        brave_search_api_key="test-brave",
        openai_api_key="test-openai",
        scout_seed_categories="clean beauty,quiet luxury",
    )


def test_scout_dry_run_returns_signals():
    from agents.scout import ScoutAgent
    agent = ScoutAgent(_make_config())
    job = ScoutJob(job_id="test_001", triggered_by="test")
    result = agent.run(job, dry_run=True)
    assert result.status == ScoutJobStatus.RUNNING
    assert len(result.signals) >= 2
    assert all(isinstance(s, NicheSignal) for s in result.signals)


def test_scout_signal_has_niche_name():
    from agents.scout import ScoutAgent
    agent = ScoutAgent(_make_config())
    job = ScoutJob(job_id="test_002", triggered_by="test")
    result = agent.run(job, dry_run=True)
    for sig in result.signals:
        assert sig.niche_name
        assert isinstance(sig.raw_data, dict)


@patch("agents.scout.requests.get")
def test_scout_live_calls_brave_search(mock_get):
    from agents.scout import ScoutAgent
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"web": {"results": [
        {"title": "Clean beauty trend", "description": "Rising fast"}
    ]}}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    with patch("agents.scout.ScoutAgent._fetch_google_trends", return_value={}), \
         patch("agents.scout.ScoutAgent._fetch_reddit", return_value={}), \
         patch("agents.scout.ScoutAgent._fetch_meta_ads", return_value={}):
        agent = ScoutAgent(_make_config())
        job = ScoutJob(job_id="test_003", triggered_by="test")
        result = agent.run(job, dry_run=False)
        assert mock_get.called
        assert len(result.signals) >= 1
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_scout_agent.py -v
```

Expected: `ModuleNotFoundError: No module named 'agents.scout'`

- [ ] **Step 3: Create Scout agent**

Create `agents/scout.py`:

```python
from __future__ import annotations
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from config import Config
from models.niche_opportunity import NicheSignal, ScoutJob, ScoutJobStatus

logger = logging.getLogger(__name__)

_BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
_META_ADS_URL = "https://graph.facebook.com/v19.0/ads_archive"

_DRY_SIGNALS = [
    NicheSignal(niche_name="clean beauty", raw_data={"source": "dry-run", "trend": "rising", "reddit_size": 450000}),
    NicheSignal(niche_name="quiet luxury", raw_data={"source": "dry-run", "trend": "rising", "reddit_size": 320000}),
    NicheSignal(niche_name="wellness routine", raw_data={"source": "dry-run", "trend": "stable", "reddit_size": 890000}),
    NicheSignal(niche_name="sustainable fashion", raw_data={"source": "dry-run", "trend": "rising", "reddit_size": 210000}),
    NicheSignal(niche_name="personal finance women", raw_data={"source": "dry-run", "trend": "rising", "reddit_size": 560000}),
]


class ScoutAgent:
    def __init__(self, config: Config):
        self.config = config

    def run(self, job: ScoutJob, dry_run: bool = False) -> ScoutJob:
        job.status = ScoutJobStatus.RUNNING
        if dry_run:
            job.signals = list(_DRY_SIGNALS)
            return job
        return self._run_live(job)

    def _run_live(self, job: ScoutJob) -> ScoutJob:
        categories = [c.strip() for c in self.config.scout_seed_categories.split(",") if c.strip()]
        signals: list[NicheSignal] = []

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(self._fetch_all_for_niche, cat): cat for cat in categories}
            for future in as_completed(futures):
                cat = futures[future]
                try:
                    sig = future.result()
                    signals.append(sig)
                except Exception as exc:
                    logger.warning("Scout fetch failed for %s: %s", cat, exc)

        job.signals = signals
        return job

    def _fetch_all_for_niche(self, niche: str) -> NicheSignal:
        raw: dict = {"niche": niche}
        raw["brave"] = self._fetch_brave(niche)
        raw["google_trends"] = self._fetch_google_trends(niche)
        raw["reddit"] = self._fetch_reddit(niche)
        raw["meta_ads"] = self._fetch_meta_ads(niche)
        return NicheSignal(niche_name=niche, raw_data=raw)

    def _fetch_brave(self, niche: str) -> list[dict]:
        if not self.config.brave_search_api_key:
            return []
        resp = requests.get(
            _BRAVE_URL,
            headers={"Accept": "application/json", "X-Subscription-Token": self.config.brave_search_api_key},
            params={"q": f"{niche} viral trend social media 2026", "count": 5},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("web", {}).get("results", [])
        return [{"title": r.get("title", ""), "description": r.get("description", "")} for r in results[:5]]

    def _fetch_google_trends(self, niche: str) -> dict:
        try:
            from pytrends.request import TrendReq
            pt = TrendReq(hl="en-US", tz=300)
            pt.build_payload([niche], timeframe="today 3-m", geo="US")
            interest = pt.interest_over_time()
            if interest.empty:
                return {"trend_direction": "unknown"}
            values = interest[niche].tolist()
            if len(values) < 2:
                return {"trend_direction": "unknown", "recent": values[-1] if values else 0}
            direction = "rising" if values[-1] > values[0] else ("declining" if values[-1] < values[0] else "stable")
            return {"trend_direction": direction, "recent": int(values[-1]), "start": int(values[0])}
        except Exception as exc:
            logger.warning("Google Trends failed for %s: %s", niche, exc)
            return {"trend_direction": "unknown"}

    def _fetch_reddit(self, niche: str) -> dict:
        try:
            import praw
            if not self.config.reddit_client_id:
                return {}
            reddit = praw.Reddit(
                client_id=self.config.reddit_client_id,
                client_secret=self.config.reddit_client_secret,
                user_agent=self.config.reddit_user_agent,
            )
            results = []
            for sub in reddit.subreddits.search(niche, limit=3):
                results.append({
                    "name": sub.display_name,
                    "subscribers": sub.subscribers,
                    "description": str(sub.public_description)[:200],
                })
            return {"subreddits": results}
        except Exception as exc:
            logger.warning("Reddit fetch failed for %s: %s", niche, exc)
            return {}

    def _fetch_meta_ads(self, niche: str) -> dict:
        try:
            resp = requests.get(
                _META_ADS_URL,
                params={
                    "search_terms": niche,
                    "ad_reached_countries": '["US"]',
                    "ad_active_status": "ACTIVE",
                    "limit": 5,
                    "fields": "id,ad_creative_body,ad_snapshot_url",
                    "access_token": self.config.meta_access_token,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            ad_count = len(data.get("data", []))
            return {"active_ads": ad_count}
        except Exception as exc:
            logger.warning("Meta Ads fetch failed for %s: %s", niche, exc)
            return {}
```

Note: `ScoutJob` needs a `signals` field. Add it to `models/niche_opportunity.py`:

```python
    signals: list[NicheSignal] = Field(default_factory=list)
```

(Add after the `approved_niche` field.)

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_scout_agent.py tests/test_niche_opportunity.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/scout.py models/niche_opportunity.py tests/test_scout_agent.py
git commit -m "feat: add Scout agent with 4-source parallel niche scanning"
```

---

## Task 5: Analyst Agent

**Files:**
- Create: `agents/analyst.py`
- Create: `tests/test_analyst_agent.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_analyst_agent.py`:

```python
from __future__ import annotations
from unittest.mock import MagicMock, patch
from config import Config
from models.niche_opportunity import NicheSignal, NicheOpportunity, ScoutJob, ScoutJobStatus


def _make_config() -> Config:
    return Config(brave_search_api_key="x", openai_api_key="test-openai")


def _make_job_with_signals() -> ScoutJob:
    job = ScoutJob(job_id="test_analyst_001", triggered_by="test")
    job.signals = [
        NicheSignal(niche_name="clean beauty", raw_data={"google_trends": {"trend_direction": "rising"}, "reddit": {"subreddits": [{"subscribers": 400000}]}}),
        NicheSignal(niche_name="quiet luxury", raw_data={"google_trends": {"trend_direction": "rising"}, "reddit": {"subreddits": [{"subscribers": 300000}]}}),
    ]
    return job


def test_analyst_dry_run_returns_opportunities():
    from agents.analyst import AnalystAgent
    agent = AnalystAgent(_make_config())
    job = _make_job_with_signals()
    result = agent.run(job, dry_run=True)
    assert len(result.opportunities) >= 1
    assert all(isinstance(o, NicheOpportunity) for o in result.opportunities)
    assert result.status == ScoutJobStatus.AWAITING_APPROVAL


def test_analyst_dry_run_reach_scores_valid():
    from agents.analyst import AnalystAgent
    agent = AnalystAgent(_make_config())
    job = _make_job_with_signals()
    result = agent.run(job, dry_run=True)
    for opp in result.opportunities:
        assert 0 <= opp.reach_score <= 100


def test_analyst_opportunities_sorted_by_reach_score():
    from agents.analyst import AnalystAgent
    agent = AnalystAgent(_make_config())
    job = _make_job_with_signals()
    result = agent.run(job, dry_run=True)
    scores = [o.reach_score for o in result.opportunities]
    assert scores == sorted(scores, reverse=True)


@patch("agents.analyst.OpenAI")
def test_analyst_live_calls_openai(mock_openai_cls):
    from agents.analyst import AnalystAgent
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.choices[0].message.content = '''[
        {"niche_name": "clean beauty", "target_audience": "Women USA 25-35", "platforms": ["instagram","tiktok"], "reach_score": 88.0, "trend_direction": "rising", "content_formats": ["reel"], "monetization_notes": "High affiliate", "signals": {}}
    ]'''
    mock_client.chat.completions.create.return_value = mock_response

    agent = AnalystAgent(_make_config())
    job = _make_job_with_signals()
    result = agent.run(job, dry_run=False)
    assert mock_client.chat.completions.create.called
    assert len(result.opportunities) == 1
    assert result.opportunities[0].niche_name == "clean beauty"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_analyst_agent.py -v
```

Expected: `ModuleNotFoundError: No module named 'agents.analyst'`

- [ ] **Step 3: Create Analyst agent**

Create `agents/analyst.py`:

```python
from __future__ import annotations
import json
import logging
import re

from openai import OpenAI

from config import Config
from models.niche_opportunity import NicheOpportunity, NicheSignal, ScoutJob, ScoutJobStatus

logger = logging.getLogger(__name__)

_DRY_OPPORTUNITIES = [
    NicheOpportunity(
        niche_name="clean beauty",
        target_audience="Women USA 22-38, ingredient-conscious, IG-native",
        platforms=["instagram", "tiktok"],
        reach_score=91.0,
        trend_direction="rising",
        content_formats=["reel", "carousel", "infographic"],
        monetization_notes="High affiliate affiliate potential (skincare), e-book: 'Your Clean Routine'",
        signals={"source": "dry-run"},
    ),
    NicheOpportunity(
        niche_name="quiet luxury",
        target_audience="Women USA 25-40, aspirational minimalists",
        platforms=["instagram", "tiktok", "youtube"],
        reach_score=85.0,
        trend_direction="rising",
        content_formats=["reel", "ootd", "listicle"],
        monetization_notes="LTK affiliate, e-book: 'Dress Like Old Money'",
        signals={"source": "dry-run"},
    ),
    NicheOpportunity(
        niche_name="personal finance women",
        target_audience="Women USA 25-40, income earners building wealth",
        platforms=["tiktok", "instagram", "youtube"],
        reach_score=79.0,
        trend_direction="rising",
        content_formats=["explainer", "infographic", "series"],
        monetization_notes="High CPM, e-book: 'Your First $10K'",
        signals={"source": "dry-run"},
    ),
]


class AnalystAgent:
    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(api_key=config.openai_api_key)
        self.model = config.openai_agent_model

    def run(self, job: ScoutJob, dry_run: bool = False) -> ScoutJob:
        if dry_run:
            job.opportunities = sorted(_DRY_OPPORTUNITIES, key=lambda o: o.reach_score, reverse=True)
            job.status = ScoutJobStatus.AWAITING_APPROVAL
            return job
        return self._run_live(job)

    def _run_live(self, job: ScoutJob) -> ScoutJob:
        signals_text = "\n\n".join(
            f"Niche: {s.niche_name}\nData: {json.dumps(s.raw_data, ensure_ascii=False)}"
            for s in job.signals
        )
        system = (
            "You are Analyst, a market intelligence agent for NayzFreedom Fleet. "
            "Your job: score and rank niche opportunities for new social media pages "
            "targeting women in the USA, ages 18-44. Priority: REACH first (viral potential, "
            "audience growth speed), then monetization. Content must fit the Fleet's "
            "production capabilities (short video, image, infographic, article)."
        )
        user = (
            f"Raw niche signals:\n\n{signals_text}\n\n"
            "Return a JSON array of the top 5 opportunities, each with:\n"
            "niche_name, target_audience, platforms (list), reach_score (0-100 float), "
            "trend_direction ('rising'|'stable'|'declining'), content_formats (list), "
            "monetization_notes (str), signals (dict summary). "
            "Sort by reach_score descending. JSON array only, no markdown."
        )
        raw = self._call_openai(system, user)
        parsed = self._parse_json(raw)
        job.opportunities = [NicheOpportunity(**item) for item in parsed]
        job.status = ScoutJobStatus.AWAITING_APPROVAL
        return job

    def _call_openai(self, system: str, user: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=2048,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""

    def _parse_json(self, raw: str) -> list:
        candidate = raw.strip()
        fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL | re.IGNORECASE)
        if fence:
            candidate = fence.group(1).strip()
        return json.loads(candidate)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_analyst_agent.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/analyst.py tests/test_analyst_agent.py
git commit -m "feat: add Analyst agent — OpenAI-powered niche scoring and ranking"
```

---

## Task 6: Architect Agent

**Files:**
- Create: `agents/architect.py`
- Create: `tests/test_architect_agent.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_architect_agent.py`:

```python
from __future__ import annotations
from pathlib import Path
import yaml
from config import Config
from models.niche_opportunity import NicheOpportunity, ScoutJob, ScoutJobStatus


def _make_config() -> Config:
    return Config(brave_search_api_key="x", openai_api_key="test-openai")


def _make_approved_job(tmp_path: Path) -> tuple[ScoutJob, NicheOpportunity]:
    opp = NicheOpportunity(
        niche_name="clean beauty",
        target_audience="Women USA 22-38",
        platforms=["instagram", "tiktok"],
        reach_score=91.0,
        trend_direction="rising",
        content_formats=["reel", "infographic"],
        monetization_notes="High affiliate potential",
        signals={},
    )
    job = ScoutJob(job_id="test_arch_001", triggered_by="test")
    job.approved_niche = "clean beauty"
    job.opportunities = [opp]
    return job, opp


def test_architect_dry_run_returns_slug(tmp_path):
    from agents.architect import ArchitectAgent
    agent = ArchitectAgent(_make_config())
    job, _ = _make_approved_job(tmp_path)
    slug = agent.run(job, projects_root=tmp_path, dry_run=True)
    assert slug == "clean_beauty"


def test_architect_dry_run_does_not_write_files(tmp_path):
    from agents.architect import ArchitectAgent
    agent = ArchitectAgent(_make_config())
    job, _ = _make_approved_job(tmp_path)
    agent.run(job, projects_root=tmp_path, dry_run=True)
    assert not (tmp_path / "clean_beauty").exists()


def test_architect_live_creates_project_files(tmp_path):
    from agents.architect import ArchitectAgent
    agent = ArchitectAgent(_make_config())
    job, _ = _make_approved_job(tmp_path)
    slug = agent.run(job, projects_root=tmp_path, dry_run=False)
    project_dir = tmp_path / slug
    assert project_dir.exists()
    for fname in ["brand.yaml", "pm_profile.yaml", "platform_specs.yaml", "weekly_calendar.yaml"]:
        assert (project_dir / fname).exists(), f"Missing {fname}"


def test_architect_brand_yaml_has_required_keys(tmp_path):
    from agents.architect import ArchitectAgent
    agent = ArchitectAgent(_make_config())
    job, _ = _make_approved_job(tmp_path)
    slug = agent.run(job, projects_root=tmp_path, dry_run=False)
    brand = yaml.safe_load((tmp_path / slug / "brand.yaml").read_text())
    assert "mission" in brand
    assert "target_audience" in brand
    assert "platforms" in brand
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_architect_agent.py -v
```

Expected: `ModuleNotFoundError: No module named 'agents.architect'`

- [ ] **Step 3: Create Architect agent**

Create `agents/architect.py`:

```python
from __future__ import annotations
import logging
import re
from pathlib import Path

import yaml

from config import Config
from models.niche_opportunity import NicheOpportunity, ScoutJob

logger = logging.getLogger(__name__)

_PROJECTS_ROOT = Path(__file__).resolve().parent.parent / "projects"


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _brand_yaml(opp: NicheOpportunity) -> dict:
    return {
        "mission": (
            f"Character-driven {opp.niche_name} content that builds a loyal audience "
            f"of {opp.target_audience} and converts trust into owned products."
        ),
        "visual": {
            "style": "warm 3D Pixar CGI, expressive lifestyle objects, soft left-side lighting, vertical 9:16",
            "colors": ["#FFFFFF", "#F5F5DC", "#D4AF37"],
        },
        "platforms": opp.platforms,
        "tone": "smart, supportive, aspirational, never preachy",
        "target_audience": opp.target_audience,
        "script_style": (
            "English only, casual bestie voice, punchy hook in first three words, "
            "no corporate language"
        ),
        "nora_max_retries": 2,
        "allowed_content_types": opp.content_formats,
    }


def _pm_profile_yaml(opp: NicheOpportunity, slug: str) -> dict:
    page_name = slug.replace("_", " ").title().replace(" ", "")
    return {
        "name": "Alex",
        "page_name": page_name,
        "persona": (
            f"You are Alex, the Project Manager for {page_name}. "
            f"You produce {opp.niche_name} content for {opp.target_audience}. "
            f"Your content stops the scroll, builds community, and moves the audience "
            f"toward owned products. Priority: {opp.trend_direction} trend, reach first."
        ),
    }


def _platform_specs_yaml(opp: NicheOpportunity) -> dict:
    return {
        platform: {"primary": True, "content_types": opp.content_formats}
        for platform in opp.platforms
    }


def _weekly_calendar_yaml(opp: NicheOpportunity) -> dict:
    return {
        "monday": {"short_video_1": f"{opp.niche_name} hack"},
        "wednesday": {"image_1": f"{opp.niche_name} aesthetic"},
        "friday": {"short_video_2": f"{opp.niche_name} trend"},
        "sunday": {"infographic_1": f"{opp.niche_name} tips"},
    }


class ArchitectAgent:
    def __init__(self, config: Config):
        self.config = config

    def run(self, job: ScoutJob, projects_root: Path = _PROJECTS_ROOT, dry_run: bool = False) -> str:
        opp = self._find_approved_opportunity(job)
        slug = _slugify(opp.niche_name)
        if dry_run:
            logger.info("Architect dry-run: would create projects/%s/", slug)
            return slug
        self._write_project(slug, opp, projects_root)
        job.status_message = f"Project {slug} created at projects/{slug}/"
        return slug

    def _find_approved_opportunity(self, job: ScoutJob) -> NicheOpportunity:
        if not job.approved_niche:
            raise ValueError("No approved_niche set on ScoutJob")
        for opp in job.opportunities:
            if opp.niche_name == job.approved_niche:
                return opp
        raise ValueError(f"Approved niche '{job.approved_niche}' not found in opportunities")

    def _write_project(self, slug: str, opp: NicheOpportunity, root: Path) -> None:
        project_dir = root / slug
        project_dir.mkdir(parents=True, exist_ok=True)

        files = {
            "brand.yaml": _brand_yaml(opp),
            "pm_profile.yaml": _pm_profile_yaml(opp, slug),
            "platform_specs.yaml": _platform_specs_yaml(opp),
            "weekly_calendar.yaml": _weekly_calendar_yaml(opp),
        }
        for filename, data in files.items():
            (project_dir / filename).write_text(
                yaml.dump(data, allow_unicode=True, default_flow_style=False),
                encoding="utf-8",
            )
        logger.info("Architect: created project at projects/%s/", slug)
```

Note: `ScoutJob` needs a `status_message` field. Add to `models/niche_opportunity.py`:

```python
    status_message: Optional[str] = None
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_architect_agent.py tests/test_niche_opportunity.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/architect.py models/niche_opportunity.py tests/test_architect_agent.py
git commit -m "feat: add Architect agent — generates project YAML files from approved niche"
```

---

## Task 7: Scout Pipeline Orchestration

**Files:**
- Create: `scout_pipeline.py`
- Create: `tests/test_scout_pipeline.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_scout_pipeline.py`:

```python
from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock, patch
from config import Config
from models.niche_opportunity import NicheOpportunity, NicheSignal, ScoutJob, ScoutJobStatus


def _make_config() -> Config:
    return Config(brave_search_api_key="x", openai_api_key="test-openai")


def _make_opportunities() -> list[NicheOpportunity]:
    return [
        NicheOpportunity(
            niche_name="clean beauty", target_audience="Women USA 22-38",
            platforms=["instagram"], reach_score=91.0, trend_direction="rising",
            content_formats=["reel"], monetization_notes="High affiliate", signals={},
        )
    ]


def test_run_dry_scout_pipeline_returns_scout_job():
    from scout_pipeline import run_scout_pipeline
    job = run_scout_pipeline(_make_config(), triggered_by="test", dry_run=True)
    assert isinstance(job, ScoutJob)
    assert job.status == ScoutJobStatus.AWAITING_APPROVAL
    assert len(job.opportunities) >= 1


def test_run_scout_pipeline_saves_report(tmp_path):
    from scout_pipeline import run_scout_pipeline
    job = run_scout_pipeline(_make_config(), triggered_by="test", dry_run=True, output_root=tmp_path)
    reports = list((tmp_path / "scout_reports").glob("*.json"))
    assert len(reports) == 1


@patch("scout_pipeline.ArchitectAgent")
def test_approve_niche_creates_project(mock_arch_cls, tmp_path):
    from scout_pipeline import approve_niche
    mock_arch = MagicMock()
    mock_arch.run.return_value = "clean_beauty"
    mock_arch_cls.return_value = mock_arch

    job = ScoutJob(job_id="test_pipe_001", triggered_by="test")
    job.opportunities = _make_opportunities()

    slug = approve_niche(job, "clean beauty", _make_config(), projects_root=tmp_path)
    assert slug == "clean_beauty"
    assert job.approved_niche == "clean beauty"
    mock_arch.run.assert_called_once()
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_scout_pipeline.py -v
```

Expected: `ModuleNotFoundError: No module named 'scout_pipeline'`

- [ ] **Step 3: Create scout_pipeline.py**

Create `scout_pipeline.py`:

```python
from __future__ import annotations
import json
import logging
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
    try:
        from google_drive import get_credentials, upload_file_to_drive
        import tempfile, os
        creds = get_credentials(
            credential_path=Path(config.google_application_credentials) if config.google_application_credentials else None
        )
        content = _format_report_markdown(job)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(content)
            tmp_path = f.name
        upload_file_to_drive(
            creds,
            file_path=Path(tmp_path),
            folder_id=config.scout_drive_folder_id,
            filename=f"scout_report_{job.job_id}.md",
        )
        os.unlink(tmp_path)
        logger.info("Scout report uploaded to Google Drive")
    except Exception as exc:
        logger.warning("Google Drive export failed: %s", exc)


def _format_report_markdown(job: ScoutJob) -> str:
    lines = [f"# Scout Report — {job.job_id}\n", f"Triggered by: {job.triggered_by}\n\n"]
    for i, opp in enumerate(job.opportunities, 1):
        lines.append(f"## {i}. {opp.niche_name} (Score: {opp.reach_score})\n")
        lines.append(f"- **Audience:** {opp.target_audience}\n")
        lines.append(f"- **Platforms:** {', '.join(opp.platforms)}\n")
        lines.append(f"- **Trend:** {opp.trend_direction}\n")
        lines.append(f"- **Formats:** {', '.join(opp.content_formats)}\n")
        lines.append(f"- **Monetization:** {opp.monetization_notes}\n\n")
    return "".join(lines)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_scout_pipeline.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scout_pipeline.py tests/test_scout_pipeline.py
git commit -m "feat: add scout_pipeline orchestration with report saving and Drive export"
```

---

## Task 8: Scheduler Integration

> **Dependency:** Complete Task 9 (Telegram/notifier) first so `send_telegram_scout_report` exists.

**Files:**
- Modify: `scheduler.py`

- [ ] **Step 1: Add daily scout trigger**

In `scheduler.py`, find the main scheduling loop or cron-style block (look for where `datetime.now()` is checked for hour/day to trigger briefs). Add two helper functions near the other `_run_*` helpers:

```python
def _should_run_scout(now: datetime) -> bool:
    return now.hour == 8 and now.minute == 0


def _run_daily_scout(config) -> None:
    try:
        logger.info("Daily scout starting...")
        from scout_pipeline import run_scout_pipeline
        from notifier import send_telegram_scout_report
        job = run_scout_pipeline(config, triggered_by="scheduler")
        send_telegram_scout_report(config, job)
    except Exception as exc:
        logger.error("Daily scout failed: %s", exc)
```

Then in the main scheduler loop, add a call where other daily checks happen:

```python
if _should_run_scout(now):
    _run_daily_scout(config)
```

Note: imports are inside the function (deferred) to avoid circular import issues.

- [ ] **Step 2: Verify no regressions**

```bash
pytest tests/ -v --tb=short
```

Expected: all existing tests PASS.

- [ ] **Step 3: Commit**

```bash
git add scheduler.py
git commit -m "feat: add daily scout trigger at 08:00 in scheduler"
```

---

## Task 9: Telegram Integration

**Files:**
- Modify: `telegram_bot.py`
- Modify: `notifier.py`

- [ ] **Step 1: Add `send_telegram_scout_report` to notifier.py**

In `notifier.py`, add:

```python
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
            f"{i}. <b>{opp.niche_name}</b> — Score: {opp.reach_score:.0f}\n"
            f"   {opp.target_audience} | {opp.trend_direction} | {', '.join(opp.platforms)}\n"
        )
    lines.append("\nApprove a niche to generate project files:")

    keyboard = {
        "inline_keyboard": [
            [{"text": f"✅ {opp.niche_name}", "callback_data": f"scout_approve:{job.job_id}:{opp.niche_name}"}]
            for opp in top3
        ] + [[{"text": "⏭ Skip this report", "callback_data": f"scout_skip:{job.job_id}"}]]
    }

    from telegram_bot import _api
    _api(token, "sendMessage", chat_id=chat_id, text="".join(lines), parse_mode="HTML", reply_markup=keyboard)
```

- [ ] **Step 2: Add `/scout` command handler to telegram_bot.py**

In `telegram_bot.py`, in the message handler (where `/run`, `/status`, etc. are handled), add:

```python
elif text == "/scout":
    _send_message(token, chat_id, "🔍 Running Scout pipeline... this may take 1-2 minutes.")
    import threading
    from config import Config
    from scout_pipeline import run_scout_pipeline
    from notifier import send_telegram_scout_report

    def _run_scout():
        try:
            cfg = Config.from_env()
            job = run_scout_pipeline(cfg, triggered_by="telegram")
            send_telegram_scout_report(cfg, job)
        except Exception as exc:
            _send_message(token, chat_id, f"❌ Scout failed: {exc}")

    threading.Thread(target=_run_scout, daemon=True).start()
```

- [ ] **Step 3: Add approve/skip callback handler**

In `telegram_bot.py`, in the callback_query handler (where inline button callbacks are handled), add:

```python
elif callback_data.startswith("scout_approve:"):
    _, job_id, niche_name = callback_data.split(":", 2)
    _answer_callback(token, callback_query_id)
    _send_message(token, chat_id, f"⚙️ Generating project files for <b>{niche_name}</b>...", )

    import threading
    from config import Config
    from scout_pipeline import approve_niche, run_scout_pipeline
    from models.niche_opportunity import ScoutJob
    import json
    from pathlib import Path

    def _run_approve():
        try:
            cfg = Config.from_env()
            # Load the saved job report
            report_path = Path("output/scout_reports") / f"{job_id}-scout-report.json"
            job = ScoutJob.model_validate_json(report_path.read_text())
            slug = approve_niche(job, niche_name, cfg)
            _send_message(token, chat_id, f"✅ Project <b>{slug}</b> created! Activate with /run {slug}")
        except Exception as exc:
            _send_message(token, chat_id, f"❌ Approve failed: {exc}")

    threading.Thread(target=_run_approve, daemon=True).start()

elif callback_data.startswith("scout_skip:"):
    _answer_callback(token, callback_query_id)
    _send_message(token, chat_id, "⏭ Scout report skipped.")
```

- [ ] **Step 4: Verify existing tests pass**

```bash
pytest tests/ -v --tb=short
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add telegram_bot.py notifier.py
git commit -m "feat: add /scout Telegram command, scout report notification, approve/skip callbacks"
```

---

## Task 10: Dashboard Routes

**Files:**
- Create: `routes/scout.py`

- [ ] **Step 1: Create scout routes**

Create `routes/scout.py`:

```python
"""Scout pipeline dashboard routes."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, Form
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from config import Config
from models.niche_opportunity import ScoutJob
from routes.deps import templates, verify_auth, _root

router = APIRouter(prefix="/scout", tags=["scout"])


def _latest_report(root: Path) -> ScoutJob | None:
    reports_dir = root / "output" / "scout_reports"
    if not reports_dir.exists():
        return None
    reports = sorted(reports_dir.glob("*.json"), reverse=True)
    if not reports:
        return None
    return ScoutJob.model_validate_json(reports[0].read_text())


@router.get("/", response_class=HTMLResponse)
async def scout_index(request: Request, _=Depends(verify_auth)):
    job = _latest_report(_root)
    return templates.TemplateResponse(
        "scout.html",
        {"request": request, "job": job},
    )


@router.post("/run")
async def scout_run(request: Request, _=Depends(verify_auth)):
    def _background():
        try:
            cfg = Config.from_env()
            from scout_pipeline import run_scout_pipeline
            run_scout_pipeline(cfg, triggered_by="dashboard")
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("Dashboard scout failed: %s", exc)

    threading.Thread(target=_background, daemon=True).start()
    return RedirectResponse(url="/scout/", status_code=303)


@router.post("/approve")
async def scout_approve(request: Request, job_id: str = Form(...), niche_name: str = Form(...), _=Depends(verify_auth)):
    def _background():
        try:
            cfg = Config.from_env()
            from scout_pipeline import approve_niche
            report_path = _root / "output" / "scout_reports" / f"{job_id}-scout-report.json"
            job = ScoutJob.model_validate_json(report_path.read_text())
            approve_niche(job, niche_name, cfg)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("Dashboard approve failed: %s", exc)

    threading.Thread(target=_background, daemon=True).start()
    return RedirectResponse(url="/scout/", status_code=303)
```

- [ ] **Step 2: Register router in main FastAPI app**

In `dashboard.py` (or wherever routers are registered), add:

```python
from routes.scout import router as scout_router
app.include_router(scout_router)
```

- [ ] **Step 3: Verify app starts**

```bash
python -c "from dashboard import app; print('OK')"
```

Expected: `OK` with no import errors.

- [ ] **Step 4: Commit**

```bash
git add routes/scout.py dashboard.py
git commit -m "feat: add /scout dashboard routes (index, run, approve)"
```

---

## Task 11: Dashboard Template

**Files:**
- Create: `templates/scout.html`

- [ ] **Step 1: Create scout.html**

Create `templates/scout.html`:

```html
{% extends "base.html" %}
{% block title %}Scout — NayzFreedom Fleet{% endblock %}

{% block content %}
<div class="container py-4">
  <div class="d-flex justify-content-between align-items-center mb-4">
    <h2>🔍 Scout — Niche Opportunities</h2>
    <form method="post" action="/scout/run">
      <button type="submit" class="btn btn-primary">Run Scout Now</button>
    </form>
  </div>

  {% if not job %}
  <div class="alert alert-info">No scout report yet. Click "Run Scout Now" to generate one.</div>
  {% else %}
  <p class="text-muted">Report: {{ job.job_id }} · Triggered by: {{ job.triggered_by }} · Status: {{ job.status }}</p>

  <div class="row g-3">
    {% for opp in job.opportunities %}
    <div class="col-md-6">
      <div class="card h-100 shadow-sm">
        <div class="card-body">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <h5 class="card-title mb-0">{{ opp.niche_name }}</h5>
            <span class="badge bg-{{ 'success' if opp.reach_score >= 80 else 'warning' }} fs-6">
              {{ opp.reach_score | round(0) | int }}
            </span>
          </div>
          <p class="text-muted small mb-1">{{ opp.target_audience }}</p>
          <p class="mb-1">
            <span class="badge bg-{{ 'success' if opp.trend_direction == 'rising' else 'secondary' }}">
              {{ opp.trend_direction }}
            </span>
            {% for p in opp.platforms %}
            <span class="badge bg-light text-dark">{{ p }}</span>
            {% endfor %}
          </p>
          <p class="small mb-2"><strong>Formats:</strong> {{ opp.content_formats | join(', ') }}</p>
          <p class="small text-muted mb-3">{{ opp.monetization_notes }}</p>

          {% if job.status == 'awaiting_approval' %}
          <form method="post" action="/scout/approve">
            <input type="hidden" name="job_id" value="{{ job.job_id }}">
            <input type="hidden" name="niche_name" value="{{ opp.niche_name }}">
            <button type="submit" class="btn btn-success btn-sm w-100">✅ Activate This Niche</button>
          </form>
          {% elif job.approved_niche == opp.niche_name %}
          <span class="badge bg-success w-100 p-2">✅ Approved</span>
          {% endif %}
        </div>
      </div>
    </div>
    {% endfor %}
  </div>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 2: Check base.html extends correctly**

```bash
grep -n "base.html\|block content" templates/scout.html templates/base.html 2>/dev/null | head -10
```

If the project uses a different base template name, update `{% extends "base.html" %}` to match.

- [ ] **Step 3: Commit**

```bash
git add templates/scout.html
git commit -m "feat: add Scout dashboard template with niche cards and approve buttons"
```

---

## Task 12: Agent Tools Registration

**Files:**
- Modify: `tools/agent_tools.py`

- [ ] **Step 1: Add scout tool definitions**

In `tools/agent_tools.py`, inside `get_tool_definitions()`, append:

```python
        {
            "name": "run_scout",
            "description": "Scan 4 data sources (Brave, Google Trends, Reddit, Meta Ads) for niche opportunities. Call first in scout pipeline.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "dry_run": {"type": "boolean", "description": "If true, use mock data. Default false."}
                },
                "required": [],
            },
        },
        {
            "name": "run_analyst",
            "description": "Score and rank niche signals from Scout. Returns top 5 NicheOpportunity ranked by reach potential.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "dry_run": {"type": "boolean", "description": "If true, use mock data. Default false."}
                },
                "required": [],
            },
        },
        {
            "name": "run_architect",
            "description": "Generate project YAML files for the approved niche. Call only after Captain has set approved_niche.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "dry_run": {"type": "boolean", "description": "If true, log only. Do not write files. Default false."}
                },
                "required": [],
            },
        },
```

- [ ] **Step 2: Verify tests pass**

```bash
pytest tests/ -v --tb=short
```

Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add tools/agent_tools.py
git commit -m "feat: register run_scout, run_analyst, run_architect in agent tool definitions"
```

---

## Final Verification

- [ ] **Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS, no regressions.

- [ ] **Smoke test dry-run pipeline**

```bash
python -c "
from config import Config
from scout_pipeline import run_scout_pipeline
cfg = Config(brave_search_api_key='x', openai_api_key='x')
job = run_scout_pipeline(cfg, triggered_by='smoke-test', dry_run=True)
print('Opportunities:', len(job.opportunities))
for o in job.opportunities:
    print(f'  {o.reach_score:.0f} — {o.niche_name}')
"
```

Expected: prints 3+ opportunities with scores.

- [ ] **Final commit**

```bash
git add -p
git commit -m "feat: Scout Pipeline complete — niche discovery, scoring, approval, project generation"
```
