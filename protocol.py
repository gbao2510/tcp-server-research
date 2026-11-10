"""Mô-đun Giao thức Truyền thông (Protocol Module) - Đồ án Khảo sát TCP Server.

Vai trò: Protocol Dev (Nguyễn Gia Bảo - MSSV: 075206006255)
Đặc tả giao thức: Length-Prefix (4 bytes Big-Endian) + UTF-8 JSON Payload.

Module này cung cấp:
1. Các hằng số chuẩn giao thức (HEADER_SIZE, HEADER_FORMAT, MAX_PAYLOAD_SIZE, DEFAULT_PORT).
2. Các ngoại lệ chuẩn cho tầng giao thức (ProtocolError, ConnectionClosedError, MessageTooLargeError, InvalidMessageError).
3. Các hàm bóc tách và đóng gói gói tin (pack_message, unpack_message, recvall, send_message, recv_message).
4. Các hàm helper khởi tạo thông điệp chuẩn (create_request, create_response).
"""

from __future__ import annotations

import json
import socket
import struct
from typing import Any

# ==============================================================================
# HẰNG SỐ GIAO THỨC (PROTOCOL CONSTANTS)
# ==============================================================================

# Kích thước header độ dài: 4 bytes (unsigned 32-bit integer, Big-Endian)
HEADER_SIZE: int = 4
HEADER_FORMAT: str = "!I"  # Chuẩn Network Byte Order (Big-Endian)

# Giới hạn kích thước payload tối đa: 2 MB (chống DoS / tràn bộ nhớ OOM)
MAX_PAYLOAD_SIZE: int = 2 * 1024 * 1024

# Cấu hình mặc định hệ thống
DEFAULT_HOST: str = "127.0.0.1"
DEFAULT_PORT: int = 9999
DEFAULT_TIMEOUT: float = 10.0


# ==============================================================================
# ĐỊNH NGHĨA NGOẠI LỆ (PROTOCOL EXCEPTIONS)
# ==============================================================================

class ProtocolError(Exception):
    """Lớp cơ sở cho tất cả các lỗi xảy ra ở tầng giao thức (Protocol Layer)."""
    pass


class ConnectionClosedError(ProtocolError):
    """Ném ra khi kết nối TCP bị đóng sạch (EOF) hoặc bị ngắt đột ngột."""
    pass


class MessageTooLargeError(ProtocolError):
    """Ném ra khi kích thước gói tin vượt quá giới hạn an toàn cho phép (MAX_PAYLOAD_SIZE)."""
    pass


class InvalidMessageError(ProtocolError):
    """Ném ra khi gói tin không thể mã hóa hoặc giải mã (lỗi định dạng JSON, UTF-8 hoặc kiểu dữ liệu)."""
    pass


class ProtocolTimeoutError(ProtocolError):
    """Ném ra khi socket bị timeout trong quá trình nhận/gửi dữ liệu gói tin."""
    pass


# ==============================================================================
# CÁC HÀM ĐÓNG GÓI VÀ BÓC TÁCH (PACKING / UNPACKING)
# ==============================================================================

def pack_message(
    message: dict[str, Any],
    max_payload_size: int = MAX_PAYLOAD_SIZE,
) -> bytes:
    """
    Đóng gói một Python dict thành chuỗi bytes theo chuẩn Length-Prefix:
    [ 4-byte Big-Endian Length Header ][ UTF-8 JSON Payload ]

    Args:
        message: Dict dữ liệu cần đóng gói.
        max_payload_size: Giới hạn kích thước payload tối đa.

    Returns:
        bytes: Gói tin nhị phân hoàn chỉnh gồm 4 bytes header và payload UTF-8 JSON.

    Raises:
        InvalidMessageError: Nếu message không phải là dict hoặc không thể serialize thành JSON.
        MessageTooLargeError: Nếu payload sau khi mã hóa UTF-8 vượt quá max_payload_size.
    """
    if not isinstance(message, dict):
        raise InvalidMessageError(
            f"Message phải là kiểu dict, nhận được: {type(message).__name__}"
        )

    try:
        json_bytes = json.dumps(message, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as err:
        raise InvalidMessageError(f"Không thể serialize đối tượng sang JSON: {err}") from err

    payload_len = len(json_bytes)
    if payload_len > max_payload_size:
        raise MessageTooLargeError(
            f"Kích thước payload ({payload_len} bytes) vượt quá giới hạn cho phép ({max_payload_size} bytes)."
        )

    header = struct.pack(HEADER_FORMAT, payload_len)
    return header + json_bytes


def unpack_message(
    buffer: bytes | bytearray,
    max_payload_size: int = MAX_PAYLOAD_SIZE,
) -> tuple[dict[str, Any] | None, int]:
    """
    Bóc tách 1 thông điệp từ raw buffer. Hỗ trợ xử lý buffer stream và giải quyết hiện tượng dính gói (coalescing).

    Args:
        buffer: Vùng đệm nhị phân chứa dữ liệu nhận được.
        max_payload_size: Giới hạn kích thước payload tối đa.

    Returns:
        tuple (message_dict, bytes_consumed):
            - Nếu đã có đủ một gói tin hoàn chỉnh: (dict, số byte đã tiêu thụ).
            - Nếu buffer chưa đủ (chưa đủ header 4 bytes hoặc chưa đủ độ dài payload): (None, 0).

    Raises:
        MessageTooLargeError: Nếu header thông báo kích thước vượt quá max_payload_size.
        InvalidMessageError: Nếu payload không phải UTF-8 hợp lệ hoặc không phải JSON Object.
    """
    buf_len = len(buffer)
    if buf_len < HEADER_SIZE:
        return None, 0

    payload_len = struct.unpack(HEADER_FORMAT, buffer[:HEADER_SIZE])[0]
    if payload_len > max_payload_size:
        raise MessageTooLargeError(
            f"Kích thước gói tin ({payload_len} bytes) vượt quá giới hạn an toàn ({max_payload_size} bytes)."
        )

    total_packet_len = HEADER_SIZE + payload_len
    if buf_len < total_packet_len:
        # Chưa nhận đủ toàn bộ payload của gói tin hiện tại
        return None, 0

    payload_bytes = buffer[HEADER_SIZE:total_packet_len]

    try:
        decoded_text = payload_bytes.decode("utf-8")
    except UnicodeDecodeError as err:
        raise InvalidMessageError(f"Payload không phải chuỗi UTF-8 hợp lệ: {err}") from err

    try:
        message = json.loads(decoded_text)
    except json.JSONDecodeError as err:
        raise InvalidMessageError(f"Payload không phải định dạng JSON hợp lệ: {err}") from err

    if not isinstance(message, dict):
        raise InvalidMessageError(
            f"Nội dung gói tin phải là một JSON Object (dict), nhận được: {type(message).__name__}"
        )

    return message, total_packet_len


# ==============================================================================
# CÁC HÀM GIAO TIẾP QUA SOCKET (SOCKET COMMUNICATION)
# ==============================================================================

def recvall(sock: socket.socket, n: int) -> bytes:
    """
    Đảm bảo đọc chính xác n byte từ socket TCP.
    Giải quyết triệt để vấn đề phân mảnh gói tin (fragmentation) của luồng TCP.

    Args:
        sock: Socket TCP đang kết nối.
        n: Số lượng byte chính xác cần nhận.

    Returns:
        bytes: Đúng n byte dữ liệu nhận được.

    Raises:
        ConnectionClosedError: Nếu kết nối bị đóng trước khi nhận đủ n byte.
        socket.timeout: Nếu socket bị timeout khi đang đọc.
    """
    data = bytearray()
    while len(data) < n:
        try:
            packet = sock.recv(n - len(data))
        except socket.timeout:
            raise
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as err:
            raise ConnectionClosedError(f"Kết nối bị ngắt do lỗi mạng: {err}") from err

        if not packet:
            if len(data) == 0:
                raise ConnectionClosedError("Kết nối đã bị đóng bởi phía đối diện (EOF sạch).")
            raise ConnectionClosedError(
                f"Kết nối bị ngắt bất ngờ khi đang nhận gói tin (nhận được {len(data)}/{n} bytes)."
            )
        data.extend(packet)
    return bytes(data)


def send_message(
    sock: socket.socket,
    message: dict[str, Any],
    max_payload_size: int = MAX_PAYLOAD_SIZE,
) -> int:
    """
    Đóng gói message thành [4-byte length][JSON payload] và gửi toàn bộ qua socket.

    Args:
        sock: Socket TCP đang kết nối.
        message: Dict dữ liệu cần gửi.
        max_payload_size: Giới hạn kích thước payload tối đa.

    Returns:
        int: Tổng số byte đã gửi thành công (header + payload).

    Raises:
        InvalidMessageError: Nếu message không hợp lệ để đóng gói.
        MessageTooLargeError: Nếu payload vượt quá giới hạn kích thước.
        ConnectionClosedError: Nếu đối phương đóng kết nối trong lúc gửi.
        OSError: Nếu xảy ra lỗi socket.
    """
    packet_bytes = pack_message(message, max_payload_size=max_payload_size)
    try:
        sock.sendall(packet_bytes)
    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as err:
        raise ConnectionClosedError(f"Kết nối bị ngắt khi đang gửi dữ liệu: {err}") from err
    return len(packet_bytes)


def recv_message(
    sock: socket.socket,
    allow_eof: bool = False,
    max_payload_size: int = MAX_PAYLOAD_SIZE,
) -> dict[str, Any] | None:
    """
    Nhận và giải mã hoàn chỉnh một gói tin Length-Prefix + JSON từ socket TCP.

    Args:
        sock: Socket TCP đang kết nối.
        allow_eof: Nếu True, trả về None khi đối phương đóng kết nối sạch (0 byte ở đầu gói).
                   Nếu False (mặc định), ném ConnectionClosedError.
        max_payload_size: Giới hạn kích thước payload tối đa.

    Returns:
        dict[str, Any] | None: Dict dữ liệu nhận được, hoặc None nếu allow_eof=True và kết nối đóng sạch.

    Raises:
        ConnectionClosedError: Nếu kết nối bị đóng (khi allow_eof=False hoặc đóng giữa chừng).
        MessageTooLargeError: Nếu header khai báo payload vượt quá max_payload_size.
        InvalidMessageError: Nếu payload không phải UTF-8 hoặc không phải JSON Object.
        socket.timeout: Nếu socket timeout trong khi chờ dữ liệu.
    """
    try:
        raw_header = recvall(sock, HEADER_SIZE)
    except ConnectionClosedError as err:
        if allow_eof and "EOF sạch" in str(err):
            return None
        raise

    payload_len = struct.unpack(HEADER_FORMAT, raw_header)[0]
    if payload_len > max_payload_size:
        raise MessageTooLargeError(
            f"Kích thước gói tin ({payload_len} bytes) vượt quá giới hạn an toàn ({max_payload_size} bytes)."
        )

    raw_payload = recvall(sock, payload_len)

    try:
        decoded_text = raw_payload.decode("utf-8")
    except UnicodeDecodeError as err:
        raise InvalidMessageError(f"Payload không phải chuỗi UTF-8 hợp lệ: {err}") from err

    try:
        message = json.loads(decoded_text)
    except json.JSONDecodeError as err:
        raise InvalidMessageError(f"Payload không phải định dạng JSON hợp lệ: {err}") from err

    if not isinstance(message, dict):
        raise InvalidMessageError(
            f"Nội dung gói tin phải là một JSON Object (dict), nhận được: {type(message).__name__}"
        )

    return message


# ==============================================================================
# HÀM TIỆN ÍCH TẠO THÔNG ĐIỆP (MESSAGE BUILDERS)
# ==============================================================================

def create_request(
    request_id: str | int,
    request_type: str = "echo",
    payload: Any = "",
) -> dict[str, Any]:
    """
    Tạo thông điệp Request chuẩn hóa.
    Đồng thời hỗ trợ cả trường 'id' và 'requestId' để đảm bảo tương thích 100%
    giữa Load Generator của Gia Bân và Server của Ngô Gia Bảo.

    Format:
        {
            "id": "<request_id>",
            "requestId": "<request_id>",
            "type": "<request_type>",
            "payload": <payload>
        }
    """
    str_id = str(request_id)
    return {
        "id": str_id,
        "requestId": str_id,
        "type": request_type,
        "payload": payload,
    }


def create_response(
    request_id: str | int,
    payload: Any = "",
    status: str = "ok",
    error: str | None = None,
) -> dict[str, Any]:
    """
    Tạo thông điệp Response chuẩn hóa.
    Đồng thời hỗ trợ cả trường 'id' và 'requestId', 'status' ('ok' / 'success')
    để đảm bảo tương thích 100% với Client Load Generator và Core Server.

    Format:
        {
            "id": "<request_id>",
            "requestId": "<request_id>",
            "status": "ok",
            "payload": <payload>,
            "error": <error_msg_or_None>
        }
    """
    str_id = str(request_id)
    res: dict[str, Any] = {
        "id": str_id,
        "requestId": str_id,
        "status": status,
        "payload": payload,
    }
    if error is not None:
        res["error"] = error
    return res
