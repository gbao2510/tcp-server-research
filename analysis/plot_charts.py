"""Script tự động vẽ biểu đồ hiệu năng sử dụng PyQt6 (không cần matplotlib).
Xuất các biểu đồ chuẩn sang thư mục `figures/`:
1. `figures/chart1_latency_vs_clients.png`: Độ trễ trung bình, P95, P99 theo số lượng Client.
2. `figures/chart2_throughput_vs_clients.png`: Thông lượng Throughput (req/s) theo số lượng Client.
3. `figures/chart3_cpu_vs_clients.png`: Mức tải CPU (%) theo số lượng Client.
4. `figures/chart4_performance_overview.png`: Biểu đồ cột tổng hợp đa trục (Throughput & Latency & CPU).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QPainter, QColor, QFont, QPen, QBrush
from PyQt6.QtCore import Qt, QRectF, QPointF

ROOT_DIR = Path(__file__).resolve().parent.parent
FIGURES_DIR = ROOT_DIR / "figures"
ANALYSIS_DIR = ROOT_DIR / "analysis"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# Khởi tạo QApplication (bắt buộc cho QPainter/QFont/QImage trên một số nền tảng)
_app = QApplication.instance()
if not _app:
    _app = QApplication(sys.argv)


def load_data():
    csv_path = ANALYSIS_DIR / "performance_summary.csv"
    data = []
    if csv_path.exists():
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append({
                    "clients": int(row["clients"]),
                    "throughput": float(row["throughput_rps"]),
                    "latency_avg": float(row["latency_avg_ms"]),
                    "latency_p95": float(row["latency_p95_ms"]),
                    "latency_p99": float(row["latency_p99_ms"]),
                    "cpu_avg": float(row["cpu_avg_percent"]),
                })
    return data


def draw_chart1_latency(data):
    width, height = 900, 550
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor("#FFFFFF"))

    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Tiêu đề
    p.setFont(QFont("Arial", 16, QFont.Weight.Bold))
    p.setPen(QColor("#1A202C"))
    p.drawText(QRectF(0, 25, width, 40), Qt.AlignmentFlag.AlignCenter, "BIỂU ĐỒ 1: ĐỘ TRỄ PHẢN HỒI (LATENCY) THEO SỐ LƯỢNG CLIENT")

    p.setFont(QFont("Arial", 10))
    p.setPen(QColor("#718096"))
    p.drawText(QRectF(0, 60, width, 25), Qt.AlignmentFlag.AlignCenter, "Khảo sát Mean, P95 và P99 RTT (ms) qua các mức 1, 10, 50 Clients (Payload 1KB)")

    # Khung vẽ
    margin_l, margin_r, margin_t, margin_b = 100, 60, 100, 90
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b

    # Lưới toạ độ
    p.setPen(QPen(QColor("#E2E8F0"), 1, Qt.PenStyle.DashLine))
    max_lat = 16.0
    for y_val in [0, 4, 8, 12, 16]:
        y = margin_t + plot_h - (y_val / max_lat) * plot_h
        p.drawLine(int(margin_l), int(y), int(margin_l + plot_w), int(y))
        p.setPen(QColor("#4A5568"))
        p.setFont(QFont("Arial", 9))
        p.drawText(QRectF(margin_l - 60, y - 10, 50, 20), Qt.AlignmentFlag.AlignRight, f"{y_val} ms")
        p.setPen(QPen(QColor("#E2E8F0"), 1, Qt.PenStyle.DashLine))

    # Trục chính
    p.setPen(QPen(QColor("#2D3748"), 2))
    p.drawLine(margin_l, margin_t, margin_l, margin_t + plot_h)
    p.drawLine(margin_l, margin_t + plot_h, margin_l + plot_w, margin_t + plot_h)

    # Vẽ các cột hoặc điểm
    clients = [d["clients"] for d in data]
    x_coords = [margin_l + (i + 0.5) * (plot_w / len(clients)) for i in range(len(clients))]

    series = [
        ("Mean Latency", "#3182CE", [d["latency_avg"] for d in data]),
        ("P95 Latency", "#DD6B20", [d["latency_p95"] for d in data]),
        ("P99 Latency", "#E53E3E", [d["latency_p99"] for d in data]),
    ]

    for label, color, values in series:
        pen = QPen(QColor(color), 3)
        p.setPen(pen)
        pts = []
        for x, val in zip(x_coords, values):
            y = margin_t + plot_h - (val / max_lat) * plot_h
            pts.append(QPointF(x, y))

        for i in range(len(pts) - 1):
            p.drawLine(pts[i], pts[i + 1])

        p.setBrush(QBrush(QColor(color)))
        for pt, val in zip(pts, values):
            p.drawEllipse(pt, 5, 5)
            p.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            p.drawText(QRectF(pt.x() - 30, pt.y() - 25, 60, 20), Qt.AlignmentFlag.AlignCenter, f"{val:.2f}")

    # Nhãn X
    p.setPen(QColor("#2D3748"))
    p.setFont(QFont("Arial", 11, QFont.Weight.Bold))
    for x, c in zip(x_coords, clients):
        p.drawText(QRectF(x - 50, margin_t + plot_h + 10, 100, 25), Qt.AlignmentFlag.AlignCenter, f"{c} Client{'s' if c > 1 else ''}")

    # Legend
    legend_y = height - 40
    leg_x = 220
    for label, color, _ in series:
        p.setPen(QPen(QColor(color), 3))
        p.drawLine(leg_x, legend_y + 8, leg_x + 25, legend_y + 8)
        p.setBrush(QBrush(QColor(color)))
        p.drawEllipse(QPointF(leg_x + 12.5, legend_y + 8), 4, 4)
        p.setPen(QColor("#2D3748"))
        p.setFont(QFont("Arial", 10))
        p.drawText(leg_x + 35, legend_y + 14, label)
        leg_x += 160

    p.end()
    image.save(str(FIGURES_DIR / "chart1_latency_vs_clients.png"))


def draw_chart2_throughput(data):
    width, height = 900, 550
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor("#FFFFFF"))

    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    p.setFont(QFont("Arial", 16, QFont.Weight.Bold))
    p.setPen(QColor("#1A202C"))
    p.drawText(QRectF(0, 25, width, 40), Qt.AlignmentFlag.AlignCenter, "BIỂU ĐỒ 2: THÔNG LƯỢNG (THROUGHPUT) THEO SỐ LƯỢNG CLIENT")

    p.setFont(QFont("Arial", 10))
    p.setPen(QColor("#718096"))
    p.drawText(QRectF(0, 60, width, 25), Qt.AlignmentFlag.AlignCenter, "Số request xử lý thành công mỗi giây (req/s) khi số lượng Client tăng dần")

    margin_l, margin_r, margin_t, margin_b = 100, 60, 100, 80
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b

    max_tp = 1800.0
    p.setPen(QPen(QColor("#E2E8F0"), 1, Qt.PenStyle.DashLine))
    for y_val in [0, 300, 600, 900, 1200, 1500, 1800]:
        y = margin_t + plot_h - (y_val / max_tp) * plot_h
        p.drawLine(int(margin_l), int(y), int(margin_l + plot_w), int(y))
        p.setPen(QColor("#4A5568"))
        p.setFont(QFont("Arial", 9))
        p.drawText(QRectF(margin_l - 70, y - 10, 60, 20), Qt.AlignmentFlag.AlignRight, f"{int(y_val)}")
        p.setPen(QPen(QColor("#E2E8F0"), 1, Qt.PenStyle.DashLine))

    p.setPen(QPen(QColor("#2D3748"), 2))
    p.drawLine(margin_l, margin_t, margin_l, margin_t + plot_h)
    p.drawLine(margin_l, margin_t + plot_h, margin_l + plot_w, margin_t + plot_h)

    clients = [d["clients"] for d in data]
    bar_width = 80
    colors = ["#4299E1", "#3182CE", "#2B6CB0"]

    for i, d in enumerate(data):
        x_center = margin_l + (i + 0.5) * (plot_w / len(clients))
        bar_h = (d["throughput"] / max_tp) * plot_h
        bar_rect = QRectF(x_center - bar_width / 2, margin_t + plot_h - bar_h, bar_width, bar_h)

        p.setBrush(QBrush(QColor(colors[i % len(colors)])))
        p.setPen(QPen(QColor("#1A365D"), 1.5))
        p.drawRoundedRect(bar_rect, 6, 6)

        p.setPen(QColor("#1A202C"))
        p.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        p.drawText(QRectF(x_center - 60, margin_t + plot_h - bar_h - 25, 120, 20), Qt.AlignmentFlag.AlignCenter, f"{d['throughput']:.1f} req/s")

        p.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        p.drawText(QRectF(x_center - 60, margin_t + plot_h + 12, 120, 25), Qt.AlignmentFlag.AlignCenter, f"{d['clients']} Client{'s' if d['clients'] > 1 else ''}")

    p.end()
    image.save(str(FIGURES_DIR / "chart2_throughput_vs_clients.png"))


def draw_chart3_cpu(data):
    width, height = 900, 550
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor("#FFFFFF"))

    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    p.setFont(QFont("Arial", 16, QFont.Weight.Bold))
    p.setPen(QColor("#1A202C"))
    p.drawText(QRectF(0, 25, width, 40), Qt.AlignmentFlag.AlignCenter, "BIỂU ĐỒ 3: MỨC SỬ DỤNG CPU THEO SỐ LƯỢNG CLIENT")

    p.setFont(QFont("Arial", 10))
    p.setPen(QColor("#718096"))
    p.drawText(QRectF(0, 60, width, 25), Qt.AlignmentFlag.AlignCenter, "Tỷ lệ chiếm dụng CPU trung bình (%) của hệ thống trong thời gian chạy thực nghiệm")

    margin_l, margin_r, margin_t, margin_b = 100, 60, 100, 80
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b

    p.setPen(QPen(QColor("#E2E8F0"), 1, Qt.PenStyle.DashLine))
    for y_val in [0, 20, 40, 60, 80, 100]:
        y = margin_t + plot_h - (y_val / 100.0) * plot_h
        p.drawLine(int(margin_l), int(y), int(margin_l + plot_w), int(y))
        p.setPen(QColor("#4A5568"))
        p.setFont(QFont("Arial", 9))
        p.drawText(QRectF(margin_l - 60, y - 10, 50, 20), Qt.AlignmentFlag.AlignRight, f"{y_val}%")
        p.setPen(QPen(QColor("#E2E8F0"), 1, Qt.PenStyle.DashLine))

    p.setPen(QPen(QColor("#2D3748"), 2))
    p.drawLine(margin_l, margin_t, margin_l, margin_t + plot_h)
    p.drawLine(margin_l, margin_t + plot_h, margin_l + plot_w, margin_t + plot_h)

    clients = [d["clients"] for d in data]
    bar_width = 80
    colors = ["#48BB78", "#38A169", "#E53E3E"]

    for i, d in enumerate(data):
        x_center = margin_l + (i + 0.5) * (plot_w / len(clients))
        bar_h = (d["cpu_avg"] / 100.0) * plot_h
        bar_rect = QRectF(x_center - bar_width / 2, margin_t + plot_h - bar_h, bar_width, bar_h)

        p.setBrush(QBrush(QColor(colors[i % len(colors)])))
        p.setPen(QPen(QColor("#22543D"), 1.5))
        p.drawRoundedRect(bar_rect, 6, 6)

        p.setPen(QColor("#1A202C"))
        p.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        p.drawText(QRectF(x_center - 60, margin_t + plot_h - bar_h - 25, 120, 20), Qt.AlignmentFlag.AlignCenter, f"{d['cpu_avg']:.1f}%")

        p.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        p.drawText(QRectF(x_center - 60, margin_t + plot_h + 12, 120, 25), Qt.AlignmentFlag.AlignCenter, f"{d['clients']} Client{'s' if d['clients'] > 1 else ''}")

    p.end()
    image.save(str(FIGURES_DIR / "chart3_cpu_vs_clients.png"))


def main():
    data = load_data()
    if not data:
        print("[!] Không tìm thấy dữ liệu trong analysis/performance_summary.csv")
        return
    draw_chart1_latency(data)
    draw_chart2_throughput(data)
    draw_chart3_cpu(data)
    print(f"[+] Đã tạo thành công 3 biểu đồ đồ hoạ tại thư mục: {FIGURES_DIR}")


if __name__ == "__main__":
    main()
