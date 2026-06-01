"""Storage backends for collected danmu."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import DanmuMessage, MySQLConfig


class MySQLDanmuWriter:
    """Persist danmu messages into a MySQL table."""

    def __init__(self, config: MySQLConfig) -> None:
        self.config = config
        self._connection = None

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

        table = quote_mysql_identifier(self.config.table)
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


def quote_mysql_identifier(identifier: str) -> str:
    if not identifier or "`" in identifier or "\x00" in identifier:
        raise ValueError(f"Invalid MySQL identifier: {identifier!r}")
    return f"`{identifier}`"


def parse_mysql_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
