# Hướng dẫn cập nhật Frontend — StudyMate AI

## Các file đã cập nhật (đặt đúng đường dẫn)

**01 — Hiển thị nguồn tham khảo và nhãn cảnh báo AI**
- `front-end/src/js/pages/chat-live.js`
- Luồng chat thật dùng `GET /api/chat/messages/{messageId}/sources` khi người học mở mục Nguồn tham khảo.
- Hiển thị tên tài liệu, số đoạn, trạng thái nguồn; xử lý trường hợp không có nguồn, tải lỗi và nút thử lại.
- Thêm nhãn `Nội dung do AI tạo` trên từng phản hồi AI và cảnh báo chung ở đầu khung chat.

**02 — CSS nguồn tham khảo và cảnh báo AI (file mới)**
- `front-end/src/css/chat-sources.css`
- Dùng biến màu có sẵn của dự án (`--pale`, `--hover`, `--border`, `--muted`), hỗ trợ màn hình nhỏ.

**03 — Nạp stylesheet mới**
- `front-end/index.html`
- Đã thêm link tới `src/css/chat-sources.css`; không cần import thủ công trong JavaScript.

**04 — Quản trị tài liệu**
- `front-end/src/js/pages/admin.js`
- Dùng đúng API backend: `GET /api/admin/documents/options`, `GET /api/admin/documents`, `POST /api/admin/documents`, `POST /api/admin/documents/{id}/process`, `PATCH /api/admin/documents/{id}`.
- Upload gửi `multipart/form-data` gồm `file`, `topic_id`, `title`; bật/tắt gửi JSON `{ "isActive": true|false }`.
- Chỉ bật/tắt khi tài liệu có trạng thái `ready`; trạng thái hiển thị được cập nhật theo phản hồi máy chủ.
- Khóa nút thao tác khi xử lý/bật-tắt đang chạy và xác minh trạng thái trả về trước khi cập nhật giao diện.

**05 — Kiểm thử hồi quy**
- `front-end/tests/ai-workflows.cjs`
- Thêm assertion kiểm tra nhãn AI trên từng phản hồi; bài test sẵn có kiểm tra API nguồn tham khảo và hiển thị tên nguồn.
- Các kiểm thử tài liệu hiện có nằm trong `front-end/tests/profile-upload.cjs`.

## API contract được sử dụng

Nguồn tham khảo chi tiết trả về `messageId`, `hasSources`, `sourceRefs`, `notice`; mỗi source có `documentId`, `chunkId`, `title`, `chunkIndex`, `sourceUrl` (có thể rỗng). Danh sách tin nhắn cũng có `sourceRefs` và `available`. Giao diện không tự tạo URL nguồn khi backend không trả `sourceUrl`.

Tài liệu quản trị lấy các trường `id`, `topicId`, `title`, `subjectName`, `topicName`, `status`, `isActive`, `createdAt`, `sizeBytes`, `fileName`, `processedAt`, `chunkCount`.

## Cách thay vào dự án

Giải nén `StudyMate_AI_Frontend_Updated.zip`. Chép đè thư mục `front-end` trong dự án của bạn bằng thư mục `front-end` trong gói. Backend không bị thay đổi. Nếu chỉ muốn thay từng file, dùng danh sách đường dẫn ở trên; `chat-sources.css` là file mới cần thêm.

## Kiểm tra đã thực hiện

- `node --check` cho các file JavaScript frontend và test: đạt.
- `python -m compileall -q app` cho mã backend: đạt.
- Chưa chạy được browser E2E/API tests trong môi trường đóng gói này: thiếu package Node `playwright`, thiếu `PyMySQL`, bản `pypdf` có sẵn không tương thích với import của dự án và Chromium bị môi trường chặn truy cập localhost. Chạy lại `npm ci` và các lệnh test trong môi trường dự án có đủ dependency trước khi merge.
