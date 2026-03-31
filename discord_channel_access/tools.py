"""Discord channel access plugin tools."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

import requests

from hermes_cli.config import get_hermes_home

DISCORD_API_BASE = "https://discord.com/api/v10"
TEXT_CHANNEL_TYPES = {0, 5}
THREAD_CHANNEL_TYPES = {10, 11, 12}
ARCHIVABLE_PARENT_TYPES = {0, 5, 15, 16}
MESSAGEABLE_CHANNEL_TYPES = TEXT_CHANNEL_TYPES | THREAD_CHANNEL_TYPES


class DiscordRequestError(RuntimeError):
    """Raised when the Discord API returns a non-success response."""

    def __init__(self, status_code: int, message: str, payload: Any | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class DiscordRESTClient:
    """Small synchronous Discord REST wrapper for history export tasks."""

    def __init__(
        self,
        token: str,
        *,
        session: requests.Session | Any | None = None,
        sleep_fn=time.sleep,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self.token = (token or "").strip()
        self.session = session or requests.Session()
        self.sleep_fn = sleep_fn
        self.timeout = timeout
        self.max_retries = max_retries

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        stream: bool = False,
        url: str | None = None,
        json_body: dict | None = None,
        data: dict | None = None,
        files: Sequence[tuple[str, tuple[str, Any, str]]] | None = None,
    ):
        target_url = url or f"{DISCORD_API_BASE}{path}"
        attempts = 0
        headers = {"Authorization": f"Bot {self.token}"}

        while True:
            request_kwargs = {
                "headers": headers,
                "params": params,
                "timeout": self.timeout,
                "stream": stream,
            }
            if json_body is not None:
                request_kwargs["json"] = json_body
            if data is not None:
                request_kwargs["data"] = data
            if files is not None:
                request_kwargs["files"] = files

            response = self.session.request(method, target_url, **request_kwargs)
            if response.status_code == 429 and attempts < self.max_retries:
                retry_after = 1.0
                try:
                    payload = response.json() or {}
                    retry_after = float(payload.get("retry_after", retry_after))
                except Exception:
                    pass
                self.sleep_fn(retry_after)
                attempts += 1
                continue

            if response.status_code >= 400:
                payload = None
                message = getattr(response, "text", "") or f"Discord API error {response.status_code}"
                try:
                    payload = response.json()
                    if isinstance(payload, dict) and payload.get("message"):
                        message = str(payload["message"])
                except Exception:
                    payload = None
                raise DiscordRequestError(response.status_code, message, payload=payload)

            return response

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        data: dict | None = None,
        files: Sequence[tuple[str, tuple[str, Any, str]]] | None = None,
    ):
        response = self._request(method, path, params=params, json_body=json_body, data=data, files=files)
        try:
            return response.json()
        except Exception as exc:
            raise DiscordRequestError(response.status_code, f"Invalid JSON response: {exc}") from exc

    def list_guilds(self) -> list[dict]:
        payload = self._request_json("GET", "/users/@me/guilds")
        return payload if isinstance(payload, list) else []

    def get_channel(self, channel_id: str) -> dict:
        channel = self._request_json("GET", f"/channels/{channel_id}")
        guild_name = None
        guild_id = str(channel.get("guild_id")) if channel.get("guild_id") is not None else None
        if guild_id:
            try:
                for guild in self.list_guilds():
                    if str(guild.get("id")) == guild_id:
                        guild_name = guild.get("name")
                        break
            except Exception:
                guild_name = None
        return _decorate_channel(channel, guild_name=guild_name)

    def list_channels(
        self,
        guild_id: str | None = None,
        include_archived_threads: bool = False,
    ) -> list[dict]:
        guilds = self.list_guilds()
        if guild_id:
            guilds = [g for g in guilds if str(g.get("id")) == str(guild_id)]
            if not guilds:
                guilds = [{"id": str(guild_id), "name": str(guild_id)}]

        accessible: list[dict] = []
        for guild in guilds:
            gid = str(guild.get("id"))
            gname = guild.get("name") or gid
            candidates = self._list_candidate_channels(gid, gname, include_archived_threads=include_archived_threads)
            for channel in candidates:
                if self._channel_has_history_access(channel["id"]):
                    accessible.append(channel)

        accessible.sort(key=lambda item: ((item.get("guild_name") or ""), item.get("name") or "", item.get("id") or ""))
        return accessible

    def _list_candidate_channels(
        self,
        guild_id: str,
        guild_name: str,
        *,
        include_archived_threads: bool = False,
    ) -> list[dict]:
        payload = self._request_json("GET", f"/guilds/{guild_id}/channels")
        channels = payload if isinstance(payload, list) else []
        candidates = [
            _decorate_channel(channel, guild_name=guild_name)
            for channel in channels
            if int(channel.get("type", -1)) in TEXT_CHANNEL_TYPES
        ]

        try:
            threads_payload = self._request_json("GET", f"/guilds/{guild_id}/threads/active")
            for thread in threads_payload.get("threads", []) if isinstance(threads_payload, dict) else []:
                if int(thread.get("type", -1)) in THREAD_CHANNEL_TYPES:
                    candidates.append(_decorate_channel(thread, guild_name=guild_name))
        except DiscordRequestError as exc:
            if exc.status_code not in (403, 404):
                raise

        if include_archived_threads:
            parent_channels = [
                _decorate_channel(channel, guild_name=guild_name)
                for channel in channels
                if int(channel.get("type", -1)) in ARCHIVABLE_PARENT_TYPES
            ]
            for parent in parent_channels:
                candidates.extend(self._list_archived_threads(parent, guild_name=guild_name))

        deduped: dict[str, dict] = {}
        for channel in candidates:
            deduped[channel["id"]] = channel
        return list(deduped.values())

    def _list_archived_threads(self, parent_channel: dict, *, guild_name: str) -> list[dict]:
        results: list[dict] = []
        parent_id = parent_channel["id"]
        endpoints = [
            f"/channels/{parent_id}/threads/archived/public",
            f"/channels/{parent_id}/users/@me/threads/archived/private",
        ]
        for endpoint in endpoints:
            try:
                payload = self._request_json("GET", endpoint, params={"limit": 100})
            except DiscordRequestError as exc:
                if exc.status_code in (403, 404):
                    continue
                raise
            threads = payload.get("threads", []) if isinstance(payload, dict) else []
            for thread in threads:
                if int(thread.get("type", -1)) in THREAD_CHANNEL_TYPES:
                    results.append(_decorate_channel(thread, guild_name=guild_name))
        return results

    def _channel_has_history_access(self, channel_id: str) -> bool:
        try:
            self._request_json("GET", f"/channels/{channel_id}/messages", params={"limit": 1})
            return True
        except DiscordRequestError as exc:
            if exc.status_code in (403, 404):
                return False
            raise

    def read_messages(
        self,
        channel_id: str,
        *,
        limit: int = 50,
        before: str | None = None,
        after: str | None = None,
    ) -> dict:
        channel = self.get_channel(channel_id)
        messages = list(self.iter_messages(channel_id, before=before, after=after, max_messages=limit))
        return {"channel": channel, "messages": messages, "count": len(messages)}

    def create_message(
        self,
        channel_id: str,
        *,
        content: str | None = None,
        reply_to_message_id: str | None = None,
        attachment_paths: Sequence[str | Path] | None = None,
    ) -> dict:
        cleaned_content = (content or "").strip()
        paths = [Path(path).expanduser() for path in (attachment_paths or [])]
        if not cleaned_content and not paths:
            raise ValueError("content or attachment_paths is required")

        payload: dict[str, Any] = {}
        if cleaned_content:
            payload["content"] = cleaned_content
        if reply_to_message_id:
            payload["message_reference"] = {"message_id": str(reply_to_message_id)}

        if not paths:
            message = self._request_json("POST", f"/channels/{channel_id}/messages", json_body=payload)
            return _normalize_message(message)

        files: list[tuple[str, tuple[str, Any, str]]] = []
        handles: list[Any] = []
        try:
            for index, path in enumerate(paths):
                if not path.is_file():
                    raise FileNotFoundError(f"Attachment not found: {path}")
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                handle = path.open("rb")
                handles.append(handle)
                files.append((f"files[{index}]", (path.name, handle, content_type)))

            message = self._request_json(
                "POST",
                f"/channels/{channel_id}/messages",
                data={"payload_json": json.dumps(payload)},
                files=files,
            )
            return _normalize_message(message)
        finally:
            for handle in handles:
                handle.close()

    def iter_messages(
        self,
        channel_id: str,
        *,
        before: str | None = None,
        after: str | None = None,
        max_messages: int | None = None,
    ) -> Iterator[dict]:
        remaining = max_messages if max_messages and max_messages > 0 else None
        before_cursor = before
        after_int = _snowflake_int(after) if after else None
        collected: list[dict] = []
        stop = False

        while not stop:
            page_limit = min(100, remaining) if remaining else 100
            params = {"limit": page_limit}
            if before_cursor:
                params["before"] = before_cursor

            page = self._request_json("GET", f"/channels/{channel_id}/messages", params=params)
            if not page:
                break

            for raw in page:
                message_id = str(raw.get("id"))
                if after_int is not None and _snowflake_int(message_id) <= after_int:
                    stop = True
                    break
                collected.append(_normalize_message(raw))
                if remaining is not None:
                    remaining -= 1
                    if remaining <= 0:
                        stop = True
                        break

            if stop:
                break
            if len(page) < page_limit:
                break
            before_cursor = str(page[-1].get("id"))

        collected.reverse()
        yield from collected

    def download_attachment(self, url: str, destination: Path) -> Path:
        response = self._request("GET", "", url=url, stream=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return destination


def _token() -> str:
    return str(os.getenv("DISCORD_BOT_TOKEN", "")).strip()


def _build_client() -> DiscordRESTClient:
    token = _token()
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required")
    return DiscordRESTClient(token)


def discord_list_channels(args: dict, **kwargs) -> str:
    try:
        client = _build_client()
        channels = client.list_channels(
            guild_id=args.get("guild_id"),
            include_archived_threads=bool(args.get("include_archived_threads", False)),
        )
        return json.dumps({"count": len(channels), "channels": channels})
    except Exception as exc:
        return json.dumps({"error": f"Failed to list Discord channels: {exc}"})


def discord_read_messages(args: dict, **kwargs) -> str:
    try:
        channel_id = str(args.get("channel_id", "")).strip()
        if not channel_id:
            return json.dumps({"error": "channel_id is required"})
        limit = int(args.get("limit", 50) or 50)
        client = _build_client()
        result = client.read_messages(
            channel_id,
            limit=max(1, min(limit, 500)),
            before=args.get("before"),
            after=args.get("after"),
        )
        return json.dumps(result)
    except Exception as exc:
        return json.dumps({"error": f"Failed to read Discord messages: {exc}"})


def discord_download_messages(args: dict, **kwargs) -> str:
    try:
        scope = str(args.get("scope") or ("channel" if args.get("channel_id") else "all")).strip().lower()
        client = _build_client()
        result = export_history(
            client,
            scope=scope,
            channel_id=args.get("channel_id"),
            guild_id=args.get("guild_id"),
            output_dir=args.get("output_dir"),
            export_format=str(args.get("export_format", "jsonl") or "jsonl").lower(),
            download_attachments=bool(args.get("download_attachments", False)),
            include_archived_threads=bool(args.get("include_archived_threads", False)),
            max_messages_per_channel=int(args.get("max_messages_per_channel", 0) or 0),
            before=args.get("before"),
            after=args.get("after"),
        )
        return json.dumps(result)
    except Exception as exc:
        return json.dumps({"error": f"Failed to export Discord messages: {exc}"})


def discord_send_message(args: dict, **kwargs) -> str:
    try:
        channel_id = str(args.get("channel_id", "")).strip()
        if not channel_id:
            return json.dumps({"error": "channel_id is required"})
        attachment_paths = _normalize_attachment_paths(args.get("attachment_paths"))
        client = _build_client()
        message = client.create_message(
            channel_id,
            content=args.get("content"),
            reply_to_message_id=args.get("reply_to_message_id"),
            attachment_paths=attachment_paths,
        )
        return json.dumps({"success": True, "message": message})
    except Exception as exc:
        return json.dumps({"error": f"Failed to send Discord message: {exc}"})


def _normalize_attachment_paths(raw: Any) -> list[str]:
    if raw in (None, ""):
        return []
    if isinstance(raw, str):
        value = raw.strip()
        return [value] if value else []
    return [str(item).strip() for item in raw if str(item).strip()]


def export_history(
    client: Any,
    *,
    scope: str,
    channel_id: str | None = None,
    guild_id: str | None = None,
    output_dir: str | Path | None = None,
    export_format: str = "jsonl",
    download_attachments: bool = False,
    include_archived_threads: bool = False,
    max_messages_per_channel: int = 0,
    before: str | None = None,
    after: str | None = None,
) -> dict:
    export_format = export_format.lower().strip()
    if export_format not in {"jsonl", "json", "markdown"}:
        raise ValueError("export_format must be one of: jsonl, json, markdown")

    scope = scope.lower().strip()
    out_dir = Path(output_dir) if output_dir else _default_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    if scope == "channel":
        if not channel_id:
            raise ValueError("channel_id is required when scope=channel")
        channels = [client.get_channel(str(channel_id))]
    elif scope == "guild":
        if not guild_id:
            raise ValueError("guild_id is required when scope=guild")
        channels = client.list_channels(guild_id=str(guild_id), include_archived_threads=include_archived_threads)
    elif scope == "all":
        channels = client.list_channels(include_archived_threads=include_archived_threads)
    else:
        raise ValueError("scope must be one of: channel, guild, all")

    channel_results: list[dict] = []
    total_messages = 0
    for channel in channels:
        channel_slug = _slugify(f"{channel.get('guild_name', 'discord')}-{channel.get('name', channel['id'])}-{channel['id']}")
        channel_dir = out_dir / channel_slug
        channel_dir.mkdir(parents=True, exist_ok=True)

        messages = list(
            client.iter_messages(
                str(channel["id"]),
                before=before,
                after=after,
                max_messages=max_messages_per_channel or None,
            )
        )
        attachment_records: list[dict] = []
        if download_attachments:
            attachment_records = _download_message_attachments(client, messages, channel_dir / "attachments")

        transcript_path = channel_dir / f"messages.{_extension_for(export_format)}"
        _write_transcript(transcript_path, messages, export_format)

        total_messages += len(messages)
        channel_results.append(
            {
                "channel": channel,
                "message_count": len(messages),
                "transcript_path": str(transcript_path),
                "attachments": attachment_records,
            }
        )

    manifest = {
        "scope": scope,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(out_dir),
        "channels_exported": len(channel_results),
        "total_messages": total_messages,
        "channels": [
            {
                "channel": result["channel"],
                "message_count": result["message_count"],
                "transcript_path": result["transcript_path"],
                "attachment_count": len(result["attachments"]),
            }
            for result in channel_results
        ],
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    return {
        "success": True,
        "scope": scope,
        "output_dir": str(out_dir),
        "manifest_path": str(manifest_path),
        "channels_exported": len(channel_results),
        "total_messages": total_messages,
        "channels": channel_results,
    }


def _download_message_attachments(client: Any, messages: list[dict], attachments_dir: Path) -> list[dict]:
    records: list[dict] = []
    attachments_dir.mkdir(parents=True, exist_ok=True)
    for message in messages:
        for attachment in message.get("attachments", []):
            filename = _safe_filename(f"{message['id']}-{attachment.get('filename', attachment.get('id', 'attachment'))}")
            local_path = attachments_dir / filename
            client.download_attachment(attachment["url"], local_path)
            attachment_record = dict(attachment)
            attachment_record["local_path"] = str(local_path)
            records.append(attachment_record)
    return records


def _write_transcript(path: Path, messages: list[dict], export_format: str) -> None:
    if export_format == "jsonl":
        path.write_text("\n".join(json.dumps(message, ensure_ascii=False) for message in messages) + ("\n" if messages else ""))
        return
    if export_format == "json":
        path.write_text(json.dumps(messages, indent=2, ensure_ascii=False))
        return

    lines = [f"# Discord export ({len(messages)} messages)", ""]
    for message in messages:
        author = (
            message.get("author", {}).get("display_name")
            or message.get("author", {}).get("username")
            or "unknown"
        )
        timestamp = message.get("timestamp", "")
        lines.append(f"## {author} — {timestamp}")
        lines.append("")
        lines.append(message.get("content", ""))
        if message.get("attachments"):
            lines.append("")
            lines.append("Attachments:")
            for attachment in message["attachments"]:
                lines.append(f"- {attachment.get('filename')} — {attachment.get('url')}")
        lines.append("")
    path.write_text("\n".join(lines))


def _decorate_channel(channel: dict, *, guild_name: str | None = None) -> dict:
    return {
        "id": str(channel.get("id")),
        "guild_id": str(channel.get("guild_id")) if channel.get("guild_id") is not None else None,
        "guild_name": guild_name,
        "name": channel.get("name") or str(channel.get("id")),
        "type": int(channel.get("type", -1)) if channel.get("type") is not None else None,
        "parent_id": str(channel.get("parent_id")) if channel.get("parent_id") is not None else None,
        "topic": channel.get("topic"),
        "archived": bool(((channel.get("thread_metadata") or {}).get("archived")) if isinstance(channel.get("thread_metadata"), dict) else False),
    }


def _normalize_message(message: dict) -> dict:
    author = message.get("author") or {}
    return {
        "id": str(message.get("id")),
        "timestamp": message.get("timestamp"),
        "edited_timestamp": message.get("edited_timestamp"),
        "content": message.get("content") or "",
        "author": {
            "id": str(author.get("id")) if author.get("id") is not None else None,
            "username": author.get("username"),
            "display_name": author.get("global_name") or author.get("display_name") or author.get("username"),
        },
        "attachments": [
            {
                "id": str(attachment.get("id")) if attachment.get("id") is not None else None,
                "filename": attachment.get("filename"),
                "url": attachment.get("url"),
                "content_type": attachment.get("content_type"),
                "size": attachment.get("size"),
            }
            for attachment in (message.get("attachments") or [])
        ],
        "embeds": [
            {
                "type": embed.get("type"),
                "title": embed.get("title"),
                "description": embed.get("description"),
                "url": embed.get("url"),
            }
            for embed in (message.get("embeds") or [])
        ],
    }


def _default_output_dir() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return get_hermes_home() / "downloads" / "discord-history" / timestamp


def _extension_for(export_format: str) -> str:
    return {"jsonl": "jsonl", "json": "json", "markdown": "md"}[export_format]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return slug or "discord-export"


def _safe_filename(value: str) -> str:
    return _slugify(value)


def _snowflake_int(value: str | None) -> int:
    if value is None:
        return 0
    try:
        return int(str(value))
    except Exception:
        return 0
