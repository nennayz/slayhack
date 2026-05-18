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
from typing import Any

import requests
import yaml

from comment_model_router import ModelRouter, ProviderConfig
from project_loader import load_project, resolve_project_slug

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent
_BASE_URL = "https://api.telegram.org/bot{token}/{method}"
_MODEL_STATE_FILE = Path("/tmp/comment_bot_model_state.json")
_LOG_DIR = _ROOT / "output" / "comment_reply_log"

_PLATFORM_ALIASES = {
    "ig": "instagram",
    "instagram": "instagram",
    "fb": "facebook",
    "facebook": "facebook",
    "tiktok": "tiktok",
    "tt": "tiktok",
    "youtube": "youtube",
    "yt": "youtube",
}

_PLATFORM_MAX_CHARS_DEFAULTS = {
    "tiktok": 150,
    "instagram": 2200,
    "facebook": 8000,
    "youtube": 10000,
}

_NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
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


def parse_ai_response(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    current_comment: str | None = None
    for line in text.strip().splitlines():
        line = line.strip()
        if line.startswith("COMMENT_") and ":" in line:
            current_comment = line.split(":", 1)[1].strip()
        elif line.startswith("REPLY_") and ":" in line and current_comment is not None:
            pairs.append((current_comment, line.split(":", 1)[1].strip()))
            current_comment = None
    return pairs


def detect_platform(caption: str | None, default: str) -> str:
    if not caption:
        return default
    for word in caption.lower().replace(",", " ").split():
        if word in _PLATFORM_ALIASES:
            return _PLATFORM_ALIASES[word]
    return default


def compute_image_hash(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def enforce_char_limit(reply: str, max_chars: int, router: ModelRouter | None) -> str:
    if len(reply) <= max_chars:
        return reply
    if router is not None:
        prompt = (
            f"Shorten this reply to under {max_chars} characters. "
            f"Keep the same tone and language. Return only the shortened reply.\n\n{reply}"
        )
        try:
            shortened, _ = router.call_text(prompt)
            return shortened[:max_chars] if len(shortened) > max_chars else shortened
        except RuntimeError:
            pass
    return reply[: max_chars - 3] + "..."


def build_system_prompt(brand: object, max_chars: int) -> str:
    return (
        "You are a social media community manager.\n"
        f"Brand tone: {brand.tone}\n"
        f"Target audience: {brand.target_audience}\n"
        f"Writing style: {brand.script_style}\n\n"
        "Look at this screenshot carefully.\n\n"
        "1. Find ALL comments visible in the image, reading top to bottom.\n"
        "2. For each comment, write ONE reply that matches the brand tone.\n"
        f"3. Each reply must be under {max_chars} characters.\n"
        "4. Match the language of the comment (Thai replies Thai, English replies English).\n"
        "5. Do not use hashtags unless the comment contains them.\n"
        "6. Never mention AI or automation.\n\n"
        "Return your response in this exact format:\n"
        "COMMENT_1: [exact comment text you read]\n"
        "REPLY_1: [your reply]\n"
        "COMMENT_2: [exact comment text you read]\n"
        "REPLY_2: [your reply]\n\n"
        "Return ONLY this format. No other text."
    )


def format_output(pairs: list[tuple[str, str]], model_label: str, platform: str) -> str:
    count = len(pairs)
    noun = "comment" if count == 1 else "comments"
    lines = [f"📸 พบ {count} {noun} ในภาพ\n"]
    for i, (comment, reply) in enumerate(pairs):
        marker = _NUMBER_EMOJIS[i] if i < len(_NUMBER_EMOJIS) else f"{i + 1}."
        lines.append(f"{marker} {comment}")
        lines.append(f'💬 "{reply}"\n')
    lines.append("─────────────────")
    model_short = model_label.split("/")[-1] if "/" in model_label else model_label
    lines.append(f"🤖 {model_short}  |  📱 {platform}")
    return "\n".join(lines)


def find_in_log(log_path: Path, image_hash: str) -> dict[str, Any] | None:
    if not log_path.exists():
        return None
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("image_hash") == image_hash:
                return entry
    except (json.JSONDecodeError, OSError):
        return None
    return None


def append_to_log(log_path: Path, entry: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _api(token: str, method: str, **kwargs: Any) -> dict[str, Any]:
    url = _BASE_URL.format(token=token, method=method)
    http_timeout = int(kwargs.get("timeout", 5)) + 5
    try:
        response = requests.post(url, json=kwargs, timeout=http_timeout)
        response.raise_for_status()
    except Exception as exc:
        safe_url = _BASE_URL.format(token="<redacted>", method=method)
        raise RuntimeError(f"Telegram request failed [{method}] {safe_url}: {type(exc).__name__}") from exc
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error ({method}): {data.get('description', 'unknown')}")
    return data


def _get_updates(token: str, offset: int, timeout: int = 5) -> list[dict[str, Any]]:
    try:
        data = _api(token, "getUpdates", offset=offset, timeout=timeout, allowed_updates=["message"])
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
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except Exception as exc:
        safe_url = f"https://api.telegram.org/file/bot<redacted>/{file_path}"
        raise RuntimeError(f"Photo download failed [{safe_url}]: {type(exc).__name__}") from exc
    return response.content


def _load_comment_max_chars(project_slug: str, platform: str, root: Path) -> int:
    resolved = resolve_project_slug(project_slug, root=root)
    specs_path = root / "projects" / resolved / "platform_specs.yaml"
    if specs_path.exists():
        try:
            data = yaml.safe_load(specs_path.read_text(encoding="utf-8")) or {}
            platform_data = data.get(platform, {})
            if isinstance(platform_data, dict) and "comment_max_chars" in platform_data:
                return int(platform_data["comment_max_chars"])
        except (OSError, ValueError, yaml.YAMLError):
            pass
    return _PLATFORM_MAX_CHARS_DEFAULTS.get(platform, 2200)


def _load_model_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_model_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(path)


def _handle_photo_message(
    msg: dict[str, Any],
    token: str,
    chat_map_data: dict[str, Any],
    root: Path,
    router: ModelRouter,
    model_state_path: Path,
    log_dir: Path,
) -> None:
    chat_id = str(msg["chat"]["id"])
    chat_config = chat_map_data.get("chats", {}).get(chat_id)
    if chat_config is None:
        return

    project_slug = chat_config["project"]
    platform = detect_platform(msg.get("caption") or "", chat_config.get("default_platform", "instagram"))
    photos = msg.get("photo", [])
    if not photos:
        return

    image_bytes = _download_photo(token, photos[-1]["file_id"])
    image_hash = compute_image_hash(image_bytes)
    log_path = log_dir / f"{project_slug}.jsonl"
    existing = find_in_log(log_path, image_hash)
    if existing:
        cached_pairs = list(zip(existing.get("comments", []), existing.get("replies", [])))
        cached = format_output(cached_pairs, existing.get("model_used", "cached"), existing.get("platform", platform))
        _send_message(token, chat_id, f"♻️ รูปนี้ตอบไปแล้วเมื่อ {existing.get('timestamp', 'unknown')}\n\n{cached}")
        return

    active_router = router
    model_state = _load_model_state(model_state_path)
    override = model_state.get(chat_id)
    if override:
        active_router = ModelRouter(
            fallback_chain=[ProviderConfig(**override)],
            anthropic_key=router.anthropic_key,
            openai_key=router.openai_key,
            gemini_key=router.gemini_key,
        )

    try:
        brand = load_project(project_slug, root=root).brand
    except Exception as exc:
        _send_message(token, chat_id, f"❌ ไม่สามารถโหลด project {project_slug!r}: {exc}")
        return

    max_chars = _load_comment_max_chars(project_slug, platform, root)
    prompt = build_system_prompt(brand, max_chars)
    _send_message(token, chat_id, "⏳ กำลังอ่าน comment...")

    try:
        raw_text, model_label = active_router.call(base64.b64encode(image_bytes).decode("ascii"), prompt)
    except RuntimeError as exc:
        _send_message(token, chat_id, f"❌ {exc}")
        return

    pairs = parse_ai_response(raw_text)
    if not pairs:
        _send_message(token, chat_id, "ไม่เจอ comment ในรูป กรุณาส่งรูปใหม่")
        return

    enforced_pairs = [(comment, enforce_char_limit(reply, max_chars, active_router)) for comment, reply in pairs]
    _send_message(token, chat_id, format_output(enforced_pairs, model_label, platform))
    append_to_log(
        log_path,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "chat_id": chat_id,
            "image_hash": image_hash,
            "platform": platform,
            "model_used": model_label,
            "comments": [comment for comment, _ in enforced_pairs],
            "replies": [reply for _, reply in enforced_pairs],
        },
    )


def _handle_model_command(
    msg: dict[str, Any],
    token: str,
    args: list[str],
    model_state_path: Path,
    chat_map_data: dict[str, Any],
) -> None:
    chat_id = str(msg["chat"]["id"])
    if chat_id not in chat_map_data.get("chats", {}):
        return

    if len(args) == 2 and args[1] == "auto":
        state = _load_model_state(model_state_path)
        state.pop(chat_id, None)
        _save_model_state(model_state_path, state)
        _send_message(token, chat_id, "✅ Reset to automatic fallback chain")
        return

    if len(args) == 3 and args[1] in _VALID_PROVIDERS:
        state = _load_model_state(model_state_path)
        state[chat_id] = {"provider": args[1], "model": args[2]}
        _save_model_state(model_state_path, state)
        _send_message(token, chat_id, f"✅ Switched to {args[1]} / {args[2]} for this chat")
        return

    _send_message(
        token,
        chat_id,
        "❌ Valid options:\n"
        "/model anthropic claude-sonnet-4-6\n"
        "/model openai gpt-4o\n"
        "/model gemini gemini-2.0-flash\n"
        "/model auto",
    )


def _handle_help_command(msg: dict[str, Any], token: str, chat_map_data: dict[str, Any]) -> None:
    chat_id = str(msg["chat"]["id"])
    if chat_id not in chat_map_data.get("chats", {}):
        return
    _send_message(token, chat_id, _HELP_TEXT)


def _load_chat_map(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeError(f"Failed to load chat map from {path}: {exc}") from exc
    data["chats"] = {str(chat_id): value for chat_id, value in data.get("chats", {}).items()}
    return data


def _build_router_from_map(chat_map_data: dict[str, Any]) -> ModelRouter:
    chain = [
        ProviderConfig(provider=item["provider"], model=item["model"])
        for item in chat_map_data.get("fallback_chain", [])
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
    offset = 0
    chat_map_data = _load_chat_map(chat_map_path)
    router = _build_router_from_map(chat_map_data)
    logger.info("Comment reply bot started with %d registered chats.", len(chat_map_data.get("chats", {})))

    while True:
        for update in _get_updates(token, offset=offset, timeout=5):
            offset = int(update["update_id"]) + 1
            try:
                msg = update.get("message", {})
                if not msg:
                    continue
                chat_map_data = _load_chat_map(chat_map_path)
                router = _build_router_from_map(chat_map_data)
                text = (msg.get("text") or "").strip()
                if text.startswith("/help"):
                    _handle_help_command(msg, token, chat_map_data)
                elif text.startswith("/model"):
                    _handle_model_command(msg, token, text.split(), _MODEL_STATE_FILE, chat_map_data)
                elif msg.get("photo"):
                    _handle_photo_message(msg, token, chat_map_data, root, router, _MODEL_STATE_FILE, _LOG_DIR)
            except Exception as exc:
                logger.error("Error handling update %s: %s", update.get("update_id"), exc)
        time.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    token = os.getenv("COMMENT_BOT_TOKEN", "")
    if not token:
        logger.error("COMMENT_BOT_TOKEN must be set.")
        sys.exit(1)
    chat_map_path = Path(os.getenv("COMMENT_CHAT_MAP_PATH", str(_ROOT / "comment_chat_map.yaml")))
    if not chat_map_path.exists():
        logger.error("comment_chat_map.yaml not found at %s", chat_map_path)
        sys.exit(1)
    run_bot(token, chat_map_path, _ROOT)
