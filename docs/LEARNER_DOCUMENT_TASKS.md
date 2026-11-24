# Hai task bổ sung: người học xem tài liệu

Ghi nhận ngày 24/11/2026 theo yêu cầu người dùng. TK-096 và TK-097 được thêm
trong [task-additions.json](reference/task-additions.json); không phải các dòng
có sẵn trong bản XLSX gốc. Đây là mô tả công việc, chưa triển khai chức năng.

95 task gốc có upload/quản trị tài liệu (TK-038/039, TK-069/070) và trích dẫn AI
(TK-048/049), chưa có task người học mở và đọc toàn bộ tài liệu PDF/TXT.

## TK-096 — Giao diện xem tài liệu học tập

**Mô tả:** Người học xem danh sách và đọc tài liệu đã phát hành theo môn/chủ đề.

**Công việc cụ thể:**

- Thêm thao tác Xem tài liệu tại môn/chủ đề, điều hướng bằng ID thật.
- Lấy danh sách từ API: tên tài liệu, môn, chủ đề và định dạng PDF/TXT.
- Mở PDF trong trình xem và TXT dưới dạng văn bản UTF-8; nội dung lấy từ API
  có xác thực, không ghép URL tới đường dẫn lưu trữ nội bộ.
- Hiển thị tải, trống, lỗi và thao tác thử lại; không tạo tài liệu mẫu thay thế.
- Có thao tác Hỏi gia sư về chủ đề này, mở đúng topic trong luồng chat hiện có.
- Thông báo rõ khi tài liệu đã tắt, không còn truy cập được hoặc file bị thiếu.

## TK-097 — API xem tài liệu học tập

**Mô tả:** Tài khoản active đã đăng nhập lấy danh sách, thông tin và nội dung
tài liệu đã phát hành; dữ liệu lấy từ MySQL và file gốc được liên kết.

**Công việc cụ thể:**

| Endpoint đề xuất | Công việc |
| --- | --- |
| `GET /api/documents?subjectId=…&topicId=…&limit=…&offset=…` | Liệt kê, lọc theo môn/chủ đề và phân trang. |
| `GET /api/documents/{id}` | Trả metadata tài liệu cùng môn/chủ đề liên quan. |
| `GET /api/documents/{id}/content` | Trả nội dung file PDF/TXT để đọc trực tiếp. |

- Dùng MySQL/repository hiện có; file gốc đọc từ kho UPLOAD_DIR được liên kết
  qua bản ghi documents. Không cần lưu thêm bản PDF/TXT vào cột database.
- Chỉ liệt kê/đọc tài liệu ready và is_active=true, thuộc môn/chủ đề active.
- LEARNER và ADMIN active có thể đọc nguồn đã phát hành. Quản lý/upload/xem
  pending/error vẫn dùng các endpoint ADMIN hiện có, không mở quyền quản trị.
- Kiểm tra token và quyền ở cả ba endpoint, kể cả truy cập trực tiếp theo ID;
  trả lỗi phù hợp khi chưa đăng nhập, tài khoản bị khóa, tài liệu không khả dụng
  hoặc file không còn tồn tại.
- Trả MIME đúng PDF/TXT để hiển thị, không trả file_path nội bộ và không cho
  truy cập file ngoài kho được phép.
- GET chỉ đọc, không gọi model AI, không tiêu quota và không thay trạng thái nguồn.

Tài liệu học tập là nguồn chung theo môn/chủ đề, không phải tài liệu riêng theo
user_id. Lịch sử chat, quiz và tiến độ vẫn riêng từng tài khoản. Hai task này
không yêu cầu thay cơ chế retrieval hoặc ép AI chỉ được trả lời từ tài liệu.
