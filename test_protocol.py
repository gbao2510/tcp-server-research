"""Unit Test cho Module Giao thức (Protocol Module) - Protocol Dev.

Kiểm thử toàn diện:
1. Đóng/mở gói tin cơ bản (Roundtrip).
2. Xử lý ký tự đặc biệt UTF-8 (Tiếng Việt, Unicode).
3. Đúng tải trọng 1KB (theo yêu cầu đồ án).
4. Khắc phục hiện tượng xé gói (Fragmentation).
5. Khắc phục hiện tượng dính gói (Coalescing).
6. Bẫy lỗi dữ liệu rác (Invalid JSON, Non-UTF8, Payload quá lớn, Đứt kết nối dở dang).
7. Kiểm thử tích hợp qua Socket TCP thực tế (Loopback socket).
"""

from __future__ import annotations

import json
import os
import socket
import struct
import sys
import threading
import unittest
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
for d in (str(ROOT_DIR), str(SRC_DIR)):
    if d not in sys.path:
        sys.path.insert(0, d)

from protocol.protocol import (
    DEFAULT_MAX_PAYLOAD_SIZE,
    HEADER_FORMAT,
    HEADER_SIZE,
    FramingError,
    MalformedJSONError,
    MessageBuffer,
    PayloadTooLargeError,
    ProtocolError,
    create_request,
    create_response,
    decode_payload,
    encode_message,
    recv_exact,
    recv_message,
    send_message,
)


class MockSocket:
    """Giả lập socket TCP để kiểm thử hành vi recv_exact với các kích thước chunk tùy ý."""

    def __init__(self, data: bytes, chunk_size: int = 1) -> None:
        self.data = data
        self.chunk_size = chunk_size
        self.cursor = 0

    def recv(self, bufsize: int) -> bytes:
        if self.cursor >= len(self.data):
            return b""  # Giả lập EOF
        read_len = min(bufsize, self.chunk_size, len(self.data) - self.cursor)
        chunk = self.data[self.cursor : self.cursor + read_len]
        self.cursor += read_len
        return chunk


class TestProtocol(unittest.TestCase):

    def test_encode_and_decode_roundtrip(self) -> None:
        """Kiểm tra đóng gói và giải mã gói tin thông thường."""
        original_msg = {"id": "req-1", "type": "echo", "payload": "hello world"}
        raw_packet = encode_message(original_msg)

        # Kiểm tra cấu trúc header 4 bytes
        self.assertGreaterEqual(len(raw_packet), HEADER_SIZE)
        (payload_len,) = struct.unpack(HEADER_FORMAT, raw_packet[:HEADER_SIZE])
        self.assertEqual(payload_len, len(raw_packet) - HEADER_SIZE)

        # Giải mã và so sánh nội dung
        decoded_msg = decode_payload(raw_packet[HEADER_SIZE:])
        self.assertEqual(decoded_msg, original_msg)

    def test_unicode_and_vietnamese(self) -> None:
        """Kiểm tra tính toàn vẹn của chuỗi UTF-8 tiếng Việt và ký tự đặc biệt."""
        msg = {
            "id": "vn-01",
            "type": "message",
            "payload": "Lập trình mạng: Thí nghiệm khảo sát hiệu năng TCP Server đa luồng 🚀 🇻🇳",
        }
        raw_packet = encode_message(msg)
        (payload_len,) = struct.unpack(HEADER_FORMAT, raw_packet[:HEADER_SIZE])

        # Header phải tính theo số bytes UTF-8 chứ không phải số ký tự chuỗi
        expected_bytes = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        self.assertEqual(payload_len, len(expected_bytes))

        decoded_msg = decode_payload(raw_packet[HEADER_SIZE:])
        self.assertEqual(decoded_msg["payload"], msg["payload"])

    def test_1kb_payload(self) -> None:
        """Kiểm tra payload kích thước 1KB theo yêu cầu của đồ án."""
        payload_1kb = "A" * 1024
        req = create_request("client-1-0", "echo", payload_1kb)
        raw_packet = encode_message(req)

        self.assertGreater(len(raw_packet), 1024)
        decoded = decode_payload(raw_packet[HEADER_SIZE:])
        self.assertEqual(len(decoded["payload"]), 1024)
        self.assertEqual(decoded["payload"], payload_1kb)

    def test_packet_fragmentation(self) -> None:
        """Mô phỏng hiện tượng xé gói (nhận từng 1-2 byte một) qua recv_exact."""
        msg = {"id": "frag-1", "status": "ok", "payload": "testing fragmentation handling"}
        raw_packet = encode_message(msg)

        # Giả lập socket trả về mỗi lần chỉ đúng 1 byte
        mock_sock = MockSocket(raw_packet, chunk_size=1)
        received_header = recv_exact(mock_sock, HEADER_SIZE)  # type: ignore[arg-type]
        (p_len,) = struct.unpack(HEADER_FORMAT, received_header)
        received_body = recv_exact(mock_sock, p_len)  # type: ignore[arg-type]

        decoded = decode_payload(received_body)
        self.assertEqual(decoded, msg)

    def test_packet_coalescing_with_message_buffer(self) -> None:
        """Mô phỏng hiện tượng dính gói (nhận nhiều gói tin gộp lại trong 1 lần đọc buffer)."""
        msg1 = {"id": "msg-1", "type": "ping"}
        msg2 = {"id": "msg-2", "type": "echo", "payload": "packet 2"}
        msg3 = {"id": "msg-3", "type": "bye"}

        combined_stream = encode_message(msg1) + encode_message(msg2) + encode_message(msg3)

        buf = MessageBuffer()
        buf.feed(combined_stream)

        # Trích xuất lần lượt từng gói tin
        res1 = buf.next_message()
        res2 = buf.next_message()
        res3 = buf.next_message()
        res4 = buf.next_message()

        self.assertEqual(res1, msg1)
        self.assertEqual(res2, msg2)
        self.assertEqual(res3, msg3)
        self.assertIsNone(res4)  # Không còn gói nào

    def test_garbage_data_non_utf8(self) -> None:
        """Bẫy lỗi dữ liệu rác: Chuỗi byte không giải mã được UTF-8."""
        garbage_bytes = b"\xff\xfe\x00\x00\xaa\xbb"
        with self.assertRaises(MalformedJSONError) as ctx:
            decode_payload(garbage_bytes)
        self.assertIn("Không thể giải mã chuỗi UTF-8", str(ctx.exception))

    def test_garbage_data_invalid_json(self) -> None:
        """Bẫy lỗi dữ liệu rác: Chuỗi không tuân theo cú pháp JSON."""
        invalid_json_bytes = b"{this is not valid json : 123"
        with self.assertRaises(MalformedJSONError) as ctx:
            decode_payload(invalid_json_bytes)
        self.assertIn("Cú pháp JSON không hợp lệ", str(ctx.exception))

    def test_garbage_data_non_dict_json(self) -> None:
        """Bẫy lỗi dữ liệu rác: JSON hợp lệ nhưng không phải là Object (dict)."""
        array_json = b"[1, 2, 3, 4]"
        with self.assertRaises(MalformedJSONError) as ctx:
            decode_payload(array_json)
        self.assertIn("Gói tin phải là JSON Object", str(ctx.exception))

    def test_payload_too_large(self) -> None:
        """Bẫy lỗi tấn công tràn RAM: Gói tin khai báo vượt ngưỡng max_size."""
        max_limit = 100
        msg = {"id": "big", "data": "X" * 150}

        # Encode với max_size nhỏ sẽ bị chặn ngay lúc đóng gói
        with self.assertRaises(PayloadTooLargeError):
            encode_message(msg, max_size=max_limit)

        # Hoặc một header giả mạo báo độ dài 100MB
        fake_header = struct.pack(HEADER_FORMAT, 100 * 1024 * 1024)
        mock_sock = MockSocket(fake_header)
        with self.assertRaises(PayloadTooLargeError):
            recv_message(mock_sock, max_size=DEFAULT_MAX_PAYLOAD_SIZE)  # type: ignore[arg-type]

    def test_unexpected_eof_midway(self) -> None:
        """Bẫy lỗi luồng bị đứt đột ngột khi gói tin chưa nhận đủ."""
        # Khai báo payload dài 20 bytes nhưng stream chỉ gửi 5 bytes rồi đóng
        fake_header = struct.pack(HEADER_FORMAT, 20)
        incomplete_data = fake_header + b"12345"
        mock_sock = MockSocket(incomplete_data)

        with self.assertRaises(FramingError) as ctx:
            recv_message(mock_sock)  # type: ignore[arg-type]
        self.assertIn("Mất kết nối đột ngột", str(ctx.exception))

    def test_real_tcp_socket_roundtrip(self) -> None:
        """Kiểm thử trao đổi gói tin qua kết nối TCP Loopback thực tế giữa 2 thread."""
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        port = server_sock.getsockname()[1]

        received_by_server: list[dict[str, Any]] = []

        def server_thread() -> None:
            conn, _ = server_sock.accept()
            try:
                # Nhận request từ client
                req = recv_message(conn)
                received_by_server.append(req)
                # Gửi response lại
                res = create_response(req["id"], "ok", req["payload"])
                send_message(conn, res)
            finally:
                conn.close()
                server_sock.close()

        th = threading.Thread(target=server_thread)
        th.start()

        # Client kết nối
        client_sock = socket.create_connection(("127.0.0.1", port))
        try:
            req_data = create_request("req-real-1", "echo", "hello over real tcp")
            send_message(client_sock, req_data)

            response = recv_message(client_sock)
            self.assertEqual(response["id"], "req-real-1")
            self.assertEqual(response["status"], "ok")
            self.assertEqual(response["payload"], "hello over real tcp")
        finally:
            client_sock.close()

        th.join(timeout=3.0)
        self.assertEqual(len(received_by_server), 1)
        self.assertEqual(received_by_server[0]["id"], "req-real-1")


if __name__ == "__main__":
    unittest.main()
