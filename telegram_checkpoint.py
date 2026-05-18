from __future__ import annotations
import logging
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.telegram.org/bot{token}/{method}"
_LOCK_FILE = Path("/tmp/nayz_pipeline.lock")


def _api(token: str, method: str, **kwargs) -> dict:
    url = _BASE_URL.format(token=token, method=method)
    http_timeout = kwargs.get("timeout", 5) + 5
    try:
        resp = requests.post(url, json=kwargs, timeout=http_timeout)
        resp.raise_for_status()
    except Exception as exc:
        safe_url = _BASE_URL.format(token="<redacted>", method=method)
        raise RuntimeError(f"Telegram request failed [{method}] {safe_url}: {type(exc).__name__}") from exc
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error ({method}): {data.get('description', 'unknown')}")
    return data


def _get_updates(token: str, offset: int, timeout: int = 5) -> list[dict]:
    try:
        data = _api(
            token, "getUpdates",
            offset=offset, timeout=timeout,
            allowed_updates=["message", "callback_query"],
        )
        return data.get("result", [])
    except Exception as exc:
        logger.warning("getUpdates failed: %s", exc)
        return []


def _drain_updates(token: str) -> int:
    updates = _get_updates(token, offset=-1, timeout=0)
    if updates:
        return updates[-1]["update_id"] + 1
    return 0


def _send_message(token: str, chat_id: str, text: str, reply_markup=None) -> int:
    kwargs: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup is not None:
        kwargs["reply_markup"] = reply_markup
    data = _api(token, "sendMessage", **kwargs)
    return data["result"]["message_id"]


def _edit_message(token: str, chat_id: str, message_id: int, text: str) -> None:
    try:
        _api(
            token, "editMessageText",
            chat_id=chat_id, message_id=message_id, text=text,
            parse_mode="HTML", reply_markup={"inline_keyboard": []},
        )
    except Exception as exc:
        logger.warning("editMessageText failed: %s", exc)


def _answer_callback(token: str, callback_query_id: str) -> None:
    try:
        _api(token, "answerCallbackQuery", callback_query_id=callback_query_id)
    except Exception as exc:
        logger.warning("answerCallbackQuery failed: %s", exc)


def _build_keyboard(options: list[str]) -> dict:
    return {"inline_keyboard": [[{"text": opt, "callback_data": opt}] for opt in options]}


def _checkpoint_text(stage: str, summary: str) -> str:
    mode = os.environ.get("NAYZ_TELEGRAM_CHECKPOINT_DETAIL", "minimal").strip().lower()
    cleaned = " ".join(summary.split())
    if mode != "full" and len(cleaned) > 600:
        cleaned = f"{cleaned[:597]}..."
    if mode == "minimal":
        return f"⏸ <b>Approval needed:</b> {stage}\n\n{cleaned}\n\nChoose a button or reply:"
    return f"⏸ <b>Checkpoint: {stage}</b>\n\n{summary}\n\nReply with a button or type freely:"


def send_and_wait(
    stage: str,
    summary: str,
    options: list[str],
    token: str,
    chat_id: str,
    timeout_seconds: int,
    fallback: str,
) -> str:
    try:
        _LOCK_FILE.write_text(str(time.time()))
    except OSError as exc:
        logger.warning("Could not write pipeline lock file: %s", exc)

    keyboard = _build_keyboard(options)
    text = _checkpoint_text(stage, summary)

    offset = _drain_updates(token)

    try:
        message_id = _send_message(token, chat_id, text, reply_markup=keyboard)
    except Exception as exc:
        logger.error("Failed to send Telegram checkpoint message: %s", exc)
        return fallback

    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        poll_timeout = min(5, int(remaining))
        if poll_timeout <= 0:
            break

        updates = _get_updates(token, offset=offset, timeout=poll_timeout)
        for update in updates:
            offset = update["update_id"] + 1

            if "callback_query" in update:
                cq = update["callback_query"]
                cq_chat_id = str(cq.get("message", {}).get("chat", {}).get("id", ""))
                if cq_chat_id != str(chat_id):
                    continue
                decision = cq["data"]
                _answer_callback(token, cq["id"])
                _edit_message(token, chat_id, message_id,
                               text + f"\n✅ Decision recorded: {decision}")
                return decision

            elif "message" in update:
                msg = update["message"]
                msg_chat_id = str(msg.get("chat", {}).get("id", ""))
                if msg_chat_id != str(chat_id):
                    continue
                decision = msg.get("text", "").strip()
                if not decision:
                    continue
                _edit_message(token, chat_id, message_id,
                               text + f"\n✅ Decision recorded: {decision}")
                return decision

    logger.warning(
        "Telegram checkpoint %s timed out after %ds, using fallback: %s",
        stage, timeout_seconds, fallback,
    )
    try:
        _send_message(
            token, chat_id,
            f"⏰ No reply for <b>{stage}</b> — auto-continuing with: {fallback}",
        )
    except Exception:
        pass
    return fallback
