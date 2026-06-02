"""Command-line interface for the Douyu danmu collector."""

from __future__ import annotations

import argparse
import os
import sys

from .client import SERVER_HOST, SERVER_PORT
from .collector import collect
from .models import MySQLConfig
from .protocol import DouyuProtocolError


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Douyu live danmu collector")
    parser.add_argument("room_id", help="Douyu room id")
    parser.add_argument("-o", "--output", help="Save messages as JSON Lines, for example data/douyu.jsonl")
    parser.add_argument("-n", "--limit", type=positive_int, help="Stop after collecting this many chat messages")
    parser.add_argument("--json", action="store_true", help="Print JSON Lines to the terminal")
    parser.add_argument("--host", default=SERVER_HOST, help=f"Danmu server host, default {SERVER_HOST}")
    parser.add_argument("--port", type=positive_int, default=SERVER_PORT, help=f"Danmu server port, default {SERVER_PORT}")
    parser.add_argument("--transport", choices=("tcp", "websocket"), default="tcp", help="Connection transport")
    parser.add_argument("--ws-tls", action="store_true", help="Use TLS/WSS for WebSocket transport")
    parser.add_argument("--mysql", action="store_true", help="Save messages to MySQL")
    parser.add_argument("--mysql-host", default=os.getenv("DOUYU_MYSQL_HOST", "localhost"))
    parser.add_argument("--mysql-port", type=positive_int, default=int(os.getenv("DOUYU_MYSQL_PORT", "3306")))
    parser.add_argument("--mysql-user", default=os.getenv("DOUYU_MYSQL_USER", "douyu_user"))
    parser.add_argument("--mysql-password", default=os.getenv("DOUYU_MYSQL_PASSWORD", os.getenv("MYSQL_PWD", "")))
    parser.add_argument("--mysql-db", default=os.getenv("DOUYU_MYSQL_DB", "douyu_danmu"))
    parser.add_argument("--mysql-table", default=os.getenv("DOUYU_MYSQL_TABLE", "danmu_messages"))
    parser.add_argument("--mysql-per-room", action="store_true", help="Save each room into its own table, for example danmu_room_4767111")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    mysql_config = None
    if args.mysql:
        mysql_config = MySQLConfig(
            host=args.mysql_host,
            port=args.mysql_port,
            user=args.mysql_user,
            password=args.mysql_password,
            database=args.mysql_db,
            table=args.mysql_table,
            per_room_tables=args.mysql_per_room,
        )

    try:
        collect(
            args.room_id,
            output_path=args.output,
            limit=args.limit,
            raw_json=args.json,
            host=args.host,
            port=args.port,
            transport=args.transport,
            websocket_tls=args.ws_tls,
            mysql_config=mysql_config,
        )
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
    except OSError as exc:
        print(f"Connection failed: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Runtime error: {exc}", file=sys.stderr)
        return 1
    except DouyuProtocolError as exc:
        print(f"Protocol error: {exc}", file=sys.stderr)
        return 1
    return 0
