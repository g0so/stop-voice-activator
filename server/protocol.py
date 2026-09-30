"""Binary protocol shared by the ESP32 voice activator and local server."""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass

MAGIC = b"VA"
VERSION = 1
HEADER = struct.Struct(">2sBBI")
MAX_PAYLOAD = 64 * 1024

HELLO = 1
TRIGGER = 2
AUDIO = 3
END = 4
PING = 5

HELLO_STRUCT = struct.Struct(">I H B B H H")
TRIGGER_STRUCT = struct.Struct(">I I H H H H")
AUDIO_PREFIX = struct.Struct(">I I I I h B B H")
END_STRUCT = struct.Struct(">I I I I I")
PING_STRUCT = struct.Struct(">I")


class ProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class Frame:
    frame_type: int
    payload: bytes


def encode_frame(frame_type: int, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload too large")
    return HEADER.pack(MAGIC, VERSION, frame_type, len(payload)) + payload


def recv_exact(sock: socket.socket, size: int) -> bytes:
    parts: list[bytes] = []
    remaining = size
    while remaining:
        block = sock.recv(remaining)
        if not block:
            raise EOFError("connection closed")
        parts.append(block)
        remaining -= len(block)
    return b"".join(parts)


def recv_frame(sock: socket.socket) -> Frame:
    magic, version, frame_type, payload_size = HEADER.unpack(recv_exact(sock, HEADER.size))
    if magic != MAGIC:
        raise ProtocolError(f"bad magic {magic!r}")
    if version != VERSION:
        raise ProtocolError(f"unsupported protocol version {version}")
    if payload_size > MAX_PAYLOAD:
        raise ProtocolError(f"payload exceeds {MAX_PAYLOAD} bytes")
    return Frame(frame_type, recv_exact(sock, payload_size))
