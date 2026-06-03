"""Douyu room status detection."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import urllib.request


DOUYU_ROOM_URL = "https://www.douyu.com/{room_id}"
DOUYU_ROOM_API_URL = "http://open.douyucdn.cn/api/RoomApi/room/{room_id}"
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
    request = urllib.request.Request(
        DOUYU_ROOM_URL.format(room_id=room_id),
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"},
    )
    html = urllib.request.urlopen(request, timeout=timeout).read().decode("utf-8", "ignore")

    show_status = _extract_first_int(html, ["show_status", "showStatus"])
    video_loop = _extract_first_int(html, ["videoLoop", "video_loop"])
    real_room_id = _extract_first_int(html, ["room_id", "roomId", "rid"])
    room_name = _extract_first_string(html, ["room_name", "roomName", "name"])
    normalized_room_id = str(real_room_id) if real_room_id is not None else room_id

    if show_status == 1 and video_loop != 1:
        return RoomStatus(normalized_room_id, "live", "\u5f00\u64ad", room_name, show_status, video_loop)
    if show_status == 1 and video_loop == 1:
        return RoomStatus(normalized_room_id, "recorded", "\u5f55\u64ad", room_name, show_status, video_loop)
    if show_status == 2:
        return RoomStatus(normalized_room_id, "offline", "\u5173\u64ad", room_name, show_status, video_loop)

    api_status = _fetch_room_api_status(room_id, timeout)
    if api_status is not None:
        return api_status
    return RoomStatus(normalized_room_id, "unknown", "\u672a\u77e5", room_name, show_status, video_loop)


def _fetch_room_api_status(room_id: str, timeout: float) -> RoomStatus | None:
    request = urllib.request.Request(
        DOUYU_ROOM_API_URL.format(room_id=room_id),
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"},
    )
    try:
        payload = urllib.request.urlopen(request, timeout=timeout).read().decode("utf-8", "ignore")
        parsed = json.loads(payload)
    except Exception:
        return None

    data = parsed.get("data") if isinstance(parsed, dict) else None
    if not isinstance(data, dict):
        return None

    real_room_id = str(data.get("room_id") or room_id)
    room_name = str(data.get("room_name") or "")
    raw_status = data.get("room_status")
    try:
        room_status = int(raw_status)
    except (TypeError, ValueError):
        return None

    if room_status == 1:
        return RoomStatus(real_room_id, "live", "\u5f00\u64ad", room_name, show_status=1, video_loop=0)
    if room_status == 2:
        return RoomStatus(real_room_id, "offline", "\u5173\u64ad", room_name, show_status=2, video_loop=None)
    return RoomStatus(real_room_id, "unknown", "\u672a\u77e5", room_name, show_status=room_status, video_loop=None)


def _extract_first_int(html: str, keys: list[str]) -> int | None:
    for key in keys:
        value = _extract_int(html, key)
        if value is not None:
            return value
    return None


def _extract_first_string(html: str, keys: list[str]) -> str:
    for key in keys:
        value = _extract_string(html, key)
        if value:
            return value
    return ""


def _extract_int(html: str, key: str) -> int | None:
    escaped_key = re.escape(key)
    patterns = (
        rf'"{escaped_key}"\s*:\s*(\d+)',
        rf'\\"{escaped_key}\\"\s*:\s*(\d+)',
        rf'\b{escaped_key}\b\s*:\s*(\d+)',
    )
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return int(match.group(1))
    return None


def _extract_string(html: str, key: str) -> str:
    escaped_key = re.escape(key)
    patterns = (
        rf'"{escaped_key}"\s*:\s*"(.*?)(?<!\\)"',
        rf'\\"{escaped_key}\\"\s*:\s*\\"(.*?)(?<!\\)\\"',
        rf'\b{escaped_key}\b\s*:\s*"(.*?)(?<!\\)"',
    )
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1).replace('\\"', '"').replace('\\/', '/')
    return ""
