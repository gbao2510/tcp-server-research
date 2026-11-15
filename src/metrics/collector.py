"""Module thu thập, tính toán và xuất số liệu đo lường hiệu năng TCP Server.
Chức năng:
- Định nghĩa cấu trúc mẫu đo Sample (client_id, seq, t_start, latency_ms, ok, error).
- Tính toán Throughput (req/s), Latency trung bình, p95, p99, min, max.
- Hỗ trợ loại bỏ thời gian khởi động (warmup).
- Xuất/nhập dữ liệu thô dạng CSV vào thư mục raw-data / experiments/raw_data.
"""
from __future__ import annotations

import csv
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Sample:
    """Mỗi mẫu đại diện cho 1 lượt request - response."""
    client_id: int
    seq: int
    t_start: float       # Thời điểm gửi (giây tính từ mốc bắt đầu test)
    latency_ms: float    # Thời gian xử lý RTT (ms)
    ok: bool             # True nếu request thành công và response đúng
    error: str = ""      # Mô tả lỗi hoặc phân loại lỗi nếu thất bại


def calculate_percentile(data: list[float], percentile: float) -> float:
    """Tính phân vị (percentile) sử dụng phương pháp nội suy tuyến tính (linear interpolation)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    n = len(sorted_data)
    if n == 1:
        return sorted_data[0]
    k = (n - 1) * (percentile / 100.0)
    f = int(k)
    c = f + 1
    if c >= n:
        return sorted_data[-1]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


def summarize(
    samples: list[Sample],
    elapsed_s: float,
    warmup_s: float = 0.0,
) -> dict[str, Any]:
    """Tính toán thống kê từ danh sách Sample.

    Có thể bỏ qua các mẫu phát sinh trong khoảng thời gian khởi động `warmup_s`.
    """
    if warmup_s > 0:
        filtered = [s for s in samples if s.t_start >= warmup_s]
        effective_duration = max(elapsed_s - warmup_s, 0.001)
    else:
        filtered = samples
        effective_duration = max(elapsed_s, 0.001)

    total_req = len(filtered)
    ok_samples = [s for s in filtered if s.ok]
    fail_samples = [s for s in filtered if not s.ok]

    ok_count = len(ok_samples)
    fail_count = len(fail_samples)
    throughput = ok_count / effective_duration if effective_duration > 0 else 0.0

    error_breakdown: dict[str, int] = {}
    for s in fail_samples:
        err_key = s.error or "unknown_error"
        error_breakdown[err_key] = error_breakdown.get(err_key, 0) + 1

    if ok_samples:
        latencies = [s.latency_ms for s in ok_samples]
        lat_avg = sum(latencies) / len(latencies)
        lat_min = min(latencies)
        lat_max = max(latencies)
        lat_p95 = calculate_percentile(latencies, 95.0)
        lat_p99 = calculate_percentile(latencies, 99.0)
    else:
        lat_avg = lat_min = lat_max = lat_p95 = lat_p99 = 0.0

    return {
        "total_requests": total_req,
        "requests_ok": ok_count,
        "requests_failed": fail_count,
        "elapsed_s": round(effective_duration, 3),
        # Throughput
        "throughput": round(throughput, 2),
        "throughput_rps": round(throughput, 2),
        # Latency (ms)
        "latency_avg_ms": round(lat_avg, 3),
        "latency_avg": round(lat_avg, 3),
        "latency_p95_ms": round(lat_p95, 3),
        "latency_p95": round(lat_p95, 3),
        "latency_p99_ms": round(lat_p99, 3),
        "latency_p99": round(lat_p99, 3),
        "latency_min_ms": round(lat_min, 3),
        "latency_min": round(lat_min, 3),
        "latency_max_ms": round(lat_max, 3),
        "latency_max": round(lat_max, 3),
        # Chi tiết lỗi
        "errors": error_breakdown,
    }


def format_summary(summary: dict[str, Any], clients: int = 1, connected: int = 1) -> str:
    """Định dạng kết quả thống kê thành bảng văn bản trực quan."""
    lines = [
        "=" * 60,
        "          BÁO CÁO HIỆU NĂNG TCP SERVER (BENCHMARK)",
        "=" * 60,
        f"  Số Client đồng thời      : {clients} (Kết nối thành công: {connected}/{clients})",
        f"  Thời gian chạy đo lường  : {summary.get('elapsed_s', 0):.2f} giây",
        f"  Tổng số Request gửi      : {summary.get('total_requests', 0)}",
        f"    - Thành công (OK)      : {summary.get('requests_ok', 0)}",
        f"    - Thất bại (Failed)    : {summary.get('requests_failed', 0)}",
        "-" * 60,
        f"  THÔNG LƯỢNG (Throughput) : {summary.get('throughput_rps', 0):.2f} req/s",
        "-" * 60,
        "  ĐỘ TRỄ (Latency RTT):",
        f"    - Nhỏ nhất (Min)       : {summary.get('latency_min_ms', 0):.3f} ms",
        f"    - Trung bình (Mean)    : {summary.get('latency_avg_ms', 0):.3f} ms",
        f"    - Phân vị 95 (p95)     : {summary.get('latency_p95_ms', 0):.3f} ms",
        f"    - Phân vị 99 (p99)     : {summary.get('latency_p99_ms', 0):.3f} ms",
        f"    - Lớn nhất (Max)       : {summary.get('latency_max_ms', 0):.3f} ms",
        "=" * 60,
    ]
    errors = summary.get("errors", {})
    if errors:
        lines.append("  Phân loại lỗi phát sinh:")
        for err_type, count in sorted(errors.items(), key=lambda x: -x[1]):
            lines.append(f"    * {err_type}: {count}")
        lines.append("=" * 60)
    return "\n".join(lines)


def write_csv(samples: list[Sample], filepath: str | Path) -> None:
    """Ghi dữ liệu thô từng request ra file CSV."""
    p = Path(filepath)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["client_id", "seq", "t_start", "latency_ms", "ok", "error"])
        for s in samples:
            writer.writerow([
                s.client_id,
                s.seq,
                f"{s.t_start:.6f}",
                f"{s.latency_ms:.4f}",
                1 if s.ok else 0,
                s.error,
            ])


def read_csv(filepath: str | Path) -> list[Sample]:
    """Đọc dữ liệu thô từ file CSV trả về danh sách Sample."""
    p = Path(filepath)
    samples: list[Sample] = []
    with open(p, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            samples.append(
                Sample(
                    client_id=int(row["client_id"]),
                    seq=int(row["seq"]),
                    t_start=float(row["t_start"]),
                    latency_ms=float(row["latency_ms"]),
                    ok=row["ok"] in ("1", "True", "true"),
                    error=row.get("error", ""),
                )
            )
    return samples


class MetricsCollector:
    """Bộ thu thập dữ liệu thread-safe hỗ trợ nhiều Client worker chạy song song."""
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._samples: list[Sample] = []

    def record(
        self,
        client_id: int,
        seq: int,
        t_start: float,
        latency_ms: float,
        ok: bool,
        error: str = "",
    ) -> Sample:
        s = Sample(client_id, seq, t_start, latency_ms, ok, error)
        with self._lock:
            self._samples.append(s)
        return s

    def add_samples(self, samples: list[Sample]) -> None:
        with self._lock:
            self._samples.extend(samples)

    def get_samples(self) -> list[Sample]:
        with self._lock:
            return list(self._samples)

    def summarize(self, elapsed_s: float, warmup_s: float = 0.0) -> dict[str, Any]:
        return summarize(self.get_samples(), elapsed_s, warmup_s)

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()
