#!/usr/bin/env python3
"""Telegram -> OneDrive jrnl appender.

Polls a private Telegram bot chat and appends timestamped entries to a journal file.
Downloads attachments to OneDrive\\jrnl-media and links them in markdown.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import logging
import os
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Config:
    telegram_bot_token: str
    onedrive_dir: Path
    journal_file_name: str
    media_subdir: str
    poll_timeout_seconds: int
    poll_interval_seconds: float
    allowed_chat_id: int | None
    timezone_name: str | None


STATE_FILE = "bot_state.json"
LOG_DIR = "logs"
LOG_FILE = "telegram_jrnl_bot.log"


class SingleInstanceLock:
    """Cross-platform single-instance guard.

    On Windows, uses a named mutex.
    On other platforms, uses an exclusive lock file.
    """

    def __init__(self, instance_id: str, base_dir: Path) -> None:
        self.instance_id = instance_id
        self.base_dir = base_dir
        self._win_handle: int | None = None
        self._win_owned = False
        self._lock_fd: int | None = None
        self._lock_path: Path | None = None

    def acquire(self) -> bool:
        if sys.platform == "win32":
            return self._acquire_windows_mutex()
        return self._acquire_lock_file()

    def release(self) -> None:
        if sys.platform == "win32":
            self._release_windows_mutex()
            return
        self._release_lock_file()

    def _acquire_windows_mutex(self) -> bool:
        kernel32 = ctypes.windll.kernel32
        mutex_name = f"Local\\{self.instance_id}"

        handle = kernel32.CreateMutexW(None, False, mutex_name)
        if not handle:
            raise OSError("Failed to create/open Windows mutex")

        WAIT_OBJECT_0 = 0x00000000
        WAIT_ABANDONED = 0x00000080
        WAIT_TIMEOUT = 0x00000102

        wait_result = kernel32.WaitForSingleObject(handle, 0)
        if wait_result in (WAIT_OBJECT_0, WAIT_ABANDONED):
            self._win_handle = handle
            self._win_owned = True
            return True

        if wait_result == WAIT_TIMEOUT:
            kernel32.CloseHandle(handle)
            return False

        kernel32.CloseHandle(handle)
        raise OSError(f"Unexpected mutex wait result: {wait_result}")

    def _release_windows_mutex(self) -> None:
        if self._win_handle is None:
            return

        kernel32 = ctypes.windll.kernel32
        if self._win_owned:
            kernel32.ReleaseMutex(self._win_handle)
        kernel32.CloseHandle(self._win_handle)
        self._win_handle = None
        self._win_owned = False

    def _acquire_lock_file(self) -> bool:
        lock_path = self.base_dir / f".{self.instance_id}.lock"
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(fd, str(os.getpid()).encode("utf-8"))
            self._lock_fd = fd
            self._lock_path = lock_path
            return True
        except FileExistsError:
            return False

    def _release_lock_file(self) -> None:
        if self._lock_fd is not None:
            try:
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None

        if self._lock_path is not None:
            try:
                self._lock_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._lock_path = None


def build_instance_id(cfg: Config, base_dir: Path) -> str:
    key = "|".join(
        [
            str(base_dir.resolve()),
            str(cfg.onedrive_dir.resolve()),
            cfg.journal_file_name,
            cfg.media_subdir,
        ]
    )
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return f"TelegramJrnlBot_{digest}"


def load_env_file(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not env_path.exists():
        return env

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def getenv(env_map: dict[str, str], key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, env_map.get(key, default))


def load_config(base_dir: Path) -> Config:
    env = load_env_file(base_dir / ".env")

    token = getenv(env, "TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN in .env or environment")

    onedrive_dir_raw = getenv(env, "ONEDRIVE_DIR")
    if not onedrive_dir_raw:
        raise ValueError("Missing ONEDRIVE_DIR in .env or environment")

    journal_file_name = getenv(env, "JOURNAL_FILE_NAME", "telegram-jrnl.txt") or "telegram-jrnl.txt"
    media_subdir = getenv(env, "MEDIA_SUBDIR", "jrnl-media") or "jrnl-media"

    poll_timeout_seconds = int(getenv(env, "POLL_TIMEOUT_SECONDS", "30") or "30")
    poll_interval_seconds = float(getenv(env, "POLL_INTERVAL_SECONDS", "2") or "2")

    allowed_chat_id_raw = getenv(env, "TELEGRAM_ALLOWED_CHAT_ID", "")
    allowed_chat_id = int(allowed_chat_id_raw) if allowed_chat_id_raw else None

    timezone_name = getenv(env, "TIMEZONE", "") or None

    return Config(
        telegram_bot_token=token,
        onedrive_dir=Path(onedrive_dir_raw).expanduser(),
        journal_file_name=journal_file_name,
        media_subdir=media_subdir,
        poll_timeout_seconds=poll_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        allowed_chat_id=allowed_chat_id,
        timezone_name=timezone_name,
    )


def configure_logging(base_dir: Path) -> None:
    log_dir = base_dir / LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_dir / LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def load_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {"last_update_id": 0}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        logging.warning("Failed to parse state file. Resetting state.")
        return {"last_update_id": 0}


def save_state(state_path: Path, state: dict[str, Any]) -> None:
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def telegram_api_request(token: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    base = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    headers = {}

    if params is not None:
        encoded = urllib.parse.urlencode(params).encode("utf-8")
        data = encoded
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    req = urllib.request.Request(base, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=70) as resp:
            payload = resp.read().decode("utf-8")
            parsed = json.loads(payload)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise PermissionError(
                "Telegram returned 401 Unauthorized. Your TELEGRAM_BOT_TOKEN is invalid, revoked, "
                "or belongs to a different bot. Generate a new token in BotFather and update .env."
            ) from e
        raise

    if not parsed.get("ok"):
        raise RuntimeError(f"Telegram API error: {parsed}")

    return parsed


def telegram_download_file(token: str, file_path: str) -> bytes:
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read()


def resolve_timestamp(unix_ts: int, timezone_name: str | None) -> str:
    dt_utc = datetime.fromtimestamp(unix_ts, tz=timezone.utc)

    if timezone_name:
        try:
            from zoneinfo import ZoneInfo

            dt_local = dt_utc.astimezone(ZoneInfo(timezone_name))
        except Exception:
            logging.warning("Invalid TIMEZONE '%s', using system local timezone", timezone_name)
            dt_local = dt_utc.astimezone()
    else:
        dt_local = dt_utc.astimezone()

    return dt_local.strftime("[%Y-%m-%d %H:%M]")


def ensure_paths(cfg: Config) -> tuple[Path, Path]:
    onedrive_dir = cfg.onedrive_dir
    media_dir = onedrive_dir / cfg.media_subdir
    journal_file = onedrive_dir / cfg.journal_file_name

    onedrive_dir.mkdir(parents=True, exist_ok=True)
    media_dir.mkdir(parents=True, exist_ok=True)
    journal_file.touch(exist_ok=True)

    return media_dir, journal_file


def sanitize_filename(name: str) -> str:
    forbidden = '<>:"/\\|?*'
    safe = "".join("_" if ch in forbidden else ch for ch in name).strip()
    return safe or "attachment"


def markdown_link(file_path: Path) -> str:
    name = file_path.name
    markdown_path = file_path.as_posix()
    return f"[{name}]({markdown_path})"


def detect_attachment(message: dict[str, Any]) -> dict[str, Any] | None:
    if "document" in message:
        doc = message["document"]
        return {
            "kind": "document",
            "file_id": doc.get("file_id"),
            "file_name": doc.get("file_name") or f"document_{message.get('message_id', 'x')}",
        }

    if "voice" in message:
        voice = message["voice"]
        return {
            "kind": "voice",
            "file_id": voice.get("file_id"),
            "file_name": f"voice_{message.get('message_id', 'x')}.ogg",
        }

    if "audio" in message:
        audio = message["audio"]
        fallback = f"audio_{message.get('message_id', 'x')}.mp3"
        return {
            "kind": "audio",
            "file_id": audio.get("file_id"),
            "file_name": audio.get("file_name") or fallback,
        }

    if "video" in message:
        video = message["video"]
        return {
            "kind": "video",
            "file_id": video.get("file_id"),
            "file_name": f"video_{message.get('message_id', 'x')}.mp4",
        }

    if "video_note" in message:
        note = message["video_note"]
        return {
            "kind": "video_note",
            "file_id": note.get("file_id"),
            "file_name": f"video_note_{message.get('message_id', 'x')}.mp4",
        }

    if "photo" in message:
        photos = message["photo"]
        if photos:
            largest = max(photos, key=lambda p: p.get("file_size", 0))
            return {
                "kind": "photo",
                "file_id": largest.get("file_id"),
                "file_name": f"photo_{message.get('message_id', 'x')}.jpg",
            }

    return None


def save_attachment(cfg: Config, message: dict[str, Any], media_dir: Path) -> Path | None:
    attachment = detect_attachment(message)
    if not attachment:
        return None

    file_id = attachment.get("file_id")
    if not file_id:
        logging.warning("Attachment without file_id in message %s", message.get("message_id"))
        return None

    info = telegram_api_request(cfg.telegram_bot_token, "getFile", {"file_id": file_id})
    file_path = info["result"]["file_path"]
    binary = telegram_download_file(cfg.telegram_bot_token, file_path)

    timestamp_token = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base_name = sanitize_filename(str(attachment["file_name"]))
    final_name = f"{timestamp_token}_{message.get('message_id', 'x')}_{base_name}"
    output_path = media_dir / final_name

    output_path.write_bytes(binary)
    logging.info("Saved attachment to %s", output_path)
    return output_path


def extract_message_text(message: dict[str, Any]) -> str:
    text = message.get("text")
    if text:
        return text.strip()

    caption = message.get("caption")
    if caption:
        return caption.strip()

    return ""


def build_entry_content(text: str, attachment_path: Path | None) -> str:
    if attachment_path and text:
        return f"{text} {markdown_link(attachment_path)}"

    if attachment_path and not text:
        return f"sent file {markdown_link(attachment_path)}"

    if text:
        return text

    return ""


def append_journal_entry(journal_file: Path, timestamp_label: str, content: str) -> None:
    if not content:
        return

    line = f"{timestamp_label} {content}\n\n"
    with journal_file.open("a", encoding="utf-8") as f:
        f.write(line)


def message_allowed(message: dict[str, Any], allowed_chat_id: int | None) -> bool:
    if allowed_chat_id is None:
        return True
    chat_id = message.get("chat", {}).get("id")
    return chat_id == allowed_chat_id


def process_update(cfg: Config, update: dict[str, Any], media_dir: Path, journal_file: Path) -> None:
    message = update.get("message")
    if not message:
        return

    if not message_allowed(message, cfg.allowed_chat_id):
        logging.info("Skipping message from unauthorized chat_id=%s", message.get("chat", {}).get("id"))
        return

    unix_ts = message.get("date")
    if not unix_ts:
        logging.warning("Message without date metadata. Skipping message_id=%s", message.get("message_id"))
        return

    ts_label = resolve_timestamp(int(unix_ts), cfg.timezone_name)
    text = extract_message_text(message)
    attachment_path = save_attachment(cfg, message, media_dir)

    content = build_entry_content(text, attachment_path)
    append_journal_entry(journal_file, ts_label, content)

    if content:
        logging.info("Appended entry: %s", content[:120])


def poll_forever(cfg: Config, base_dir: Path) -> None:
    media_dir, journal_file = ensure_paths(cfg)
    state_path = base_dir / STATE_FILE
    state = load_state(state_path)

    last_update_id = int(state.get("last_update_id", 0))
    logging.info("Starting polling with last_update_id=%s", last_update_id)

    while True:
        try:
            params = {
                "offset": last_update_id + 1,
                "timeout": cfg.poll_timeout_seconds,
                "allowed_updates": json.dumps(["message"]),
            }
            data = telegram_api_request(cfg.telegram_bot_token, "getUpdates", params)
            updates = data.get("result", [])

            if updates:
                for update in updates:
                    update_id = int(update["update_id"])
                    process_update(cfg, update, media_dir, journal_file)
                    last_update_id = max(last_update_id, update_id)

                state["last_update_id"] = last_update_id
                save_state(state_path, state)

            time.sleep(cfg.poll_interval_seconds)
        except KeyboardInterrupt:
            logging.info("Interrupted by user, shutting down.")
            break
        except PermissionError as e:
            logging.error("%s", e)
            logging.error("Stopping bot to avoid repeated unauthorized polling attempts.")
            break
        except urllib.error.URLError as e:
            logging.error("Network error while polling Telegram: %s", e)
            time.sleep(max(cfg.poll_interval_seconds, 5))
        except Exception as e:
            logging.error("Unexpected error: %s", e)
            traceback.print_exc()
            time.sleep(max(cfg.poll_interval_seconds, 5))


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    configure_logging(base_dir)

    try:
        cfg = load_config(base_dir)
    except Exception as e:
        logging.error("Configuration error: %s", e)
        return 2

    instance_id = build_instance_id(cfg, base_dir)
    instance_lock = SingleInstanceLock(instance_id, base_dir)
    if not instance_lock.acquire():
        logging.error("Another bot instance is already running (instance_id=%s). Exiting.", instance_id)
        return 3

    try:
        logging.info("Single-instance lock acquired: %s", instance_id)
        logging.info("Journal file: %s", cfg.onedrive_dir / cfg.journal_file_name)
        logging.info("Media folder: %s", cfg.onedrive_dir / cfg.media_subdir)

        poll_forever(cfg, base_dir)
        return 0
    finally:
        instance_lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
