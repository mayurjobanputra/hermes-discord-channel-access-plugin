# Hermes Discord Channel Access Plugin

Externalized user plugin for Hermes that exposes three Discord history tools without patching Hermes core:

- `discord_list_channels`
- `discord_read_messages`
- `discord_download_messages`

This keeps `~/.hermes/hermes-agent` clean and upgradeable while still letting Hermes read/export Discord history where the configured bot token has permission.

## Repository layout

```text
~/Source/MormonTranshumanistAssociation/hermes-discord-channel-access-plugin/
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

Install this repo into Hermes with a symlink:

```bash
mkdir -p ~/.hermes/plugins
ln -sfn ~/Source/MormonTranshumanistAssociation/hermes-discord-channel-access-plugin/discord_channel_access   ~/.hermes/plugins/discord_channel_access
```

No Hermes source changes are required.

## Requirements

- Hermes repo available locally, usually at `~/.hermes/hermes-agent`
- `DISCORD_BOT_TOKEN` available to Hermes
- Bot/app has permission to read the target channels and message history

## Test

From the Hermes repo venv:

```bash
cd ~/Source/MormonTranshumanistAssociation/hermes-discord-channel-access-plugin
~/.hermes/hermes-agent/venv/bin/pytest tests -q
```

If your Hermes repo lives somewhere else, set `HERMES_AGENT_REPO=/path/to/hermes-agent` before running tests.

## Notes

- This plugin is for collecting raw Discord review material and exports.
- It does **not** replace Hermes' voice bridge/runtime behavior.
- Raw audio should remain primary; transcripts are secondary.
