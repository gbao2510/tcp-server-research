"""Script tự động chạy thực nghiệm và xuất toàn bộ dữ liệu thô ra file CSV/JSON.
Tác giả: Trần Trung Trực (Metrics & Test Script Dev).

Nhiệm vụ (Giai đoạn 15/11 - 18/11):
1. Viết script tự động chạy các mức Client (1, 10, 50).
2. Lưu toàn bộ dữ liệu thô (thời gian phản hồi, CPU) ra file CSV/JSON vào thư mục `experiments/raw_data/`.
"""

from __future__ import annotations

# Import các thư viện chuẩn của Python
import argparse
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

# Xác định đường dẫn thư mục gốc của dự án (Project Root)
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parent.parent.parent
SRC_DIR = ROOT_DIR / "src"

# Thêm đường dẫn vào sys.path để Python tìm thấy các module trong dự án
for directory in (str(ROOT_DIR), str(SRC_DIR)):
    if directory not in sys.path:
        sys.path.insert(0, directory)

# Import các module đã xây dựng trong dự án
from client import Client
from src.metrics import (
    CpuMonitor,
    Sample,
    export_all_raw_data,
    format_summary,
    summarize,
    write_cpu_csv,
    write_cpu_json,
    write_csv,
    write_json,
)
from src.server.server import HOST as DEFAULT_HOST, PORT as DEFAULT_PORT, handle_client

# Định nghĩa kích thước payload gửi đi là 1KB (1024 bytes) theo quy định của đồ án
PAYLOAD_1KB = "X" * 1024


def check_server_online(host: str, port: int) -> bool:
    """Hàm kiểm tra xem TCP Server có đang hoạt động trên địa chỉ IP và Port không."""
    # Tạo một socket TCP (AF_INET là IPv4, SOCK_STREAM là TCP)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # Đặt timeout ngắn 0.5s để kiểm tra nhanh
        s.settimeout(0.5)
        # connect_ex trả về 0 nếu kết nối thành công (server đang mở)
        return s.connect_ex((host, port)) == 0


def start_test_server(host: str, port: int, stop_flag: threading.Event) -> None:
    """Hàm chạy Server tạm thời phục vụ đo lường nếu người dùng chưa bật server trước."""
    # Tạo socket server
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Cho phép tái sử dụng địa chỉ ngay lập tức tránh lỗi Address already in use
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Gắn socket với IP và Port
    server_sock.bind((host, port))
    # Bắt đầu lắng nghe kết nối, hàng đợi tối đa 100 kết nối
    server_sock.listen(100)
    # Đặt timeout cho accept để luồng có thể dừng khi có tín hiệu stop_flag
    server_sock.settimeout(0.5)

    # Vòng lặp lắng nghe kết nối cho đến khi có tín hiệu dừng
    while not stop_flag.is_set():
        try:
            # Chấp nhận kết nối từ client
            conn, addr = server_sock.accept()
            # Khởi chạy một thread mới để xử lý request từ client này
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
        except socket.timeout:
            # Hết thời gian chờ 0.5s mà không có client nào thì lặp lại để kiểm tra stop_flag
            continue
        except OSError:
            # Bị lỗi socket thì thoát vòng lặp
            break

    # Đóng socket khi hoàn tất
    server_sock.close()


def run_single_client_worker(
    client_id: int,
    host: str,
    port: int,
    num_requests: int,
    all_samples: list[Sample],
    samples_lock: threading.Lock,
    start_barrier: threading.Barrier,
    t_benchmark_start: float,
) -> None:
    """Hàm worker xử lý cho từng Client: gửi request và đo thời gian phản hồi (Latency)."""
    # Khởi tạo đối tượng Client với timeout 5 giây
    client = Client(host=host, port=port, timeout=5.0)

    try:
        # Kết nối tới TCP Server
        client.connect()
    except Exception as e:
        # Nếu không kết nối được thì ghi nhận mẫu lỗi
        with samples_lock:
            all_samples.append(
                Sample(
                    client_id=client_id,
                    seq=0,
                    t_start=time.perf_counter() - t_benchmark_start,
                    latency_ms=0.0,
                    ok=False,
                    error=f"ConnectError: {e}",
                )
            )
        return

    # Chờ tất cả các client sẵn sàng để cùng xuất phát đồng thời
    try:
        start_barrier.wait()
    except threading.BrokenBarrierError:
        client.close()
        return

    # Gửi lần lượt các request theo số lượng chỉ định
    for seq in range(num_requests):
        req_id = f"cli_{client_id}_req_{seq}"
        req_data = {
            "id": req_id,
            "type": "echo",
            "payload": PAYLOAD_1KB,
        }

        # Ghi lại mốc thời gian bắt đầu gửi request
        t_req_start = time.perf_counter()
        ok = True
        err_msg = ""

        try:
            # Gửi dữ liệu và chờ phản hồi từ server
            resp = client.request(req_data)
            # Kiểm tra phản hồi có đúng chuẩn không
            if resp.get("status") != "ok":
                ok = False
                err_msg = f"status_{resp.get('status')}"
            elif resp.get("id") != req_id:
                ok = False
                err_msg = "id_mismatch"
        except Exception as exc:
            # Nếu gặp lỗi mạng hoặc ngắt kết nối
            ok = False
            err_msg = f"{type(exc).__name__}: {exc}"

        # Ghi lại mốc thời gian nhận được phản hồi
        t_req_end = time.perf_counter()
        # Tính độ trễ RTT (Round Trip Time) đổi sang đơn vị mili-giây (ms)
        latency_ms = (t_req_end - t_req_start) * 1000.0

        # Tạo đối tượng Sample chứa kết quả đo của request này
        sample = Sample(
            client_id=client_id,
            seq=seq,
            t_start=t_req_start - t_benchmark_start,
            latency_ms=latency_ms,
            ok=ok,
            error=err_msg,
        )

        # Lưu mẫu đo vào danh sách chung (sử dụng Lock để đảm bảo thread-safe)
        with samples_lock:
            all_samples.append(sample)

        # Nghỉ nhẹ 5ms giữa các request để mô phỏng khoảng cách truy cập thực tế
        time.sleep(0.005)

    # Đóng kết nối của client sau khi gửi xong
    client.close()


def run_scenario(
    num_clients: int,
    requests_per_client: int,
    host: str,
    port: int,
    raw_data_dir: Path,
) -> dict:
    """Hàm thực thi 1 kịch bản đo lường với số lượng client cụ thể và lưu dữ liệu thô."""
    scenario_name = f"{num_clients}_clients"
    print("\n" + "=" * 65)
    print(f"[*] BẮT ĐẦU KỊCH BẢN: {num_clients} CLIENT ĐỒNG THỜI ({requests_per_client} req/client)")
    print("=" * 65)

    # 1. Khởi động công cụ theo dõi CPU
    # Đo CPU mỗi 0.1 giây (100ms) để có dữ liệu chi tiết
    cpu_monitor = CpuMonitor(interval=0.1)
    cpu_monitor.start()

    # 2. Chuẩn bị danh sách lưu trữ mẫu đo và Barrier đồng bộ luồng
    all_samples: list[Sample] = []
    samples_lock = threading.Lock()
    barrier = threading.Barrier(num_clients)

    # 3. Tạo các luồng (thread) cho từng Client
    threads: list[threading.Thread] = []
    t_benchmark_start = time.perf_counter()

    for cid in range(1, num_clients + 1):
        t = threading.Thread(
            target=run_single_client_worker,
            args=(
                cid,
                host,
                port,
                requests_per_client,
                all_samples,
                samples_lock,
                barrier,
                t_benchmark_start,
            ),
            name=f"ClientThread-{cid}",
        )
        threads.append(t)
        t.start()

    # Chờ tất cả các client hoàn thành việc gửi request
    for t in threads:
        t.join()

    # Tính tổng thời gian chạy kịch bản
    t_benchmark_end = time.perf_counter()
    total_elapsed_s = t_benchmark_end - t_benchmark_start

    # 4. Dừng theo dõi CPU và lấy thống kê CPU
    cpu_stats = cpu_monitor.stop()

    # 5. Sắp xếp lại các mẫu đo theo thứ tự thời gian gửi
    all_samples.sort(key=lambda s: s.t_start)

    # 6. Tính toán các chỉ số thống kê (Throughput, Latency avg, p95, p99...)
    summary = summarize(all_samples, elapsed_s=total_elapsed_s)
    # Bổ sung thông tin CPU vào bản tóm tắt
    summary["cpu"] = cpu_stats
    summary["clients"] = num_clients

    # 7. In tóm tắt kết quả kịch bản ra màn hình
    print(format_summary(summary, clients=num_clients, connected=num_clients))
    print(f"  Mức sử dụng CPU trung bình: {cpu_stats.get('cpu_avg', 0)}% (Min: {cpu_stats.get('cpu_min', 0)}%, Max: {cpu_stats.get('cpu_max', 0)}%)")
    print(f"  Số mẫu CPU thu thập được  : {cpu_stats.get('samples_count', 0)} mẫu")

    # 8. XUẤT TOÀN BỘ DỮ LIỆU THÔ RA CẢ FILE CSV VÀ FILE JSON (Nhiệm vụ của Trần Trung Trực - Metrics Dev)
    saved_files = export_all_raw_data(
        output_dir=raw_data_dir,
        scenario_name=scenario_name,
        samples=all_samples,
        cpu_monitor=cpu_monitor,
        summary=summary,
    )

    print("\n[+] ĐÃ LƯU DỮ LIỆU THÔ RA THƯ MỤC 'experiments/raw_data/':")
    print(f"    - File CSV độ trễ request : {saved_files['latency_csv'].name}")
    print(f"    - File JSON độ trễ request: {saved_files['latency_json'].name}")
    print(f"    - File CSV dữ liệu CPU    : {saved_files['cpu_csv'].name}")
    print(f"    - File JSON dữ liệu CPU   : {saved_files['cpu_json'].name}")
    print(f"    - File JSON tóm tắt       : {saved_files['summary_json'].name}")

    return summary


def main() -> int:
    """Hàm điều khiển chính: Quản lý server và chạy tự động các kịch bản 1, 10, 50 clients."""
    parser = argparse.ArgumentParser(
        description="Script chạy thực nghiệm tải TCP Server và xuất toàn bộ dữ liệu thô (CSV/JSON)"
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Địa chỉ Host (mặc định: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Cổng Port (mặc định: {DEFAULT_PORT})")
    parser.add_argument(
        "--requests",
        type=int,
        default=50,
        help="Số lượng request mỗi client gửi trong mỗi kịch bản (mặc định: 50)",
    )
    args = parser.parse_args()

    # Thư mục lưu dữ liệu thô
    raw_data_dir = ROOT_DIR / "experiments" / "raw_data"
    raw_data_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("   CHƯƠNG TRÌNH THỰC NGHIỆM HIỆU NĂNG TCP SERVER (NHÓM LẬP TRÌNH MẠNG)")
    print("   Phụ trách thực nghiệm & xuất dữ liệu thô (CSV/JSON): Trần Trung Trực (Metrics Dev)")
    print("=" * 65)

    # Kiểm tra xem Server đã bật chưa, nếu chưa thì tự động bật server ngầm
    stop_server_event = threading.Event()
    server_thread = None

    if not check_server_online(args.host, args.port):
        print(f"[*] Chưa thấy Server tại {args.host}:{args.port}. Đang tự động khởi chạy Server test ngầm...")
        server_thread = threading.Thread(
            target=start_test_server,
            args=(args.host, args.port, stop_server_event),
            daemon=True,
        )
        server_thread.start()
        time.sleep(0.5)

        if not check_server_online(args.host, args.port):
            print(f"[!] Không thể mở Server test tại {args.host}:{args.port}. Vui lòng chạy thủ công 'python src/server/server.py'!")
            return 1
        print(f"[+] Server test ngầm đã sẵn sàng hoạt động tại {args.host}:{args.port}!\n")
    else:
        print(f"[+] Đã phát hiện Server đang hoạt động tại {args.host}:{args.port}!\n")

    # Danh sách các kịch bản cần thực nghiệm theo yêu cầu đề bài: 1, 10, 50 Client
    scenarios = [1, 10, 50]
    all_results = {}

    try:
        # Chạy lần lượt từng kịch bản
        for clients_count in scenarios:
            result = run_scenario(
                num_clients=clients_count,
                requests_per_client=args.requests,
                host=args.host,
                port=args.port,
                raw_data_dir=raw_data_dir,
            )
            all_results[f"{clients_count}_clients"] = result
            # Nghỉ 1 giây giữa các kịch bản để tài nguyên hệ thống ổn định trở lại
            time.sleep(1.0)

        # Lưu bản so sánh tổng hợp cả 3 kịch bản ra 1 file JSON lớn
        master_summary_file = raw_data_dir / "benchmark_all_summary.json"
        with open(master_summary_file, mode="w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 65)
        print(f"[+] HOÀN THÀNH TẤT CẢ KỊCH BẢN THỰC NGHIỆM!")
        print(f"[+] File tổng hợp toàn bộ 3 kịch bản: {master_summary_file}")
        print("=" * 65)

    finally:
        # Dừng Server ngầm nếu có tạo
        if server_thread:
            stop_server_event.set()
            server_thread.join(timeout=1.0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
