# BÁO CÁO NGHIÊN CỨU & KHẢO SÁT HIỆU NĂNG TCP SERVER ĐA LUỒNG
**Môn học:** Lập trình mạng  
**Đề tài:** Khảo sát ảnh hưởng của số lượng Client đồng thời đến hiệu năng TCP Server (Mô hình Thread Pool)  
**Người thực hiện:** Trần Thuận Trí (Data Analytics Dev) & Nhóm nghiên cứu  
**Thời gian thực hiện:** Tháng 11/2026  

---

## 1. TỔNG QUAN VÀ MỤC TIÊU NGHIÊN CỨU

### 1.1. Bối cảnh
Trong các hệ thống mạng phân tán và ứng dụng mạng hiện đại, máy chủ TCP (TCP Server) đóng vai trò trung tâm trong việc tiếp nhận, xử lý và phản hồi dữ liệu từ hàng trăm đến hàng nghìn máy trạm (clients) kết nối đồng thời. Việc thiết kế kiến trúc xử lý đồng thời (concurrency model) ảnh hưởng trực tiếp đến khả năng mở rộng (scalability), độ trễ phản hồi (latency), thông lượng (throughput) và mức tiêu thụ tài nguyên phần cứng (CPU, Memory).

### 1.2. Mục tiêu nghiên cứu
Đồ án này tập trung hiện thực một TCP Server hoàn chỉnh bằng ngôn ngữ Python, áp dụng mô hình kiến trúc **Thread Pool** (lớp `ThreadPoolExecutor` của thư viện `concurrent.futures`) kết hợp với giao thức truyền thông tầng ứng dụng **Length-Prefix kết hợp JSON**. Thông qua thực nghiệm đo lường tự động, nhóm tiến hành khảo sát và đánh giá định lượng:
1. Sự thay đổi của **thông lượng (Throughput - req/s)** khi số lượng kết nối đồng thời tăng dần (1, 10, 50 clients).
2. Sự biến thiên của **độ trễ phản hồi (Round Trip Time - Latency)** và các phân vị độ trễ quan trọng (P50, P95, P99).
3. Mức độ khai thác và sử dụng **tài nguyên CPU (%)** của hệ thống trong từng kịch bản tải.
4. Đánh giá tính ổn định, độ biến thiên (jitter) và tính công bằng (fairness) giữa các worker threads trong Thread Pool.

---

## 2. KIẾN TRÚC HỆ THỐNG VÀ THIẾT KẾ THỰC NGHIỆM

### 2.1. Kiến trúc TCP Server & Giao thức truyền thông
- **Mô hình xử lý:** Thread Pool với giới hạn `max_workers = 100`. Server lắng nghe trên một socket chính (`socket.AF_INET, socket.SOCK_STREAM`), khi có kết nối mới qua `accept()`, tác vụ xử lý client được ủy quyền cho một worker thread trong pool thực thi.
- **Giao thức ứng dụng (Protocol Framing):** Sử dụng cơ chế phân khung **Length-Prefix (4 bytes Big-Endian) + JSON Payload**:
  ```text
  Frame = [4-byte Length N] + [N-byte JSON UTF-8]
  ```
  Cơ chế này loại bỏ hoàn toàn các lỗi dính gói (packet sticking) hoặc phân mảnh gói tin (fragmentation) vốn là đặc tính cố hữu của luồng byte hướng dòng TCP.
- **Kích thước Payload:** Mỗi request mang gói tin echo có kích thước chuẩn **1 KB** (1024 bytes) dữ liệu ngẫu nhiên.

### 2.2. Kịch bản thực nghiệm
Hệ thống đo kiểm giả lập các client kết nối bền vững (persistent connection), đồng loạt xuất phát thông qua cơ chế đồng bộ `threading.Barrier`:
- **Kịch bản 1 (Tải tối thiểu):** 1 Client gửi 20 requests (đánh giá baseline độ trễ nguyên bản).
- **Kịch bản 2 (Tải trung bình):** 10 Clients đồng thời, mỗi client gửi 20 requests (tổng 200 requests).
- **Kịch bản 3 (Tải cao):** 50 Clients đồng thời, mỗi client gửi 20 requests (tổng 1000 requests).

Mức sử dụng CPU được lấy mẫu liên tục với chu kỳ 100 ms thông qua module `CpuMonitor` (tận dụng Windows Kernel32 Native API `GetSystemTimes`).

---

## 3. KẾT QUẢ VÀ PHÂN TÍCH BIỂU ĐỒ HIỆU NĂNG

### 3.1. Bảng số liệu tổng hợp thực nghiệm

Dữ liệu thô được ghi nhận và tổng hợp tự động từ module `src/metrics`:

| Kịch bản | Số Client | Tổng Request | Thành công | Throughput (req/s) | Latency Min (ms) | Latency Avg (ms) | P95 (ms) | P99 (ms) | Latency Max (ms) | CPU Avg (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Kịch bản 1** | 1 | 20 | 100% | **59.49** | 0.309 | **0.455** | 0.617 | 0.627 | 0.630 | 45.03% |
| **Kịch bản 2** | 10 | 200 | 100% | **620.87** | 0.531 | **2.169** | 4.372 | 5.231 | 5.598 | 35.58% |
| **Kịch bản 3** | 50 | 1000 | 100% | **1484.23** | 0.256 | **6.584** | 11.733 | 13.511 | 14.803 | 76.37% |

*Tỷ lệ request thành công đạt tuyệt đối 100% trên toàn bộ các kịch bản, không phát sinh lỗi timeout hay ngắt kết nối đột ngột.*

---

### 3.2. Phân tích Biểu đồ 1: Hàm phân phối tích lũy độ trễ (CDF - Cumulative Distribution Function)

Biểu đồ CDF biểu diễn xác suất một request có thời gian phản hồi nhỏ hơn hoặc bằng giá trị độ trễ cho trước:

```
CDF(x) = P(Latency <= x)
```

1. **Ở kịch bản 1 Client:** Đường cong CDF dựng đứng gần như vuông góc với trục hoành tại dải giá trị 0.35 - 0.55 ms. Điều này chứng minh độ trễ cực kỳ tập trung và ổn định, gần như không có độ biến động ngoài ý muốn (P99 chỉ đạt 0.63 ms).
2. **Ở kịch bản 10 Clients:** Đường cong dịch chuyển nhẹ sang phải, dốc thoai thoải từ 1.5 ms đến 4.0 ms. Giá trị trung vị P50 xấp xỉ 2.1 ms và 95% các request hoàn thành dưới 4.37 ms.
3. **Ở kịch bản 50 Clients:** Đường cong trải dài từ 3 ms đến 14.8 ms. Độ dốc giảm rõ rệt thể hiện hiện tượng phân tán độ trễ (long-tail latency). Mặc dù vậy, điểm P95 = 11.73 ms và P99 = 13.51 ms vẫn duy trì ở ngưỡng rất tốt đối với ứng dụng mạng chạy trên môi trường cục bộ, không có request nào bị kẹt bất thường.

---

### 3.3. Phân tích Biểu đồ 2: Phân bố độ trễ theo trục thời gian thực (Scatter Plot)

Đồ thị phân tán (Scatter Plot) giúp quan sát hành vi của hệ thống theo từng mốc thời gian thực:
- **Hiệu ứng Khởi tạo (Warmup Effect):** Ở kịch bản 10 và 50 clients, trong khoảng 0.05 giây đầu tiên, một số request đầu tiên có độ trễ cao hơn trung bình (khoảng 3.5 - 5.5 ms ở 10 clients và 8 - 14 ms ở 50 clients). Đây là thời điểm Server phải xử lý đồng thời việc thiết lập hàng loạt socket kết nối TCP thông qua hàm `accept()`, phân bổ bộ nhớ cho luồng mới trong Thread Pool và cấp phát buffer mạng.
- **Tính ổn định của pha ổn định (Steady State):** Ngay sau giai đoạn bắt tay kết nối ban đầu, các điểm đo tập trung thành dải ngang liên tục, không xuất hiện các điểm dị biệt (outliers) hoặc hiện tượng độ trễ tăng dần theo thời gian (dấu hiệu của rò rỉ bộ nhớ hoặc nghẽn hàng đợi tích lũy).

---

### 3.4. Phân tích Biểu đồ 3: So sánh tổng thể Thông lượng, Độ trễ và CPU (Grouped Bar Chart)

Biểu đồ so sánh tổng thể phản ánh rõ nét bản chất của mô hình xử lý đa luồng:
1. **Tăng trưởng Thông lượng (Throughput Scaling):**
   - Từ 1 lên 10 clients: Thông lượng tăng vọt từ 59.49 RPS lên 620.87 RPS (tăng gấp **10.43 lần**). Đây là mức tăng trưởng gần như tuyến tính hoàn hảo (tỷ lệ thuận O(N)), cho thấy Thread Pool phát huy tối đa hiệu quả trong việc xử lý các tác vụ chờ I/O mạng song song.
   - Từ 10 lên 50 clients: Thông lượng đạt **1484.23 RPS** (tăng gấp 2.39 lần so với 10 clients và gấp gần 25 lần so với 1 client). Tốc độ tăng trưởng thông lượng bắt đầu có xu hướng giảm tốc do hệ thống tiếp cận dần giới hạn năng lực xử lý của phần cứng.
2. **Sự đánh đổi về Độ trễ (Latency Trade-off):**
   - Độ trễ trung bình tăng từ 0.455 ms (1 client) -> 2.169 ms (10 clients) -> 6.584 ms (50 clients). Đây là cái giá tất yếu khi các luồng phải chia sẻ chu kỳ CPU và tài nguyên mạng socket.
3. **Mức tiêu thụ CPU:**
   - Kịch bản 1 và 10 clients duy trì mức CPU hệ thống trong khoảng 35% - 45% (phần lớn là mức nền của hệ điều hành).
   - Khi lên đến 50 clients, mức sử dụng CPU tăng vọt lên **76.37%** (đỉnh điểm 83.33%). Điều này khẳng định CPU đang hoạt động tích cực để giải mã JSON, mã hóa dữ liệu nhị phân và điều phối các luồng.

---

### 3.5. Phân tích Biểu đồ 4: Bản đồ nhiệt độ trễ từng Client (Heatmap per-client x seq)

Biểu đồ Heatmap khảo sát chi tiết 10 clients qua 20 lượt gửi liên tiếp:
- **Đánh giá tính công bằng (Fairness):** Các ô màu chuyển từ xanh thẫm (1.0 - 2.5 ms) sang vàng nhạt (3.0 - 4.5 ms) được phân bố đều khắp ma trận giữa các client từ `Client-1` đến `Client-10`.
- **Không có hiện tượng Starvation:** Không có bất kỳ client nào bị độc chiếm tài nguyên hay bị rơi vào vùng màu đỏ kéo dài. Điều này khẳng định thuật toán điều phối luồng của hệ điều hành và Thread Pool hoạt động công bằng, các socket nhận được thời gian CPU tương đương nhau.

---

## 4. ĐÁNH GIÁ CHUYÊN SÂU & ĐIỂM NGHẼN HỆ THỐNG (BOTTLENECK)

Từ các phân tích trên, nhóm rút ra các nhận định kỹ thuật chuyên sâu:

1. **Ảnh hưởng của Python Global Interpreter Lock (GIL):**
   - Mặc dù Python sử dụng cơ chế đa luồng thực (OS Native Threads), GIL ngăn cản nhiều bytecode Python chạy song song trên nhiều lõi CPU vật lý tại cùng một thời điểm.
   - Tuy nhiên, trong ứng dụng TCP Server này, phần lớn thời gian tiêu tốn là **I/O Bound** (đọc/ghi socket). Khi một thread thực hiện hàm gọi hệ thống `recv()` hoặc `send()`, Python tự động nhả khóa GIL, cho phép các thread khác tiếp tục thực thi. Nhờ đó, thông lượng vẫn tăng trưởng ấn tượng từ 59 lên 1484 RPS.
2. **Chi phí Chuyển đổi ngữ cảnh (Context Switching Overhead):**
   - Khi tăng từ 10 lên 50 clients, CPU tăng mạnh từ 35% lên 76%. Nguyên nhân chính không chỉ đến từ việc xử lý dữ liệu mà còn do hệ điều hành phải liên tục thực hiện chuyển đổi ngữ cảnh (context switch) giữa 50 worker threads đang đồng thời hoạt động.
3. **Chi phí Phân tích cú pháp (JSON Serialization Overhead):**
   - Việc đóng gói và phân tích chuỗi JSON (`json.dumps` và `json.loads`) tiêu tốn chu kỳ tính toán đáng kể của CPU trên mỗi request. Đối với các hệ thống cần hiệu năng cực cao, các định dạng nhị phân nhẹ hơn (như Protocol Buffers hoặc MsgPack) sẽ giúp giảm tải CPU rõ rệt.

---

## 5. ĐỀ XUẤT GIẢI PHÁP TỐI ƯU HÓA

Để nâng cao hơn nữa hiệu năng của TCP Server khi mở rộng lên quy mô 1000+ clients đồng thời, nhóm đề xuất các hướng cải tiến kỹ thuật sau:
1. **Chuyển đổi sang mô hình Hướng sự kiện (Event-Driven / I/O Multiplexing):**
   - Thay thế Thread-per-Client bằng mô hình bất đồng bộ không đồng bộ sử dụng các hàm gọi hệ thống hướng sự kiện như `epoll` (Linux) hoặc `I/O Completion Ports - IOCP` (Windows), tiêu biểu là thư viện `asyncio` trong Python. Mô hình này cho phép 1 luồng duy nhất quản lý hàng chục nghìn kết nối mà không tốn chi phí context switch.
2. **Áp dụng Zero-Copy và Tối ưu Buffer:**
   - Sử dụng các kiểu dữ liệu `memoryview` hoặc `bytearray` có sẵn của Python để thao tác cắt ghép byte header 4-byte mà không cần cấp phát thêm bộ nhớ trung gian.
3. **Cấu hình Socket TCP:**
   - Bật tùy chọn `TCP_NODELAY` (`setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)`) để vô hiệu hóa thuật toán Nagle, giúp các gói tin nhỏ phản hồi ngay lập tức mà không phải chờ gom buffer, giảm thiểu độ trễ RTT.

---

## 6. KẾT LUẬN

Đồ án đã hiện thực thành công mô hình **TCP Server đa luồng với Thread Pool** và xây dựng quy trình đo lường, phân tích dữ liệu hiệu năng hoàn chỉnh:
- Hệ thống hoạt động tin cậy, tỷ lệ thành công đạt 100% qua cả 3 mức tải thực nghiệm.
- Khẳng định được tính đúng đắn của mô hình lý thuyết: Thread Pool giúp tăng thông lượng lên tới gần **25 lần** (1484 req/s), trong khi giữ độ trễ trung bình ở mức an toàn (6.58 ms).
- Bộ công cụ đo lường và giao diện trực quan hóa dữ liệu được chuẩn hóa, cung cấp góc nhìn đa chiều qua các biểu đồ CDF, Scatter Plot, Grouped Bar Chart và Heatmap.

---
