"""
test_server_robustness.py — Bộ kiểm thử hỏng hóc cho Core Server Dev (Ngô Gia Bảo)
Tuần 10/11 – 14/11: Ghép nối và kiểm thử hỏng hóc

Phần UNIT (U1–U8): Dùng FakeSocket từ BytesIO — không cần TCP port thực.
Phần INTEGRATION (I1–I4): Dùng TCP loopback — chạy: pytest -m integration

Kịch bản kiểm thử:
  U1. Echo round-trip — handle_client phản hồi đúng id, status='ok', payload.
  U2. Dữ liệu rác non-UTF8 — đóng kết nối sạch.
  U3. JSON array không phải dict — đóng kết nối sạch.
  U4. Payload vượt ngưỡng >2MB — đóng kết nối, không cấp phát bộ nhớ.
  U5. Xé gói dở dang (FramingError) — handle_client kết thúc, không crash.
  U6. Request type không hỗ trợ — phản hồi status='error'.
  U7. Nhiều request liên tiếp cùng kết nối bền.
  U8. Payload đúng 1KB nguyên vẹn.
  I1. TCP echo round-trip qua loopback.
  I2. Timeout — client im lặng → server tự đóng.
  I3. Ngắt kết nối đột ngột sau header.
  I4. 50 client đồng thời — không deadlock.
"""
from __future__ import annotations

import json
import random
import socket
import string
import struct
import sys
import threading
import time
import unittest
from io import BytesIO
from pathlib import Path
from typing import Any

# ── Đảm bảo import được module ────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR  = ROOT_DIR / "src"
for _d in (str(ROOT_DIR), str(SRC_DIR)):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from protocol.protocol import (
    HEADER_FORMAT,
    HEADER_SIZE,
    DEFAULT_MAX_PAYLOAD_SIZE,
    create_request,
    create_response,
    encode_message,
    decode_payload,
    recv_message,
    send_message,
    FramingError,
    MalformedJSONError,
    PayloadTooLargeError,
)
from src.server.server import handle_client


# ══════════════════════════════════════════════════════════════════════════════
# FAKE SOCKET — Thay thế hoàn toàn socket thật bằng BytesIO (không cần TCP)
# ══════════════════════════════════════════════════════════════════════════════
class FakeSocket:
    """Giả lập socket TCP hai chiều dùng BytesIO.
    
    - `inbound`:  Dữ liệu mà server sẽ đọc (simulate CLIENT gửi).
    - `outbound`: Buffer mà server ghi vào (chúng ta đọc lại để verify).
    """

    def __init__(self, inbound_data: bytes = b"") -> None:
        self._in  = BytesIO(inbound_data)
        self._out = BytesIO()
        self._closed = False
        self._timeout: float | None = None

    # ── Socket interface mà handle_client cần ───────────────────────────────
    def recv(self, bufsize: int) -> bytes:
        if self._closed:
            return b""
        chunk = self._in.read(bufsize)
        return chunk  # trả b"" khi hết dữ liệu (giả lập EOF)

    def sendall(self, data: bytes) -> None:
        if not self._closed:
            self._out.write(data)

    def send(self, data: bytes) -> int:
        self.sendall(data)
        return len(data)

    def settimeout(self, timeout: float | None) -> None:
        self._timeout = timeout

    def close(self) -> None:
        self._closed = True

    def fileno(self) -> int:
        return -1   # không dùng select/epoll

    # ── Tiện ích ────────────────────────────────────────────────────────────
    def get_response_bytes(self) -> bytes:
        return self._out.getvalue()

    def get_response_messages(self) -> list[dict]:
        """Giải mã tất cả message mà server đã gửi vào outbound buffer."""
        raw = self.get_response_bytes()
        messages = []
        pos = 0
        while pos < len(raw):
            if pos + HEADER_SIZE > len(raw):
                break
            (plen,) = struct.unpack(HEADER_FORMAT, raw[pos:pos + HEADER_SIZE])
            pos += HEADER_SIZE
            if pos + plen > len(raw):
                break
            messages.append(decode_payload(raw[pos:pos + plen]))
            pos += plen
        return messages


def _run_handle_client_sync(fake_sock: FakeSocket) -> None:
    """Chạy handle_client đồng bộ trong thread riêng và chờ nó kết thúc."""
    t = threading.Thread(
        target=handle_client,
        args=(fake_sock, ("fake-client", 0)),
        daemon=True,
    )
    t.start()
    t.join(timeout=5.0)
    return t


# ══════════════════════════════════════════════════════════════════════════════
# UNIT TESTS — Chạy được trong mọi môi trường (sandbox OK)
# ══════════════════════════════════════════════════════════════════════════════
class TestServerUnit(unittest.TestCase):
    """Unit tests dùng FakeSocket — không cần TCP port thực."""

    # U1 — Echo round-trip cơ bản ─────────────────────────────────────────────
    def test_U1_echo_roundtrip(self) -> None:
        """handle_client nhận request echo → phản hồi đúng id, status='ok', payload."""
        req = encode_message(create_request("ngobao-001", "echo", "xin chào server!"))
        fake = FakeSocket(req)
        t = _run_handle_client_sync(fake)

        msgs = fake.get_response_messages()
        self.assertGreater(len(msgs), 0, "Server không gửi bất kỳ response nào")
        resp = msgs[0]
        self.assertEqual(resp["id"], "ngobao-001")
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["payload"], "xin chào server!")

    # U2 — Dữ liệu rác non-UTF8 ───────────────────────────────────────────────
    def test_U2_garbage_non_utf8(self) -> None:
        """Gửi payload bytes không decode UTF-8 → server đóng kết nối, không gửi response."""
        garbage = b"\xff\xfe\x00\x01\xaa\xbb\xcc\xdd" * 8   # 64 bytes rác
        packet = struct.pack(HEADER_FORMAT, len(garbage)) + garbage
        fake = FakeSocket(packet)
        _run_handle_client_sync(fake)

        # Server phải đóng kết nối sạch: không gửi bất kỳ response nào
        self.assertEqual(
            fake.get_response_bytes(), b"",
            "Server không được gửi response khi nhận dữ liệu rác non-UTF8"
        )
        self.assertTrue(fake._closed, "Server phải đóng kết nối sau khi nhận byte rác")

    # U3 — JSON array không phải dict ─────────────────────────────────────────
    def test_U3_json_array_not_dict(self) -> None:
        """Payload là JSON array [1,2,3] → server đóng kết nối sạch, không response."""
        array_payload = b"[1, 2, 3, 4, 5]"
        packet = struct.pack(HEADER_FORMAT, len(array_payload)) + array_payload
        fake = FakeSocket(packet)
        _run_handle_client_sync(fake)

        self.assertEqual(fake.get_response_bytes(), b"")
        self.assertTrue(fake._closed)

    # U4 — Payload vượt ngưỡng >2MB ───────────────────────────────────────────
    def test_U4_payload_too_large(self) -> None:
        """Header khai báo payload 10MB → server chặn ngay, không cố đọc 10MB vào RAM."""
        oversized_header = struct.pack(HEADER_FORMAT, 10 * 1024 * 1024)
        fake = FakeSocket(oversized_header)
        _run_handle_client_sync(fake)

        self.assertEqual(fake.get_response_bytes(), b"")
        self.assertTrue(fake._closed, "Server phải đóng kết nối khi payload quá lớn")

    # U5 — Xé gói dở dang (FramingError) ─────────────────────────────────────
    def test_U5_truncated_payload(self) -> None:
        """Header khai báo 200 bytes nhưng chỉ có 50 bytes → FramingError, không crash."""
        partial = b"A" * 50
        packet = struct.pack(HEADER_FORMAT, 200) + partial
        # EOF ngay sau 50 bytes → handle_client phải raise FramingError
        fake = FakeSocket(packet)
        t = _run_handle_client_sync(fake)

        # Thread phải kết thúc (không treo)
        self.assertFalse(t.is_alive(), "handle_client phải kết thúc sau FramingError")
        self.assertTrue(fake._closed)

    # U6 — Request type không hỗ trợ ──────────────────────────────────────────
    def test_U6_unsupported_request_type(self) -> None:
        """Gửi type='delete' → server trả về status='error', có trường 'error'."""
        req = encode_message(create_request("ngobao-err", "delete", "some data"))
        fake = FakeSocket(req)
        _run_handle_client_sync(fake)

        msgs = fake.get_response_messages()
        self.assertGreater(len(msgs), 0)
        resp = msgs[0]
        self.assertEqual(resp["id"], "ngobao-err")
        self.assertEqual(resp["status"], "error")
        self.assertIn("error", resp)

    # U7 — Nhiều request liên tiếp cùng kết nối bền ───────────────────────────
    def test_U7_persistent_connection(self) -> None:
        """20 request liên tiếp trên 1 kết nối bền — tất cả phản hồi đúng."""
        inbound = b"".join(
            encode_message(create_request(f"persist-{i}", "echo", f"msg-{i}"))
            for i in range(20)
        )
        fake = FakeSocket(inbound)
        _run_handle_client_sync(fake)

        msgs = fake.get_response_messages()
        self.assertEqual(len(msgs), 20, f"Chỉ nhận được {len(msgs)}/20 response")
        for i, resp in enumerate(msgs):
            self.assertEqual(resp["id"], f"persist-{i}", f"Lần {i}: id không khớp")
            self.assertEqual(resp["status"], "ok", f"Lần {i}: status sai")
            self.assertEqual(resp["payload"], f"msg-{i}", f"Lần {i}: payload sai")

    # U8 — Payload 1KB nguyên vẹn ─────────────────────────────────────────────
    def test_U8_1kb_payload_roundtrip(self) -> None:
        """Payload đúng 1KB — server echo nguyên vẹn không mất/thêm byte."""
        payload_1kb = "".join(random.choices(string.ascii_letters + string.digits, k=1024))
        req = encode_message(create_request("1kb-test", "echo", payload_1kb))
        fake = FakeSocket(req)
        _run_handle_client_sync(fake)

        msgs = fake.get_response_messages()
        self.assertEqual(len(msgs), 1)
        resp = msgs[0]
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(len(resp["payload"]), 1024, "Payload bị mất/thêm byte")
        self.assertEqual(resp["payload"], payload_1kb, "Payload bị biến đổi nội dung")


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS — Cần TCP socket thực
# Chạy: pytest test_server_robustness.py -m integration
# ══════════════════════════════════════════════════════════════════════════════
def _can_bind_tcp() -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        s.close()
        return True
    except OSError:
        return False


_SKIP_TCP = not _can_bind_tcp()
_TCP_MSG  = "Môi trường hiện tại chặn TCP socket — chạy trực tiếp trên máy thật"


class _MiniServer:
    def __init__(self, client_timeout: float = 2.0) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(100)
        self._sock.settimeout(5.0)
        self.port: int = self._sock.getsockname()[1]
        self._client_timeout = client_timeout

    def start(self) -> "_MiniServer":
        threading.Thread(target=self._accept_loop, daemon=True).start()
        return self

    def _accept_loop(self) -> None:
        try:
            while True:
                try:
                    conn, addr = self._sock.accept()
                    conn.settimeout(self._client_timeout)
                    threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
                except (socket.timeout, OSError):
                    break
        finally:
            pass

    def stop(self) -> None:
        try: self._sock.close()
        except OSError: pass

    def __enter__(self) -> "_MiniServer": return self.start()
    def __exit__(self, *_: Any) -> None: self.stop()


def _tcp_connect(port: int, timeout: float = 3.0) -> socket.socket:
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return s


@unittest.skipIf(_SKIP_TCP, _TCP_MSG)
class TestServerIntegration(unittest.TestCase):
    """Integration tests qua TCP loopback thực."""

    def test_I1_tcp_echo_roundtrip(self) -> None:
        with _MiniServer() as srv:
            with _tcp_connect(srv.port) as sock:
                send_message(sock, create_request("i1-001", "echo", "hello TCP!"))
                resp = recv_message(sock)
        self.assertEqual(resp["id"], "i1-001")
        self.assertEqual(resp["status"], "ok")

    def test_I2_client_timeout(self) -> None:
        """Client kết nối nhưng không gửi gì → server đóng sau timeout ngắn."""
        with _MiniServer(client_timeout=0.3) as srv:
            with _tcp_connect(srv.port, timeout=5.0) as sock:
                sock.settimeout(5.0)
                try:
                    data = sock.recv(4096)
                    self.assertEqual(data, b"")
                except (ConnectionResetError, OSError):
                    pass

    def test_I3_abrupt_disconnect(self) -> None:
        """Client gửi header 100-byte rồi đóng socket — server không crash."""
        with _MiniServer() as srv:
            sock = _tcp_connect(srv.port)
            sock.sendall(struct.pack(HEADER_FORMAT, 100))
            sock.close()
            time.sleep(0.3)
            with _tcp_connect(srv.port) as sock2:
                send_message(sock2, create_request("after-abrupt", "echo", "vẫn ổn!"))
                resp = recv_message(sock2)
        self.assertEqual(resp["status"], "ok")

    def test_I4_concurrent_clients(self) -> None:
        """50 client đồng thời, 5 request mỗi client — không deadlock."""
        NUM = 50; REQS = 5
        results: list[bool] = []
        errors: list[str] = []
        lock = threading.Lock()

        def one_client(cid: int) -> None:
            try:
                with _tcp_connect(srv.port, timeout=10.0) as sock:
                    ok = True
                    for seq in range(REQS):
                        rid = f"{cid}-{seq}"
                        send_message(sock, create_request(rid, "echo", f"p-{rid}"))
                        resp = recv_message(sock)
                        if resp.get("id") != rid or resp.get("status") != "ok":
                            ok = False; break
                    with lock:
                        results.append(ok)
            except Exception as exc:
                with lock:
                    errors.append(f"client-{cid}: {exc}")

        with _MiniServer() as srv:
            threads = [threading.Thread(target=one_client, args=(i,)) for i in range(NUM)]
            for t in threads: t.start()
            for t in threads: t.join(timeout=15.0)

        self.assertEqual(len(errors), 0, f"Lỗi: {errors}")
        self.assertEqual(len(results), NUM)
        self.assertTrue(all(results))


if __name__ == "__main__":
    unittest.main(verbosity=2)
