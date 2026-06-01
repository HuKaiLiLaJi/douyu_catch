"""Shared data models for Douyu danmu collection."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DanmuMessage:
    """A normalized chat message."""

    room_id: str
    nickname: str
    text: str
    user_id: str = ""
    level: str = ""
    raw_type: str = "chatmsg"
    received_at: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "room_id": self.room_id,
            "nickname": self.nickname,
            "text": self.text,
            "user_id": self.user_id,
            "level": self.level,
            "raw_type": self.raw_type,
            "received_at": self.received_at,
        }


@dataclass(frozen=True)
class MySQLConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    table: str = "danmu_messages"
    charset: str = "utf8mb4"
