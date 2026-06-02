"""Douyu room status detection."""

from __future__ import annotations

from dataclasses import dataclass
import re
import urllib.request


DOUYU_ROOM_URL = "https://www.douyu.com/{room_id}"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"


@dataclass(frozen=True)
class RoomStatus:
    room_id: str
    status: str
    label: str
    room_name: str = ""
    show_status: int | None = None
    video_loop: int | None = None

    @property
    def is_live(self) -> bool:
        return self.status == "live"


def fetch_room_status(room_id: str, timeout: float = 10.0) -> RoomStatus:
    room_id = str(room_id).strip()
    request = urllib.request.Request(DOUYU_ROOM_URL.format(room_id=room_id), headers={"User-Agent": USER_AGENT})
    html = urllib.request.urlopen(request, timeout=timeout).read().decode("utf-8", "ignore")

    show_status = _extract_int(html, "show_status")
    video_loop = _extract_int(html, "videoLoop")
    real_room_id = _extract_int(html, "room_id")
    room_name = _extract_string(html, "room_name")
    normalized_room_id = str(real_room_id) if real_room_id is not None else room_id

    if show_status == 1 and video_loop != 1:
        return RoomStatus(normalized_room_id, "live", "开播", room_name, show_status, video_loop)
    if show_status == 1 and video_loop == 1:
        return RoomStatus(normalized_room_id, "recorded", "录播", room_name, show_status, video_loop)
    if show_status == 2:
        return RoomStatus(normalized_room_id, "offline", "关播", room_name, show_status, video_loop)
    return RoomStatus(normalized_room_id, "unknown", "未知", room_name, show_status, video_loop)


def _extract_int(html: str, key: str) -> int | None:
    match = re.search(rf'(?:"|\\")' + re.escape(key) + rf'(?:"|\\"):(\d+)', html)
    return int(match.group(1)) if match else None


def _extract_string(html: str, key: str) -> str:
    match = re.search(rf'(?:"|\\")' + re.escape(key) + rf'(?:"|\\"):"(.*?)(?<!\\)"', html)
    if not match:
        return ""
    return match.group(1).replace('\\"', '"').replace('\\/', '/')
