# Đồ án: Khảo sát ảnh hưởng của số lượng Client đồng thời đến hiệu năng TCP Server

## 1. Thông tin chung
- **Môn học:** [Lập trình mạng]
- **Thời gian thực hiện:** 11/2026
- **Mục tiêu:** Xây dựng một TCP Server đơn giản xử lý nhiều Client đồng thời bằng mô hình **Thread Pool**. Qua đó, đo lường và khảo sát sự thay đổi của độ trễ (latency), thông lượng (throughput) và mức sử dụng CPU khi số lượng Client thay đổi (1, 10, 50 Client).

## 2. Cấu trúc thư mục
Dự án được tổ chức theo tiêu chuẩn để tách biệt rõ ràng giữa mã nguồn, cấu hình và dữ liệu thực nghiệm:
- `src/server/`: Chứa mã nguồn TCP Server (Python).
- `src/load-generator/`: Chứa chương trình giả lập Client tạo tải (Python).
- `configs/`: File cấu hình cho các kịch bản test (IP, Port, số lượng Client, thời gian đo).
- `raw-data/`: Nơi lưu trữ dữ liệu thô (CSV/JSON) thu được sau mỗi lần chạy thực nghiệm.
- `analysis/`: Script Python/Jupyter Notebook dùng để phân tích dữ liệu thô.
- `figures/`: Biểu đồ trực quan hóa kết quả (Latency, Throughput, CPU).
- `experiments/`: Chứa các kịch bản hoặc script chạy tự động (bash/bat).
- `docs/`: Chứa báo cáo PDF, slide thuyết trình và các tài liệu tham khảo.

## 3. Yêu cầu hệ thống (Prerequisites)
- **Môi trường:** Python 3.8 trở lên.
- **Thư viện:** Đa số sử dụng thư viện chuẩn của Python (`socket`, `json`, `struct`, `threading`, `concurrent.futures`). Có thể cần thêm `psutil` để đo CPU.
- **Công cụ:** Visual Studio 2022 (hoặc VS Code) kèm Terminal để thực thi lệnh.

## 4. Hướng dẫn chạy và tái tạo thí nghiệm
Để tái tạo lại toàn bộ thí nghiệm đo lường hiệu năng và phân tích biểu đồ, hãy thực hiện lần lượt theo các bước sau:

### Bước 1: Khởi động TCP Server
Mở một cửa sổ Terminal (PowerShell hoặc CMD) tại thư mục gốc của dự án và chạy:
```bash
python src/server/server.py
```
Server sẽ bắt đầu lắng nghe tại địa chỉ `127.0.0.1:9000` với cơ chế Thread Pool (tối đa 100 workers).

---

### Bước 2: Kiểm thử kết nối và đo lường Prototype ban đầu
Mở một cửa sổ Terminal thứ hai để chạy script kiểm tra nhanh kết nối giữa Client và Server:
```bash
python prototype_test.py --requests 20
```
Script sẽ gửi 20 request thử nghiệm (payload 1KB echo), đo độ trễ và tự động xuất dữ liệu thô vào `experiments/raw_data/prototype_test.csv` và `prototype_test.json`.

---

### Bước 3: Chạy toàn bộ kịch bản tải thực nghiệm (1, 10, 50 Clients)
Để chạy tự động toàn bộ 3 kịch bản tải theo đúng yêu cầu đồ án (1 client, 10 clients, 50 clients đồng thời, mỗi client gửi request kèm đo CPU liên tục):
```bash
python experiments/scripts/run_benchmarks.py --requests 20
```
> **Ghi chú:** Script có cơ chế tự động kiểm tra, nếu bạn chưa bật `server.py` ở Bước 1, script sẽ tự động khởi động một Server test ngầm để tiến hành đo lường mà không gây gián đoạn.  
> Toàn bộ dữ liệu thô sẽ được lưu vào `experiments/raw_data/`:
> - `raw_data_1_clients.csv` / `.json` & `cpu_1_clients.csv` / `.json`
> - `raw_data_10_clients.csv` / `.json` & `cpu_10_clients.csv` / `.json`
> - `raw_data_50_clients.csv` / `.json` & `cpu_50_clients.csv` / `.json`
> - `benchmark_all_summary.json`

---

### Bước 4: Trực quan hóa và xem biểu đồ tương tác
Sau khi đã có dữ liệu thô, mở file giao diện trực quan hóa đồ thị được dựng bằng Chart.js:
- Mở trực tiếp file `experiments/charts.html` bằng trình duyệt web (Google Chrome, Microsoft Edge, Firefox):
  ```bash
  start experiments/charts.html
  ```
- Giao diện sẽ hiển thị đầy đủ 4 biểu đồ tương tác:
  1. **CDF:** Phân phối tích lũy Latency (đọc $P_{50}, P_{95}, P_{99}$).
  2. **Scatter Plot:** Độ trễ theo trục thời gian thực (nhận diện pha warmup và jitter).
  3. **Grouped Bar:** So sánh tổng hợp Thông lượng (RPS), Độ trễ (ms) và CPU (%).
  4. **Heatmap:** Ma trận độ trễ chi tiết từng Client qua các lượt gửi.

---

### Bước 5: Chạy phân tích thống kê và xuất báo cáo
Chạy script phân tích để xuất bảng số liệu đối chiếu và file tổng hợp phục vụ làm báo cáo:
```bash
python analysis/analyze_data.py
```
- Kết quả đối chiếu sẽ được in ngay trên màn hình Terminal.
- File dữ liệu tổng hợp sẽ được lưu tại:
  - `analysis/performance_summary.csv` (dễ dàng nhấp đúp mở bằng Excel).
  - `analysis/performance_summary.json`.

---

### Bước 6: Xem tài liệu Báo cáo nghiên cứu chi tiết
Nhóm đã biên soạn tài liệu báo cáo nghiên cứu chi tiết:
- File Báo cáo Markdown: `docs/Bao_Cao_Phan_Tich_Hieu_Nang_TCP_Server.md`
- Tài liệu báo cáo hoàn chỉnh được lưu trữ tại thư mục `docs/`.

---

### Bước 7: Chạy kiểm thử tự động (Unit Tests)
Để xác nhận tính đúng đắn của toàn bộ module giao thức và module thu thập chỉ số:
```bash
# Kiểm thử module đo lường và xuất dữ liệu thô CSV/JSON
python -m unittest test_metrics.py

# Kiểm thử giao thức phân khung Length-Prefix + JSON
python -m unittest test_protocol.py
```


