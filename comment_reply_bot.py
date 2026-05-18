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


def enforce_char_limit(reply: str, max_chars: int, router) -> str:
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
