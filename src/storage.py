"""Storage backends for collected danmu."""

from __future__ import annotations

from datetime import datetime, timezone
import re

from .models import DanmuMessage, MySQLConfig


ROOM_TABLE_PREFIX = "danmu_room_"
SESSION_TABLE_NAME = "capture_sessions"


class MySQLDanmuWriter:
    """Persist danmu messages into MySQL."""

    def __init__(self, config: MySQLConfig) -> None:
        self.config = config
        self._connection = None
        self._ensured_tables: set[str] = set()
        self._session_table_ensured = False

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

    def create_session(self, task_id: str, room_id: str, requested_duration: int, table_name: str) -> int:
        if self._connection is None:
            self.connect()
        self.ensure_session_table()

        table = quote_mysql_identifier(SESSION_TABLE_NAME)
        sql = (
            f"INSERT INTO {table} "
            "(task_id, room_id, requested_duration, status, table_name, started_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        )
        values = (
            task_id,
            room_id,
            requested_duration,
            "starting",
            table_name,
            datetime.utcnow(),
        )
        with self._connection.cursor() as cursor:
            cursor.execute(sql, values)
            return int(cursor.lastrowid)

    def update_session(
        self,
        session_id: int,
        *,
        status: str | None = None,
        room_name: str | None = None,
        room_status: str | None = None,
        message_count: int | None = None,
        error_message: str | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        if self._connection is None:
            self.connect()
        self.ensure_session_table()

        assignments = []
        values: list[object] = []
        if status is not None:
            assignments.append("status = %s")
            values.append(status)
        if room_name is not None:
            assignments.append("room_name = %s")
            values.append(room_name)
        if room_status is not None:
            assignments.append("room_status = %s")
            values.append(room_status)
        if message_count is not None:
            assignments.append("message_count = %s")
            values.append(message_count)
        if error_message is not None:
            assignments.append("error_message = %s")
            values.append(error_message)
        if ended_at is not None:
            assignments.append("ended_at = %s")
            values.append(ended_at)

        if not assignments:
            return

        assignments.append("updated_at = CURRENT_TIMESTAMP")
        values.append(session_id)
        table = quote_mysql_identifier(SESSION_TABLE_NAME)
        sql = f"UPDATE {table} SET {', '.join(assignments)} WHERE id = %s"
        with self._connection.cursor() as cursor:
            cursor.execute(sql, values)

    def list_sessions(self, limit: int = 50) -> list[dict[str, object]]:
        if self._connection is None:
            self.connect()
        self.ensure_session_table()

        table = quote_mysql_identifier(SESSION_TABLE_NAME)
        normalized_limit = max(1, min(int(limit), 200))
        sql = f"""
        SELECT
          id,
          task_id,
          room_id,
          room_name,
          room_status,
          requested_duration,
          status,
          table_name,
          message_count,
          error_message,
          started_at,
          ended_at,
          created_at,
          updated_at
        FROM {table}
        ORDER BY started_at DESC, id DESC
        LIMIT %s
        """
        with self._connection.cursor() as cursor:
            cursor.execute(sql, (normalized_limit,))
            rows = cursor.fetchall()
            columns = [column[0] for column in cursor.description]
        return [serialize_mysql_row(dict(zip(columns, row))) for row in rows]

    def get_session(self, session_id: int) -> dict[str, object] | None:
        if self._connection is None:
            self.connect()
        self.ensure_session_table()

        table = quote_mysql_identifier(SESSION_TABLE_NAME)
        sql = f"""
        SELECT
          id,
          task_id,
          room_id,
          room_name,
          room_status,
          requested_duration,
          status,
          table_name,
          message_count,
          error_message,
          started_at,
          ended_at,
          created_at,
          updated_at
        FROM {table}
        WHERE id = %s
        """
        with self._connection.cursor() as cursor:
            cursor.execute(sql, (session_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            columns = [column[0] for column in cursor.description]
        return serialize_mysql_row(dict(zip(columns, row)))

    def list_session_messages(self, session_id: int, limit: int = 500) -> tuple[dict[str, object], list[dict[str, object]]] | None:
        session = self.get_session(session_id)
        if session is None:
            return None

        table_name = str(session["table_name"])
        table = quote_mysql_identifier(table_name)
        normalized_limit = max(1, min(int(limit), 2000))
        sql = f"""
        SELECT
          id,
          session_id,
          room_id,
          nickname,
          text,
          user_id,
          level,
          raw_type,
          received_at,
          created_at
        FROM {table}
        WHERE session_id = %s
        ORDER BY received_at ASC, id ASC
        LIMIT %s
        """
        with self._connection.cursor() as cursor:
            cursor.execute(sql, (session_id, normalized_limit))
            rows = cursor.fetchall()
            columns = [column[0] for column in cursor.description]
        messages = [serialize_mysql_row(dict(zip(columns, row))) for row in rows]
        return session, messages

    def delete_session_messages(self, session_id: int) -> int | None:
        session = self.get_session(session_id)
        if session is None:
            return None

        table_name = str(session["table_name"])
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                """,
                (table_name,),
            )
            if cursor.fetchone()[0] == 0:
                return 0

            table = quote_mysql_identifier(table_name)
            sql = f"DELETE FROM {table} WHERE session_id = %s"
            cursor.execute(sql, (session_id,))
            return int(cursor.rowcount)

    def ensure_session_table(self) -> None:
        if self._connection is None:
            self.connect()
        if self._session_table_ensured:
            return

        table = quote_mysql_identifier(SESSION_TABLE_NAME)
        sql = f"""
        CREATE TABLE IF NOT EXISTS {table} (
          id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
          task_id CHAR(36) NOT NULL,
          room_id VARCHAR(32) NOT NULL,
          room_name VARCHAR(255) DEFAULT '',
          room_status VARCHAR(32) DEFAULT '',
          requested_duration INT UNSIGNED NOT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'starting',
          table_name VARCHAR(64) NOT NULL,
          message_count INT UNSIGNED NOT NULL DEFAULT 0,
          error_message TEXT NULL,
          started_at DATETIME NOT NULL,
          ended_at DATETIME NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

          PRIMARY KEY (id),
          UNIQUE KEY uq_task_id (task_id),
          KEY idx_room_started_at (room_id, started_at),
          KEY idx_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        with self._connection.cursor() as cursor:
            cursor.execute(sql)
        self._session_table_ensured = True

    def write(self, message: DanmuMessage, session_id: int | None = None) -> None:
        if self._connection is None:
            self.connect()

        table_name = self._table_name_for(message.room_id)
        if self.config.per_room_tables:
            self._ensure_room_table(table_name)

        table = quote_mysql_identifier(table_name)
        base_values = (
            message.room_id,
            message.nickname,
            message.text,
            message.user_id,
            message.level,
            message.raw_type,
            parse_mysql_datetime(message.received_at),
        )
        if session_id is None and not self.config.per_room_tables:
            sql = (
                f"INSERT INTO {table} "
                "(room_id, nickname, text, user_id, level, raw_type, received_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)"
            )
            values = base_values
        else:
            sql = (
                f"INSERT INTO {table} "
                "(session_id, room_id, nickname, text, user_id, level, raw_type, received_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            )
            values = (session_id, *base_values)
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
          session_id BIGINT UNSIGNED NULL,
          room_id VARCHAR(32) NOT NULL,
          nickname VARCHAR(255) NOT NULL,
          text TEXT NOT NULL,
          user_id VARCHAR(64) DEFAULT '',
          level VARCHAR(32) DEFAULT '',
          raw_type VARCHAR(32) DEFAULT 'chatmsg',
          received_at DATETIME NOT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

          PRIMARY KEY (id),
          KEY idx_session_received_at (session_id, received_at),
          KEY idx_received_at (received_at),
          KEY idx_room_received_at (room_id, received_at),
          KEY idx_user_id (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        with self._connection.cursor() as cursor:
            cursor.execute(sql)
            self._ensure_room_session_column(cursor, table_name)
        self._ensured_tables.add(table_name)

    def _ensure_room_session_column(self, cursor, table_name: str) -> None:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = 'session_id'
            """,
            (table_name,),
        )
        exists = cursor.fetchone()[0]
        if exists:
            return

        table = quote_mysql_identifier(table_name)
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN session_id BIGINT UNSIGNED NULL AFTER id")
        cursor.execute(f"ALTER TABLE {table} ADD KEY idx_session_received_at (session_id, received_at)")


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



def serialize_mysql_row(row: dict[str, object]) -> dict[str, object]:
    serialized = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            serialized[key] = value.isoformat(sep=" ")
        else:
            serialized[key] = value
    return serialized
