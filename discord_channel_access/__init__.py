"""Hermes user plugin for Discord channel/message access."""

from __future__ import annotations

import os

from . import schemas, tools

REQUIRES_ENV = ["DISCORD_BOT_TOKEN"]


def register(ctx):
    """Register Discord history tools with Hermes."""
    if not str(os.getenv("DISCORD_BOT_TOKEN", "")).strip():
        raise RuntimeError("DISCORD_BOT_TOKEN is required for the discord_channel_access plugin")

    ctx.register_tool(
        name="discord_list_channels",
        toolset="discord_channel_access",
        schema=schemas.LIST_CHANNELS,
        handler=tools.discord_list_channels,
        requires_env=["DISCORD_BOT_TOKEN"],
        description=schemas.LIST_CHANNELS["description"],
        emoji="💬",
    )
    ctx.register_tool(
        name="discord_read_messages",
        toolset="discord_channel_access",
        schema=schemas.READ_MESSAGES,
        handler=tools.discord_read_messages,
        requires_env=["DISCORD_BOT_TOKEN"],
        description=schemas.READ_MESSAGES["description"],
        emoji="📖",
    )
    ctx.register_tool(
        name="discord_download_messages",
        toolset="discord_channel_access",
        schema=schemas.DOWNLOAD_MESSAGES,
        handler=tools.discord_download_messages,
        requires_env=["DISCORD_BOT_TOKEN"],
        description=schemas.DOWNLOAD_MESSAGES["description"],
        emoji="📦",
    )
