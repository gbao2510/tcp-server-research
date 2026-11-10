# Đồ án: Khảo sát ảnh hưởng của số lượng Client đồng thời đến hiệu năng TCP Server

## 1. Thông tin chung
- **Môn học:** Lập trình mạng
- **Thời gian thực hiện:** 11/2026
- **Mục tiêu:** Xây dựng một TCP Server đơn giản xử lý nhiều Client đồng thời bằng mô hình **Thread Pool**. Qua đó, đo lường và khảo sát sự thay đổi của độ trễ (latency), thông lượng (throughput) và mức sử dụng CPU khi số lượng Client thay đổi (1, 10, 50 Client).

## 2. Cấu trúc thư mục
Dự án được tổ chức theo tiêu chuẩn để tách biệt rõ ràng giữa mã nguồn, cấu hình và dữ liệu thực nghiệm:
- `protocol.py` / `src/protocol.py`: Mô-đun giao thức truyền thông chuẩn (Length-Prefix 4 bytes Big-Endian + UTF-8 JSON) do Protocol Dev phụ trách.
- `src/server/`: Chứa mã nguồn TCP Server xử lý đa luồng (Thread Pool).
- `src/load-generator/`: Chứa chương trình Client và Load Generator tạo tải đồng thời (1, 10, 50 Client).
- `tests/`: Bộ kiểm thử đơn vị tự động (Unit Tests) cho giao thức và tính tương thích mạng.
- `docs/`: Chứa tài liệu đặc tả giao thức `docs/PROTOCOL_SPEC.md`, báo cáo và tài liệu kỹ thuật.
- `configs/`: File cấu hình cho các kịch bản test (IP, Port, số lượng Client, thời gian đo).
- `raw-data/`: Nơi lưu trữ dữ liệu thô (CSV/JSON) thu được sau mỗi lần chạy thực nghiệm.
- `analysis/`: Script Python/Jupyter Notebook dùng để phân tích dữ liệu thô.
- `figures/`: Biểu đồ trực quan hóa kết quả (Latency, Throughput, CPU).
- `experiments/`: Chứa các kịch bản hoặc script chạy tự động (bash/bat).

## 3. Yêu cầu hệ thống (Prerequisites)
- **Môi trường:** Python 3.8 trở lên (đã kiểm thử tương thích Python 3.12).
- **Thư viện:** Toàn bộ hệ thống sử dụng thư viện chuẩn của Python (`socket`, `json`, `struct`, `threading`, `concurrent.futures`, `unittest`).
- **Công cụ:** Visual Studio Code / Terminal PowerShell hoặc Bash.

## 4. Hướng dẫn chạy và tái tạo thí nghiệm

### Bước 1: Chạy kiểm thử đơn vị cho giao thức (Unit Tests)
```bash
python -m unittest tests/test_protocol.py -v
```

### Bước 2: Khởi động TCP Server
Mở Terminal 1 và khởi chạy Server:
```bash
python src/server/server.py --port 9999 --workers 100
```

### Bước 3: Chạy Load Generator kiểm thử tải
Mở Terminal 2 và thực hiện các kịch bản kiểm thử:
- **Kịch bản 1 Client:**
  ```bash
  python src/load-generator/load_generator.py --clients 1 --requests 100 --port 9999
  ```
- **Kịch bản 10 Client đồng thời:**
  ```bash
  python src/load-generator/load_generator.py --clients 10 --duration 5 --port 9999
  ```
- **Kịch bản 50 Client đồng thời:**
  ```bash
  python src/load-generator/load_generator.py --clients 50 --duration 5 --port 9999
  ```

Chi tiết đặc tả giao thức và cấu trúc gói tin xem tại: [`docs/PROTOCOL_SPEC.md`](docs/PROTOCOL_SPEC.md).
