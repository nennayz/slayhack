from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from comment_model_router import ModelRouter, ProviderConfig


def _make_router(chain: list[ProviderConfig] | None = None) -> ModelRouter:
    return ModelRouter(
        fallback_chain=chain or [ProviderConfig(provider="anthropic", model="claude-sonnet-4-6")],
        anthropic_key="test-anthropic",
        openai_key="test-openai",
        gemini_key="test-gemini",
    )


def test_parse_single_comment():
    from comment_reply_bot import parse_ai_response

    text = "COMMENT_1: great post!\nREPLY_1: Thank you so much! 🤍"
    assert parse_ai_response(text) == [("great post!", "Thank you so much! 🤍")]


def test_parse_multiple_comments():
    from comment_reply_bot import parse_ai_response

    text = "COMMENT_1: omg where?\nREPLY_1: Linked in bio!\nCOMMENT_2: price?\nREPLY_2: Check bio\n"
    assert parse_ai_response(text) == [("omg where?", "Linked in bio!"), ("price?", "Check bio")]


def test_parse_empty_response_returns_empty_list():
    from comment_reply_bot import parse_ai_response

    assert parse_ai_response("") == []
    assert parse_ai_response("No comments found.") == []


def test_parse_ignores_extra_whitespace():
    from comment_reply_bot import parse_ai_response

    text = "COMMENT_1:  hello there  \nREPLY_1:  Hey! 👋  "
    assert parse_ai_response(text) == [("hello there", "Hey! 👋")]


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


def test_compute_image_hash_is_deterministic():
    from comment_reply_bot import compute_image_hash

    assert compute_image_hash(b"fake image bytes") == compute_image_hash(b"fake image bytes")


def test_compute_image_hash_differs_for_different_data():
    from comment_reply_bot import compute_image_hash

    assert compute_image_hash(b"image1") != compute_image_hash(b"image2")


def test_compute_image_hash_is_hex_string():
    from comment_reply_bot import compute_image_hash

    digest = compute_image_hash(b"data")
    assert isinstance(digest, str)
    assert len(digest) == 32


def test_enforce_char_limit_no_op_when_within_limit():
    from comment_reply_bot import enforce_char_limit

    assert enforce_char_limit("Short reply", 150, router=None) == "Short reply"


def test_enforce_char_limit_truncates_when_router_fails():
    from comment_reply_bot import enforce_char_limit

    router = MagicMock()
    router.call_text.side_effect = RuntimeError("all failed")
    result = enforce_char_limit("x" * 200, 150, router=router)
    assert len(result) <= 150
    assert result.endswith("...")


def test_enforce_char_limit_uses_router_to_shorten():
    from comment_reply_bot import enforce_char_limit

    router = MagicMock()
    router.call_text.return_value = ("Short version", "anthropic/claude-sonnet-4-6")
    assert enforce_char_limit("x" * 200, 150, router=router) == "Short version"
    router.call_text.assert_called_once()


def test_format_output_single_comment():
    from comment_reply_bot import format_output

    result = format_output([("great post!", "Thank you! 🤍")], "anthropic/claude-sonnet-4-6", "instagram")
    assert "1️⃣" in result
    assert "great post!" in result
    assert "Thank you! 🤍" in result
    assert "claude-sonnet-4-6" in result
    assert "instagram" in result


def test_format_output_multiple_comments():
    from comment_reply_bot import format_output

    result = format_output([("q1", "a1"), ("q2", "a2"), ("q3", "a3")], "openai/gpt-4o", "tiktok")
    assert "1️⃣" in result
    assert "2️⃣" in result
    assert "3️⃣" in result
    assert "3 comments" in result


def test_format_output_single_uses_singular():
    from comment_reply_bot import format_output

    assert "1 comment" in format_output([("q", "a")], "model/x", "fb")


def test_build_system_prompt_contains_brand_fields():
    from comment_reply_bot import build_system_prompt

    class FakeBrand:
        tone = "sassy and smart"
        target_audience = "women 18-44"
        script_style = "casual Gen Z"
        comment_reply_style = ""

    result = build_system_prompt(FakeBrand(), max_chars=150)
    assert "sassy and smart" in result
    assert "women 18-44" in result
    assert "casual Gen Z" in result
    assert "150" in result
    assert "COMMENT_1:" in result
    assert "REPLY_1:" in result


def test_build_system_prompt_includes_comment_reply_style():
    from comment_reply_bot import build_system_prompt

    class FakeBrand:
        tone = "sassy and smart"
        target_audience = "female Gen Z USA"
        script_style = "English only"
        comment_reply_style = (
            "Slay Hack Commenting Guideline:\n"
            "- No Gatekeeping.\n"
            "- Avoid: Thank you so much.\n"
            "- Good reply example: Same, and we came back prettier. Periodt 💅"
        )

    result = build_system_prompt(FakeBrand(), max_chars=150)
    assert "Comment reply style guide:" in result
    assert "No Gatekeeping" in result
    assert "Avoid: Thank you so much" in result
    assert "Same, and we came back prettier" in result
    assert "unless the style guide gives a stricter language rule" in result


def test_find_in_log_returns_none_when_log_missing(tmp_path):
    from comment_reply_bot import find_in_log

    assert find_in_log(tmp_path / "nonexistent.jsonl", "abc123") is None


def test_append_and_find_in_log(tmp_path):
    from comment_reply_bot import append_to_log, find_in_log

    log_path = tmp_path / "slay_hack.jsonl"
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


def test_find_in_log_returns_none_for_unknown_hash(tmp_path):
    from comment_reply_bot import append_to_log, find_in_log

    log_path = tmp_path / "test.jsonl"
    append_to_log(log_path, {"image_hash": "known", "timestamp": "t"})
    assert find_in_log(log_path, "unknown_hash") is None


def test_append_to_log_creates_parent_directory(tmp_path):
    from comment_reply_bot import append_to_log

    log_path = tmp_path / "subdir" / "project.jsonl"
    append_to_log(log_path, {"image_hash": "x", "timestamp": "t"})
    assert log_path.exists()


def test_download_photo_calls_get_file_then_fetches():
    from comment_reply_bot import _download_photo

    with (
        patch("comment_reply_bot._api", return_value={"result": {"file_path": "photos/file123.jpg"}}) as mock_api,
        patch("comment_reply_bot.requests.get") as mock_get,
    ):
        mock_get.return_value.content = b"\xff\xd8fake jpeg"
        mock_get.return_value.raise_for_status = MagicMock()
        result = _download_photo("bot_token", "file_id_123")
    mock_api.assert_called_once_with("bot_token", "getFile", file_id="file_id_123")
    assert result == b"\xff\xd8fake jpeg"


def test_load_comment_max_chars_reads_from_yaml(tmp_path):
    from comment_reply_bot import _load_comment_max_chars

    project_dir = tmp_path / "projects" / "test_project"
    project_dir.mkdir(parents=True)
    (project_dir / "platform_specs.yaml").write_text(
        "tiktok:\n  comment_max_chars: 150\ninstagram:\n  comment_max_chars: 2200\n",
        encoding="utf-8",
    )
    assert _load_comment_max_chars("test_project", "tiktok", root=tmp_path) == 150
    assert _load_comment_max_chars("test_project", "instagram", root=tmp_path) == 2200


def test_load_comment_max_chars_uses_default_when_missing(tmp_path):
    from comment_reply_bot import _load_comment_max_chars

    assert _load_comment_max_chars("nonexistent", "tiktok", root=tmp_path) == 150


def test_load_model_state_returns_empty_when_missing(tmp_path):
    from comment_reply_bot import _load_model_state

    assert _load_model_state(tmp_path / "state.json") == {}


def test_load_and_save_model_state(tmp_path):
    from comment_reply_bot import _load_model_state, _save_model_state

    state_path = tmp_path / "state.json"
    _save_model_state(state_path, {"-100123": {"provider": "gemini", "model": "gemini-2.0-flash"}})
    assert _load_model_state(state_path)["-100123"]["provider"] == "gemini"


def test_handle_photo_message_ignores_unknown_chat(tmp_path):
    from comment_reply_bot import _handle_photo_message

    with patch("comment_reply_bot._send_message") as mock_send:
        _handle_photo_message(
            {"chat": {"id": -1}, "photo": [{"file_id": "x"}]},
            "token",
            {"chats": {}},
            tmp_path,
            _make_router(),
            tmp_path / "state.json",
            tmp_path / "logs",
        )
    mock_send.assert_not_called()


def test_handle_photo_message_sends_cached_duplicate(tmp_path):
    from comment_reply_bot import _handle_photo_message, append_to_log, compute_image_hash

    image = b"same image"
    image_hash = compute_image_hash(image)
    log_dir = tmp_path / "logs"
    append_to_log(
        log_dir / "slay_hack.jsonl",
        {
            "timestamp": "2026-05-18T10:00:00Z",
            "image_hash": image_hash,
            "platform": "instagram",
            "model_used": "cached/model",
            "comments": ["hi"],
            "replies": ["hello"],
        },
    )
    msg = {"chat": {"id": -100123}, "photo": [{"file_id": "small"}, {"file_id": "large"}]}
    chat_map = {"chats": {"-100123": {"project": "slay_hack", "default_platform": "instagram"}}}
    with (
        patch("comment_reply_bot._download_photo", return_value=image),
        patch("comment_reply_bot._send_message") as mock_send,
    ):
        _handle_photo_message(msg, "token", chat_map, tmp_path, _make_router(), tmp_path / "state.json", log_dir)
    assert "ตอบไปแล้ว" in mock_send.call_args[0][2]


def test_handle_photo_message_generates_and_logs_reply(tmp_path):
    from comment_reply_bot import _handle_photo_message, find_in_log

    project_dir = tmp_path / "projects" / "slay_hack"
    project_dir.mkdir(parents=True)
    (project_dir / "pm_profile.yaml").write_text(
        "name: Slay\npage_name: SlayHack\npersona: PM\n",
        encoding="utf-8",
    )
    (project_dir / "brand.yaml").write_text(
        "mission: test\n"
        "visual:\n  colors: ['#fff']\n  style: clean\n"
        "platforms: [instagram]\n"
        "tone: warm\n"
        "target_audience: women\n"
        "script_style: concise\n",
        encoding="utf-8",
    )
    (project_dir / "platform_specs.yaml").write_text("instagram:\n  comment_max_chars: 2200\n", encoding="utf-8")

    router = _make_router()
    msg = {"chat": {"id": -100123}, "caption": "ig", "photo": [{"file_id": "large"}]}
    chat_map = {"chats": {"-100123": {"project": "slay_hack", "default_platform": "tiktok"}}}
    with (
        patch("comment_reply_bot._download_photo", return_value=b"image"),
        patch.object(router, "call", return_value=("COMMENT_1: hi\nREPLY_1: hello", "anthropic/test")),
        patch("comment_reply_bot._send_message") as mock_send,
    ):
        _handle_photo_message(msg, "token", chat_map, tmp_path, router, tmp_path / "state.json", tmp_path / "logs")
    assert mock_send.call_args_list[-1][0][2].count("hello") == 1
    assert find_in_log(tmp_path / "logs" / "slay_hack.jsonl", "78805a221a988e79ef3f42d7c5bfd418") is not None


def _make_msg(text: str, chat_id: str = "-100123") -> dict:
    return {"chat": {"id": int(chat_id)}, "text": text}


def test_handle_model_command_valid_sets_override(tmp_path):
    from comment_reply_bot import _handle_model_command, _load_model_state

    state_path = tmp_path / "state.json"
    chat_map = {"chats": {"-100123": {"project": "slay_hack", "default_platform": "instagram"}}}
    with patch("comment_reply_bot._send_message") as mock_send:
        _handle_model_command(_make_msg("/model gemini gemini-2.0-flash"), "token", ["/model", "gemini", "gemini-2.0-flash"], state_path, chat_map)
    state = _load_model_state(state_path)
    assert state["-100123"]["provider"] == "gemini"
    assert state["-100123"]["model"] == "gemini-2.0-flash"
    assert "gemini" in mock_send.call_args[0][2]


def test_handle_model_command_auto_clears_override(tmp_path):
    from comment_reply_bot import _handle_model_command, _load_model_state, _save_model_state

    state_path = tmp_path / "state.json"
    _save_model_state(state_path, {"-100123": {"provider": "gemini", "model": "gemini-2.0-flash"}})
    chat_map = {"chats": {"-100123": {"project": "slay_hack", "default_platform": "instagram"}}}
    with patch("comment_reply_bot._send_message"):
        _handle_model_command(_make_msg("/model auto"), "token", ["/model", "auto"], state_path, chat_map)
    assert "-100123" not in _load_model_state(state_path)


def test_handle_model_command_invalid_shows_help(tmp_path):
    from comment_reply_bot import _handle_model_command

    chat_map = {"chats": {"-100123": {"project": "slay_hack", "default_platform": "instagram"}}}
    with patch("comment_reply_bot._send_message") as mock_send:
        _handle_model_command(_make_msg("/model badprovider badmodel"), "token", ["/model", "badprovider", "badmodel"], tmp_path / "state.json", chat_map)
    assert "valid" in mock_send.call_args[0][2].lower()


def test_load_chat_map_normalizes_chat_ids(tmp_path):
    from comment_reply_bot import _load_chat_map

    path = tmp_path / "comment_chat_map.yaml"
    path.write_text("chats:\n  -100123:\n    project: slay_hack\n", encoding="utf-8")
    assert "-100123" in _load_chat_map(path)["chats"]


def test_build_router_from_map_uses_fallback_chain():
    from comment_reply_bot import _build_router_from_map

    router = _build_router_from_map({"fallback_chain": [{"provider": "openai", "model": "gpt-4o"}]})
    assert router.fallback_chain == [ProviderConfig(provider="openai", model="gpt-4o")]


def test_get_bot_info_returns_result():
    from comment_reply_bot import _get_bot_info

    with patch("comment_reply_bot._api", return_value={"result": {"username": "Comment4U_bot"}}) as mock_api:
        result = _get_bot_info("token")
    mock_api.assert_called_once_with("token", "getMe")
    assert result["username"] == "Comment4U_bot"


def test_format_status_message_reports_privacy_mode_on():
    from comment_reply_bot import _format_status_message

    result = _format_status_message(
        "-100123",
        {"project": "slay_hack", "default_platform": "instagram"},
        {"username": "Comment4U_bot", "can_read_all_group_messages": False},
    )
    assert "Chat map: ✅ registered" in result
    assert "Project: <code>slay_hack</code>" in result
    assert "Privacy mode: ❌ ON" in result
    assert "/setprivacy" in result


def test_format_status_message_reports_unknown_chat():
    from comment_reply_bot import _format_status_message

    result = _format_status_message(
        "-999",
        None,
        {"username": "Comment4U_bot", "can_read_all_group_messages": True},
    )
    assert "Chat ID: <code>-999</code>" in result
    assert "Chat map: ❌ not registered" in result
    assert "Privacy mode: ✅ OFF" in result


def test_handle_status_command_replies_even_for_unknown_chat():
    from comment_reply_bot import _handle_status_command

    with (
        patch("comment_reply_bot._get_bot_info", return_value={"username": "Comment4U_bot"}),
        patch("comment_reply_bot._send_message") as mock_send,
    ):
        _handle_status_command(_make_msg("/status", chat_id="-999"), "token", {"chats": {}})
    assert "Chat map: ❌ not registered" in mock_send.call_args[0][2]
