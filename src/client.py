"""Douyu danmu client."""

from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import Callable, Iterator
import socket
import struct
import threading
import time

from .models import DanmuMessage
from .protocol import decode_fields, encode_fields, pack_message, read_frame
from .websocket_transport import DouyuWebSocket


SERVER_HOST = "openbarrage.douyutv.com"
SERVER_PORT = 8601
WEBSOCKET_HOST = "danmuproxy.douyu.com"
WEBSOCKET_PORT = 8503
DEFAULT_GROUP_ID = -9999
HEARTBEAT_INTERVAL_SECONDS = 45


class DouyuDanmuClient:
    """Minimal Douyu barrage client."""

    def __init__(
        self,
        room_id: str,
        host: str = SERVER_HOST,
        port: int = SERVER_PORT,
        group_id: int = DEFAULT_GROUP_ID,
        heartbeat_interval: int = HEARTBEAT_INTERVAL_SECONDS,
        timeout: float = 15.0,
        transport: str = "tcp",
        websocket_tls: bool = False,
        read_timeout: float | None = None,
    ) -> None:
        self.room_id = str(room_id)
        self.host = host
        self.port = port
        self.group_id = group_id
        self.heartbeat_interval = heartbeat_interval
        self.timeout = timeout
        self.transport = transport
        self.websocket_tls = websocket_tls
        self.read_timeout = read_timeout
        self._sock: socket.socket | DouyuWebSocket | None = None
        self._closed = threading.Event()
        self._send_lock = threading.Lock()
        self._heartbeat_thread: threading.Thread | None = None

    def connect(self) -> None:
        if self.transport == "websocket":
            ws = DouyuWebSocket(self.host, self.port, timeout=self.timeout, tls=self.websocket_tls)
            ws.connect()
            self._sock = ws
        else:
            sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            sock.settimeout(self.read_timeout)
            self._sock = sock
        self._send_command({"type": "loginreq", "roomid": self.room_id})
        self._send_command({"type": "joingroup", "rid": self.room_id, "gid": self.group_id})
        self._start_heartbeat()

    def close(self) -> None:
        self._closed.set()
        if self._sock is None:
            return

        try:
            self._send_command({"type": "logout"})
        except OSError:
            pass
        if isinstance(self._sock, socket.socket):
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self._sock.close()
        self._sock = None

    def messages(self) -> Iterator[DanmuMessage]:
        if self._sock is None:
            self.connect()

        while not self._closed.is_set():
            try:
                message = self._read_chat_message()
            except socket.timeout:
                continue
            if message is not None:
                yield message

    def messages_for(
        self,
        seconds: int | float,
        should_stop: Callable[[], bool] | None = None,
    ) -> Iterator[DanmuMessage]:
        if self._sock is None:
            self.connect()

        deadline = time.monotonic() + float(seconds)
        while not self._closed.is_set() and time.monotonic() < deadline:
            if should_stop is not None and should_stop():
                return
            try:
                message = self._read_chat_message()
            except socket.timeout:
                continue
            if should_stop is not None and should_stop():
                return
            if message is not None:
                yield message

    def _read_chat_message(self) -> DanmuMessage | None:
        frame = self._read_message()
        fields = decode_fields(frame)
        if fields.get("type") != "chatmsg":
            return None
        return DanmuMessage(
            room_id=self.room_id,
            nickname=fields.get("nn", ""),
            text=fields.get("txt", ""),
            user_id=fields.get("uid", ""),
            level=fields.get("level", ""),
            raw_type=fields.get("type", "chatmsg"),
            received_at=datetime.now(timezone.utc).isoformat(),
        )

    def _send_command(self, fields: dict[str, object]) -> None:
        data = pack_message(encode_fields(fields))
        with self._send_lock:
            self._require_socket().sendall(data)

    def _read_message(self) -> str:
        sock = self._require_socket()
        if isinstance(sock, DouyuWebSocket):
            payload = sock.recv_message()
            if len(payload) >= 12:
                length, duplicate_length, _message_type = struct.unpack("<III", payload[:12])
                if length == duplicate_length and length >= 9:
                    return payload[12 : 12 + length - 8].rstrip(b"\x00").decode("utf-8", errors="replace")
            return payload.rstrip(b"\x00").decode("utf-8", errors="replace")
        return read_frame(sock)

    def _start_heartbeat(self) -> None:
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _heartbeat_loop(self) -> None:
        while not self._closed.wait(self.heartbeat_interval):
            try:
                self._send_command({"type": "keeplive", "tick": int(time.time())})
            except OSError:
                self._closed.set()
                return

    def _require_socket(self) -> socket.socket | DouyuWebSocket:
        if self._sock is None:
            raise ConnectionError("Not connected to Douyu danmu server")
        return self._sock
