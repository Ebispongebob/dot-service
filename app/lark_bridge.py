"""
Lark / Feishu polling bridge for Dot Service.

Implements the simple "方案 A" integration: periodically call lark-cli to
poll recent IM messages, filter them, and push compact notifications to Dot.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from .config import Settings
from .dot_client import DotClient, DotClientError

logger = logging.getLogger(__name__)


@dataclass
class LarkMessage:
    """Normalized Lark message used by the bridge."""

    message_id: str
    sender: str
    text: str
    source_type: str
    source_id: str
    created_at: Optional[str] = None
    link: Optional[str] = None


class LarkNotifyBridge:
    """Poll lark-cli for messages and push matched notifications to Dot."""

    def __init__(
        self,
        settings: Settings,
        dot_client_factory: Callable[[], DotClient],
        device_id_provider: Callable[[], str],
    ):
        self.settings = settings
        self._dot_client_factory = dot_client_factory
        self._device_id_provider = device_id_provider
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._seen_ids: set[str] = set()
        self._state_loaded = False
        self._first_poll = True
        self._last_poll_at: Optional[str] = None
        self._last_error: Optional[str] = None
        self._notified_count = 0
        self._matched_count = 0
        self._skipped_count = 0
        self._discovered_chats: list[dict[str, str]] = []
        self._discovered_at: Optional[str] = None

    @property
    def enabled(self) -> bool:
        return self.settings.lark_notify_enabled

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Start the background polling task when enabled."""
        if not self.enabled:
            logger.info("Lark notification bridge disabled")
            return
        if self.settings.lark_notify_monitor_all:
            await self._discover_chats()
        if not self.sources and not self.settings.lark_notify_monitor_all:
            logger.warning(
                "Lark notification bridge enabled but no source configured "
                "and monitor_all is off"
            )
            return
        # monitor_all with zero discovered chats is allowed — they'll be
        # populated on the next discovery cycle.
        self._load_state()
        self._task = asyncio.create_task(self._run(), name="lark-notify-bridge")
        logger.info("Lark notification bridge started")

    async def stop(self) -> None:
        """Stop the background polling task."""
        self._stop_event.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._save_state()
        logger.info("Lark notification bridge stopped")

    @property
    def keywords(self) -> list[str]:
        return _split_csv(self.settings.lark_notify_keywords)

    @property
    def mention_ids(self) -> list[str]:
        return _split_csv(self.settings.lark_notify_mention_ids)

    @property
    def sources(self) -> list[tuple[str, str]]:
        sources: list[tuple[str, str]] = []
        # Explicitly configured sources
        chat_ids = _split_csv(self.settings.lark_notify_chat_ids)
        user_ids = _split_csv(self.settings.lark_notify_user_ids)
        sources.extend(("chat", chat_id) for chat_id in chat_ids)
        sources.extend(("user", user_id) for user_id in user_ids)
        # Auto-discovered chats (monitor all mode)
        for chat in self._discovered_chats:
            cid = chat["chat_id"]
            if not any(s[1] == cid for s in sources):
                sources.append(("chat", cid))
        return sources

    def status(self) -> dict[str, Any]:
        """Return runtime status for API inspection."""
        return {
            "enabled": self.enabled,
            "running": self.running,
            "monitor_all": self.settings.lark_notify_monitor_all,
            "identity": self.settings.lark_notify_identity,
            "profile": self.settings.lark_notify_profile or None,
            "sources": [
                {"type": source_type, "id": source_id}
                for source_type, source_id in self.sources
            ],
            "keywords": self.keywords,
            "mention_ids": self.mention_ids,
            "discovered_chats": self._discovered_chats,
            "discovered_at": self._discovered_at,
            "poll_interval_seconds": self.settings.lark_notify_poll_interval_seconds,
            "lookback_minutes": self.settings.lark_notify_lookback_minutes,
            "skip_existing_on_start": self.settings.lark_notify_skip_existing_on_start,
            "seen_count": len(self._seen_ids),
            "matched_count": self._matched_count,
            "notified_count": self._notified_count,
            "skipped_count": self._skipped_count,
            "last_poll_at": self._last_poll_at,
            "last_error": self._last_error,
            "state_file": str(self._state_file),
        }

    async def poll_once(self, *, notify: bool = True) -> dict[str, Any]:
        """Poll all configured sources once."""
        if not self._state_loaded:
            self._load_state()

        now = datetime.now().astimezone()
        start = now - timedelta(minutes=self.settings.lark_notify_lookback_minutes)
        matched: list[LarkMessage] = []
        errors: list[str] = []
        total_messages = 0

        for source_type, source_id in self.sources:
            try:
                messages = await self._poll_source(source_type, source_id, start, now)
                total_messages += len(messages)
            except Exception as exc:  # noqa: BLE001 - keep background loop alive
                msg = f"{source_type}:{source_id}: {exc}"
                errors.append(msg)
                logger.exception("Failed to poll Lark source %s", msg)
                continue

            for raw_message in sorted(messages, key=_message_sort_key):
                normalized = self._normalize_message(raw_message, source_type, source_id)
                if normalized is None:
                    continue
                if normalized.message_id in self._seen_ids:
                    continue

                self._seen_ids.add(normalized.message_id)

                if self._matches(raw_message, normalized):
                    matched.append(normalized)
                    self._matched_count += 1
                else:
                    self._skipped_count += 1

        should_skip_initial = (
            self._first_poll and self.settings.lark_notify_skip_existing_on_start
        )
        sent = False
        if notify and matched and not should_skip_initial:
            try:
                await self._send_summary(matched)
            except Exception:
                # Keep matched messages retryable when Dot delivery fails.
                for message in matched:
                    self._seen_ids.discard(message.message_id)
                raise
            sent = True
            self._notified_count += 1
        elif matched:
            self._skipped_count += len(matched)

        self._first_poll = False
        self._last_poll_at = now.isoformat(timespec="seconds")
        self._last_error = "; ".join(errors) if errors else None
        self._trim_seen_ids()
        self._save_state()

        return {
            "polled_sources": len(self.sources),
            "total_messages": total_messages,
            "matched_messages": len(matched),
            "sent": sent,
            "initial_poll_skipped": should_skip_initial,
            "errors": errors,
        }

    async def send_test_notification(
        self,
        *,
        title: str = "飞书通知",
        message: str = "这是一条 Dot Service 飞书通知测试",
        signature: str = "Lark Bridge",
    ) -> dict[str, Any]:
        """Push a test notification to Dot."""
        return await self._send_to_dot(title=title, message=message, signature=signature)

    async def _run(self) -> None:
        # Re-discover chats every 30 minutes in monitor_all mode
        discover_interval = 30 * 60
        last_discover = 0.0
        while not self._stop_event.is_set():
            try:
                now = asyncio.get_event_loop().time()
                if (
                    self.settings.lark_notify_monitor_all
                    and now - last_discover > discover_interval
                ):
                    await self._discover_chats()
                    last_discover = now
                await self.poll_once(notify=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - background task must survive
                self._last_error = str(exc)
                logger.exception("Lark notification poll failed")

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=max(5, self.settings.lark_notify_poll_interval_seconds),
                )
            except asyncio.TimeoutError:
                continue

    async def _discover_chats(self) -> None:
        """Call lark-cli im chats list to auto-discover all chats."""
        cmd = [
            self.settings.lark_notify_cli,
            "im", "chats", "list",
            "--as", self.settings.lark_notify_identity,
            "--format", "json",
            "--page-all",
        ]
        if self.settings.lark_notify_profile:
            cmd.extend(["--profile", self.settings.lark_notify_profile])

        logger.info("Discovering Lark chats: %s", _safe_cmd(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.settings.lark_notify_cli_timeout_seconds,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            logger.warning("Chat discovery timed out")
            return

        if proc.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()
            logger.warning("Chat discovery failed: %s", detail or f"exit {proc.returncode}")
            return

        data = _loads_json(stdout.decode("utf-8", errors="replace").strip())
        items = _extract_chat_list(data)
        self._discovered_chats = [
            {"chat_id": c["chat_id"], "name": c.get("name", "")}
            for c in items
            if c.get("chat_id")
        ]
        self._discovered_at = datetime.now().astimezone().isoformat(
            timespec="seconds"
        )
        logger.info(
            "Discovered %d Lark chats: %s",
            len(self._discovered_chats),
            ", ".join(c["name"] or c["chat_id"] for c in self._discovered_chats),
        )

    async def _poll_source(
        self,
        source_type: str,
        source_id: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        cmd = [
            self.settings.lark_notify_cli,
            "im",
            "+chat-messages-list",
            "--as",
            self.settings.lark_notify_identity,
            "--format",
            "json",
            "--sort",
            "desc",
            "--page-size",
            str(self.settings.lark_notify_page_size),
            "--start",
            start.isoformat(timespec="seconds"),
            "--end",
            end.isoformat(timespec="seconds"),
        ]
        if self.settings.lark_notify_profile:
            cmd.extend(["--profile", self.settings.lark_notify_profile])
        if source_type == "chat":
            cmd.extend(["--chat-id", source_id])
        else:
            cmd.extend(["--user-id", source_id])

        logger.debug("Polling Lark messages: %s", _safe_cmd(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.settings.lark_notify_cli_timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.communicate()
            raise RuntimeError("lark-cli command timed out") from exc

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            detail = stderr_text or stdout_text or f"exit code {proc.returncode}"
            raise RuntimeError(detail)

        data = _loads_json(stdout_text)
        return _extract_messages(data)

    def _normalize_message(
        self,
        raw: dict[str, Any],
        source_type: str,
        source_id: str,
    ) -> Optional[LarkMessage]:
        if raw.get("deleted") is True:
            return None
        message_id = str(raw.get("message_id") or raw.get("id") or "").strip()
        if not message_id:
            return None
        text = _content_to_text(raw.get("content"))
        if not text:
            text = f"[{raw.get('msg_type') or 'message'}]"
        sender = _sender_name(raw.get("sender"))
        return LarkMessage(
            message_id=message_id,
            sender=sender,
            text=text,
            source_type=source_type,
            source_id=source_id,
            created_at=str(raw.get("create_time") or raw.get("created_at") or ""),
            link=raw.get("url") or raw.get("link"),
        )

    def _matches(self, raw: dict[str, Any], message: LarkMessage) -> bool:
        keywords = self.keywords
        mention_ids = self.mention_ids
        if not keywords and not mention_ids:
            return True

        haystack = f"{message.sender}\n{message.text}".casefold()
        if any(keyword.casefold() in haystack for keyword in keywords):
            return True

        mentions = raw.get("mentions") or []
        if isinstance(mentions, list):
            found_ids = {
                str(item.get("id") or item.get("user_id") or item.get("open_id") or "")
                for item in mentions
                if isinstance(item, dict)
            }
            if found_ids.intersection(mention_ids):
                return True
        return False

    async def _send_summary(self, messages: list[LarkMessage]) -> dict[str, Any]:
        max_items = max(1, self.settings.lark_notify_max_messages_per_push)
        selected = messages[-max_items:]

        if len(messages) == 1:
            title = self.settings.lark_notify_dot_title or "飞书通知"
            body = f"{selected[0].sender}: {selected[0].text}"
            signature = _signature_for(selected[0], self.settings.lark_notify_dot_signature)
            link = selected[0].link
        else:
            title = f"飞书 {len(messages)}条"
            body = "\n".join(f"{msg.sender}: {msg.text}" for msg in selected)
            signature = self.settings.lark_notify_dot_signature or "Lark Bridge"
            link = selected[-1].link

        return await self._send_to_dot(
            title=_truncate(title, 12),
            message=_truncate(body, self.settings.lark_notify_max_message_chars),
            signature=_truncate(signature, 24),
            link=link,
        )

    async def _send_to_dot(
        self,
        *,
        title: str,
        message: str,
        signature: str,
        link: Optional[str] = None,
    ) -> dict[str, Any]:
        device_id = self._device_id_provider()
        try:
            return await self._dot_client_factory().send_text(
                device_id,
                refresh_now=True,
                title=title,
                message=message,
                signature=signature,
                link=link,
            )
        except DotClientError:
            raise

    @property
    def _state_file(self) -> Path:
        return Path(self.settings.lark_notify_state_file)

    def _load_state(self) -> None:
        self._state_loaded = True
        path = self._state_file
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text("utf-8"))
            self._seen_ids = set(data.get("seen_message_ids") or [])
            self._notified_count = int(data.get("notified_count") or 0)
            self._matched_count = int(data.get("matched_count") or 0)
            self._skipped_count = int(data.get("skipped_count") or 0)
            self._first_poll = False
        except Exception:  # noqa: BLE001
            logger.warning("Failed to load Lark notification state: %s", path)

    def _save_state(self) -> None:
        path = self._state_file
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "seen_message_ids": sorted(self._seen_ids),
                "notified_count": self._notified_count,
                "matched_count": self._matched_count,
                "skipped_count": self._skipped_count,
                "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
        except Exception:  # noqa: BLE001
            logger.warning("Failed to save Lark notification state: %s", path)

    def _trim_seen_ids(self) -> None:
        max_seen = max(100, self.settings.lark_notify_max_seen_messages)
        if len(self._seen_ids) <= max_seen:
            return
        # IDs are opaque; deterministic trimming is enough for bounded local state.
        self._seen_ids = set(sorted(self._seen_ids)[-max_seen:])


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _safe_cmd(cmd: list[str]) -> str:
    return " ".join(cmd)


def _loads_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Be tolerant if a wrapper prints a notice around JSON.
        first_obj = text.find("{")
        first_arr = text.find("[")
        starts = [idx for idx in (first_obj, first_arr) if idx >= 0]
        if not starts:
            raise
        start = min(starts)
        last_obj = text.rfind("}")
        last_arr = text.rfind("]")
        end = max(last_obj, last_arr)
        return json.loads(text[start : end + 1])


def _extract_messages(data: Any) -> list[dict[str, Any]]:
    """Extract message list from lark-cli +chat-messages-list output."""
    if isinstance(data, dict):
        messages = data.get("messages")
        if isinstance(messages, list):
            return [msg for msg in messages if isinstance(msg, dict)]
        for key in ("data", "result"):
            nested = data.get(key)
            if isinstance(nested, dict):
                messages = nested.get("messages") or nested.get("items")
                if isinstance(messages, list):
                    return [msg for msg in messages if isinstance(msg, dict)]
    if isinstance(data, list):
        return [msg for msg in data if isinstance(msg, dict)]
    return []


def _extract_chat_list(data: Any) -> list[dict[str, Any]]:
    """Extract chat list from lark-cli im chats list output."""
    if isinstance(data, dict):
        items = None
        # {"data": {"items": [...]}}
        nested = data.get("data")
        if isinstance(nested, dict):
            items = nested.get("items")
        # {"items": [...]}
        if items is None:
            items = data.get("items")
        if isinstance(items, list):
            return [c for c in items if isinstance(c, dict) and c.get("chat_id")]
    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict) and c.get("chat_id")]
    return []


def _message_sort_key(raw: dict[str, Any]) -> str:
    return str(raw.get("create_time") or raw.get("created_at") or raw.get("message_id") or "")


def _sender_name(sender: Any) -> str:
    if isinstance(sender, dict):
        return str(
            sender.get("name")
            or sender.get("display_name")
            or sender.get("sender_id")
            or sender.get("id")
            or "飞书"
        )
    if isinstance(sender, str) and sender:
        return sender
    return "飞书"


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, dict):
        for key in ("text", "title", "content", "message"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return _collapse(value)
        return _collapse(json.dumps(content, ensure_ascii=False))
    if isinstance(content, list):
        return _collapse(" ".join(_content_to_text(item) for item in content))
    text = str(content)
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return _content_to_text(json.loads(stripped))
        except json.JSONDecodeError:
            pass
    return _collapse(stripped)


def _signature_for(message: LarkMessage, fallback: str) -> str:
    created = message.created_at or ""
    if created:
        return created[-5:] if len(created) >= 5 else created
    if fallback:
        return fallback
    return "Lark Bridge"


def _collapse(text: str) -> str:
    return " ".join(text.replace("\r", " ").replace("\n", " ").split())


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)] + "…"
