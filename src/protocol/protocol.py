"""Module Giao thức Truyền thông (Protocol Module) - Protocol Dev.

Cung cấp cơ chế đóng gói (framing) và bóc tách gói tin dựa trên Length-Prefix
kết hợp định dạng JSON UTF-8 cho kết nối TCP, bẫy lỗi dữ liệu rác,
chống tấn công tràn bộ nhớ và giải quyết triệt để hiện tượng dính/xé gói.
"""

from __future__ import annotations

import json
import socket
import struct
from typing import Any

# ==============================================================================
# CẤU HÌNH GIAO THỨC (PROTOCOL CONSTANTS)
# ==============================================================================
# Header: 4 bytes unsigned integer, Big-Endian (Network Byte Order)
HEADER_FORMAT: str = ">I"
HEADER_SIZE: int = struct.calcsize(HEADER_FORMAT)  # 4 bytes

# Giới hạn kích thước payload tối đa (mặc định 2MB, có thể cấu hình tới 10MB)
# Ngăn chặn tấn công cạn kiệt tài nguyên (Memory Exhaustion / DoS) do header giả mạo
DEFAULT_MAX_PAYLOAD_SIZE: int = 2 * 1024 * 1024  # 2MB


# ==============================================================================
# CÁC LỚP NGOẠI LỆ GIAO THỨC (EXCEPTIONS)
# ==============================================================================
class ProtocolError(Exception):
    """Lỗi chung của tầng giao thức (sai định dạng, dữ liệu hỏng, vi phạm quy chuẩn)."""
    pass


class FramingError(ProtocolError):
    """Lỗi liên quan đến cấu trúc khung gói tin (Header, độ dài, ngắt luồng bất thường)."""
    pass


class PayloadTooLargeError(ProtocolError):
    """Lỗi khi gói tin vượt quá kích thước payload tối đa cho phép."""
    pass


class MalformedJSONError(ProtocolError):
    """Lỗi khi payload không thể decode UTF-8 hoặc không thể parse thành JSON hợp lệ."""
    pass


# ==============================================================================
# CÁC HÀM CỐT LÕI (CORE FUNCTIONS)
# ==============================================================================
def encode_message(
    message: dict[str, Any],
    max_size: int = DEFAULT_MAX_PAYLOAD_SIZE,
) -> bytes:
    """Đóng gói một message (dict) thành bytes theo chuẩn Length-Prefix Framing:

    [4 bytes Header: Payload Length (Big-Endian)] + [N bytes Payload JSON (UTF-8)]

    Args:
        message: Dictionary chứa nội dung request hoặc response.
        max_size: Kích thước tối đa cho phép của payload.

    Returns:
        Mảng bytes hoàn chỉnh sẵn sàng gửi qua TCP socket.

    Raises:
        MalformedJSONError: Khi dữ liệu không thể tuần tự hóa sang JSON.
        PayloadTooLargeError: Khi kích thước payload vượt quá max_size.
    """
    if not isinstance(message, dict):
        raise MalformedJSONError(f"Gói tin phải là kiểu dict, nhận được: {type(message).__name__}")

    try:
        payload_bytes = json.dumps(message, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MalformedJSONError(f"Không thể serialize dict sang JSON: {exc}") from exc

    payload_len = len(payload_bytes)
    if payload_len > max_size:
        raise PayloadTooLargeError(
            f"Kích thước gói tin ({payload_len} bytes) vượt quá giới hạn tối đa ({max_size} bytes)"
        )

    header = struct.pack(HEADER_FORMAT, payload_len)
    return header + payload_bytes


def decode_payload(payload_bytes: bytes) -> dict[str, Any]:
    """Bóc tách và parse dữ liệu JSON từ bytes của phần payload.

    Bẫy triệt để các lỗi dữ liệu rác:
    - Không thể giải mã UTF-8 (chuỗi byte rác).
    - Cú pháp JSON bị hỏng / thiếu dấu ngoặc / dữ liệu rác.
    - Dữ liệu JSON không phải dạng Object ({...}).

    Args:
        payload_bytes: Mảng bytes của phần payload đã nhận đủ.

    Returns:
        Dictionary đại diện cho message.

    Raises:
        MalformedJSONError: Khi dữ liệu không phải UTF-8 hoặc JSON hợp lệ.
    """
    try:
        text = payload_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MalformedJSONError(f"Dữ liệu rác: Không thể giải mã chuỗi UTF-8: {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MalformedJSONError(f"Dữ liệu rác: Cú pháp JSON không hợp lệ: {exc}") from exc

    if not isinstance(data, dict):
        raise MalformedJSONError(
            f"Dữ liệu rác: Gói tin phải là JSON Object (dict), nhận được {type(data).__name__}"
        )

    return data


def recv_exact(sock: socket.socket, num_bytes: int) -> bytes:
    """Đọc chính xác `num_bytes` từ socket TCP.

    Giải quyết bản chất stream-oriented của TCP:
    - Gom byte lặp lại khi xảy ra hiện tượng xé gói (packet fragmentation).
    - Bẫy lỗi ngắt kết nối đột ngột giữa chừng.

    Args:
        sock: Socket TCP đang kết nối.
        num_bytes: Số byte cần đọc.

    Returns:
        Mảng bytes có độ dài đúng bằng num_bytes.

    Raises:
        ConnectionResetError: Đối phương chủ động ngắt kết nối sạch trước khi gửi gói mới.
        FramingError: Luồng bị ngắt kết nối khi đang nhận dở gói tin.
    """
    buffer = bytearray()
    while len(buffer) < num_bytes:
        chunk = sock.recv(num_bytes - len(buffer))
        if not chunk:
            if len(buffer) == 0:
                raise ConnectionResetError("Kết nối đã đóng bởi phía đối tác (EOF sạch)")
            raise FramingError(
                f"Mất kết nối đột ngột (xé gói dở dang): cần {num_bytes} bytes nhưng luồng bị ngắt khi mới nhận {len(buffer)} bytes"
            )
        buffer.extend(chunk)
    return bytes(buffer)


# Alias cho recv_exact tương thích với các module khác
recvall = recv_exact


def send_message(
    sock: socket.socket,
    message: dict[str, Any],
    max_size: int = DEFAULT_MAX_PAYLOAD_SIZE,
) -> None:
    """Đóng gói message và gửi toàn bộ qua socket TCP bằng sendall."""
    packet = encode_message(message, max_size=max_size)
    sock.sendall(packet)


def recv_message(
    sock: socket.socket,
    max_size: int = DEFAULT_MAX_PAYLOAD_SIZE,
) -> dict[str, Any]:
    """Nhận và bóc tách một message JSON hoàn chỉnh từ TCP socket:

    1. Đọc đúng 4 bytes Header (Length-Prefix).
    2. Giải mã độ dài và kiểm tra bảo vệ chống tràn bộ nhớ (PayloadTooLargeError).
    3. Đọc đúng số bytes của Payload.
    4. Bẫy lỗi dữ liệu rác (MalformedJSONError) và trả về dict.
    """
    header_bytes = recv_exact(sock, HEADER_SIZE)
    (payload_len,) = struct.unpack(HEADER_FORMAT, header_bytes)

    if payload_len > max_size:
        raise PayloadTooLargeError(
            f"Kích thước gói tin ({payload_len} bytes) vượt quá giới hạn tối đa ({max_size} bytes)"
        )

    payload_bytes = recv_exact(sock, payload_len)
    return decode_payload(payload_bytes)


# ==============================================================================
# BỘ GIẢI MÃ DẠNG STREAM (STREAMING DECODER / MESSAGE BUFFER)
# Phục vụ kiểm thử dính gói (coalescing) và hỗ trợ kiến trúc non-blocking/buffers
# ==============================================================================
class MessageBuffer:
    """Bộ đệm dữ liệu stream TCP để bóc tách từng gói tin Length-Prefix.

    Rất hữu ích khi nhận buffer chứa nhiều gói tin dính nhau (coalescing)
    hoặc nhận các mảnh vụn nhỏ (fragmentation).
    """

    def __init__(self, max_size: int = DEFAULT_MAX_PAYLOAD_SIZE) -> None:
        self.buffer = bytearray()
        self.max_size = max_size

    def feed(self, chunk: bytes) -> None:
        """Đưa thêm dữ liệu nhận được từ socket vào buffer."""
        self.buffer.extend(chunk)

    def next_message(self) -> dict[str, Any] | None:
        """Trích xuất gói tin hoàn chỉnh tiếp theo từ buffer nếu có.

        Returns:
            dict message nếu đã đủ 1 gói tin hoàn chỉnh, hoặc None nếu chưa đủ byte.
        """
        if len(self.buffer) < HEADER_SIZE:
            return None

        (payload_len,) = struct.unpack(HEADER_FORMAT, self.buffer[:HEADER_SIZE])
        if payload_len > self.max_size:
            raise PayloadTooLargeError(
                f"Kích thước gói tin ({payload_len} bytes) vượt quá giới hạn tối đa ({self.max_size} bytes)"
            )

        total_packet_len = HEADER_SIZE + payload_len
        if len(self.buffer) < total_packet_len:
            return None  # Chưa gom đủ payload

        # Lấy payload và loại bỏ gói tin đã bóc khỏi buffer
        payload_bytes = bytes(self.buffer[HEADER_SIZE:total_packet_len])
        del self.buffer[:total_packet_len]

        return decode_payload(payload_bytes)


# ==============================================================================
# HÀM BỔ TRỢ TẠO CHUẨN GÓI TIN (MESSAGE BUILDERS)
# Giúp đồng bộ giữa Client và Server
# ==============================================================================
def create_request(request_id: str, req_type: str = "echo", payload: Any = "") -> dict[str, Any]:
    """Tạo request chuẩn theo định dạng đồ án."""
    return {
        "id": request_id,
        "type": req_type,
        "payload": payload,
    }


def create_response(
    request_id: str,
    status: str = "ok",
    payload: Any = "",
    error_message: str | None = None,
) -> dict[str, Any]:
    """Tạo response chuẩn theo định dạng đồ án."""
    res: dict[str, Any] = {
        "id": request_id,
        "status": status,
        "payload": payload,
    }
    if error_message is not None:
        res["error"] = error_message
    return res
