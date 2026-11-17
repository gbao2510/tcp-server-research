"""Script phân tích dữ liệu thô và vẽ biểu đồ hiệu năng TCP Server.
Tác giả: Trần Thuận Trí (Data Analytics Dev).

Chức năng:
1. Đọc tự động các file dữ liệu thô (CSV/JSON) trong thư mục `experiments/raw_data/`.
2. Tính toán và so sánh hiệu năng qua các mức tải: 1, 10, 50 Client:
   - Thông lượng (Throughput - req/s)
   - Độ trễ phản hồi (Average Latency, p95, p99 - ms)
   - Mức tiêu thụ CPU (%)
3. Xuất file báo cáo tổng hợp:
   - `analysis/performance_summary.csv` (dễ dàng mở bằng Microsoft Excel)
   - `analysis/performance_summary.json`
4. Tự động vẽ 3 biểu đồ trực quan lưu vào thư mục `figures/`:
   - Biểu đồ 1: Độ trễ phản hồi (Latency) theo số lượng Client.
   - Biểu đồ 2: Thông lượng (Throughput) theo số lượng Client.
   - Biểu đồ 3: Mức sử dụng CPU theo số lượng Client.
"""

from __future__ import annotations

# Import các thư viện chuẩn của Python
import csv
import json
import os
import sys
from pathlib import Path

# Xác định đường dẫn thư mục gốc của dự án
CURRENT_FILE = Path(__file__).resolve()
ROOT_DIR = CURRENT_FILE.parent.parent
SRC_DIR = ROOT_DIR / "src"

# Thêm đường dẫn vào sys.path để import các module nội bộ
for directory in (str(ROOT_DIR), str(SRC_DIR)):
    if directory not in sys.path:
        sys.path.insert(0, directory)

# Import các hàm đọc/ghi dữ liệu từ module metrics
from src.metrics import read_csv, read_json, summarize


def load_scenario_data(raw_data_dir: Path, client_count: int) -> dict:
    """Đọc dữ liệu thô của 1 kịch bản từ file CSV hoặc JSON trong raw_data."""
    scenario_key = f"{client_count}_clients"

    # Đường dẫn các file dữ liệu thô
    csv_file = raw_data_dir / f"raw_data_{scenario_key}.csv"
    json_file = raw_data_dir / f"raw_data_{scenario_key}.json"
    cpu_csv_file = raw_data_dir / f"cpu_{scenario_key}.csv"
    cpu_json_file = raw_data_dir / f"cpu_{scenario_key}.json"
    summary_file = raw_data_dir / f"summary_{scenario_key}.json"

    # Kiểm tra xem file tóm tắt có sẵn không
    if summary_file.exists():
        with open(summary_file, mode="r", encoding="utf-8") as f:
            return json.load(f)

    # Nếu chưa có summary_file, ta đọc từ file thô CSV hoặc JSON rồi tự tính
    samples = []
    if csv_file.exists():
        # Đọc từ CSV bằng hàm của Thuận Trí
        samples = read_csv(csv_file)
    elif json_file.exists():
        # Đọc từ JSON bằng hàm của Thuận Trí
        samples = read_json(json_file)
    else:
        return {}

    # Đọc dữ liệu CPU
    cpu_avg = 0.0
    if cpu_json_file.exists():
        with open(cpu_json_file, mode="r", encoding="utf-8") as f:
            cpu_data = json.load(f)
            cpu_avg = cpu_data.get("summary", {}).get("cpu_avg", 0.0)
    elif cpu_csv_file.exists():
        with open(cpu_csv_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            cpu_vals = [float(row["cpu_percent"]) for row in reader if "cpu_percent" in row]
            if cpu_vals:
                cpu_avg = round(sum(cpu_vals) / len(cpu_vals), 2)

    # Tính toán tổng hợp từ danh sách Sample
    elapsed = max((s.t_start for s in samples), default=1.0)
    summary = summarize(samples, elapsed_s=elapsed)
    summary["clients"] = client_count
    summary["cpu"] = {"cpu_avg": cpu_avg}
    return summary


def generate_comparison_table(results: list[dict]) -> str:
    """Tạo bảng văn bản so sánh các chỉ số hiệu năng để in ra console hoặc dán vào báo cáo."""
    lines = []
    lines.append("=" * 80)
    lines.append("        BẢNG TỔNG HỢP SO SÁNH HIỆU NĂNG TCP SERVER (1, 10, 50 CLIENT)")
    lines.append("=" * 80)
    # Tiêu đề bảng
    header = (
        f"{'Số Client':<12} | {'Tổng Req':<10} | {'Throughput (req/s)':<20} | "
        f"{'Latency TB (ms)':<16} | {'p95 (ms)':<10} | {'CPU TB (%)':<10}"
    )
    lines.append(header)
    lines.append("-" * 80)

    # Thêm từng dòng dữ liệu của từng kịch bản
    for r in results:
        clients = r.get("clients", "N/A")
        total_req = r.get("total_requests", 0)
        throughput = r.get("throughput_rps", 0.0)
        lat_avg = r.get("latency_avg_ms", 0.0)
        lat_p95 = r.get("latency_p95_ms", 0.0)
        cpu_avg = r.get("cpu", {}).get("cpu_avg", 0.0)

        row = (
            f"{clients:<12} | {total_req:<10} | {throughput:<20.2f} | "
            f"{lat_avg:<16.3f} | {lat_p95:<10.3f} | {cpu_avg:<10.2f}%"
        )
        lines.append(row)

    lines.append("=" * 80)
    return "\n".join(lines)


def export_summary_files(results: list[dict], output_dir: Path) -> tuple[Path, Path]:
    """Xuất kết quả phân tích so sánh ra file CSV và JSON trong thư mục analysis/."""
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "performance_summary.csv"
    json_path = output_dir / "performance_summary.json"

    # 1. Ghi file CSV
    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "clients",
            "total_requests",
            "requests_ok",
            "requests_failed",
            "throughput_rps",
            "latency_avg_ms",
            "latency_p95_ms",
            "latency_p99_ms",
            "latency_min_ms",
            "latency_max_ms",
            "cpu_avg_percent",
        ])
        for r in results:
            writer.writerow([
                r.get("clients", 0),
                r.get("total_requests", 0),
                r.get("requests_ok", 0),
                r.get("requests_failed", 0),
                r.get("throughput_rps", 0.0),
                r.get("latency_avg_ms", 0.0),
                r.get("latency_p95_ms", 0.0),
                r.get("latency_p99_ms", 0.0),
                r.get("latency_min_ms", 0.0),
                r.get("latency_max_ms", 0.0),
                r.get("cpu", {}).get("cpu_avg", 0.0),
            ])

    # 2. Ghi file JSON
    with open(json_path, mode="w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    return csv_path, json_path


def draw_charts(results: list[dict], figures_dir: Path) -> bool:
    """Vẽ 3 biểu đồ trực quan hóa số liệu nếu máy có cài thư viện matplotlib."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n[!] Máy tính chưa cài thư viện 'matplotlib'.")
        print("    -> Bạn có thể cài bằng lệnh: pip install matplotlib")
        print("    -> Hiện tại dữ liệu bảng phân tích đã được lưu ra file CSV để mở bằng Excel rồi nhé!")
        return False

    figures_dir.mkdir(parents=True, exist_ok=True)

    clients = [r.get("clients", 0) for r in results]
    lat_avg = [r.get("latency_avg_ms", 0.0) for r in results]
    lat_p95 = [r.get("latency_p95_ms", 0.0) for r in results]
    throughput = [r.get("throughput_rps", 0.0) for r in results]
    cpu_avg = [r.get("cpu", {}).get("cpu_avg", 0.0) for r in results]

    x_labels = [f"{c} Clients" for c in clients]

    # --- Biểu đồ 1: Latency theo số Client ---
    plt.figure(figsize=(8, 5))
    plt.plot(x_labels, lat_avg, marker="o", color="#1f77b4", linewidth=2, label="Độ trễ TB (Mean Latency)")
    plt.plot(x_labels, lat_p95, marker="s", color="#ff7f0e", linewidth=2, linestyle="--", label="Độ trễ phân vị 95 (p95)")
    plt.title("Khảo sát Độ trễ (Latency) theo Số lượng Client", fontsize=13, fontweight="bold")
    plt.xlabel("Số lượng Client đồng thời", fontsize=11)
    plt.ylabel("Độ trễ RTT (ms)", fontsize=11)
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.legend()
    fig1_path = figures_dir / "latency_vs_clients.png"
    plt.savefig(fig1_path, dpi=300, bbox_inches="tight")
    plt.close()

    # --- Biểu đồ 2: Throughput theo số Client ---
    plt.figure(figsize=(8, 5))
    bars = plt.bar(x_labels, throughput, color="#2ca02c", width=0.45)
    plt.title("Khảo sát Thông lượng (Throughput) theo Số lượng Client", fontsize=13, fontweight="bold")
    plt.xlabel("Số lượng Client đồng thời", fontsize=11)
    plt.ylabel("Thông lượng (Request / Giây)", fontsize=11)
    plt.grid(axis="y", linestyle=":", alpha=0.6)
    # Thêm số liệu lên đầu mỗi cột
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width() / 2.0, height + 5, f"{height:.1f}", ha="center", va="bottom")
    fig2_path = figures_dir / "throughput_vs_clients.png"
    plt.savefig(fig2_path, dpi=300, bbox_inches="tight")
    plt.close()

    # --- Biểu đồ 3: CPU Usage theo số Client ---
    plt.figure(figsize=(8, 5))
    plt.bar(x_labels, cpu_avg, color="#d62728", width=0.45)
    plt.title("Khảo sát Mức sử dụng CPU theo Số lượng Client", fontsize=13, fontweight="bold")
    plt.xlabel("Số lượng Client đồng thời", fontsize=11)
    plt.ylabel("Mức sử dụng CPU (%)", fontsize=11)
    plt.ylim(0, max(max(cpu_avg, default=10) * 1.3, 100))
    plt.grid(axis="y", linestyle=":", alpha=0.6)
    fig3_path = figures_dir / "cpu_vs_clients.png"
    plt.savefig(fig3_path, dpi=300, bbox_inches="tight")
    plt.close()

    print("\n[+] ĐÃ VẼ VÀ LƯU 3 BIỂU ĐỒ VÀO THƯ MỤC 'figures/':")
    print(f"    1. {fig1_path.name}")
    print(f"    2. {fig2_path.name}")
    print(f"    3. {fig3_path.name}")
    return True


def main() -> int:
    """Hàm phân tích chính."""
    raw_data_dir = ROOT_DIR / "experiments" / "raw_data"
    analysis_dir = ROOT_DIR / "analysis"
    figures_dir = ROOT_DIR / "figures"

    print("=" * 65)
    print("   CHƯƠNG TRÌNH PHÂN TÍCH HIỆU NĂNG TCP SERVER (DATA ANALYTICS DEV)")
    print("   Tác giả: Trần Thuận Trí")
    print("=" * 65)

    scenarios = [1, 10, 50]
    results = []

    for c in scenarios:
        data = load_scenario_data(raw_data_dir, c)
        if data:
            results.append(data)

    if not results:
        print("[!] Chưa tìm thấy file dữ liệu thô nào trong thư mục 'experiments/raw_data/'.")
        print("    -> Vui lòng chạy script thu thập dữ liệu trước: python experiments/scripts/run_benchmarks.py")
        return 1

    # In bảng so sánh
    table_str = generate_comparison_table(results)
    print("\n" + table_str)

    # Xuất file CSV và JSON cho báo cáo
    csv_out, json_out = export_summary_files(results, analysis_dir)
    print(f"\n[+] Đã xuất file tổng hợp phân tích ra:")
    print(f"    -> CSV (mở bằng Excel): {csv_out}")
    print(f"    -> JSON               : {json_out}")

    # Vẽ biểu đồ (nếu có matplotlib)
    draw_charts(results, figures_dir)

    print("\n[+] Hoàn tất công việc phân tích dữ liệu hiệu năng!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
