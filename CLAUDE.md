# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**NayzFreedom Fleet / SlayHack** is a Python-based multi-agent AI pipeline that automates social media content production — from trend research through scripting, visual creation, QA, and publishing. The system supports multiple brand pages, each managed by a dedicated Project Manager with a unique persona.

Primary platforms: Facebook, Instagram (Reels). Secondary: TikTok, YouTube (later phases).

Current identity rules:

- Captain / owner identity: **Nayz**
- Current Aurora project PM identity: **Slay**
- Product and top-level operating system: **NayzFreedom Fleet**
- Current Aurora project display name: **SlayHack**
- Canonical project slug: `nayzfreedom_fleet`
- Legacy slug: `slay_hack`, compatibility alias only
- Do not rename PM `Slay` to `Nayz`; these are different roles.

Full design spec: [`docs/superpowers/specs/2026-05-12-slay-hack-agency-design.md`](docs/superpowers/specs/2026-05-12-slay-hack-agency-design.md)

---

## Agent Roster (Freedom Architects)

| Agent | File | Role |
|---|---|---|
| **Robin** | `orchestrator.py` | OpenAI tool-use orchestrator. Receives brief, loads PM, coordinates team. |
| **Mia Trend** | `agents/mia.py` | Trend research via Brave Search API |
| **Zoe Spark** | `agents/zoe.py` | Generates 5–10 content ideas from Mia's research |
| **Bella Quill** | `agents/bella.py` | Script writer (Hook → Body → CTA). Style defined by PM brand profile, not hardcoded. |
| **Lila Lens** | `agents/lila.py` | Visual Director. Calls GPT Image 2, Google Veo3, or Nano Banana. |
| **Nora Sharp** | `agents/nora.py` | QA Editor. Max 2 retries per job (configurable in `brand.yaml`). |
| **Roxy Rise** | `agents/roxy.py` | Hashtags, caption, optimal posting time |
| **Emma Heart** | `agents/emma.py` | FAQ markdown for community management |

### Scout Pipeline (Niche Discovery)

Separate 3-agent system for discovering new page opportunities. Runs daily at 08:00 ET via scheduler and on-demand via Telegram `/scout` or dashboard button.

| Agent | File | Role |
|---|---|---|
| **Scout** | `agents/scout.py` | Parallel scan: Brave Search, Google Trends (pytrends), Reddit (praw), Meta Ads Library |
| **Analyst** | `agents/analyst.py` | Scores and ranks niches on 4 dimensions via OpenAI (temperature=0) |
| **Architect** | `agents/architect.py` | Generates `projects/<slug>/` with 4 YAML files after Captain approves |

Data model: `models/niche_opportunity.py` — `NicheSignal`, `NicheOpportunity`, `ScoutJob`
Orchestrator: `scout_pipeline.py` — `run_scout_pipeline()`, `approve_niche()`

Approval flow: Captain sees top-3 report → taps Approve in Telegram or clicks "Activate This Niche" on dashboard → Architect generates project files → ready to activate with `python main.py --project <slug>`

---

## Multi-Page Architecture

Each brand page is a folder under `projects/`. Adding a new page requires only 2 YAML files — no code changes.

```
projects/
└── nayzfreedom_fleet/
    ├── pm_profile.yaml   ← page_name + PM persona
    └── brand.yaml        ← visual ID, tone, target_audience, script_style, platforms
```

`page_name` from `pm_profile.yaml` is used in all output paths and logs.

---

## Pipeline Flow

```
python main.py --project nayzfreedom_fleet --brief "..."

Robin → Mia → Zoe → [CHECKPOINT 1: pick idea]
  → Bella → Lila → [CHECKPOINT 2: review script + visual]
  → image/video generation → Nora QA → [CHECKPOINT 3: QA report]
  → Roxy → Emma → [CHECKPOINT 4: final approval]
  → Publish
```

Jobs are resumable: `python main.py --resume <job_id>`

---

## Setup

```bash
python3.12 -m venv .venv   # Python 3.12+ required (3.9 is EOL)
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in API keys
```

**Python version:** The project requires Python 3.12+. Python 3.9 reached end-of-life in October 2024.
To upgrade an existing venv: `rm -rf .venv && python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

Required env vars:
```
# Pipeline
OPENAI_API_KEY=
OPENAI_ROBIN_MODEL=gpt-4o
OPENAI_AGENT_MODEL=gpt-4o-mini
BRAVE_SEARCH_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
GOOGLE_CLOUD_PROJECT=
GOOGLE_APPLICATION_CREDENTIALS=
GOOGLE_DRIVE_MANUAL_KITS_FOLDER_ID=
GOOGLE_DRIVE_OAUTH_CLIENT_SECRETS=
GOOGLE_DRIVE_OAUTH_TOKEN_FILE=
META_ACCESS_TOKEN=
META_APP_SECRET=
META_PAGE_ID=
META_IG_USER_ID=
TIKTOK_ACCESS_TOKEN=
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
YOUTUBE_REFRESH_TOKEN=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
SCOUT_DRIVE_FOLDER_ID=

# Dashboard (both required — dashboard.py raises RuntimeError on import if missing)
DASHBOARD_USER=
DASHBOARD_PASSWORD=
PUBLIC_BASE_URL=https://fleet.nayzfreedom.cloud   # also read as OPS_PUBLIC_BASE_URL
OPS_PUBLIC_BASE_URL=https://fleet.nayzfreedom.cloud

# Comment Reply Bot
COMMENT_BOT_TOKEN=          # separate Telegram bot for the comment bot
COMMENT_CHAT_MAP_PATH=      # path to comment_chat_map.yaml (default: repo root)
ANTHROPIC_API_KEY=          # used by comment bot fallback chain
GEMINI_API_KEY=             # used by comment bot fallback chain

# Notifications / reporting
SLACK_WEBHOOK_URL=          # reporter.py weekly digest
TELEGRAM_BOT_TOKEN=         # pipeline checkpoint approval
TELEGRAM_CHAT_ID=
TELEGRAM_TIMEOUT_MINUTES=30
```

---

## Common Commands

```bash
# Run pipeline
python main.py --project nayzfreedom_fleet --brief "your brief here"

# Resume interrupted job
python main.py --resume 20260512_143022

# Dry-run from an interactive terminal (pauses for checkpoints).
# Agents use mock outputs; orchestration still follows the real deterministic stage machine.
python main.py --project nayzfreedom_fleet --brief "..." --dry-run

# Dry-run from Claude/Codex/cron (auto-approves checkpoints, no stdin block)
# Agents use mock outputs; orchestration still follows the real deterministic stage machine.
python main.py --project nayzfreedom_fleet --brief "..." --dry-run --unattended

# Run scheduler manually with mock agent/publish outputs
python scheduler.py --dry-run

# Cron entry for VPS (6 AM daily, logs to /var/log/nayzfreedom.log)
# 0 6 * * * /path/to/.venv/bin/python /path/to/scheduler.py >> /var/log/nayzfreedom.log 2>&1

# Run weekly performance reporter (generates markdown + sends Slack digest)
python reporter.py

# Weekly reporter dry-run (prints Slack message to stdout, no POST)
python reporter.py --dry-run

# Cron entry for VPS (8 AM every Monday)
# 0 8 * * 1 /path/to/.venv/bin/python /path/to/reporter.py >> /var/log/nayzfreedom.log 2>&1

# Run Scout niche discovery manually (dry-run)
python -c "from config import Config; from scout_pipeline import run_scout_pipeline; job = run_scout_pipeline(Config.from_env(), triggered_by='manual', dry_run=True); [print(f'{o.reach_score:.0f} — {o.niche_name}') for o in job.opportunities]"

# Run tests
pytest

# Single test file
pytest tests/test_orchestrator.py -v

# Type check
mypy .

# Lint
ruff check .
ruff format .

# Run dashboard (local only)
python dashboard.py

# Dashboard on VPS (accessible from outside)
python dashboard.py --host 0.0.0.0 --port 8000

# Telegram checkpoint approval (Phase 11b)
# 1. Create a bot: message @BotFather on Telegram → /newbot → copy token
# 2. Get your chat ID: message @userinfobot on Telegram → copy the id number
# 3. Set env vars in .env:
#    TELEGRAM_BOT_TOKEN=<token>
#    TELEGRAM_CHAT_ID=<your_id>
#    TELEGRAM_TIMEOUT_MINUTES=30   # optional, default 30
# 4. Run pipeline in attended mode (no --unattended flag):
#    python main.py --project nayzfreedom_fleet --brief "..."
#    Pipeline pauses at each checkpoint and sends a Telegram message.
#    Reply via button or free text. Auto-approves after TELEGRAM_TIMEOUT_MINUTES if no reply.
```

---

## Dashboard / Fleet Command Center

The dashboard is now the Fleet command interface, not just a raw jobs table.

Primary routes:

- `/` — Captain's Deck with command brief, fleet ship status, active missions, and attention signals
- `/aurora` — The Aurora mission-control hub
- `/aurora/islands/nayzfreedom_fleet` — current SlayHack project island, PM Slay, brand profile, island command state
- `/aurora/missions` — all missions
- `/jobs/{job_id}` — mission detail / voyage log with mission command, current stage, progress, output readiness, timeline, and artifacts
- `/aurora/crew` and `/aurora/crew/{slug}` — Aurora crew registry and character sheets
- `/freedom` — planned personal ship placeholder; do not add sensitive data until privacy boundaries are stronger
- `/lyra` — planned music ship placeholder
- `/scout/` — Scout niche discovery: latest report, niche cards with reach scores, Run Scout Now button, Activate This Niche approval
- `/readiness` — private operational preflight for auth, project config, output, assets, deploy files, and privacy boundary

The Freedom and Lyra should stay clearly marked as planned until their data model, privacy model, and memory boundaries are ready.

---

## Key Architecture Notes

- **`OPENAI_ROBIN_MODEL` remains in config for compatibility**, but orchestration is now code-driven with explicit stage transitions and checkpoints to keep resume deterministic.
- **All agents use `OPENAI_AGENT_MODEL`** for writing/analysis tasks.
- **`ContentJob`** (Pydantic model in `models/content_job.py`) is the single contract passed between all agents. Never pass raw dicts.
- **Jobs persist to `output/<page_name>/<job_id>/job.json`** after every deterministic stage transition. Resume reconstructs the next required step from saved job state + checkpoint log instead of replaying the full pipeline.
- **Manual Post Kits** are the default test-phase handoff: download or sync the structured kit to Google Drive, then Captain posts manually. Live publishing remains locked unless explicitly approved.
- **`job.dry_run: bool`** controls whether agents call real APIs or return mock data. Use `--dry-run` during development.
- **Bella has no hardcoded style** — `script_style` and `target_audience` in `brand.yaml` fully control her output.
- **Nora can send work back** to Bella or Lila. `nora_max_retries` in `brand.yaml` controls the limit (default: 2).
- **`BaseAgent._call_claude()` calls OpenAI**, not Claude/Anthropic — the name is misleading. All pipeline agents use the OpenAI SDK via `BaseAgent`.
- **Canonical project slug**: `nayzfreedom_fleet`. `slay_hack` is a compatibility alias only. Keep new config under `projects/nayzfreedom_fleet/` and treat any `slay_hack` references as legacy.
- **Scheduler rotation gate**: a project added by Scout won't run in the scheduler until `scout_activation.yaml` in its project dir contains `scheduler_rotation_approved: true`. `list_project_slugs()` silently skips unapproved projects.
- **Dashboard is FastAPI**, split into `routes/` modules. `dashboard.py` is a thin re-exporter for test-compatibility; route logic lives in `routes/{captain,aurora,jobs,ships,ops,project_admin,readiness,scout}.py`. Shared app/auth/templates are in `routes/deps.py`.
- **Deploy** (`deploy/`) contains systemd `.service` and `.timer` unit files plus `setup.sh` / `update.sh` for VPS deployment.

---

## Comment Reply Bot

A separate Telegram-based vision bot (`comment_reply_bot.py`) for drafting replies to social comments. It receives screenshot images from Telegram group chats and returns AI-generated draft replies.

- **`comment_chat_map.yaml`** maps each Telegram group `chat_id` to a project slug and default platform. Group IDs are negative numbers (e.g. `-1001234567890`).
- Uses a multi-provider fallback chain (Anthropic → OpenAI → Gemini) via `comment_model_router.py`. Chain is configured in `comment_chat_map.yaml` under `fallback_chain`.
- Run: `python comment_reply_bot.py` (requires `COMMENT_BOT_TOKEN` and `COMMENT_CHAT_MAP_PATH`).
- Systemd unit: `deploy/nayzfreedom-comment-reply-bot.service`.

---

## Output Structure

```
output/
└── Slayhack/
    └── 20260512_143022/
        ├── job.json          ← full ContentJob state (resume point)
        ├── ideas.md          ← Zoe's ideas
        ├── script.md         ← Bella's final script
        ├── visual_prompt.txt ← Lila's prompt
        ├── image.png         ← GPT Image 2 output
        ├── video.mp4         ← Veo3 output (Phase 3+)
        ├── growth.md         ← Roxy's hashtags + caption + timing
        └── faq.md            ← Emma's pre-written responses
```
