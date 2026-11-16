"""Script kiểm thử Prototype: Client kết nối thử vào TCP Server và đo lường số liệu ban đầu.
Cách chạy:
    python prototype_test.py
    python prototype_test.py --requests 50 --host 127.0.0.1 --port 9000
"""
from __future__ import annotations

import argparse
import random
import socket
import string
import sys
import threading
import time
from pathlib import Path

# Đảm bảo đường dẫn import
ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
for d in (str(ROOT_DIR), str(SRC_DIR)):
    if d not in sys.path:
        sys.path.insert(0, d)

from client import Client
from protocol.protocol import ProtocolError
from src.metrics import CpuMonitor, Sample, format_summary, summarize, write_csv
from src.server.server import HOST as DEFAULT_HOST, PORT as DEFAULT_PORT, handle_client

PAYLOAD_1KB = "".join(random.choices(string.ascii_letters + string.digits, k=1024))


def is_server_listening(host: str, port: int) -> bool:
    """Kiểm tra xem Server đã lắng nghe trên port chưa."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def run_ephemeral_server(host: str, port: int, stop_event: threading.Event) -> None:
    """Khởi động Server ngầm phục vụ kiểm thử prototype nếu server chưa bật."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(10)
    srv.settimeout(0.5)

    while not stop_event.is_set():
        try:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
        except socket.timeout:
            continue
        except OSError:
            break
    srv.close()


def run_prototype(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    num_requests: int = 20,
    output_csv: Path | None = None,
) -> int:
    print("=" * 60)
    print("       KIỂM THỬ KẾT NỐI PROTOTYPE (METRICS & TEST SCRIPT DEV)")
    print("=" * 60)

    # 1. Kiểm tra Server
    stop_server_event = threading.Event()
    server_thread = None
    if not is_server_listening(host, port):
        print(f"[*] Chưa phát hiện Server tại {host}:{port}. Đang khởi động Server test ngầm...")
        server_thread = threading.Thread(
            target=run_ephemeral_server,
            args=(host, port, stop_server_event),
            daemon=True,
        )
        server_thread.start()
        time.sleep(0.5)
        if not is_server_listening(host, port):
            print(f"[!] Không thể khởi động Server test tại {host}:{port}. Vui lòng chạy server thủ công!")
            return 1
        print(f"[+] Server test ngầm đã sẵn sàng tại {host}:{port}")
    else:
        print(f"[+] Phát hiện Server đang chạy tại {host}:{port}")

    # 2. Khởi động CPU Monitor
    cpu_monitor = CpuMonitor(interval=0.1)
    cpu_monitor.start()

    # 3. Kết nối Client và gửi request đo đạc
    client = Client(host=host, port=port, timeout=5.0)
    samples: list[Sample] = []
    t_start_total = time.perf_counter()

    try:
        print(f"[*] Đang kết nối Client tới Server {host}:{port}...")
        client.connect()
        print("[+] Kết nối TCP thành công! Bắt đầu gửi request đo kiểm...\n")

        for seq in range(num_requests):
            req_id = f"prototype-cli-{seq}"
            req_data = {
                "id": req_id,
                "type": "echo",
                "payload": PAYLOAD_1KB,
            }

            t_req_start = time.perf_counter()
            ok = True
            err_msg = ""

            try:
                resp = client.request(req_data)
                if resp.get("status") != "ok":
                    ok = False
                    err_msg = f"status_not_ok:{resp.get('status')}"
                elif resp.get("id") != req_id:
                    ok = False
                    err_msg = "response_id_mismatch"
                elif resp.get("payload") != PAYLOAD_1KB:
                    ok = False
                    err_msg = "payload_content_mismatch"
            except (OSError, ProtocolError) as e:
                ok = False
                err_msg = f"{type(e).__name__}: {e}"

            t_req_end = time.perf_counter()
            latency_ms = (t_req_end - t_req_start) * 1000.0

            sample = Sample(
                client_id=1,
                seq=seq,
                t_start=t_req_start - t_start_total,
                latency_ms=latency_ms,
                ok=ok,
                error=err_msg,
            )
            samples.append(sample)

            status_icon = "✓" if ok else "✗"
            print(f"  [{status_icon}] Req #{seq+1:02d} | RTT: {latency_ms:6.2f} ms | Status: {'OK' if ok else err_msg}")
            time.sleep(0.02)  # Giãn cách 20ms giữa các request

    except Exception as exc:
        print(f"\n[!] Lỗi trong quá trình kiểm thử Client: {exc}")
    finally:
        client.close()
        t_end_total = time.perf_counter()
        elapsed_s = t_end_total - t_start_total
        cpu_stats = cpu_monitor.stop()

        if server_thread:
            stop_server_event.set()
            server_thread.join(timeout=1.0)

    # 4. Tính toán và in báo cáo
    summary = summarize(samples, elapsed_s=elapsed_s)
    print("\n" + format_summary(summary, clients=1, connected=1 if samples else 0))

    print("  GIÁM SÁT CPU:")
    if cpu_stats["available"]:
        backend_desc = "Thư viện psutil" if cpu_stats.get("backend") == "psutil" else "Windows Kernel32 API (Native không cần cài đặt)"
        print(f"    - Cơ chế đo lường    : {backend_desc}")
        print(f"    - Mức CPU trung bình : {cpu_stats['cpu_avg']}%")
        print(f"    - Mức CPU nhỏ nhất   : {cpu_stats['cpu_min']}%")
        print(f"    - Mức CPU lớn nhất   : {cpu_stats['cpu_max']}%")
        print(f"    - Số mẫu thu thập    : {cpu_stats['samples_count']}")
    else:
        print("    - Giám sát CPU không khả dụng trên môi trường này.")
    print("=" * 60)

    # 5. Xuất file CSV
    csv_file = output_csv or (ROOT_DIR / "experiments" / "raw_data" / "prototype_test.csv")
    write_csv(samples, csv_file)
    print(f"\n[+] Đã lưu dữ liệu thô ({len(samples)} mẫu) vào file:\n    -> {csv_file}")

    return 0 if summary["requests_failed"] == 0 and summary["requests_ok"] > 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Script kiểm thử Prototype Client - Server & Đo lường")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Địa chỉ Host (mặc định: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Cổng Port (mặc định: {DEFAULT_PORT})")
    parser.add_argument("--requests", type=int, default=20, help="Số lượng request cần gửi (mặc định: 20)")
    parser.add_argument("--csv", type=Path, default=None, help="Đường dẫn file CSV xuất kết quả")
    args = parser.parse_args()

    return run_prototype(
        host=args.host,
        port=args.port,
        num_requests=args.requests,
        output_csv=args.csv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
