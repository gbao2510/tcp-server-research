"""Client TCP (Client / Load Gen Dev - tuần 1).

Một Client = một kết nối TCP bền, gửi request theo giao thức Length-Prefix + JSON
(xem protocol.py) và chờ response tương ứng.
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path
from typing import Any

# Đảm bảo import được protocol dù chạy từ thư mục nào
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from protocol import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_TIMEOUT, recv_message, send_message


class Client:
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self.sock: socket.socket | None = None

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def request(self, message: dict[str, Any]) -> dict[str, Any]:
        """Gửi một request và chờ response."""
        if self.sock is None:
            raise RuntimeError("Chưa kết nối: hãy gọi connect() trước")
        send_message(self.sock, message)
        resp = recv_message(self.sock)
        if resp is None:
            raise RuntimeError("Server đã ngắt kết nối mà không gửi response")
        return resp

    def __enter__(self) -> "Client":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()
