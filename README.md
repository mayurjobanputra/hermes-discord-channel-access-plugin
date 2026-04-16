# Hermes Discord Channel Access Plugin

Externalized user plugin for Hermes that exposes Discord history tools without patching Hermes core:

- `discord_list_channels` — list accessible channels and threads
- `discord_read_messages` — read messages from a channel/thread
- `discord_download_messages` — bulk export history to local files
- `discord_send_message` — post messages and file attachments
- `discord_search_messages` — search message history by keyword and filters

This keeps `~/.hermes/hermes-agent` clean and upgradeable while still letting Hermes read/export Discord history and post replies where the configured bot token has permission.

## Repository layout

```text
~/projects/hermes-discord-channel-access-plugin/
├── README.md
├── pyproject.toml
├── tests/
└── discord_channel_access/
    ├── plugin.yaml
    ├── __init__.py
    ├── schemas.py
    └── tools.py
```

## Runtime install

Hermes discovers user plugins from `~/.hermes/plugins/<name>/`.

Install this repo into Hermes by copying:

```bash
mkdir -p ~/.hermes/plugins
cp -r ~/projects/hermes-discord-channel-access-plugin/discord_channel_access ~/.hermes/plugins/
```

No Hermes source changes are required.

## Requirements

- Hermes repo available locally, usually at `~/.hermes/hermes-agent`
- `DISCORD_BOT_TOKEN` available to Hermes
- Bot/app has permission to read the target channels and message history
- For posting replies: `Send Messages`, plus `Attach Files` if you want audio/file replies
- For threaded replies: `Send Messages in Threads`

## Test

From the Hermes repo venv:

```bash
cd ~/projects/hermes-discord-channel-access-plugin
~/.hermes/hermes-agent/venv/bin/pytest tests -q
```

If your Hermes repo lives somewhere else, set `HERMES_AGENT_REPO=/path/to/hermes-agent` before running tests.

## Notes

- This plugin is for collecting raw Discord review material and exports.
- It does **not** replace Hermes' voice bridge/runtime behavior.
- Raw audio should remain primary; transcripts are secondary.
