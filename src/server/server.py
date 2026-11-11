import logging
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Đảm bảo import được module protocol
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
SRC_DIR = ROOT_DIR / "src"
for d in (str(ROOT_DIR), str(SRC_DIR)):
    if d not in sys.path:
        sys.path.insert(0, d)

from protocol.protocol import (
    DEFAULT_MAX_PAYLOAD_SIZE,
    FramingError,
    MalformedJSONError,
    PayloadTooLargeError,
    create_response,
    recv_message,
    send_message,
)

# Cấu hình log để dễ theo dõi trên Terminal
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(threadName)s - %(message)s")

HOST = "127.0.0.1"
PORT = 9000
MAX_WORKERS = 100


def handle_client(conn: socket.socket, addr: tuple[str, int]) -> None:
    """Xử lý từng Client độc lập theo chuẩn giao thức Length-Prefix + JSON."""
    logging.info(f"[+] Client kết nối: {addr}")
    conn.settimeout(10.0)

    try:
        while True:
            try:
                request = recv_message(conn, max_size=DEFAULT_MAX_PAYLOAD_SIZE)
            except ConnectionResetError:
                # Client đóng kết nối sạch sẽ (EOF)
                break
            except (FramingError, PayloadTooLargeError, MalformedJSONError) as err:
                logging.warning(f"[-] Gói tin không hợp lệ từ {addr}: {err}")
                break

            req_id = request.get("id")
            req_type = request.get("type", "echo")
            payload = request.get("payload")

            if req_type == "echo":
                response = create_response(request_id=req_id, status="ok", payload=payload)
            else:
                response = create_response(
                    request_id=req_id,
                    status="error",
                    error_message=f"Unsupported request type: {req_type}",
                )

            send_message(conn, response)

    except socket.timeout:
        logging.warning(f"[-] Bị timeout ở kết nối {addr}")
    except Exception as exc:
        logging.error(f"[!] Lỗi phát sinh với {addr}: {exc}")
    finally:
        try:
            conn.close()
        except OSError:
            pass
        logging.info(f"[-] Đóng kết nối {addr}")


def start_server() -> None:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server_socket.bind((HOST, PORT))
    server_socket.listen(100)

    logging.info(f"[*] Server đang chạy tại {HOST}:{PORT}")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        try:
            while True:
                conn, addr = server_socket.accept()
                executor.submit(handle_client, conn, addr)
        except KeyboardInterrupt:
            logging.info("\n[*] Đang tắt Server...")
        finally:
            server_socket.close()


if __name__ == "__main__":
    start_server()
