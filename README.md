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
Để tái tạo lại thí nghiệm đo lường hiệu năng, hãy thực hiện lần lượt các bước sau:


