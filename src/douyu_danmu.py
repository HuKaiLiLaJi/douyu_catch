"""Compatibility entrypoint for the Douyu danmu collector.

The implementation is split across focused modules:

- ``protocol``: Douyu frame packing/parsing helpers
- ``client``: TCP/WebSocket connection and message streaming
- ``storage``: MySQL persistence
- ``collector``: high-level collection workflow
- ``cli``: command-line parsing
"""

from __future__ import annotations

from .cli import build_parser, main, positive_int
from .client import (
    DEFAULT_GROUP_ID,
    HEARTBEAT_INTERVAL_SECONDS,
    SERVER_HOST,
    SERVER_PORT,
    WEBSOCKET_HOST,
    WEBSOCKET_PORT,
    DouyuDanmuClient,
)
from .collector import collect, safe_print
from .models import DanmuMessage, MySQLConfig
from .protocol import (
    MESSAGE_TYPE_CLIENT,
    DouyuProtocolError,
    decode_fields,
    encode_fields,
    escape_value,
    pack_message,
    read_frame,
    recv_exact,
    unescape_value,
)
from .storage import MySQLDanmuWriter, parse_mysql_datetime, quote_mysql_identifier
from .websocket_transport import DouyuWebSocket


__all__ = [
    "DEFAULT_GROUP_ID",
    "HEARTBEAT_INTERVAL_SECONDS",
    "MESSAGE_TYPE_CLIENT",
    "SERVER_HOST",
    "SERVER_PORT",
    "WEBSOCKET_HOST",
    "WEBSOCKET_PORT",
    "DanmuMessage",
    "DouyuDanmuClient",
    "DouyuProtocolError",
    "DouyuWebSocket",
    "MySQLConfig",
    "MySQLDanmuWriter",
    "build_parser",
    "collect",
    "decode_fields",
    "encode_fields",
    "escape_value",
    "main",
    "pack_message",
    "parse_mysql_datetime",
    "positive_int",
    "quote_mysql_identifier",
    "read_frame",
    "recv_exact",
    "safe_print",
    "unescape_value",
]


if __name__ == "__main__":
    raise SystemExit(main())
