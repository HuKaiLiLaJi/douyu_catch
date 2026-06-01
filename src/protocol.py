"""Douyu barrage protocol helpers."""

from __future__ import annotations

import socket
import struct


MESSAGE_TYPE_CLIENT = 689


class DouyuProtocolError(RuntimeError):
    """Raised when the server sends an invalid protocol frame."""


def escape_value(value: object) -> str:
    """Escape a value for Douyu's slash-separated key-value format."""

    return str(value).replace("@", "@A").replace("/", "@S")


def unescape_value(value: str) -> str:
    """Unescape a value from Douyu's slash-separated key-value format."""

    return value.replace("@S", "/").replace("@A", "@")


def encode_fields(fields: dict[str, object]) -> str:
    return "".join(f"{key}@={escape_value(value)}/" for key, value in fields.items())


def decode_fields(message: str) -> dict[str, str]:
    """Decode one Douyu message body into a dictionary."""

    fields: dict[str, str] = {}
    message = message.rstrip("\x00/")
    for item in message.split("/"):
        if not item or "@=" not in item:
            continue
        key, value = item.split("@=", 1)
        fields[key] = unescape_value(value)
    return fields


def pack_message(message: str) -> bytes:
    """Pack a Douyu command into a binary frame."""

    payload = message.encode("utf-8") + b"\x00"
    length = len(payload) + 8
    return struct.pack("<III", length, length, MESSAGE_TYPE_CLIENT) + payload


def recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("Douyu danmu server disconnected")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(sock: socket.socket) -> str:
    """Read and decode one Douyu frame from the socket."""

    header = recv_exact(sock, 12)
    length, duplicate_length, _message_type = struct.unpack("<III", header)
    if length != duplicate_length or length < 9:
        raise DouyuProtocolError(f"Invalid message header: length={length}, duplicate={duplicate_length}")

    payload_length = length - 8
    payload = recv_exact(sock, payload_length)
    return payload.rstrip(b"\x00").decode("utf-8", errors="replace")
