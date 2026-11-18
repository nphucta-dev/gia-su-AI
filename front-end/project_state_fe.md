# Trạng thái Frontend — Gia Sư AI

Ngày cập nhật: 18/11/2026
Phạm vi: trạng thái frontend sau khi đối chiếu `git diff` hiện tại với các task T2/T3 trong `docs/reference/task-assignments.json`. Đây là đánh giá code trong working tree; file phân công chỉ dùng để tra task, không dùng trạng thái trong file làm bằng chứng nghiệm thu.

## Kết luận từ git diff

Diff hiện tại chủ yếu thay đổi giao diện, luồng preview và bộ test frontend. Một số phần tích hợp API có trong phiên bản trước đã bị loại khỏi working tree:

- `src/js/pages/admin.js` đã giữ riêng preview trong bộ nhớ và luồng quản trị thật dùng API cho CRUD môn học/chủ đề, trạng thái active và tài liệu.
- `src/js/pages/learning.js` bỏ `loadCatalog()` và quay lại `src/js/data.js`; trang học và dashboard dùng dữ liệu mẫu.
- `src/js/pages/chat.js` bỏ `loadCatalog()` và API chat; tin nhắn, hints, lời giải, feedback và nguồn đều là nội dung minh họa.
- `src/js/pages/practice.js` bỏ tải danh mục và dùng câu hỏi từ `src/js/data.js`; submit chỉ lưu state cục bộ.
- `src/js/pages/history.js` vẫn dùng danh sách hoạt động hard-code.
- `src/js/pages/account.js` ghi rõ hồ sơ chỉ kiểm tra bản nháp cục bộ, chưa gọi API profile.
- `src/js/app.js` bỏ kiểm tra quyền ADMIN qua API; `src/js/session.js` thay đổi cách khôi phục phiên và bỏ xử lý thời hạn token ở client. Cần kiểm tra lại với backend hiện tại trước khi merge.
- Có thêm ảnh output và test frontend, nhưng ảnh/test không thay thế bằng chứng UI đã nối API thật.

Vì vậy TK-068 đã có thể kiểm thử độc lập ở frontend; các nhận định về TK-009, TK-069 và các task chat/quiz/dashboard vẫn cần được xử lý trong phạm vi riêng.

## Đã có trong diff hoặc code hiện tại

- Form đăng ký, đăng nhập và hiển thị lỗi tiếng Việt.
- Đăng xuất phía client và xóa token.
- Giao diện hồ sơ, danh mục, chat, quiz, dashboard và quản trị.
- Chặn câu hỏi trắng/rỗng trên UI.
- Nút gợi ý, ví dụ, giải thích đơn giản và modal xác nhận lời giải.
- Giao diện quiz 5 câu, chọn đáp án, điều hướng câu hỏi và cảnh báo câu chưa trả lời.
- Nhãn cảnh báo: `Câu trả lời do AI tạo, hãy đối chiếu với tài liệu học tập.`
- CSS responsive và một số test/ảnh kiểm tra giao diện.

Các mục trên chỉ xác nhận phần UI hoặc client behavior; task nghiệp vụ chỉ hoàn tất sau khi có API thật, xử lý lỗi và kiểm thử tích hợp.

## Task frontend T2/T3

| Task | Nội dung | Đánh giá sau khi xem diff |
|---|---|---|
| TK-007 | Đăng xuất phía client | Có |
| TK-009 | Trang hồ sơ cá nhân | Chưa xong; diff chuyển về bản nháp cục bộ, không gọi API profile |
| TK-022 | Trạng thái chờ phản hồi | Chưa xong; chỉ có selector xem trước, chưa gắn request chat |
| TK-024 | Sidebar lịch sử chat | Đã tích hợp sidebar lịch sử chat với API; mở lại đúng nội dung phiên theo tài khoản. |
| TK-026 | Chặn câu hỏi rỗng UI | Có |
| TK-031 | Nút gợi ý 3 mức | Một phần; có UI nhưng chưa gọi API hints |
| TK-033 | Đơn giản hơn/Cho ví dụ | Một phần; nội dung đang hard-code |
| TK-035 | Modal xác nhận lời giải | Một phần; modal có nhưng chưa gọi API lời giải |
| TK-048 | Hiển thị nguồn tham khảo | Chưa xong; chỉ có nguồn minh họa |
| TK-050 | Chọn chủ đề và độ khó quiz | Hoàn thành FE: lấy chủ đề active từ API catalog, hỗ trợ topic trên URL, chọn easy/medium/hard, validation, loading/empty/error/retry và responsive 360px. Chưa gọi API sinh quiz; phần đó thuộc task sau. |
| TK-053 | Giao diện làm quiz | Một phần; có UI nhưng câu hỏi lấy từ dữ liệu mẫu |
| TK-054 | Cảnh báo câu chưa trả lời | Có phần UI; chưa nối submit thật |
| TK-057 | Gửi đáp án quiz | Hoàn thành phạm vi FE: lưu A–D theo question ID, tạo payload có thứ tự, confirmation/loading, chặn thiếu câu và gửi trùng, giữ đáp án khi lỗi và xử lý retry/trạng thái API. Browser test dùng API mock theo hợp đồng FE dự kiến; backend submit/chấm/lưu quiz chưa được triển khai nên chưa hoàn thành end-to-end. |
| TK-060 | Trang kết quả quiz | Chưa xong; tính điểm từ dữ liệu mẫu |
| TK-068 | Trang quản trị môn/chủ đề | Đã nối API CRUD cho môn học/chủ đề và trạng thái active; có loading, lỗi/thử lại, validation, tìm kiếm và responsive 360px. Preview vẫn tách riêng, không ghi API. |
| TK-069 | Trang quản trị tài liệu | Chưa xong và đang bị hồi quy; upload/trạng thái/bật tắt chỉ ở preview |
| TK-076 | UI hiển thị quota | Chưa xong; chưa có quota API thật |
| TK-083 | Nhãn cảnh báo nội dung AI | Có phần UI |
| TK-091 | Responsive quiz/dashboard/admin | Một phần; có CSS/ảnh/test mới nhưng các trang vẫn dùng dữ liệu mẫu |

## Việc cần ưu tiên sau diff

1. Khôi phục tích hợp API thật trong `learning.js`, `account.js`, `chat.js`, `practice.js` và `history.js`; tiếp tục xử lý phần tài liệu quản trị ở task TK-069 riêng.
2. Kiểm tra lại `api-base`, đường dẫn `/api`, khôi phục kiểm tra quyền ADMIN và xác thực session thống nhất với backend.
3. Nối chat session, message, lịch sử, hints, loading, retry, citation và feedback.
4. Nối quiz create, submit một lần, result và cập nhật tiến độ.
5. Nối dashboard, history và quota.
6. Chạy lại test auth/profile/admin/upload và kiểm tra responsive 360px sau khi khôi phục API.

## Ghi chú

Không đánh dấu task hoàn thành chỉ vì có màn hình, ảnh output hoặc dữ liệu mẫu. Một task frontend hoàn chỉnh cần luồng UI → API → dữ liệu, trạng thái thành công/lỗi và kiểm thử tương ứng.
