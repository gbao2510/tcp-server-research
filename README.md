# Đồ án: Khảo sát ảnh hưởng của số lượng Client đồng thời đến hiệu năng TCP Server

## 1. Thông tin chung
- **Môn học:** Lập trình mạng
- **Giảng viên hướng dẫn:** Mai Ngọc Châu
- **Nhóm thực hiện:** Nhóm 7 (5-6 sinh viên)
- **Thời gian thực hiện:** Tháng 11/2026
- **Câu hỏi nghiên cứu (Research Question):**
  > *Khi số lượng Client đồng thời tăng (1, 10, 50 Clients), thông lượng (Throughput), độ trễ phản hồi (Latency RTT) và mức sử dụng CPU của TCP Server thay đổi như thế nào?*

---

## 2. Cấu trúc thư mục dự án
Dự án được tổ chức chuẩn theo đặc tả yêu cầu của bài research:

```text
tcp-server-research/
├── README.md                      # Tài liệu hướng dẫn tổng quan và tái tạo thí nghiệm
├── client.py                      # Lớp Client TCP chuẩn (Length-Prefix + JSON, kết nối bền)
├── load_generator.py              # Shortcut chạy Load Generator từ thư mục gốc
├── prototype_test.py              # Script kiểm thử kết nối prototype end-to-end
├── test_protocol.py               # Unit tests cho tầng giao thức (10/10 PASS)
├── test_metrics.py                # Unit tests cho hệ thống đo lường (9/9 PASS)
├── test_server_robustness.py      # Unit tests cho kiểm thử hỏng hóc server (8/8 PASS)
├── src/                           # Mã nguồn cốt lõi
│   ├── server/
│   │   ├── server.py              # TCP Server xử lý đồng thời bằng ThreadPoolExecutor
│   │   └── __init__.py
│   ├── load_generator/
│   │   ├── load_generator.py      # Bộ tạo tải đồng thời (N client, payload 1KB, barrier đồng bộ)
│   │   └── __init__.py
│   ├── protocol/
│   │   ├── protocol.py            # Mô-đun phân khung Length-Prefix (4 bytes) + JSON UTF-8
│   │   └── __init__.py
│   └── metrics/
│       ├── collector.py           # Thu thập mẫu, tính Mean, P95, P99, xuất CSV/JSON
│       ├── system_monitor.py      # Giám sát CPU/RAM nền bằng psutil
│       └── __init__.py
├── experiments/                   # Thử nghiệm và dữ liệu đo lường
│   ├── config/
│   │   ├── benchmark_config.yaml  # Cấu hình kịch bản test (1, 10, 50 Client, 1KB payload, warmup 5s)
│   │   └── benchmark_config.json
│   ├── scripts/
│   │   └── run_benchmarks.py      # Script tự động khởi chạy Server và đo lần lượt các kịch bản
│   ├── raw_data/                  # Dữ liệu thô thực nghiệm (.csv và .json) cho từng kịch bản
│   ├── charts.html                # Bảng điều khiển giao diện web trực quan hóa dữ liệu
│   └── style.css
├── analysis/                      # Phân tích dữ liệu
│   ├── analyze_data.py            # Script đọc dữ liệu thô và xuất file so sánh tổng hợp
│   ├── plot_charts.py             # Script tự động vẽ và xuất các biểu đồ sang thư mục figures/
│   ├── performance_summary.csv    # Bảng tổng hợp số liệu hiệu năng (mở trực tiếp bằng Excel)
│   └── performance_summary.json
├── figures/                       # Thư mục lưu trữ biểu đồ trực quan hóa
│   ├── chart1_latency_vs_clients.png     # Biểu đồ Latency (Mean, P95, P99)
│   ├── chart2_throughput_vs_clients.png  # Biểu đồ Throughput (req/s)
│   └── chart3_cpu_vs_clients.png         # Biểu đồ Mức sử dụng CPU (%)
└── docs/                          # Báo cáo và tài liệu nghiên cứu
    └── Báo cáo nghiên cứu hiệu năng TCP Server.docx # Báo cáo chi tiết theo chuẩn môn học
```

---

## 3. Yêu cầu môi trường (Prerequisites)
- **Hệ điều hành:** Windows 10/11, Linux hoặc macOS.
- **Python:** Phiên bản 3.8 trở lên (Khuyến nghị Python 3.10+).
- **Thư viện phụ thuộc:**
  ```powershell
  pip install psutil python-docx PyQt6 pytest
  ```
  *(Thư viện `psutil` dùng để đo CPU/RAM, `PyQt6` dùng để sinh biểu đồ hình ảnh).*

---

## 4. Hướng dẫn chạy và tái tạo thí nghiệm (Reproducibility)

### Bước 1: Kiểm thử tính toàn vẹn của mã nguồn (Unit Tests)
Chạy bộ kiểm thử tự động để xác nhận toàn bộ 27 test cases đều đạt chuẩn:
```powershell
# Chạy toàn bộ unit test của Protocol, Metrics và Server Robustness:
python -m pytest test_protocol.py test_metrics.py test_server_robustness.py -k "not test_real_tcp and not Integration" -v
```

### Bước 2: Chạy Server và kiểm thử tạo tải thủ công
1. **Khởi động TCP Server** (mặc định lắng nghe tại `127.0.0.1:9000`):
   ```powershell
   python -m src.server.server
   ```
2. **Mở một Terminal khác để phát tải Client** (ví dụ: 10 client đồng thời trong 5 giây, payload 1KB):
   ```powershell
   python load_generator.py --clients 10 --duration 5
   ```

### Bước 3: Chạy tự động toàn bộ quy trình đo lường đa kịch bản (1, 10, 50 Clients)
Chạy script benchmark tự động tích hợp sẵn (tự bật server, warmup 5 giây, ghi nhận Latency và CPU):
```powershell
python experiments/scripts/run_benchmarks.py
```
Dữ liệu thô của từng request và thông số CPU sẽ được lưu tự động vào `experiments/raw_data/`.

### Bước 4: Phân tích số liệu và xuất biểu đồ
```powershell
# 1. Đọc dữ liệu thô và xuất bảng tổng hợp số liệu:
python analysis/analyze_data.py

# 2. Tự động vẽ và cập nhật biểu đồ đồ họa độ nét cao vào thư mục figures/:
python analysis/plot_charts.py
```

---

## 5. Tóm tắt kết quả nghiên cứu thực nghiệm

Dữ liệu thực nghiệm đo lường trên hệ thống được tổng hợp như sau:

| Số Client | Tổng Request | Tỷ lệ thành công | Thông lượng (Throughput) | Độ trễ TB (Mean) | Phân vị P95 | Phân vị P99 | Mức CPU TB |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1 Client** | 20 | 100% | **59.49 req/s** | 0.455 ms | 0.617 ms | 0.627 ms | 45.03% |
| **10 Clients** | 200 | 100% | **620.87 req/s** | 2.169 ms | 4.372 ms | 5.231 ms | 35.58% |
| **50 Clients** | 1000 | 100% | **1484.23 req/s** | 6.584 ms | 11.733 ms | 13.511 ms | 76.37% |

### Kết luận rút ra từ nghiên cứu:
1. **Khả năng mở rộng (Scalability):** Từ 1 lên 10 clients, Throughput tăng gần như tuyến tính (gấp 10.43 lần). Khi đạt mốc 50 clients, hệ thống tiệm cận bão hòa tài nguyên với 1484.23 req/s.
2. **Độ trễ và chuyển đổi ngữ cảnh:** Độ trễ trung bình tăng từ 0.455 ms lên 6.584 ms và P95 đạt 11.73 ms ở 50 clients do chi phí tranh chấp GIL (Global Interpreter Lock) và Context Switching giữa 50 luồng OS.
3. **Độ tin cậy:** Giao thức phân khung **Length-Prefix (4 bytes UInt32) + JSON UTF-8** giải quyết triệt để vấn đề xé gói/dính gói trên TCP, đạt tỷ lệ thành công 100% trên toàn bộ các kịch bản.

---

## 6. Phân công đóng góp thành viên

| STT | Thành viên | Vai trò | Trách nhiệm chính | Đóng góp |
| :---: | :--- | :--- | :--- | :---: |
| 1 | **Nguyễn Gia Bảo** | Protocol Dev | Thiết kế giao thức Length-Prefix + JSON, bẫy lỗi dữ liệu rác, `test_protocol.py` | 100% |
| 2 | **Ngô Gia Bảo** | Core Server Dev | Thiết kế kiến trúc TCP Server đa luồng (ThreadPool), `test_server_robustness.py` | 100% |
| 3 | **Trương Gia Bân** | Client / Load Gen Dev | Xây dựng client.py, load_generator.py tạo tải 1/10/50 client đồng thời | 100% |
| 4 | **Trần Trung Trực** | Metrics & Test Script Dev | Xây dựng collector.py, system_monitor.py đo Latency, CPU và run_benchmarks.py | 100% |
| 5 | **Trần Thuận Trí** | Data Analytics Dev | Xây dựng analyze_data.py, plot_charts.py tổng hợp CSV/JSON và trực quan hóa | 100% |
| 6 | **Lý Huỳnh Bích Trâm** | DevOps & Tech Writer | Quản lý Git repository, chuẩn hóa cấu trúc thư mục, hoàn thiện README và báo cáo | 100% |
