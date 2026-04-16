"""Tool schemas for the Discord channel access plugin."""

LIST_CHANNELS = {
    "name": "discord_list_channels",
    "description": (
        "List Discord text channels and threads that the configured bot token "
        "can read message history from. Use this before reading or exporting messages."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "guild_id": {
                "type": "string",
                "description": "Optional Discord guild/server ID to limit the results to one server.",
            },
            "include_archived_threads": {
                "type": "boolean",
                "description": (
                    "If true, also attempt archived thread discovery. This costs extra API calls "
                    "and may still miss some archived threads depending on Discord permissions."
                ),
                "default": False,
            },
        },
        "additionalProperties": False,
    },
}


READ_MESSAGES = {
    "name": "discord_read_messages",
    "description": (
        "Read recent messages from a Discord channel or thread that the configured bot token can access."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "channel_id": {
                "type": "string",
                "description": "Discord channel or thread ID to read from.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of messages to return.",
                "default": 50,
                "minimum": 1,
                "maximum": 500,
            },
            "before": {
                "type": "string",
                "description": "Optional Discord message ID. Only return messages before this ID.",
            },
            "after": {
                "type": "string",
                "description": "Optional Discord message ID. Only return messages after this ID.",
            },
        },
        "required": ["channel_id"],
        "additionalProperties": False,
    },
}


DOWNLOAD_MESSAGES = {
    "name": "discord_download_messages",
    "description": (
        "Export Discord message history to local files for one channel, one guild, or all accessible channels everywhere. "
        "Can optionally download attachments too."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["channel", "guild", "all"],
                "description": "Whether to export one channel, all channels in one guild, or all accessible channels everywhere.",
                "default": "all",
            },
            "channel_id": {
                "type": "string",
                "description": "Required when scope=channel. Discord channel or thread ID to export.",
            },
            "guild_id": {
                "type": "string",
                "description": "Required when scope=guild. Discord guild/server ID to export from.",
            },
            "export_format": {
                "type": "string",
                "enum": ["jsonl", "json", "markdown"],
                "description": "Transcript output format for each exported channel.",
                "default": "jsonl",
            },
            "download_attachments": {
                "type": "boolean",
                "description": "If true, also download attachment files to the export directory.",
                "default": False,
            },
            "output_dir": {
                "type": "string",
                "description": "Optional local directory to write into. Defaults to ~/.hermes/downloads/discord-history/<timestamp>/.",
            },
            "include_archived_threads": {
                "type": "boolean",
                "description": "Attempt archived thread discovery when exporting guild/all scope.",
                "default": False,
            },
            "max_messages_per_channel": {
                "type": "integer",
                "description": "Optional per-channel cap. Omit or use 0 for no cap.",
                "default": 0,
                "minimum": 0,
            },
            "before": {
                "type": "string",
                "description": "Optional Discord message ID. Only export messages before this ID.",
            },
            "after": {
                "type": "string",
                "description": "Optional Discord message ID. Only export messages after this ID.",
            },
        },
        "additionalProperties": False,
    },
}


SEND_MESSAGE = {
    "name": "discord_send_message",
    "description": (
        "Send a Discord message to a channel or thread the configured bot token can post to. "
        "Can optionally reply to a message and upload local files such as audio replies."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "channel_id": {
                "type": "string",
                "description": "Discord channel or thread ID to send into.",
            },
            "content": {
                "type": "string",
                "description": "Optional message text. Required unless attachment_paths is provided.",
            },
            "reply_to_message_id": {
                "type": "string",
                "description": "Optional Discord message ID to reply to.",
            },
            "attachment_paths": {
                "type": "array",
                "description": "Optional local file paths to upload with the message, such as audio replies.",
                "items": {"type": "string"},
            },
        },
        "required": ["channel_id"],
        "additionalProperties": False,
    },
}


SEARCH_MESSAGES = {
    "name": "discord_search_messages",
    "description": (
        "Search Discord message history across a guild/server by keyword and optional filters. "
        "Returns matching messages with total count. Use this to find past conversations, "
        "decisions, or context the user references."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "guild_id": {
                "type": "string",
                "description": "Discord guild/server ID to search within.",
            },
            "content": {
                "type": "string",
                "description": "Search query — keywords to find in message content.",
            },
            "author_id": {
                "type": "string",
                "description": "Optional: filter results to messages by this user ID.",
            },
            "channel_id": {
                "type": "string",
                "description": "Optional: limit search to a specific channel or thread ID.",
            },
            "mentions_user_id": {
                "type": "string",
                "description": "Optional: filter to messages that mention this user ID.",
            },
            "has": {
                "type": "string",
                "description": "Optional: filter by attachment type. Values: 'embed', 'link', 'poll'.",
            },
            "min_id": {
                "type": "string",
                "description": "Optional: only return messages after this message ID (newer).",
            },
            "max_id": {
                "type": "string",
                "description": "Optional: only return messages before this message ID (older).",
            },
            "offset": {
                "type": "integer",
                "description": "Pagination offset (default 0). Use to page through results.",
                "default": 0,
                "minimum": 0,
            },
            "limit": {
                "type": "integer",
                "description": "Results per page (1-25, default 25).",
                "default": 25,
                "minimum": 1,
                "maximum": 25,
            },
        },
        "required": ["guild_id"],
        "additionalProperties": False,
    },
}
