import json
from pathlib import Path

import pytest

from discord_channel_access import register
from discord_channel_access import tools as plugin_tools


class DummyContext:
    def __init__(self):
        self.tools = []

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)


class FakeResponse:
    def __init__(self, status_code, payload=None, text="", headers=None, content=b""):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = headers or {"content-type": "application/json"}
        self.content = content

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_register_requires_discord_bot_token(monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="DISCORD_BOT_TOKEN"):
        register(DummyContext())


def test_register_registers_three_tools(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    ctx = DummyContext()

    register(ctx)

    assert [tool["name"] for tool in ctx.tools] == [
        "discord_list_channels",
        "discord_read_messages",
        "discord_download_messages",
    ]


def test_request_json_retries_on_rate_limit():
    sleeps = []
    responses = [
        FakeResponse(429, payload={"retry_after": 0.25}),
        FakeResponse(200, payload={"ok": True}),
    ]

    class Session:
        def __init__(self):
            self.calls = []

        def request(self, method, url, headers=None, params=None, timeout=None, stream=False):
            self.calls.append({
                "method": method,
                "url": url,
                "params": params,
                "stream": stream,
            })
            return responses.pop(0)

    session = Session()
    client = plugin_tools.DiscordRESTClient("test-token", session=session, sleep_fn=sleeps.append)

    payload = client._request_json("GET", "/users/@me")

    assert payload == {"ok": True}
    assert sleeps == [0.25]
    assert len(session.calls) == 2


def test_list_channels_filters_inaccessible_channels(monkeypatch):
    client = plugin_tools.DiscordRESTClient("test-token", session=object(), sleep_fn=lambda *_: None)

    def fake_request_json(method, path, params=None):
        assert method == "GET"
        if path == "/users/@me/guilds":
            return [{"id": "g1", "name": "Guild One"}]
        if path == "/guilds/g1/channels":
            return [
                {"id": "c-text", "guild_id": "g1", "name": "general", "type": 0},
                {"id": "c-news", "guild_id": "g1", "name": "announcements", "type": 5},
                {"id": "c-voice", "guild_id": "g1", "name": "voice", "type": 2},
            ]
        if path == "/guilds/g1/threads/active":
            return {
                "threads": [
                    {
                        "id": "t-1",
                        "guild_id": "g1",
                        "parent_id": "c-text",
                        "name": "incident-thread",
                        "type": 11,
                    }
                ]
            }
        if path == "/channels/c-text/messages":
            return [{"id": "m1"}]
        if path == "/channels/t-1/messages":
            return []
        if path == "/channels/c-news/messages":
            raise plugin_tools.DiscordRequestError(403, "Forbidden")
        raise AssertionError(f"Unexpected request: {path}")

    monkeypatch.setattr(client, "_request_json", fake_request_json)

    channels = client.list_channels()

    assert [channel["id"] for channel in channels] == ["c-text", "t-1"]
    assert channels[0]["guild_name"] == "Guild One"
    assert channels[1]["parent_id"] == "c-text"


def test_read_messages_returns_chronological_normalized_messages(monkeypatch):
    client = plugin_tools.DiscordRESTClient("test-token", session=object(), sleep_fn=lambda *_: None)

    def fake_request_json(method, path, params=None):
        assert method == "GET"
        if path == "/channels/c-1":
            return {"id": "c-1", "guild_id": "g1", "name": "general", "type": 0}
        if path == "/channels/c-1/messages":
            return [
                {
                    "id": "m-2",
                    "content": "second",
                    "timestamp": "2026-03-19T16:01:00.000000+00:00",
                    "author": {"id": "u-2", "username": "bob", "global_name": "Bob"},
                    "attachments": [
                        {
                            "id": "a-1",
                            "filename": "note.txt",
                            "url": "https://cdn.example/note.txt",
                            "size": 12,
                            "content_type": "text/plain",
                        }
                    ],
                    "embeds": [],
                },
                {
                    "id": "m-1",
                    "content": "first",
                    "timestamp": "2026-03-19T16:00:00.000000+00:00",
                    "author": {"id": "u-1", "username": "alice", "global_name": None},
                    "attachments": [],
                    "embeds": [],
                },
            ]
        raise AssertionError(f"Unexpected request: {path}")

    monkeypatch.setattr(client, "_request_json", fake_request_json)

    result = client.read_messages("c-1", limit=2)

    assert result["channel"]["id"] == "c-1"
    assert [message["id"] for message in result["messages"]] == ["m-1", "m-2"]
    assert result["messages"][0]["author"]["username"] == "alice"
    assert result["messages"][1]["attachments"][0]["filename"] == "note.txt"


def test_export_history_writes_channel_transcript_and_manifest(tmp_path):
    class FakeClient:
        def get_channel(self, channel_id):
            assert channel_id == "c-1"
            return {"id": "c-1", "guild_id": "g1", "guild_name": "Guild One", "name": "general", "type": 0}

        def iter_messages(self, channel_id, before=None, after=None, max_messages=None):
            assert channel_id == "c-1"
            return iter([
                {
                    "id": "m-1",
                    "timestamp": "2026-03-19T16:00:00Z",
                    "content": "hello",
                    "author": {"id": "u-1", "username": "alice", "display_name": "Alice"},
                    "attachments": [
                        {
                            "id": "a-1",
                            "filename": "hello.txt",
                            "url": "https://cdn.example/hello.txt",
                            "content_type": "text/plain",
                            "size": 5,
                        }
                    ],
                    "embeds": [],
                },
                {
                    "id": "m-2",
                    "timestamp": "2026-03-19T16:01:00Z",
                    "content": "world",
                    "author": {"id": "u-2", "username": "bob", "display_name": "Bob"},
                    "attachments": [],
                    "embeds": [],
                },
            ])

        def download_attachment(self, url, destination):
            destination.write_bytes(b"hello")
            return destination

    result = plugin_tools.export_history(
        FakeClient(),
        scope="channel",
        channel_id="c-1",
        output_dir=tmp_path,
        export_format="jsonl",
        download_attachments=True,
    )

    manifest_path = Path(result["manifest_path"])
    transcript_path = Path(result["channels"][0]["transcript_path"])
    attachment_path = Path(result["channels"][0]["attachments"][0]["local_path"])

    assert manifest_path.exists()
    assert transcript_path.exists()
    assert attachment_path.exists()

    lines = transcript_path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["id"] == "m-1"

    manifest = json.loads(manifest_path.read_text())
    assert manifest["scope"] == "channel"
    assert manifest["total_messages"] == 2


def test_export_history_all_scope_writes_one_transcript_per_channel(tmp_path):
    class FakeClient:
        def list_channels(self, guild_id=None, include_archived_threads=False):
            assert guild_id is None
            return [
                {"id": "c-1", "guild_id": "g1", "guild_name": "Guild One", "name": "general", "type": 0},
                {"id": "c-2", "guild_id": "g1", "guild_name": "Guild One", "name": "random", "type": 0},
            ]

        def get_channel(self, channel_id):
            return {"id": channel_id, "guild_id": "g1", "guild_name": "Guild One", "name": channel_id, "type": 0}

        def iter_messages(self, channel_id, before=None, after=None, max_messages=None):
            return iter([
                {
                    "id": f"{channel_id}-m1",
                    "timestamp": "2026-03-19T16:00:00Z",
                    "content": f"message from {channel_id}",
                    "author": {"id": "u-1", "username": "alice", "display_name": "Alice"},
                    "attachments": [],
                    "embeds": [],
                }
            ])

        def download_attachment(self, url, destination):
            raise AssertionError("Attachments should not be downloaded in this test")

    result = plugin_tools.export_history(
        FakeClient(),
        scope="all",
        output_dir=tmp_path,
        export_format="json",
        download_attachments=False,
    )

    manifest = json.loads(Path(result["manifest_path"]).read_text())
    transcript_paths = [Path(channel["transcript_path"]) for channel in result["channels"]]

    assert manifest["scope"] == "all"
    assert manifest["channels_exported"] == 2
    assert all(path.exists() for path in transcript_paths)
