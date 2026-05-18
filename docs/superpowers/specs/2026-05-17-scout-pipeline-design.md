# Scout Pipeline Design
**Date:** 2026-05-17
**Status:** Approved
**Author:** Captain Nayz + Codex

---

## Overview

Scout Pipeline คือ 3-agent system สำหรับค้นหาโอกาสเพจใหม่ (**niche discovery**) โดยสแกนตลาดจากหลายแหล่ง, score และ rank โอกาส, และ generate project files อัตโนมัติหลัง Captain approve

ทำงานแยกจาก Aurora production pipeline แต่แชร์ infrastructure เดิม (Config, Telegram, Scheduler, Google Drive)

**Priority:** Reach ก่อน — เลือก niche ที่มี viral potential และ audience growth สูง, monetize ทีหลัง

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  TRIGGER LAYER                       │
│   Telegram /scout  │  Dashboard Button  │  Scheduler │
└──────────────────────────┬──────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │      ScoutJob           │
              │  (shared job_store +    │
              │   config)               │
              └────────────┬────────────┘
                           │
         ┌─────────────────▼──────────────────┐
         │           SCOUT PIPELINE            │
         │                                     │
         │  Scout → Analyst → [Checkpoint] →   │
         │          Architect                  │
         └─────────────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │          OUTPUT          │
              │  Telegram (top 3)        │
              │  Dashboard /scout        │
              │  Google Drive archive    │
              └─────────────────────────┘
```

---

## Agents

### Scout — Scan & Signal Collection

ดึงข้อมูลจาก 4 แหล่งพร้อมกัน:

| แหล่ง | ข้อมูลที่ได้ | Library |
|---|---|---|
| Brave Search | trend articles, viral content signals | requests (มีอยู่แล้ว) |
| Google Trends | search volume + trend direction per niche | pytrends |
| Reddit API | subreddit size, growth rate, pain point language | praw |
| Meta Ads Library | advertiser activity per category (monetization signal) | requests |

Output: รายการ `NicheSignal` 10-20 niches

**NotebookLM integration point (optional):**
- ถ้ามี API → Scout ส่ง raw signals ไปให้ NotebookLM synthesize ก่อนส่ง Analyst
- ถ้าไม่มี API → Scout export raw data ไป Google Drive, Captain เปิด NotebookLM เองได้เป็น manual research step

### Analyst — Score & Rank

รับ `NicheSignal` → ใช้ OpenAI scoring ผ่าน runtime เดิมของ Fleet เพื่อ score แต่ละ niche ด้วย 4 มิติ:

| มิติ | นิยาม |
|---|---|
| Reach Score | trend direction + search volume growth rate |
| Audience Fit | ตรง women USA 18-44 + language/tone match |
| Content Fit | Fleet ผลิตได้โดยไม่ต้องปรับระบบ |
| Competition Gap | ใหญ่พอ แต่ไม่ saturated เกิน |

Output: top 5 `NicheOpportunity` ranked by Reach Score

### Architect — Project File Generator

Triggered หลัง Captain approve niche ที่เลือก

Generate ไฟล์ครบชุดใน `projects/<slug>/`:
- `brand.yaml`
- `pm_profile.yaml`
- `platform_specs.yaml`
- `weekly_calendar.yaml`

แล้วแจ้ง Captain ผ่าน Telegram ว่า project พร้อม activate

---

## Data Model

```python
# models/niche_opportunity.py

@dataclass
class NicheSignal:
    niche_name: str
    raw_data: dict  # ข้อมูลดิบจากแต่ละ source

@dataclass
class NicheOpportunity:
    niche_name: str
    target_audience: str
    platforms: list[str]
    reach_score: float          # 0-100
    trend_direction: str        # "rising" | "stable" | "declining"
    content_formats: list[str]
    monetization_notes: str
    signals: dict               # breakdown ต่อ source

@dataclass
class ScoutJob:
    job_id: str
    triggered_by: str           # "scheduler" | "telegram" | "dashboard"
    created_at: datetime
    status: str
    opportunities: list[NicheOpportunity]
    approved_niche: str | None
```

---

## Trigger Flows

### Daily Scheduler (อัตโนมัติ)
- ทุกวัน 08:00 ตาม `SCOUT_TIMEZONE` ใน config.py (default: `America/New_York`)
- `scheduler.py` สร้าง ScoutJob → Scout → Analyst → Report
- ส่ง output ครบ 3 ช่องทางพร้อมกัน

### On-demand
- **Telegram:** `/scout [optional seed keyword]`
- **Dashboard:** ปุ่ม "Run Scout Now"
- ScoutJob ทำงานทันที, output เหมือน scheduled

---

## Approval & Architect Flow

```
Captain เห็น Report
    │
    ├── Telegram: กด [Approve: <niche_name>]
    │   หรือ
    └── Dashboard: คลิก "Activate This Niche"
              │
              ▼
    Checkpoint (telegram_checkpoint.py)
    บันทึก approved_niche ลง ScoutJob
              │
              ▼
    Architect generate:
    projects/<slug>/brand.yaml
    projects/<slug>/pm_profile.yaml
    projects/<slug>/platform_specs.yaml
    projects/<slug>/weekly_calendar.yaml
              │
              ▼
    Telegram: "Project <name> ready — activate ด้วย /run <slug>"
```

---

## Output Layer

| ช่องทาง | เนื้อหา |
|---|---|
| **Telegram** | สรุป top 3 niches + Reach Score + ปุ่ม Approve/Skip |
| **Dashboard /scout** | Full niche cards พร้อม signal breakdown ทุก source |
| **Google Drive** | `scout_report_YYYY-MM-DD.md` เก็บเป็น weekly archive |

---

## Files to Create / Modify

### ไฟล์ใหม่
```
agents/scout.py                      — Scout agent (4 data sources)
agents/analyst.py                    — Analyst agent (score & rank)
agents/architect.py                  — Project file generator
models/niche_opportunity.py          — NicheSignal, NicheOpportunity, ScoutJob
routes/scout.py                      — Dashboard /scout endpoints
templates/scout.html                 — Scout report UI
```

### ไฟล์ที่แก้ไข (minimal)
```
scheduler.py             — เพิ่ม daily scout trigger (08:00 ทุกวัน)
telegram_bot.py          — เพิ่ม /scout command + approve handler
config.py                — เพิ่ม SCOUT_SCHEDULE, SCOUT_SEED_CATEGORIES
tools/agent_tools.py     — เพิ่ม scout pipeline tool definitions
requirements.txt         — เพิ่ม pytrends, praw
```

### Output Structure
```
output/scout_reports/
  └── 2026-05-17-scout-report.json

projects/
  └── <new_slug>/
      ├── brand.yaml
      ├── pm_profile.yaml
      ├── platform_specs.yaml
      └── weekly_calendar.yaml
```

---

## Out of Scope (Phase 1)

- Social listening ผ่าน Apify / PhantomBuster
- Auto-publish content สำหรับ page ใหม่ทันที (ต้อง activate แยก)
- Competitive page analysis (จำนวน followers, engagement rate ของ competitor)
- NotebookLM API integration (รอยืนยัน API access ก่อน)
