# Comment Reply Bot — Design Spec
**Date:** 2026-05-18  
**Project:** NayzFreedom Fleet  
**Status:** Approved

---

## Overview

A dedicated Telegram bot that accepts screenshot images of social media comments, extracts all comments using AI vision, and drafts brand-appropriate replies for each comment. Runs as a separate process alongside the existing pipeline bot. Designed for daily use across multiple brand pages (SlayHack, Stadium Sweethearts, Personal Finance for Women).

---

## Architecture

### New Files

| File | Purpose |
|---|---|
| `comment_reply_bot.py` | Main bot — Telegram polling loop, photo handler, `/model` command |
| `comment_model_router.py` | Provider adapter for Anthropic / OpenAI / Gemini with auto-fallback |
| `comment_chat_map.yaml` | Maps Telegram chat_id → project slug + fallback chain config |

### Modified Files

| File | Change |
|---|---|
| `projects/*/platform_specs.yaml` | Add `comment_max_chars` per platform |

### Integration Points

- Reads `projects/<slug>/brand.yaml` for `tone`, `target_audience`, `script_style`
- Reads `projects/<slug>/platform_specs.yaml` for `comment_max_chars`
- Uses existing Anthropic + OpenAI API keys from `config.py` / `.env`
- Adds `COMMENT_BOT_TOKEN` and `GEMINI_API_KEY` to `.env`

---

## Configuration

### `comment_chat_map.yaml`

```yaml
chats:
  "-1001234567890":
    project: slay_hack
    default_platform: instagram
  "-1009876543210":
    project: stadium_sweethearts
    default_platform: tiktok
  "-1001122334455":
    project: personal_finance_for_women
    default_platform: instagram

default_provider: anthropic
default_model: claude-sonnet-4-6

fallback_chain:
  - provider: anthropic
    model: claude-sonnet-4-6
  - provider: openai
    model: gpt-4o
  - provider: gemini
    model: gemini-2.0-flash
```

### Platform Comment Limits (added to each `platform_specs.yaml`)

```yaml
tiktok:
  comment_max_chars: 150
instagram:
  comment_max_chars: 2200
facebook:
  comment_max_chars: 8000
youtube:
  comment_max_chars: 10000
```

### New `.env` Keys

```
COMMENT_BOT_TOKEN=<new dedicated bot token>
GEMINI_API_KEY=<google gemini api key>
```

---

## Data Flow

```
1. User sends photo (screenshot) to Telegram group
2. Bot receives update → checks message has photo
3. Lookup chat_id in comment_chat_map.yaml → get project_slug
   └── If chat_id not found → bot stays silent (spam guard)
4. Load brand.yaml for project → tone, target_audience, script_style
5. Determine platform:
   - If user includes platform in photo caption (e.g. "tiktok", "ig", "fb") → use that
   - Otherwise → use default_platform for this chat from comment_chat_map.yaml
   - No auto-detection from screenshot (unreliable)
6. Load platform_specs.yaml → get comment_max_chars for detected platform
7. Download photo from Telegram → base64 encode
8. Send to Model Router with system prompt
9. Router tries providers in fallback_chain order
10. If reply exceeds comment_max_chars → request AI to shorten automatically
11. Bot sends formatted draft reply back to group
```

---

## AI Prompt Design

### System Prompt Template

```
You are a social media community manager for {project_name}.
Brand tone: {tone}
Target audience: {target_audience}
Writing style: {script_style}

Look at this screenshot carefully.

1. Find ALL comments visible in the image, reading top to bottom.
2. For each comment, write ONE reply that matches the brand tone.
3. Each reply must be under {comment_max_chars} characters.
4. Match the language of the comment (Thai replies Thai, English replies English).
5. Do not use hashtags unless the comment contains them.
6. Never mention AI or automation.

Return your response in this exact format:
COMMENT_1: [exact comment text you read]
REPLY_1: [your reply]
COMMENT_2: [exact comment text you read]
REPLY_2: [your reply]
...

Return ONLY this format. No other text.
```

---

## Telegram Output Format

```
📸 พบ 3 comments ในภาพ

1️⃣ @user_one: "omg where did you get this?"
💬 "Girlie it's linked in bio! 🔗 You're going to love it ✨"

2️⃣ @user_two: "price?"
💬 "Check the link in bio babe, there's a discount code waiting for you 💅"

3️⃣ @user_three: "this looks amazing!"
💬 "You're so sweet, thank you! 🤍 More coming soon!"

─────────────────
🤖 claude-sonnet-4-6  |  📱 instagram
```

---

## Model Router

### Auto-Fallback (always active)

```
Try provider[0] (Anthropic)
  → 429 / quota error → try provider[1] (OpenAI)
  → error → try provider[2] (Gemini)
  → all failed → send error message listing all providers tried
```

### Manual Switch via Telegram Command

Users can switch the active model for their specific chat group:

```
/model anthropic claude-sonnet-4-6
/model anthropic claude-opus-4-7
/model openai gpt-4o
/model gemini gemini-2.0-flash
/model auto      ← reset to fallback chain
```

Bot confirms: `✅ Switched to gemini / gemini-2.0-flash for this chat`

Model preference persists per chat_id in a state file (same pattern as `_STATE_FILE` in `telegram_bot.py`).

---

## Error Handling

| Scenario | Bot Response |
|---|---|
| No photo in message | Ignored silently |
| chat_id not in map | Ignored silently (spam guard) |
| No comment detected in image | "ไม่เจอ comment ในรูป กรุณาส่งรูปใหม่" |
| Reply exceeds platform limit | AI automatically shortens before sending |
| All providers fail | Lists each provider tried and their error |
| Unknown `/model` argument | Shows valid options |

---

## Reply History Log

เก็บ log การตอบ comment ป้องกันตอบซ้ำถ้าส่งรูปเดิมมาอีกครั้ง

- ไฟล์: `output/comment_reply_log/<project_slug>.jsonl`
- แต่ละ entry เก็บ: `timestamp`, `chat_id`, `image_hash` (MD5 ของรูป), `comments[]`, `replies[]`, `model_used`, `platform`
- ก่อน draft: ตรวจ `image_hash` — ถ้าพบแล้วในไฟล์ → แจ้ง "รูปนี้ตอบไปแล้วเมื่อ [timestamp]" พร้อมแสดง reply เดิม

---

## Bot Commands

```
/help        แสดง commands ทั้งหมด + วิธีใช้งาน
/model       สลับ AI provider และโมเดล
/model auto  รีเซ็ตกลับ fallback chain ปกติ
```

ตัวอย่าง `/help` response:
```
🤖 Comment Reply Bot

ส่งรูป screenshot → ได้ draft reply ทันที

Commands:
/model anthropic claude-sonnet-4-6
/model openai gpt-4o
/model gemini gemini-2.0-flash
/model auto   ← fallback อัตโนมัติ

แนบ platform ใน caption ได้เลย:
  "tiktok" | "ig" | "fb" | "youtube"
  (ถ้าไม่แนบ ใช้ default ของ group นี้)
```

---

## Phase 2: Auto-Post (Future)

After draft is sent, bot adds inline keyboard:

```
[✅ Post IG]  [✅ Post FB]  [✅ Post TikTok]  [✏️ Edit]
```

Tapping Post triggers the existing Meta API / TikTok API in `config.py`. No architecture changes needed — this is additive only.

---

## Deployment

```bash
# Run alongside existing pipeline bot
python comment_reply_bot.py
```

No changes to existing `telegram_bot.py`, `orchestrator.py`, or pipeline code.
