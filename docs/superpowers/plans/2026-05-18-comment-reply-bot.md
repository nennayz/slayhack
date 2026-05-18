# Comment Reply Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dedicated Telegram bot that receives screenshot images of social media comments, extracts all comments with Claude Vision, and drafts brand-appropriate replies using a multi-provider AI router (Anthropic / OpenAI / Gemini) with auto-fallback.

**Architecture:** New `comment_reply_bot.py` (Telegram polling loop + handlers) and `comment_model_router.py` (provider adapter) added alongside the existing pipeline — no existing files broken. Per-chat model overrides are persisted in a state file; reply history is logged as `.jsonl` per project to prevent duplicate replies.

**Tech Stack:** Python 3.12, `requests` (raw Telegram API — same pattern as `telegram_bot.py`), `anthropic>=0.40.0`, `openai>=1.0.0` (already present), `google-generativeai>=0.8.0`, `pillow>=10.0.0`, `pyyaml>=6.0` (already present), `pytest` + `pytest-mock`.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `comment_model_router.py` | Provider adapter — Anthropic / OpenAI / Gemini, auto-fallback, text+vision calls |
| Create | `comment_reply_bot.py` | Telegram polling loop, photo handler, `/model`, `/help`, reply log helpers |
| Create | `comment_chat_map.yaml` | Maps Telegram chat_id → project slug + default platform + fallback chain |
| Create | `tests/test_comment_model_router.py` | Unit tests for ModelRouter |
| Create | `tests/test_comment_reply_bot.py` | Unit tests for pure helpers and handlers |
| Modify | `requirements.txt` | Add `anthropic`, `google-generativeai`, `pillow` |
| Modify | `tests/conftest.py` | Stub `anthropic` and `google.generativeai` for CI |
| Modify | `projects/slay_hack/platform_specs.yaml` | Add `comment_max_chars` per platform |
| Modify | `projects/stadium_sweethearts/platform_specs.yaml` | Add `comment_max_chars` per platform |
| Modify | `projects/personal_finance_for_women/platform_specs.yaml` | Add `comment_max_chars` per platform |

---

## Task 1: Dependencies + conftest stubs

**Files:**
- Modify: `requirements.txt`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add new dependencies to requirements.txt**

Open `requirements.txt` and append after the existing `openai>=1.0.0` line:

```
anthropic>=0.40.0
google-generativeai>=0.8.0
pillow>=10.0.0
```

- [ ] **Step 2: Install dependencies**

```bash
cd /Users/nennayz/Documents/NayzFreedom/code/nayzfreedom-fleet
source .venv/bin/activate
pip install anthropic>=0.40.0 "google-generativeai>=0.8.0" "pillow>=10.0.0"
```

Expected: All three packages install without error.

- [ ] **Step 3: Stub new packages in conftest.py so tests run without real API keys**

Append to `tests/conftest.py` after the existing google stubs:

```python
import sys
from unittest.mock import MagicMock

# Stub anthropic for tests that don't need real API calls
if "anthropic" not in sys.modules:
    _anthropic = MagicMock()
    sys.modules["anthropic"] = _anthropic

# Stub google.generativeai for tests
if "google.generativeai" not in sys.modules:
    _genai = MagicMock()
    sys.modules["google.generativeai"] = _genai
    sys.modules.setdefault("google.generativeai.types", MagicMock())
```

- [ ] **Step 4: Run existing tests to confirm nothing broke**

```bash
pytest tests/ -v --tb=short
```

Expected: All existing tests pass.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt tests/conftest.py
git commit -m "feat: add anthropic, google-generativeai, pillow dependencies for comment reply bot"
```

---

## Task 2: Create comment_chat_map.yaml

**Files:**
- Create: `comment_chat_map.yaml`

- [ ] **Step 1: Create the config file with placeholder chat IDs**

Create `comment_chat_map.yaml` at the repo root:

```yaml
# Map each Telegram group chat_id to a project.
# To find a chat_id: add @userinfobot to the group, it will report the group ID.
# Group IDs are negative numbers e.g. -1001234567890
chats:
  "-1001111111111":
    project: slay_hack
    default_platform: instagram
  "-1002222222222":
    project: stadium_sweethearts
    default_platform: tiktok
  "-1003333333333":
    project: personal_finance_for_women
    default_platform: instagram

# Global fallback chain — tried in order when the active provider fails (429 / quota)
fallback_chain:
  - provider: anthropic
    model: claude-sonnet-4-6
  - provider: openai
    model: gpt-4o
  - provider: gemini
    model: gemini-2.0-flash
```

- [ ] **Step 2: Commit**

```bash
git add comment_chat_map.yaml
git commit -m "feat: add comment_chat_map.yaml config template"
```

---

## Task 3: Add comment_max_chars to platform_specs.yaml

**Files:**
- Modify: `projects/slay_hack/platform_specs.yaml`
- Modify: `projects/stadium_sweethearts/platform_specs.yaml`
- Modify: `projects/personal_finance_for_women/platform_specs.yaml`

- [ ] **Step 1: Update slay_hack/platform_specs.yaml**

Add `comment_max_chars` to each platform block. The file currently has `tiktok`, `instagram`, `facebook`, `youtube`. Add the field to each:

```yaml
tiktok:
  comment_max_chars: 150
  editorial: "Prioritize viral retention and comments. Use a mistake-callout hook in the first 3 words, fast pacing, sound-on assumptions, and a comment CTA. Favor 60+ second Hack videos when Creator Rewards revenue is the goal."
instagram:
  comment_max_chars: 2200
  editorial: "Optimize for saves and profile trust. Use polished Reels, concise captions, clear visual hierarchy, Stories or poll follow-ups, and save-first CTAs. Avoid dumping cross-posts with no engagement strategy."
facebook:
  comment_max_chars: 8000
  editorial: "Optimize for shares, broad clarity, and community funnel movement. Use slightly clearer language than TikTok, longer captions when useful, and rotate CTAs to the Group, Messenger Channel, TikTok, or YouTube."
youtube:
  comment_max_chars: 10000
  editorial: "Optimize for searchability and repeat viewing. Keep Shorts titles under 60 characters, make the first second visually clear, add simple descriptions, and group episodes into repeatable playlists."
messenger:
  editorial: "Use as the high-intimacy broadcast layer. Send short daily tips, polls, Q&A prompts, and exclusive previews that feed future public content ideas."
facebook_group:
  editorial: "Use as the community depth layer. Weekly rituals, guides, member questions, and exclusive first-look posts should become future content briefs."
google_drive:
  editorial: "Final production assets belong under Slay Hack > Episodes > [Pillar] > [Episode ID] or New-Creative-Formats for Producer V2. Character references belong under Slay Hack > Assets > Characters."
notion:
  editorial: "Use the Episode Tracker and Meme Concept Tracker as duplicate checks and delivery status sources. Do not mark work ready until assets are synced and QA has passed."
```

- [ ] **Step 2: Update stadium_sweethearts/platform_specs.yaml**

Add `comment_max_chars` to each platform block:

```yaml
tiktok:
  comment_max_chars: 150
  editorial: "Use fast 6-8 second vertical fan-cam loops with an immediate visual moment, crowd ambience, short overlays, and playful captions. Avoid claims that the footage is real or hidden-camera."
instagram:
  comment_max_chars: 2200
  editorial: "Keep the grid polished with pink, navy, white, red, and golden stadium-light consistency. Prioritize clear face, emotion, stadium atmosphere, and safe AI disclosure in bio or pinned context."
youtube:
  comment_max_chars: 10000
  editorial: "Use repeatable Shorts titles under 60 characters such as The Camera Found Her, Sweetheart of the Night, or Wrong Team Right Energy. Make the first frame readable and the reaction loop obvious."
facebook:
  comment_max_chars: 8000
  editorial: "Use cleaner disclosure and broad sports lifestyle captions for Reels. Favor football, baseball, basketball, and tailgate themes with shareable PG-13 charm."
google_drive:
  editorial: "Organize assets under Stadium Sweethearts > Assets for logos, profiles, covers, character references, prompts, and published-ready exports. Flag any image with real team marks for cleanup before use."
notion:
  editorial: "Track each post by date, platform, title, sport, character archetype, content pillar, prompt, caption, hashtags, performance, and repost decision."
```

- [ ] **Step 3: Update personal_finance_for_women/platform_specs.yaml**

This file uses a different schema. Replace the entire file with a unified schema that adds `comment_max_chars`:

```yaml
instagram:
  comment_max_chars: 2200
  content_types:
    - video
    - infographic
    - article
  primary: true
tiktok:
  comment_max_chars: 150
  content_types:
    - video
    - infographic
    - article
  primary: true
youtube:
  comment_max_chars: 10000
  content_types:
    - video
    - infographic
    - article
  primary: true
facebook:
  comment_max_chars: 8000
```

- [ ] **Step 4: Commit**

```bash
git add projects/slay_hack/platform_specs.yaml \
        projects/stadium_sweethearts/platform_specs.yaml \
        projects/personal_finance_for_women/platform_specs.yaml
git commit -m "feat: add comment_max_chars to platform_specs.yaml for all projects"
```

---

## Task 4: comment_model_router.py (TDD)

**Files:**
- Create: `tests/test_comment_model_router.py`
- Create: `comment_model_router.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_comment_model_router.py`:

```python
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch
from comment_model_router import ModelRouter, ProviderConfig


def _make_router(chain=None):
    chain = chain or [
        ProviderConfig(provider="anthropic", model="claude-sonnet-4-6"),
        ProviderConfig(provider="openai", model="gpt-4o"),
        ProviderConfig(provider="gemini", model="gemini-2.0-flash"),
    ]
    return ModelRouter(
        fallback_chain=chain,
        anthropic_key="test-anthropic",
        openai_key="test-openai",
        gemini_key="test-gemini",
    )


def test_call_uses_first_provider_on_success():
    router = _make_router()
    with patch.object(router, "_call_anthropic", return_value="draft reply") as mock_a:
        text, label = router.call("base64img==", "system prompt")
    mock_a.assert_called_once_with("claude-sonnet-4-6", "base64img==", "system prompt")
    assert text == "draft reply"
    assert "anthropic" in label
    assert "claude-sonnet-4-6" in label


def test_call_falls_back_to_openai_when_anthropic_fails():
    router = _make_router()
    with patch.object(router, "_call_anthropic", side_effect=Exception("429")), \
         patch.object(router, "_call_openai", return_value="openai reply") as mock_o:
        text, label = router.call("base64img==", "system prompt")
    mock_o.assert_called_once()
    assert text == "openai reply"
    assert "openai" in label


def test_call_falls_back_to_gemini_when_anthropic_and_openai_fail():
    router = _make_router()
    with patch.object(router, "_call_anthropic", side_effect=Exception("quota")), \
         patch.object(router, "_call_openai", side_effect=Exception("quota")), \
         patch.object(router, "_call_gemini", return_value="gemini reply") as mock_g:
        text, label = router.call("base64img==", "system prompt")
    mock_g.assert_called_once()
    assert text == "gemini reply"
    assert "gemini" in label


def test_call_raises_when_all_providers_fail():
    router = _make_router()
    with patch.object(router, "_call_anthropic", side_effect=Exception("err1")), \
         patch.object(router, "_call_openai", side_effect=Exception("err2")), \
         patch.object(router, "_call_gemini", side_effect=Exception("err3")):
        with pytest.raises(RuntimeError, match="All providers failed"):
            router.call("base64img==", "system prompt")


def test_call_text_uses_first_provider():
    router = _make_router()
    with patch.object(router, "_call_anthropic_text", return_value="short reply") as mock_a:
        text, label = router.call_text("shorten this")
    mock_a.assert_called_once_with("claude-sonnet-4-6", "shorten this")
    assert text == "short reply"


def test_call_text_falls_back():
    router = _make_router()
    with patch.object(router, "_call_anthropic_text", side_effect=Exception("quota")), \
         patch.object(router, "_call_openai_text", return_value="short openai") as mock_o:
        text, label = router.call_text("shorten this")
    assert text == "short openai"
    assert "openai" in label


def test_single_provider_chain():
    router = _make_router(chain=[ProviderConfig(provider="gemini", model="gemini-2.0-flash")])
    with patch.object(router, "_call_gemini", return_value="gemini only") as mock_g:
        text, label = router.call("img==", "prompt")
    assert text == "gemini only"
    assert "gemini" in label
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_comment_model_router.py -v
```

Expected: `ModuleNotFoundError: No module named 'comment_model_router'`

- [ ] **Step 3: Implement comment_model_router.py**

Create `comment_model_router.py`:

```python
from __future__ import annotations
import base64
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    provider: str  # "anthropic" | "openai" | "gemini"
    model: str


@dataclass
class ModelRouter:
    fallback_chain: list[ProviderConfig]
    anthropic_key: str = ""
    openai_key: str = ""
    gemini_key: str = ""

    def call(self, image_b64: str, system_prompt: str) -> tuple[str, str]:
        """Vision call. Try each provider in fallback_chain. Returns (text, model_label)."""
        errors: list[str] = []
        for cfg in self.fallback_chain:
            try:
                text = self._call_provider(cfg, image_b64, system_prompt)
                return text, f"{cfg.provider}/{cfg.model}"
            except Exception as exc:
                logger.warning("Provider %s/%s failed: %s", cfg.provider, cfg.model, exc)
                errors.append(f"{cfg.provider}/{cfg.model}: {exc}")
        raise RuntimeError("All providers failed:\n" + "\n".join(errors))

    def call_text(self, prompt: str) -> tuple[str, str]:
        """Text-only call (no image). Used for reply shortening. Returns (text, model_label)."""
        errors: list[str] = []
        for cfg in self.fallback_chain:
            try:
                text = self._call_provider_text(cfg, prompt)
                return text, f"{cfg.provider}/{cfg.model}"
            except Exception as exc:
                logger.warning("Provider %s/%s text failed: %s", cfg.provider, cfg.model, exc)
                errors.append(f"{cfg.provider}/{cfg.model}: {exc}")
        raise RuntimeError("All providers failed:\n" + "\n".join(errors))

    # ── Vision dispatchers ──────────────────────────────────────────────────

    def _call_provider(self, cfg: ProviderConfig, image_b64: str, system_prompt: str) -> str:
        if cfg.provider == "anthropic":
            return self._call_anthropic(cfg.model, image_b64, system_prompt)
        if cfg.provider == "openai":
            return self._call_openai(cfg.model, image_b64, system_prompt)
        if cfg.provider == "gemini":
            return self._call_gemini(cfg.model, image_b64, system_prompt)
        raise ValueError(f"Unknown provider: {cfg.provider!r}")

    def _call_anthropic(self, model: str, image_b64: str, system_prompt: str) -> str:
        import anthropic  # imported lazily so tests can mock at module level
        client = anthropic.Anthropic(api_key=self.anthropic_key)
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [{
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_b64,
                    },
                }],
            }],
        )
        return response.content[0].text

    def _call_openai(self, model: str, image_b64: str, system_prompt: str) -> str:
        import openai
        client = openai.OpenAI(api_key=self.openai_key)
        response = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [{
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    }],
                },
            ],
        )
        return response.choices[0].message.content

    def _call_gemini(self, model: str, image_b64: str, system_prompt: str) -> str:
        import google.generativeai as genai
        import PIL.Image
        import io
        genai.configure(api_key=self.gemini_key)
        gmodel = genai.GenerativeModel(model, system_instruction=system_prompt)
        image_bytes = base64.b64decode(image_b64)
        img = PIL.Image.open(io.BytesIO(image_bytes))
        response = gmodel.generate_content(img)
        return response.text

    # ── Text-only dispatchers ───────────────────────────────────────────────

    def _call_provider_text(self, cfg: ProviderConfig, prompt: str) -> str:
        if cfg.provider == "anthropic":
            return self._call_anthropic_text(cfg.model, prompt)
        if cfg.provider == "openai":
            return self._call_openai_text(cfg.model, prompt)
        if cfg.provider == "gemini":
            return self._call_gemini_text(cfg.model, prompt)
        raise ValueError(f"Unknown provider: {cfg.provider!r}")

    def _call_anthropic_text(self, model: str, prompt: str) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=self.anthropic_key)
        response = client.messages.create(
            model=model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _call_openai_text(self, model: str, prompt: str) -> str:
        import openai
        client = openai.OpenAI(api_key=self.openai_key)
        response = client.chat.completions.create(
            model=model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    def _call_gemini_text(self, model: str, prompt: str) -> str:
        import google.generativeai as genai
        genai.configure(api_key=self.gemini_key)
        gmodel = genai.GenerativeModel(model)
        response = gmodel.generate_content(prompt)
        return response.text
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_comment_model_router.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add comment_model_router.py tests/test_comment_model_router.py
git commit -m "feat: add ModelRouter with Anthropic/OpenAI/Gemini fallback chain"
```

---

## Task 5: Pure helper functions (TDD)

**Files:**
- Create (partial): `comment_reply_bot.py` — pure functions only, no Telegram I/O yet
- Create: `tests/test_comment_reply_bot.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_comment_reply_bot.py`:

```python
from __future__ import annotations
import pytest


# ── parse_ai_response ───────────────────────────────────────────────────────

def test_parse_single_comment():
    from comment_reply_bot import parse_ai_response
    text = "COMMENT_1: great post!\nREPLY_1: Thank you so much! 🤍"
    result = parse_ai_response(text)
    assert result == [("great post!", "Thank you so much! 🤍")]


def test_parse_multiple_comments():
    from comment_reply_bot import parse_ai_response
    text = (
        "COMMENT_1: omg where?\n"
        "REPLY_1: Linked in bio!\n"
        "COMMENT_2: price?\n"
        "REPLY_2: Check bio for discount 💅\n"
    )
    result = parse_ai_response(text)
    assert len(result) == 2
    assert result[0] == ("omg where?", "Linked in bio!")
    assert result[1] == ("price?", "Check bio for discount 💅")


def test_parse_empty_response_returns_empty_list():
    from comment_reply_bot import parse_ai_response
    assert parse_ai_response("") == []
    assert parse_ai_response("No comments found.") == []


def test_parse_ignores_extra_whitespace():
    from comment_reply_bot import parse_ai_response
    text = "COMMENT_1:  hello there  \nREPLY_1:  Hey! 👋  "
    result = parse_ai_response(text)
    assert result == [("hello there", "Hey! 👋")]


# ── detect_platform ─────────────────────────────────────────────────────────

def test_detect_platform_from_caption():
    from comment_reply_bot import detect_platform
    assert detect_platform("tiktok", "instagram") == "tiktok"
    assert detect_platform("ig", "tiktok") == "instagram"
    assert detect_platform("fb", "instagram") == "facebook"
    assert detect_platform("youtube", "instagram") == "youtube"
    assert detect_platform("yt", "instagram") == "youtube"


def test_detect_platform_defaults_when_no_match():
    from comment_reply_bot import detect_platform
    assert detect_platform("some random caption", "instagram") == "instagram"
    assert detect_platform(None, "tiktok") == "tiktok"
    assert detect_platform("", "facebook") == "facebook"


def test_detect_platform_case_insensitive():
    from comment_reply_bot import detect_platform
    assert detect_platform("TikTok", "instagram") == "tiktok"
    assert detect_platform("IG", "tiktok") == "instagram"


# ── compute_image_hash ──────────────────────────────────────────────────────

def test_compute_image_hash_is_deterministic():
    from comment_reply_bot import compute_image_hash
    data = b"fake image bytes"
    assert compute_image_hash(data) == compute_image_hash(data)


def test_compute_image_hash_differs_for_different_data():
    from comment_reply_bot import compute_image_hash
    assert compute_image_hash(b"image1") != compute_image_hash(b"image2")


def test_compute_image_hash_is_hex_string():
    from comment_reply_bot import compute_image_hash
    h = compute_image_hash(b"data")
    assert isinstance(h, str)
    assert len(h) == 32  # MD5 hex digest length


# ── enforce_char_limit ──────────────────────────────────────────────────────

def test_enforce_char_limit_no_op_when_within_limit():
    from comment_reply_bot import enforce_char_limit
    reply = "Short reply"
    assert enforce_char_limit(reply, 150, router=None) == reply


def test_enforce_char_limit_truncates_when_router_fails():
    from comment_reply_bot import enforce_char_limit
    from unittest.mock import MagicMock
    router = MagicMock()
    router.call_text.side_effect = RuntimeError("all failed")
    long_reply = "x" * 200
    result = enforce_char_limit(long_reply, 150, router=router)
    assert len(result) <= 150
    assert result.endswith("...")


def test_enforce_char_limit_uses_router_to_shorten():
    from comment_reply_bot import enforce_char_limit
    from unittest.mock import MagicMock
    router = MagicMock()
    router.call_text.return_value = ("Short version", "anthropic/claude-sonnet-4-6")
    long_reply = "x" * 200
    result = enforce_char_limit(long_reply, 150, router=router)
    assert result == "Short version"
    router.call_text.assert_called_once()


# ── format_output ───────────────────────────────────────────────────────────

def test_format_output_single_comment():
    from comment_reply_bot import format_output
    pairs = [("great post!", "Thank you! 🤍")]
    result = format_output(pairs, "anthropic/claude-sonnet-4-6", "instagram")
    assert "1️⃣" in result
    assert "great post!" in result
    assert "Thank you! 🤍" in result
    assert "claude-sonnet-4-6" in result
    assert "instagram" in result


def test_format_output_multiple_comments():
    from comment_reply_bot import format_output
    pairs = [("q1", "a1"), ("q2", "a2"), ("q3", "a3")]
    result = format_output(pairs, "openai/gpt-4o", "tiktok")
    assert "1️⃣" in result
    assert "2️⃣" in result
    assert "3️⃣" in result
    assert "3 comments" in result


def test_format_output_single_uses_singular():
    from comment_reply_bot import format_output
    pairs = [("q", "a")]
    result = format_output(pairs, "model/x", "fb")
    assert "1 comment" in result


# ── build_system_prompt ─────────────────────────────────────────────────────

def test_build_system_prompt_contains_brand_fields():
    from comment_reply_bot import build_system_prompt
    class FakeBrand:
        tone = "sassy and smart"
        target_audience = "women 18-44"
        script_style = "casual Gen Z"
    result = build_system_prompt(FakeBrand(), max_chars=150)
    assert "sassy and smart" in result
    assert "women 18-44" in result
    assert "casual Gen Z" in result
    assert "150" in result
    assert "COMMENT_1:" in result
    assert "REPLY_1:" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_comment_reply_bot.py -v
```

Expected: `ModuleNotFoundError: No module named 'comment_reply_bot'`

- [ ] **Step 3: Create comment_reply_bot.py with pure helper functions**

Create `comment_reply_bot.py`:

```python
from __future__ import annotations
import base64
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

from comment_model_router import ModelRouter, ProviderConfig
from project_loader import load_project, resolve_project_slug

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent
_BASE_URL = "https://api.telegram.org/bot{token}/{method}"
_MODEL_STATE_FILE = Path("/tmp/comment_bot_model_state.json")
_LOG_DIR = _ROOT / "output" / "comment_reply_log"

_PLATFORM_ALIASES: dict[str, str] = {
    "ig": "instagram",
    "instagram": "instagram",
    "fb": "facebook",
    "facebook": "facebook",
    "tiktok": "tiktok",
    "tt": "tiktok",
    "youtube": "youtube",
    "yt": "youtube",
}

_PLATFORM_MAX_CHARS_DEFAULTS: dict[str, int] = {
    "tiktok": 150,
    "instagram": 2200,
    "facebook": 8000,
    "youtube": 10000,
}

_NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


# ── Pure helper functions ───────────────────────────────────────────────────

def parse_ai_response(text: str) -> list[tuple[str, str]]:
    """Parse COMMENT_N: / REPLY_N: structured AI output into (comment, reply) pairs."""
    pairs: list[tuple[str, str]] = []
    current_comment: str | None = None
    for line in text.strip().splitlines():
        line = line.strip()
        if line.startswith("COMMENT_") and ":" in line:
            current_comment = line[line.index(":") + 1:].strip()
        elif line.startswith("REPLY_") and ":" in line and current_comment is not None:
            reply = line[line.index(":") + 1:].strip()
            pairs.append((current_comment, reply))
            current_comment = None
    return pairs


def detect_platform(caption: str | None, default: str) -> str:
    """Determine platform from caption keyword; falls back to default."""
    if not caption:
        return default
    for word in caption.lower().split():
        if word in _PLATFORM_ALIASES:
            return _PLATFORM_ALIASES[word]
    return default


def compute_image_hash(data: bytes) -> str:
    """Return MD5 hex digest of image bytes for duplicate detection."""
    return hashlib.md5(data).hexdigest()


def enforce_char_limit(reply: str, max_chars: int, router: ModelRouter | None) -> str:
    """Shorten reply to max_chars. Uses router.call_text; falls back to truncation."""
    if len(reply) <= max_chars:
        return reply
    if router is not None:
        prompt = (
            f"Shorten this reply to under {max_chars} characters. "
            f"Keep the same tone and language. Return ONLY the shortened reply.\n\n{reply}"
        )
        try:
            shortened, _ = router.call_text(prompt)
            return shortened[:max_chars] if len(shortened) > max_chars else shortened
        except RuntimeError:
            pass
    return reply[: max_chars - 3] + "..."


def build_system_prompt(brand: object, max_chars: int) -> str:
    """Build the vision system prompt for comment extraction and reply drafting."""
    return (
        f"You are a social media community manager.\n"
        f"Brand tone: {brand.tone}\n"
        f"Target audience: {brand.target_audience}\n"
        f"Writing style: {brand.script_style}\n\n"
        f"Look at this screenshot carefully.\n\n"
        f"1. Find ALL comments visible in the image, reading top to bottom.\n"
        f"2. For each comment, write ONE reply that matches the brand tone.\n"
        f"3. Each reply must be under {max_chars} characters.\n"
        f"4. Match the language of the comment (Thai replies Thai, English replies English).\n"
        f"5. Do not use hashtags unless the comment contains them.\n"
        f"6. Never mention AI or automation.\n\n"
        f"Return your response in this EXACT format:\n"
        f"COMMENT_1: [exact comment text you read]\n"
        f"REPLY_1: [your reply]\n"
        f"COMMENT_2: [exact comment text you read]\n"
        f"REPLY_2: [your reply]\n\n"
        f"Return ONLY this format. No other text."
    )


def format_output(pairs: list[tuple[str, str]], model_label: str, platform: str) -> str:
    """Format (comment, reply) pairs into a Telegram message."""
    count = len(pairs)
    noun = "comment" if count == 1 else "comments"
    lines = [f"📸 พบ {count} {noun} ในภาพ\n"]
    for i, (comment, reply) in enumerate(pairs):
        emoji = _NUMBER_EMOJIS[i] if i < len(_NUMBER_EMOJIS) else f"{i + 1}."
        lines.append(f"{emoji} {comment}")
        lines.append(f'💬 "{reply}"\n')
    lines.append("─────────────────")
    model_short = model_label.split("/")[-1] if "/" in model_label else model_label
    lines.append(f"🤖 {model_short}  |  📱 {platform}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_comment_reply_bot.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add comment_reply_bot.py tests/test_comment_reply_bot.py
git commit -m "feat: add comment_reply_bot pure helpers (parse, detect_platform, hash, format)"
```

---

## Task 6: Reply history log (TDD)

**Files:**
- Modify: `comment_reply_bot.py` — append log functions
- Modify: `tests/test_comment_reply_bot.py` — append log tests

- [ ] **Step 1: Append failing log tests to tests/test_comment_reply_bot.py**

Add at the bottom of `tests/test_comment_reply_bot.py`:

```python
# ── Reply history log ───────────────────────────────────────────────────────

import tempfile
from pathlib import Path


def test_find_in_log_returns_none_when_log_missing():
    from comment_reply_bot import find_in_log
    with tempfile.TemporaryDirectory() as d:
        result = find_in_log(Path(d) / "nonexistent.jsonl", "abc123")
    assert result is None


def test_append_and_find_in_log():
    from comment_reply_bot import append_to_log, find_in_log
    with tempfile.TemporaryDirectory() as d:
        log_path = Path(d) / "slay_hack.jsonl"
        entry = {
            "timestamp": "2026-05-18T10:00:00",
            "chat_id": "-100123",
            "image_hash": "abc123",
            "platform": "instagram",
            "model_used": "anthropic/claude-sonnet-4-6",
            "comments": ["nice post!"],
            "replies": ["Thank you! 🤍"],
        }
        append_to_log(log_path, entry)
        found = find_in_log(log_path, "abc123")
    assert found is not None
    assert found["image_hash"] == "abc123"
    assert found["platform"] == "instagram"


def test_find_in_log_returns_none_for_unknown_hash():
    from comment_reply_bot import append_to_log, find_in_log
    with tempfile.TemporaryDirectory() as d:
        log_path = Path(d) / "test.jsonl"
        append_to_log(log_path, {"image_hash": "known", "timestamp": "t"})
        result = find_in_log(log_path, "unknown_hash")
    assert result is None


def test_append_to_log_creates_parent_directory():
    from comment_reply_bot import append_to_log
    with tempfile.TemporaryDirectory() as d:
        log_path = Path(d) / "subdir" / "project.jsonl"
        append_to_log(log_path, {"image_hash": "x", "timestamp": "t"})
        assert log_path.exists()
```

- [ ] **Step 2: Run to verify new tests fail**

```bash
pytest tests/test_comment_reply_bot.py::test_find_in_log_returns_none_when_log_missing -v
```

Expected: `ImportError` or `AttributeError` — `find_in_log` not defined yet.

- [ ] **Step 3: Append log functions to comment_reply_bot.py**

Add after the `format_output` function in `comment_reply_bot.py`:

```python
# ── Reply history log ───────────────────────────────────────────────────────

def find_in_log(log_path: Path, image_hash: str) -> dict | None:
    """Return the log entry matching image_hash, or None if not found."""
    if not log_path.exists():
        return None
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("image_hash") == image_hash:
                return entry
    except (json.JSONDecodeError, OSError):
        pass
    return None


def append_to_log(log_path: Path, entry: dict) -> None:
    """Append a reply entry to the JSONL log. Creates parent dirs if needed."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/test_comment_reply_bot.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add comment_reply_bot.py tests/test_comment_reply_bot.py
git commit -m "feat: add reply history log (JSONL per project, duplicate detection)"
```

---

## Task 7: Telegram helpers + photo handler (TDD)

**Files:**
- Modify: `comment_reply_bot.py` — append Telegram helpers + photo handler
- Modify: `tests/test_comment_reply_bot.py` — append handler tests

- [ ] **Step 1: Append Telegram helper tests**

Add at the bottom of `tests/test_comment_reply_bot.py`:

```python
# ── Telegram helpers ────────────────────────────────────────────────────────

from unittest.mock import patch, MagicMock


def test_download_photo_calls_get_file_then_fetches():
    from comment_reply_bot import _download_photo
    fake_api_response = {"result": {"file_path": "photos/file123.jpg"}}
    fake_image = b"\xff\xd8fake jpeg"
    with patch("comment_reply_bot._api", return_value=fake_api_response) as mock_api, \
         patch("comment_reply_bot.requests.get") as mock_get:
        mock_get.return_value.content = fake_image
        mock_get.return_value.raise_for_status = MagicMock()
        result = _download_photo("bot_token", "file_id_123")
    mock_api.assert_called_once_with("bot_token", "getFile", file_id="file_id_123")
    assert result == fake_image


def test_load_comment_max_chars_reads_from_yaml(tmp_path):
    from comment_reply_bot import _load_comment_max_chars
    project_dir = tmp_path / "projects" / "test_project"
    project_dir.mkdir(parents=True)
    (project_dir / "platform_specs.yaml").write_text(
        "tiktok:\n  comment_max_chars: 150\ninstagram:\n  comment_max_chars: 2200\n"
    )
    result = _load_comment_max_chars("test_project", "tiktok", root=tmp_path)
    assert result == 150
    result2 = _load_comment_max_chars("test_project", "instagram", root=tmp_path)
    assert result2 == 2200


def test_load_comment_max_chars_uses_default_when_missing(tmp_path):
    from comment_reply_bot import _load_comment_max_chars
    result = _load_comment_max_chars("nonexistent", "tiktok", root=tmp_path)
    assert result == 150  # default for tiktok


def test_load_model_state_returns_empty_when_missing(tmp_path):
    from comment_reply_bot import _load_model_state
    result = _load_model_state(tmp_path / "state.json")
    assert result == {}


def test_load_and_save_model_state(tmp_path):
    from comment_reply_bot import _load_model_state, _save_model_state
    state_path = tmp_path / "state.json"
    state = {"-100123": {"provider": "gemini", "model": "gemini-2.0-flash"}}
    _save_model_state(state_path, state)
    loaded = _load_model_state(state_path)
    assert loaded["-100123"]["provider"] == "gemini"
```

- [ ] **Step 2: Run to verify new tests fail**

```bash
pytest tests/test_comment_reply_bot.py::test_download_photo_calls_get_file_then_fetches -v
```

Expected: `AttributeError` — `_download_photo` not defined yet.

- [ ] **Step 3: Append Telegram helpers + photo handler to comment_reply_bot.py**

Add after `append_to_log` in `comment_reply_bot.py`:

```python
# ── Telegram API helpers ────────────────────────────────────────────────────

def _api(token: str, method: str, **kwargs) -> dict:
    url = _BASE_URL.format(token=token, method=method)
    http_timeout = kwargs.get("timeout", 5) + 5
    try:
        resp = requests.post(url, json=kwargs, timeout=http_timeout)
        resp.raise_for_status()
    except Exception as exc:
        safe_url = _BASE_URL.format(token="<redacted>", method=method)
        raise RuntimeError(
            f"Telegram request failed [{method}] {safe_url}: {type(exc).__name__}"
        ) from exc
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error ({method}): {data.get('description', 'unknown')}")
    return data


def _get_updates(token: str, offset: int, timeout: int = 5) -> list[dict]:
    try:
        data = _api(token, "getUpdates", offset=offset, timeout=timeout,
                    allowed_updates=["message"])
        return data.get("result", [])
    except Exception as exc:
        logger.warning("getUpdates failed: %s", exc)
        return []


def _send_message(token: str, chat_id: str, text: str) -> None:
    try:
        _api(token, "sendMessage", chat_id=chat_id, text=text, parse_mode="HTML")
    except Exception as exc:
        logger.warning("sendMessage failed: %s", exc)


def _download_photo(token: str, file_id: str) -> bytes:
    data = _api(token, "getFile", file_id=file_id)
    file_path = data["result"]["file_path"]
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content


# ── Config helpers ──────────────────────────────────────────────────────────

def _load_comment_max_chars(project_slug: str, platform: str, root: Path) -> int:
    resolved = resolve_project_slug(project_slug, root=root)
    specs_path = root / "projects" / resolved / "platform_specs.yaml"
    if specs_path.exists():
        try:
            data = yaml.safe_load(specs_path.read_text()) or {}
            platform_data = data.get(platform, {})
            if isinstance(platform_data, dict) and "comment_max_chars" in platform_data:
                return int(platform_data["comment_max_chars"])
        except (yaml.YAMLError, ValueError, KeyError):
            pass
    return _PLATFORM_MAX_CHARS_DEFAULTS.get(platform, 2200)


def _load_model_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_model_state(path: Path, state: dict) -> None:
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(state))
        tmp.replace(path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


# ── Photo handler ───────────────────────────────────────────────────────────

def _handle_photo_message(
    msg: dict,
    token: str,
    chat_map_data: dict,
    root: Path,
    router: ModelRouter,
    model_state_path: Path,
    log_dir: Path,
) -> None:
    chat_id = str(msg["chat"]["id"])
    chat_config = chat_map_data.get("chats", {}).get(chat_id)
    if chat_config is None:
        return  # not a registered group — stay silent

    project_slug = chat_config["project"]
    default_platform = chat_config.get("default_platform", "instagram")
    caption = msg.get("caption") or ""
    platform = detect_platform(caption, default_platform)

    # Download largest photo variant
    photos = msg.get("photo", [])
    if not photos:
        return
    image_bytes = _download_photo(token, photos[-1]["file_id"])
    image_b64 = base64.b64encode(image_bytes).decode()

    # Duplicate check
    image_hash = compute_image_hash(image_bytes)
    log_path = log_dir / f"{project_slug}.jsonl"
    existing = find_in_log(log_path, image_hash)
    if existing:
        ts = existing.get("timestamp", "unknown")
        cached_pairs = list(zip(existing.get("comments", []), existing.get("replies", [])))
        cached_text = format_output(
            cached_pairs, existing.get("model_used", "cached"), existing.get("platform", platform)
        )
        _send_message(token, chat_id, f"♻️ รูปนี้ตอบไปแล้วเมื่อ {ts}\n\n{cached_text}")
        return

    # Check per-chat model override
    model_state = _load_model_state(model_state_path)
    chat_override = model_state.get(chat_id)
    if chat_override:
        active_router = ModelRouter(
            fallback_chain=[ProviderConfig(**chat_override)],
            anthropic_key=router.anthropic_key,
            openai_key=router.openai_key,
            gemini_key=router.gemini_key,
        )
    else:
        active_router = router

    # Load brand + platform config
    try:
        brand = load_project(project_slug, root=root).brand
    except Exception as exc:
        _send_message(token, chat_id, f"❌ ไม่สามารถโหลด project {project_slug!r}: {exc}")
        return
    max_chars = _load_comment_max_chars(project_slug, platform, root)
    system_prompt = build_system_prompt(brand, max_chars)

    _send_message(token, chat_id, "⏳ กำลังอ่าน comment...")

    try:
        raw_text, model_label = active_router.call(image_b64, system_prompt)
    except RuntimeError as exc:
        _send_message(token, chat_id, f"❌ {exc}")
        return

    pairs = parse_ai_response(raw_text)
    if not pairs:
        _send_message(token, chat_id, "ไม่เจอ comment ในรูป กรุณาส่งรูปใหม่")
        return

    enforced_pairs = [
        (comment, enforce_char_limit(reply, max_chars, active_router))
        for comment, reply in pairs
    ]

    output = format_output(enforced_pairs, model_label, platform)
    _send_message(token, chat_id, output)

    append_to_log(log_path, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "chat_id": chat_id,
        "image_hash": image_hash,
        "platform": platform,
        "model_used": model_label,
        "comments": [c for c, _ in enforced_pairs],
        "replies": [r for _, r in enforced_pairs],
    })
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/test_comment_reply_bot.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add comment_reply_bot.py tests/test_comment_reply_bot.py
git commit -m "feat: add Telegram helpers, photo handler, and reply history integration"
```

---

## Task 8: Command handlers + polling loop + __main__

**Files:**
- Modify: `comment_reply_bot.py` — append commands + polling loop + entry point

- [ ] **Step 1: Append command handler tests**

Add at the bottom of `tests/test_comment_reply_bot.py`:

```python
# ── Command handlers ────────────────────────────────────────────────────────

def _make_msg(text: str, chat_id: str = "-100123") -> dict:
    return {"chat": {"id": int(chat_id)}, "text": text}


def test_handle_model_command_valid_sets_override(tmp_path):
    from comment_reply_bot import _handle_model_command, _load_model_state
    state_path = tmp_path / "state.json"
    chat_map = {"chats": {"-100123": {"project": "slay_hack", "default_platform": "instagram"}}}
    with patch("comment_reply_bot._send_message") as mock_send:
        _handle_model_command(
            _make_msg("/model gemini gemini-2.0-flash"),
            "token",
            ["/model", "gemini", "gemini-2.0-flash"],
            state_path,
            chat_map,
        )
    state = _load_model_state(state_path)
    assert state["-100123"]["provider"] == "gemini"
    assert state["-100123"]["model"] == "gemini-2.0-flash"
    mock_send.assert_called_once()
    assert "gemini" in mock_send.call_args[0][2]


def test_handle_model_command_auto_clears_override(tmp_path):
    from comment_reply_bot import _handle_model_command, _load_model_state, _save_model_state
    state_path = tmp_path / "state.json"
    _save_model_state(state_path, {"-100123": {"provider": "gemini", "model": "gemini-2.0-flash"}})
    chat_map = {"chats": {"-100123": {"project": "slay_hack", "default_platform": "instagram"}}}
    with patch("comment_reply_bot._send_message"):
        _handle_model_command(
            _make_msg("/model auto"),
            "token",
            ["/model", "auto"],
            state_path,
            chat_map,
        )
    state = _load_model_state(state_path)
    assert "-100123" not in state


def test_handle_model_command_invalid_shows_help(tmp_path):
    from comment_reply_bot import _handle_model_command
    state_path = tmp_path / "state.json"
    chat_map = {"chats": {"-100123": {"project": "slay_hack", "default_platform": "instagram"}}}
    with patch("comment_reply_bot._send_message") as mock_send:
        _handle_model_command(
            _make_msg("/model badprovider badmodel"),
            "token",
            ["/model", "badprovider", "badmodel"],
            state_path,
            chat_map,
        )
    assert "anthropic" in mock_send.call_args[0][2].lower() or "valid" in mock_send.call_args[0][2].lower()
```

- [ ] **Step 2: Run to verify new tests fail**

```bash
pytest tests/test_comment_reply_bot.py::test_handle_model_command_valid_sets_override -v
```

Expected: `AttributeError` — `_handle_model_command` not defined yet.

- [ ] **Step 3: Append command handlers + polling loop to comment_reply_bot.py**

Add at the end of `comment_reply_bot.py`:

```python
# ── Command handlers ────────────────────────────────────────────────────────

_VALID_PROVIDERS = {"anthropic", "openai", "gemini"}

_HELP_TEXT = (
    "🤖 <b>Comment Reply Bot</b>\n\n"
    "ส่งรูป screenshot → ได้ draft reply ทันที\n\n"
    "<b>Commands:</b>\n"
    "/model anthropic claude-sonnet-4-6\n"
    "/model anthropic claude-opus-4-7\n"
    "/model openai gpt-4o\n"
    "/model gemini gemini-2.0-flash\n"
    "/model auto   ← fallback อัตโนมัติ\n\n"
    "<b>แนบ platform ใน caption ได้เลย:</b>\n"
    "  tiktok | ig | fb | youtube\n"
    "  (ถ้าไม่แนบ ใช้ default ของ group นี้)"
)


def _handle_model_command(
    msg: dict,
    token: str,
    args: list[str],
    model_state_path: Path,
    chat_map_data: dict,
) -> None:
    chat_id = str(msg["chat"]["id"])

    # Only registered chats can use this command
    if chat_id not in chat_map_data.get("chats", {}):
        return

    if len(args) == 2 and args[1] == "auto":
        state = _load_model_state(model_state_path)
        state.pop(chat_id, None)
        _save_model_state(model_state_path, state)
        _send_message(token, chat_id, "✅ Reset to automatic fallback chain")
        return

    if len(args) == 3 and args[1] in _VALID_PROVIDERS:
        provider, model = args[1], args[2]
        state = _load_model_state(model_state_path)
        state[chat_id] = {"provider": provider, "model": model}
        _save_model_state(model_state_path, state)
        _send_message(token, chat_id, f"✅ Switched to {provider} / {model} for this chat")
        return

    _send_message(
        token, chat_id,
        "❌ Valid options:\n"
        "/model anthropic claude-sonnet-4-6\n"
        "/model openai gpt-4o\n"
        "/model gemini gemini-2.0-flash\n"
        "/model auto",
    )


def _handle_help_command(msg: dict, token: str, chat_map_data: dict) -> None:
    chat_id = str(msg["chat"]["id"])
    if chat_id not in chat_map_data.get("chats", {}):
        return
    _send_message(token, chat_id, _HELP_TEXT)


# ── Polling loop ────────────────────────────────────────────────────────────

def _load_chat_map(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text()) or {}
        # Normalize chat IDs to strings
        raw_chats = data.get("chats", {})
        data["chats"] = {str(k): v for k, v in raw_chats.items()}
        return data
    except (yaml.YAMLError, OSError) as exc:
        raise RuntimeError(f"Failed to load chat map from {path}: {exc}") from exc


def _build_router_from_map(chat_map_data: dict) -> ModelRouter:
    chain = [
        ProviderConfig(provider=entry["provider"], model=entry["model"])
        for entry in chat_map_data.get("fallback_chain", [])
    ]
    if not chain:
        chain = [ProviderConfig(provider="anthropic", model="claude-sonnet-4-6")]
    return ModelRouter(
        fallback_chain=chain,
        anthropic_key=os.getenv("ANTHROPIC_API_KEY", ""),
        openai_key=os.getenv("OPENAI_API_KEY", ""),
        gemini_key=os.getenv("GEMINI_API_KEY", ""),
    )


def run_bot(token: str, chat_map_path: Path, root: Path) -> None:
    """Main entry point. Polls Telegram indefinitely. Blocks."""
    chat_map_data = _load_chat_map(chat_map_path)
    router = _build_router_from_map(chat_map_data)
    log_dir = root / "output" / "comment_reply_log"
    offset = 0
    logger.info("Comment reply bot started (%d registered chats).", len(chat_map_data.get("chats", {})))

    while True:
        updates = _get_updates(token, offset=offset, timeout=5)
        for update in updates:
            offset = update["update_id"] + 1
            try:
                msg = update.get("message", {})
                if not msg:
                    continue
                text = msg.get("text", "").strip()
                # Reload chat map on each update so new chats can be added without restart
                chat_map_data = _load_chat_map(chat_map_path)
                router = _build_router_from_map(chat_map_data)

                if text.startswith("/help"):
                    _handle_help_command(msg, token, chat_map_data)
                elif text.startswith("/model"):
                    args = text.split()
                    _handle_model_command(msg, token, args, _MODEL_STATE_FILE, chat_map_data)
                elif msg.get("photo"):
                    _handle_photo_message(
                        msg, token, chat_map_data, root, router, _MODEL_STATE_FILE, log_dir
                    )
            except Exception as exc:
                logger.error("Error handling update %s: %s", update.get("update_id"), exc)


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    _token = os.environ.get("COMMENT_BOT_TOKEN", "")
    if not _token:
        logger.error("COMMENT_BOT_TOKEN must be set in .env")
        sys.exit(1)
    _map_path = _ROOT / "comment_chat_map.yaml"
    if not _map_path.exists():
        logger.error("comment_chat_map.yaml not found at %s", _map_path)
        sys.exit(1)
    run_bot(_token, _map_path, root=_ROOT)
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/test_comment_reply_bot.py tests/test_comment_model_router.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
pytest tests/ -v --tb=short
```

Expected: All tests PASS.

- [ ] **Step 6: Final commit**

```bash
git add comment_reply_bot.py tests/test_comment_reply_bot.py
git commit -m "feat: add command handlers (/model, /help), polling loop, and __main__ entry point"
```

---

## Setup Checklist (after implementation)

Before running the bot:

- [ ] Create bot via @BotFather on Telegram → `/newbot` → copy token → set `COMMENT_BOT_TOKEN=<token>` in `.env`
- [ ] Get Gemini API key at [aistudio.google.com](https://aistudio.google.com) → set `GEMINI_API_KEY=<key>` in `.env`
- [ ] Add the new bot to each Telegram group
- [ ] Find each group's chat_id (add @userinfobot to the group → it reports the ID)
- [ ] Replace placeholder IDs in `comment_chat_map.yaml` with real group IDs
- [ ] Run: `python comment_reply_bot.py`
