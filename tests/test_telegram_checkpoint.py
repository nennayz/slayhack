from __future__ import annotations
from unittest.mock import MagicMock, patch

from telegram_checkpoint import _checkpoint_text, _drain_updates, send_and_wait


def _resp(result_data):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"ok": True, "result": result_data}
    return m


def test_drain_stale_updates_empty():
    with patch("telegram_checkpoint.requests.post", return_value=_resp([])):
        result = _drain_updates("token123")
    assert result == 0


def test_drain_stale_updates_has_updates():
    updates = [{"update_id": 10}, {"update_id": 20}]
    with patch("telegram_checkpoint.requests.post", return_value=_resp(updates)):
        result = _drain_updates("token123")
    assert result == 21


def test_send_and_wait_button_press():
    TOKEN, CHAT_ID = "tok", "456789"
    responses = [
        _resp([]),                          # drain getUpdates
        _resp({"message_id": 100}),         # sendMessage (checkpoint)
        _resp([{                            # getUpdates (poll) → callback query
            "update_id": 1,
            "callback_query": {
                "id": "cq1",
                "from": {"id": 456789},
                "message": {"chat": {"id": 456789}},
                "data": "approved",
            },
        }]),
        _resp(True),                        # answerCallbackQuery
        _resp({}),                          # editMessageText
    ]
    with patch("telegram_checkpoint.requests.post", side_effect=responses):
        with patch("telegram_checkpoint.time.monotonic", return_value=0.0):
            result = send_and_wait(
                "content_review", "Script ok.", ["approved", "rejected"],
                TOKEN, CHAT_ID, 30, "approved",
            )
    assert result == "approved"


def test_send_and_wait_text_reply():
    TOKEN, CHAT_ID = "tok", "456789"
    responses = [
        _resp([]),                          # drain
        _resp({"message_id": 100}),         # sendMessage
        _resp([{                            # getUpdates (poll) → text message
            "update_id": 1,
            "message": {"chat": {"id": 456789}, "text": "2"},
        }]),
        _resp({}),                          # editMessageText
    ]
    with patch("telegram_checkpoint.requests.post", side_effect=responses):
        with patch("telegram_checkpoint.time.monotonic", return_value=0.0):
            result = send_and_wait(
                "idea_selection", "Pick one.", ["1", "2", "3"],
                TOKEN, CHAT_ID, 30, "1",
            )
    assert result == "2"


def test_send_and_wait_ignores_other_chat():
    TOKEN, CHAT_ID = "tok", "456789"
    responses = [
        _resp([]),                          # drain
        _resp({"message_id": 100}),         # sendMessage
        _resp([{                            # poll 1: wrong chat
            "update_id": 1,
            "message": {"chat": {"id": 999999}, "text": "hacked"},
        }]),
        _resp([{                            # poll 2: correct chat
            "update_id": 2,
            "message": {"chat": {"id": 456789}, "text": "approved"},
        }]),
        _resp({}),                          # editMessageText
    ]
    with patch("telegram_checkpoint.requests.post", side_effect=responses):
        with patch("telegram_checkpoint.time.monotonic", return_value=0.0):
            result = send_and_wait(
                "qa_review", "s", ["approved", "rejected"],
                TOKEN, CHAT_ID, 30, "approved",
            )
    assert result == "approved"


def test_send_and_wait_timeout():
    TOKEN, CHAT_ID = "tok", "456789"
    responses = [
        _resp([]),                          # drain
        _resp({"message_id": 100}),         # sendMessage (checkpoint)
        _resp({"message_id": 101}),         # sendMessage (timeout notification)
    ]
    with patch("telegram_checkpoint.requests.post", side_effect=responses):
        # monotonic call 1 → 0.0 (deadline = 30); call 2 → 100.0 (while False, skip loop)
        with patch("telegram_checkpoint.time.monotonic", side_effect=[0.0, 100.0]):
            result = send_and_wait(
                "final_approval", "Last check.", ["approved", "rejected"],
                TOKEN, CHAT_ID, 30, "approved",
            )
    assert result == "approved"


def test_send_and_wait_send_fails():
    call_n = 0

    def post_se(*args, **kwargs):
        nonlocal call_n
        call_n += 1
        if call_n == 1:
            return _resp([])            # drain succeeds
        raise Exception("send failed")  # sendMessage raises

    with patch("telegram_checkpoint.requests.post", side_effect=post_se):
        result = send_and_wait(
            "qa_review", "s", ["approved"], "tok", "456", 30, "approved",
        )
    assert result == "approved"


def test_send_and_wait_get_updates_error():
    call_n = 0

    def post_se(*args, **kwargs):
        nonlocal call_n
        call_n += 1
        if call_n == 1:
            return _resp([])                    # drain
        if call_n == 2:
            return _resp({"message_id": 100})   # sendMessage
        if call_n == 3:
            raise Exception("network error")    # getUpdates in loop raises
        return _resp({"message_id": 101})       # timeout notification

    with patch("telegram_checkpoint.requests.post", side_effect=post_se):
        # monotonic: deadline=0+30=30; while 0<30→True; remaining=30-0=30;
        # getUpdates raises (caught); while 100<30→False; timeout handler
        with patch("telegram_checkpoint.time.monotonic",
                   side_effect=[0.0, 0.0, 0.0, 100.0]):
            result = send_and_wait(
                "qa_review", "s", ["approved"], "tok", "456", 30, "approved",
            )
    assert result == "approved"


def test_send_and_wait_writes_lock(tmp_path):
    import telegram_checkpoint as tc
    lock = tmp_path / "pipeline.lock"
    TOKEN, CHAT_ID = "tok", "456789"
    responses = [
        _resp([]),
        _resp({"message_id": 100}),
        _resp([{"update_id": 1, "message": {"chat": {"id": 456789}, "text": "approved"}}]),
        _resp({}),
    ]
    with patch("telegram_checkpoint.requests.post", side_effect=responses):
        with patch("telegram_checkpoint.time.monotonic", return_value=0.0):
            with patch.object(tc, "_LOCK_FILE", lock):
                send_and_wait("qa_review", "s", ["approved"], TOKEN, CHAT_ID, 30, "approved")
    # Lock is written (not deleted — main.py owns deletion)
    assert lock.exists()
    content = lock.read_text()
    assert content  # non-empty
    float(content)  # parseable as a timestamp — raises ValueError if wrong


def test_send_and_wait_writes_lock_on_send_failure(tmp_path):
    import telegram_checkpoint as tc
    lock = tmp_path / "pipeline.lock"
    call_n = 0

    def post_se(*args, **kwargs):
        nonlocal call_n
        call_n += 1
        if call_n == 1:
            return _resp([])
        raise Exception("send failed")

    with patch("telegram_checkpoint.requests.post", side_effect=post_se):
        with patch.object(tc, "_LOCK_FILE", lock):
            result = send_and_wait("qa_review", "s", ["approved"], "tok", "456", 30, "approved")
    assert result == "approved"
    # Lock is written even on failure (main.py will clean it up)
    assert lock.exists()
    content = lock.read_text()
    assert content  # non-empty
    float(content)  # parseable as a timestamp — raises ValueError if wrong


def test_checkpoint_text_defaults_to_minimal_and_truncates(monkeypatch):
    monkeypatch.delenv("NAYZ_TELEGRAM_CHECKPOINT_DETAIL", raising=False)

    text = _checkpoint_text("qa_review", "x" * 700)

    assert "Approval needed" in text
    assert "Checkpoint:" not in text
    assert len(text) < 700


def test_checkpoint_text_full_mode_keeps_original_summary(monkeypatch):
    monkeypatch.setenv("NAYZ_TELEGRAM_CHECKPOINT_DETAIL", "full")

    text = _checkpoint_text("qa_review", "Line 1\n\nLine 2")

    assert "Checkpoint: qa_review" in text
    assert "Line 1\n\nLine 2" in text
