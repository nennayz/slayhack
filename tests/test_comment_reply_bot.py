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
