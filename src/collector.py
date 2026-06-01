"""High-level collection workflow."""

from __future__ import annotations

from typing import Callable
import json
import sys

from .client import DouyuDanmuClient, SERVER_HOST, SERVER_PORT
from .models import MySQLConfig
from .storage import MySQLDanmuWriter


def collect(
    room_id: str,
    output_path: str | None = None,
    limit: int | None = None,
    raw_json: bool = False,
    host: str = SERVER_HOST,
    port: int = SERVER_PORT,
    transport: str = "tcp",
    websocket_tls: bool = False,
    mysql_config: MySQLConfig | None = None,
    printer: Callable[[str], None] = print,
) -> None:
    client = DouyuDanmuClient(
        room_id,
        host=host,
        port=port,
        transport=transport,
        websocket_tls=websocket_tls,
    )
    output_file = open(output_path, "a", encoding="utf-8") if output_path else None
    mysql_writer = MySQLDanmuWriter(mysql_config) if mysql_config else None
    count = 0

    try:
        client.connect()
        if mysql_writer:
            mysql_writer.connect()
        printer(f"Connected to Douyu room {room_id}. Press Ctrl+C to stop.")
        for message in client.messages():
            payload = message.as_dict()
            line = json.dumps(payload, ensure_ascii=False)
            if output_file:
                output_file.write(line + "\n")
                output_file.flush()
            if mysql_writer:
                mysql_writer.write(message)

            if raw_json:
                safe_print(line, printer)
            else:
                nickname = message.nickname or "anonymous"
                safe_print(f"[{message.received_at}] {nickname}: {message.text}", printer)

            count += 1
            if limit is not None and count >= limit:
                break
    finally:
        client.close()
        if output_file:
            output_file.close()
        if mysql_writer:
            mysql_writer.close()


def safe_print(text: str, printer: Callable[[str], None] = print) -> None:
    """Print text even when the terminal encoding cannot represent it."""

    try:
        printer(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe_text = text.encode(encoding, errors="replace").decode(encoding)
        printer(safe_text)
