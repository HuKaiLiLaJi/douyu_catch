"""Small RFC 6455 transport used by the optional WebSocket mode."""

from __future__ import annotations

import base64
import hashlib
import os
import socket
import ssl
import struct

from .protocol import recv_exact


class DouyuWebSocket:
    """Small RFC 6455 client for Douyu's binary barrage frames."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = 15.0,
        path: str = "/",
        tls: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.path = path
        self.tls = tls
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        raw_sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        if self.tls:
            tls_context = ssl.create_default_context()
            self._sock = tls_context.wrap_socket(raw_sock, server_hostname=self.host)
        else:
            self._sock = raw_sock
        self._handshake()
        self._sock.settimeout(None)

    def close(self) -> None:
        if self._sock is None:
            return
        try:
            self._send_ws_frame(b"", opcode=0x8)
        except OSError:
            pass
        self._sock.close()
        self._sock = None

    def sendall(self, data: bytes) -> None:
        self._send_ws_frame(data, opcode=0x2)

    def recv_message(self) -> bytes:
        sock = self._require_socket()
        chunks: list[bytes] = []
        while True:
            first, second = recv_exact(sock, 2)
            opcode = first & 0x0F
            final = bool(first & 0x80)
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", recv_exact(sock, 2))[0]
            elif length == 127:
                length = struct.unpack("!Q", recv_exact(sock, 8))[0]

            mask = recv_exact(sock, 4) if masked else b""
            payload = recv_exact(sock, length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))

            if opcode == 0x8:
                raise ConnectionError("Douyu WebSocket server closed the connection")
            if opcode == 0x9:
                self._send_ws_frame(payload, opcode=0xA)
                continue
            if opcode in (0x1, 0x2, 0x0):
                chunks.append(payload)
                if final:
                    return b"".join(chunks)

    def _handshake(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "Origin: https://www.douyu.com\r\n"
            "\r\n"
        )
        self._require_socket().sendall(request.encode("ascii"))
        response = self._read_http_response()
        expected_accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if " 101 " not in response.split("\r\n", 1)[0]:
            raise ConnectionError(f"WebSocket handshake failed: {response.splitlines()[0] if response else 'empty response'}")
        if f"sec-websocket-accept: {expected_accept.lower()}" not in response.lower():
            raise ConnectionError("WebSocket handshake verification failed")

    def _read_http_response(self) -> str:
        data = bytearray()
        while b"\r\n\r\n" not in data:
            data.extend(recv_exact(self._require_socket(), 1))
            if len(data) > 65536:
                raise ConnectionError("WebSocket handshake response is too large")
        return data.decode("iso-8859-1")

    def _send_ws_frame(self, payload: bytes, opcode: int) -> None:
        mask = os.urandom(4)
        length = len(payload)
        header = bytearray([0x80 | opcode])
        if length < 126:
            header.append(0x80 | length)
        elif length <= 0xFFFF:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        masked_payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self._require_socket().sendall(bytes(header) + mask + masked_payload)

    def _require_socket(self) -> socket.socket:
        if self._sock is None:
            raise ConnectionError("Not connected to Douyu WebSocket server")
        return self._sock
