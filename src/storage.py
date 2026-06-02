"""Storage backends for collected danmu."""

from __future__ import annotations

from datetime import datetime, timezone
import re

from .models import DanmuMessage, MySQLConfig


ROOM_TABLE_PREFIX = "danmu_room_"


class MySQLDanmuWriter:
    """Persist danmu messages into MySQL."""

    def __init__(self, config: MySQLConfig) -> None:
        self.config = config
        self._connection = None
        self._ensured_tables: set[str] = set()

    def connect(self) -> None:
        try:
            import pymysql
        except ImportError as exc:
            raise RuntimeError("PyMySQL is required for --mysql. Install it with: python -m pip install pymysql") from exc

        self._connection = pymysql.connect(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
            charset=self.config.charset,
            autocommit=True,
        )

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def write(self, message: DanmuMessage) -> None:
        if self._connection is None:
            self.connect()

        table_name = self._table_name_for(message.room_id)
        if self.config.per_room_tables:
            self._ensure_room_table(table_name)

        table = quote_mysql_identifier(table_name)
        sql = (
            f"INSERT INTO {table} "
            "(room_id, nickname, text, user_id, level, raw_type, received_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )
        values = (
            message.room_id,
            message.nickname,
            message.text,
            message.user_id,
            message.level,
            message.raw_type,
            parse_mysql_datetime(message.received_at),
        )
        with self._connection.cursor() as cursor:
            cursor.execute(sql, values)

    def _table_name_for(self, room_id: str) -> str:
        if self.config.per_room_tables:
            return room_table_name(room_id)
        return self.config.table

    def _ensure_room_table(self, table_name: str) -> None:
        if table_name in self._ensured_tables:
            return

        table = quote_mysql_identifier(table_name)
        sql = f"""
        CREATE TABLE IF NOT EXISTS {table} (
          id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
          room_id VARCHAR(32) NOT NULL,
          nickname VARCHAR(255) NOT NULL,
          text TEXT NOT NULL,
          user_id VARCHAR(64) DEFAULT '',
          level VARCHAR(32) DEFAULT '',
          raw_type VARCHAR(32) DEFAULT 'chatmsg',
          received_at DATETIME NOT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

          PRIMARY KEY (id),
          KEY idx_received_at (received_at),
          KEY idx_room_received_at (room_id, received_at),
          KEY idx_user_id (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        with self._connection.cursor() as cursor:
            cursor.execute(sql)
        self._ensured_tables.add(table_name)


def room_table_name(room_id: str) -> str:
    normalized = str(room_id).strip()
    if not re.fullmatch(r"[0-9A-Za-z_]+", normalized):
        raise ValueError(f"Invalid room id for table name: {room_id!r}")

    table_name = f"{ROOM_TABLE_PREFIX}{normalized}"
    if len(table_name) > 64:
        raise ValueError(f"Room table name is too long: {table_name!r}")
    return table_name


def quote_mysql_identifier(identifier: str) -> str:
    if not identifier or "`" in identifier or "\\x00" in identifier:
        raise ValueError(f"Invalid MySQL identifier: {identifier!r}")
    return f"`{identifier}`"


def parse_mysql_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
