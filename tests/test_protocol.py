"""Bộ kiểm thử đơn vị toàn diện cho mô-đun Protocol (Unit Tests for Protocol Module).

Tác giả: Nguyễn Gia Bảo (Protocol Dev)
Các trường hợp kiểm thử:
1. Đóng gói và bóc tách (Pack/Unpack roundtrip).
2. Xử lý ký tự đặc biệt & tiếng Việt Unicode (UTF-8).
3. Kiểm soát lỗi kiểu dữ liệu và JSON serialize.
4. Kiểm soát kích thước gói tin tối đa (chống tràn bộ nhớ / DoS).
5. Xử lý hiện tượng dính gói TCP (Coalescing / Sticky Packets).
6. Xử lý hiện tượng phân mảnh gói tin TCP (Fragmentation / Chunked Delivery).
7. Xử lý ngắt kết nối đột ngột hoặc đóng sạch (EOF / Premature Disconnection).
8. Các helper khởi tạo Request và Response.
"""

from __future__ import annotations

import json
import socket
import struct
import threading
import time
import unittest

from protocol import (
    HEADER_FORMAT,
    HEADER_SIZE,
    MAX_PAYLOAD_SIZE,
    ConnectionClosedError,
    InvalidMessageError,
    MessageTooLargeError,
    ProtocolError,
    create_request,
    create_response,
    pack_message,
    recv_message,
    recvall,
    send_message,
    unpack_message,
)


class TestProtocolFraming(unittest.TestCase):
    """Kiểm thử các hàm đóng gói và bóc tách gói tin mức buffer."""

    def test_pack_unpack_roundtrip(self) -> None:
        """Kiểm tra tính toàn vẹn dữ liệu khi pack rồi unpack."""
        original = {
            "id": "client-1-001",
            "type": "echo",
            "payload": "Hello TCP Server!",
            "numbers": [1, 2, 3],
            "nested": {"key": "value", "active": True},
        }
        packed = pack_message(original)

        # 4 bytes header + payload UTF-8 JSON
        self.assertGreater(len(packed), HEADER_SIZE)
        header_len = struct.unpack(HEADER_FORMAT, packed[:HEADER_SIZE])[0]
        self.assertEqual(len(packed) - HEADER_SIZE, header_len)

        # Unpack
        msg, consumed = unpack_message(packed)
        self.assertEqual(consumed, len(packed))
        self.assertEqual(msg, original)

    def test_unicode_utf8_support(self) -> None:
        """Kiểm tra đóng gói chuỗi tiếng Việt có dấu và Unicode emoji."""
        original = {
            "title": "Khảo sát hiệu năng TCP Server đa luồng 🚀",
            "author": "Nguyễn Gia Bảo - Protocol Dev",
            "notes": "Hệ thống kiểm thử chịu tải cao với độ trễ thấp.",
        }
        packed = pack_message(original)
        msg, consumed = unpack_message(packed)
        self.assertEqual(consumed, len(packed))
        self.assertEqual(msg, original)

    def test_pack_non_dict_raises(self) -> None:
        """Ném InvalidMessageError khi truyền tham số không phải dict."""
        with self.assertRaises(InvalidMessageError):
            pack_message("string is not allowed")  # type: ignore[arg-type]
        with self.assertRaises(InvalidMessageError):
            pack_message([1, 2, 3])  # type: ignore[arg-type]

    def test_pack_unserializable_object_raises(self) -> None:
        """Ném InvalidMessageError khi dict chứa object không serialize được thành JSON."""
        with self.assertRaises(InvalidMessageError):
            pack_message({"id": 1, "unsupported": set([1, 2, 3])})

    def test_pack_message_too_large(self) -> None:
        """Ném MessageTooLargeError khi kích thước payload vượt ngưỡng max_payload_size."""
        big_msg = {"data": "x" * 1000}
        with self.assertRaises(MessageTooLargeError):
            pack_message(big_msg, max_payload_size=500)

    def test_unpack_incomplete_buffer(self) -> None:
        """Trả về (None, 0) nếu buffer chưa đủ header hoặc chưa đủ payload."""
        # Trường hợp 1: Ít hơn 4 bytes header
        msg, consumed = unpack_message(b"\x00\x00")
        self.assertIsNone(msg)
        self.assertEqual(consumed, 0)

        # Trường hợp 2: Có đủ header báo 50 bytes nhưng payload chỉ có 10 bytes
        partial_header = struct.pack(HEADER_FORMAT, 50) + b"1234567890"
        msg, consumed = unpack_message(partial_header)
        self.assertIsNone(msg)
        self.assertEqual(consumed, 0)

    def test_unpack_message_header_exceeds_max_payload(self) -> None:
        """Ném MessageTooLargeError khi header thông báo kích thước vượt quá giới hạn an toàn."""
        fake_header = struct.pack(HEADER_FORMAT, 10 * 1024 * 1024)  # 10 MB
        with self.assertRaises(MessageTooLargeError):
            unpack_message(fake_header, max_payload_size=1 * 1024 * 1024)

    def test_unpack_malformed_json_raises(self) -> None:
        """Ném InvalidMessageError nếu payload nhận được không phải cú pháp JSON."""
        corrupted_payload = b"{ this is invalid json : [ }"
        header = struct.pack(HEADER_FORMAT, len(corrupted_payload))
        with self.assertRaises(InvalidMessageError):
            unpack_message(header + corrupted_payload)

    def test_unpack_non_dict_json_raises(self) -> None:
        """Ném InvalidMessageError nếu JSON payload không phải dạng Object (dict)."""
        array_payload = json.dumps([1, 2, 3]).encode("utf-8")
        header = struct.pack(HEADER_FORMAT, len(array_payload))
        with self.assertRaises(InvalidMessageError):
            unpack_message(header + array_payload)

    def test_unpack_coalesced_messages(self) -> None:
        """Xử lý hiện tượng dính gói TCP (Coalescing / Sticky Packets):
        Nhiều gói tin đến liên tiếp dính liền nhau trong cùng 1 byte buffer.
        """
        msg1 = {"id": "1", "data": "First"}
        msg2 = {"id": "2", "data": "Second"}
        msg3 = {"id": "3", "data": "Third"}

        # Nối cả 3 gói tin thành 1 stream bytes duy nhất
        stream = pack_message(msg1) + pack_message(msg2) + pack_message(msg3)

        # Tách gói 1
        res1, consumed1 = unpack_message(stream)
        self.assertEqual(res1, msg1)
        stream = stream[consumed1:]

        # Tách gói 2
        res2, consumed2 = unpack_message(stream)
        self.assertEqual(res2, msg2)
        stream = stream[consumed2:]

        # Tách gói 3
        res3, consumed3 = unpack_message(stream)
        self.assertEqual(res3, msg3)
        stream = stream[consumed3:]

        # Buffer rỗng
        self.assertEqual(len(stream), 0)


class TestProtocolSocketCommunication(unittest.TestCase):
    """Kiểm thử truyền nhận socket TCP thực tế giữa Server và Client."""

    def setUp(self) -> None:
        # Tạo socket server trên loopback port ngẫu nhiên
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.bind(("127.0.0.1", 0))
        self.server_sock.listen(1)
        self.port = self.server_sock.getsockname()[1]

    def tearDown(self) -> None:
        try:
            self.server_sock.close()
        except OSError:
            pass

    def test_socket_end_to_end_transmission(self) -> None:
        """Kiểm tra gửi và nhận gói tin qua socket TCP thực tế."""
        server_received: dict = {}

        def server_thread_func() -> None:
            conn, _ = self.server_sock.accept()
            try:
                msg = recv_message(conn)
                server_received["data"] = msg
                # Phản hồi lại
                resp = create_response(request_id=msg["id"], payload=msg["payload"], status="ok")
                send_message(conn, resp)
            finally:
                conn.close()

        server_thread = threading.Thread(target=server_thread_func)
        server_thread.start()

        client_sock = socket.create_connection(("127.0.0.1", self.port), timeout=5.0)
        req = create_request(request_id="test-001", request_type="echo", payload="Sample payload 123")
        bytes_sent = send_message(client_sock, req)
        self.assertGreater(bytes_sent, 0)

        response = recv_message(client_sock)
        client_sock.close()
        server_thread.join()

        self.assertEqual(server_received["data"], req)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["id"], "test-001")
        self.assertEqual(response["payload"], "Sample payload 123")

    def test_socket_fragmentation_resilience(self) -> None:
        """Kiểm tra khả năng chống chịu hiện tượng phân mảnh gói tin TCP (Fragmentation).
        Bên gửi cố tình chia nhỏ gói tin và gửi từng chunk 3 bytes qua socket.
        Bên nhận (recv_message) phải tái tạo nguyên vẹn gói tin.
        """
        original = {
            "id": "frag-test",
            "type": "fragmentation_check",
            "payload": "A" * 1500,  # 1.5 KB payload
        }
        packed = pack_message(original)
        received_by_server: dict = {}

        def server_thread_func() -> None:
            conn, _ = self.server_sock.accept()
            try:
                msg = recv_message(conn)
                received_by_server["msg"] = msg
            finally:
                conn.close()

        server_thread = threading.Thread(target=server_thread_func)
        server_thread.start()

        client_sock = socket.create_connection(("127.0.0.1", self.port), timeout=5.0)

        # Cố ý chia thành từng phần nhỏ 5 bytes để mô phỏng phân mảnh mạng
        chunk_size = 5
        for i in range(0, len(packed), chunk_size):
            client_sock.sendall(packed[i : i + chunk_size])
            time.sleep(0.001)  # Giãn cách siêu nhỏ để ép TCP tách gói

        client_sock.close()
        server_thread.join()

        self.assertEqual(received_by_server.get("msg"), original)

    def test_socket_clean_eof_handling(self) -> None:
        """Kiểm tra xử lý khi Client ngắt kết nối sạch (0 byte)."""
        def server_thread_func() -> None:
            conn, _ = self.server_sock.accept()
            try:
                # allow_eof=True thì trả về None
                msg = recv_message(conn, allow_eof=True)
                self.assertIsNone(msg)
            finally:
                conn.close()

        server_thread = threading.Thread(target=server_thread_func)
        server_thread.start()

        client_sock = socket.create_connection(("127.0.0.1", self.port), timeout=5.0)
        # Client không gửi gì và đóng ngay
        client_sock.close()

        server_thread.join()

    def test_socket_unexpected_eof_mid_payload(self) -> None:
        """Kiểm tra xử lý khi Client ngắt kết nối đột ngột khi đang truyền dở payload."""
        server_exception = {}

        def server_thread_func() -> None:
            conn, _ = self.server_sock.accept()
            try:
                recv_message(conn)
            except ConnectionClosedError as e:
                server_exception["error"] = e
            finally:
                conn.close()

        server_thread = threading.Thread(target=server_thread_func)
        server_thread.start()

        client_sock = socket.create_connection(("127.0.0.1", self.port), timeout=5.0)
        # Gửi header báo 100 bytes nhưng chỉ gửi 10 bytes rồi đóng socket
        bad_packet = struct.pack(HEADER_FORMAT, 100) + b"1234567890"
        client_sock.sendall(bad_packet)
        client_sock.close()

        server_thread.join()

        self.assertIn("error", server_exception)
        self.assertIsInstance(server_exception["error"], ConnectionClosedError)


class TestMessageFactories(unittest.TestCase):
    """Kiểm thử các hàm khởi tạo message chuẩn."""

    def test_create_request_compatibility(self) -> None:
        """create_request phải chứa cả 'id' và 'requestId' để tương thích ngược."""
        req = create_request(request_id="client-42-10", request_type="echo", payload="data")
        self.assertEqual(req["id"], "client-42-10")
        self.assertEqual(req["requestId"], "client-42-10")
        self.assertEqual(req["type"], "echo")
        self.assertEqual(req["payload"], "data")

    def test_create_response_compatibility(self) -> None:
        """create_response phải hỗ trợ đầy đủ các trường kiểm thử của Load Generator."""
        resp = create_response(request_id="client-42-10", payload="data", status="ok")
        self.assertEqual(resp["id"], "client-42-10")
        self.assertEqual(resp["requestId"], "client-42-10")
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["payload"], "data")
        self.assertNotIn("error", resp)

        err_resp = create_response(request_id="client-42-10", status="error", error="Payload too big")
        self.assertEqual(err_resp["status"], "error")
        self.assertEqual(err_resp["error"], "Payload too big")


if __name__ == "__main__":
    unittest.main()
