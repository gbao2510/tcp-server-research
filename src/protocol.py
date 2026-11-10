"""Wrapper import cho mô-đun protocol chuẩn trong thư mục src/"""
import sys
from pathlib import Path

# Đảm bảo root có trong sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from protocol import (
    HEADER_SIZE,
    HEADER_FORMAT,
    MAX_PAYLOAD_SIZE,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    ProtocolError,
    ConnectionClosedError,
    MessageTooLargeError,
    InvalidMessageError,
    ProtocolTimeoutError,
    pack_message,
    unpack_message,
    recvall,
    send_message,
    recv_message,
    create_request,
    create_response,
)

__all__ = [
    "HEADER_SIZE",
    "HEADER_FORMAT",
    "MAX_PAYLOAD_SIZE",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_TIMEOUT",
    "ProtocolError",
    "ConnectionClosedError",
    "MessageTooLargeError",
    "InvalidMessageError",
    "ProtocolTimeoutError",
    "pack_message",
    "unpack_message",
    "recvall",
    "send_message",
    "recv_message",
    "create_request",
    "create_response",
]
