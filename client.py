"""Client TCP (Client / Load Gen Dev - tuần 1).

Một Client = một kết nối TCP bền, gửi request theo giao thức Length-Prefix + JSON
(xem protocol.py) và chờ response tương ứng.
"""
from __future__ import annotations

import socket
from typing import Any

from protocol.protocol import recv_message, send_message


class Client:
    def __init__(self, host: str = "127.0.0.1", port: int = 9000, timeout: float = 10.0) -> None:
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
        return recv_message(self.sock)

    def __enter__(self) -> "Client":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()