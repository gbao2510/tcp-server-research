"""TCP Server xử lý nhiều Client đồng thời bằng mô hình Thread Pool.

Core Server Dev: Ngô Gia Bảo
Protocol Integration: Nguyễn Gia Bảo (Protocol Dev)
"""
from __future__ import annotations

import argparse
import logging
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Đảm bảo import được protocol dù chạy từ thư mục nào
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from protocol import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    MAX_PAYLOAD_SIZE,
    ConnectionClosedError,
    InvalidMessageError,
    MessageTooLargeError,
    create_response,
    recv_message,
    send_message,
)

# Cấu hình log để theo dõi trên Terminal
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(threadName)s - %(message)s")

HOST = DEFAULT_HOST
PORT = DEFAULT_PORT
MAX_WORKERS = 100


def handle_client(conn: socket.socket, addr: tuple[str, int]) -> None:
    """Xử lý từng Client độc lập thông qua mô-đun protocol chuẩn Length-Prefix + JSON."""
    logging.info(f"[+] Client kết nối: {addr}")
    conn.settimeout(DEFAULT_TIMEOUT)

    try:
        while True:
            # Nhận và bóc tách gói tin theo giao thức
            try:
                request = recv_message(conn, allow_eof=False, max_payload_size=MAX_PAYLOAD_SIZE)
            except ConnectionClosedError:
                # Client chủ động đóng kết nối sạch
                break
            except (MessageTooLargeError, InvalidMessageError) as err:
                logging.warning(f"[-] Lỗi gói tin từ {addr}: {err}")
                break

            # Trích xuất dữ liệu request (hỗ trợ cả id và requestId)
            req_id = request.get("id") or request.get("requestId", "")
            payload = request.get("payload", "")

            # Phản hồi echo chuẩn hóa giao thức
            response = create_response(request_id=req_id, payload=payload, status="ok")
            send_message(conn, response)

    except socket.timeout:
        logging.warning(f"[-] Bị timeout ở kết nối {addr}")
    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
        logging.info(f"[-] Kết nối bị ngắt đột ngột: {addr}")
    except Exception as err:
        logging.error(f"[!] Lỗi không xác định với {addr}: {err}")
    finally:
        conn.close()
        logging.info(f"[-] Đóng kết nối {addr}")


def start_server(host: str = HOST, port: int = PORT, max_workers: int = MAX_WORKERS) -> None:
    """Khởi động TCP Server với Thread Pool."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server_socket.bind((host, port))
    server_socket.listen(max_workers)

    logging.info(f"[*] Server đang chạy tại {host}:{port} (Max Workers: {max_workers})")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        try:
            while True:
                conn, addr = server_socket.accept()
                executor.submit(handle_client, conn, addr)
        except KeyboardInterrupt:
            logging.info("\n[*] Đang tắt Server...")
        finally:
            server_socket.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="TCP Multi-threaded Server")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host bind (mặc định: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Cổng lắng nghe (mặc định: {DEFAULT_PORT})")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help=f"Số luồng tối đa trong Pool (mặc định: {MAX_WORKERS})")
    args = parser.parse_args()

    start_server(args.host, args.port, args.workers)


if __name__ == "__main__":
    main()
