# Quyền sở hữu dữ liệu (TK-082)

Yêu cầu đối chiếu: TK-082 trong `reference/task-details.json`, SRS FR-10.1,
thiết kế CSDL về `user_id` và quyền của các bản ghi con qua bản ghi cha.
Chủ sở hữu luôn được xác định từ tài khoản active đã xác thực bằng Bearer token.

## API được bảo vệ

| API | Phạm vi dữ liệu |
| --- | --- |
| `GET /api/chat/sessions` | Danh sách phiên của tài khoản hiện tại. |
| `GET /api/chat/sessions/{id}` | Phiên thuộc tài khoản hiện tại. |
| `GET /api/chat/sessions/{id}/messages` | Tin nhắn thông qua phiên đã lọc chủ sở hữu. |
| `POST /api/chat/sessions/{id}/messages` | Chỉ ghi câu hỏi/phản hồi vào phiên của mình. |
| `POST /api/chat/sessions/{id}/hints` | Chỉ tiếp tục phiên của mình; từ chối trước khi gọi model khi sai chủ sở hữu. |
| `GET /api/quizzes/{id}` | Quiz của mình; câu hỏi được truy vấn qua quiz có cùng điều kiện chủ sở hữu. |
| `GET /api/progress` | Tiến độ đã lưu của mình, có `limit`/`offset`. |
| `GET /api/progress/{id}` | Bản ghi tiến độ thuộc tài khoản hiện tại. |

Các API đọc quiz/tiến độ là phần bổ sung của TK-082. Truy vấn SQL lọc đồng thời ID
tài nguyên và `user_id`; danh sách tiến độ lọc tài khoản trước khi phân trang.
Query/header tự gửi như `user_id`, `userId` hay `X-User-Id` không cấp quyền và không
đổi tài khoản đang được dùng để truy vấn. Tạo phiên/quiz lấy chủ sở hữu từ server.
ADMIN cũng áp dụng quy tắc chủ sở hữu cho dữ liệu học tập riêng.

## Phản hồi

| Trường hợp | HTTP |
| --- | --- |
| Tài nguyên thuộc tài khoản đang đăng nhập | `200` khi đọc. |
| ID không tồn tại hoặc thuộc tài khoản khác | Cùng `404` và cùng nội dung lỗi trong từng loại tài nguyên. |
| Thiếu token, token sai/hết hạn hoặc tài khoản đã bị xóa | `401`. |
| Tài khoản đã bị vô hiệu hóa | `403`. |
| ID/phân trang vượt giới hạn hoặc sai định dạng | `422`. |

ID dùng số nguyên từ 1 đến 2³¹−1. Tiến độ nhận `limit` 1–100 (mặc định 20),
`offset` 0–100000; trả `{progress: [...], limit, offset, hasMore}`. Chi tiết trả
`{progress: {...}}` với `id`, `topicId`, `totalQuizzes`, `correctCount`, `totalCount`,
`masteryPercent`, `lastStudiedAt`. API chỉ đọc các giá trị đã lưu.

Quiz dùng `QuizResponse` hiện có: thông tin bài và câu hỏi/lựa chọn; không trả
`correct_answer`, `explanation` hoặc thông tin tài khoản. Lịch sử của chủ sở hữu
vẫn đọc được khi môn/chủ đề đã tắt. Các phản hồi chat/quiz/tiến độ, gồm phản hồi lỗi,
đều có `Cache-Control: no-store`.

## Phạm vi và kiểm thử

TK-082 không thêm API sửa tiến độ, nộp/chấm quiz, sinh câu hỏi bằng LLM hoặc giao diện
dashboard. Khi triển khai thao tác mới trên câu hỏi/câu trả lời, phải suy ra chủ sở
hữu qua `quizzes → quiz_questions → quiz_answers` trước khi đọc/ghi; bảng con không
nhận thêm `user_id`. Các đường truy cập hiện tại lấy câu hỏi qua quiz đã lọc owner.

Các kiểm thử API dùng hai người học và ADMIN để kiểm tra truy cập đúng/sai chủ sở
hữu, giả mạo tài khoản, ID giả, xác thực, không lộ đáp án, phân trang và không thay
đổi dữ liệu hay gọi model khi bị từ chối:

```powershell
cd D:\gia-su-AI\back-end
.\venv\Scripts\python.exe -m pytest -q tests/test_chat_ownership_api.py tests/test_quiz_ownership_api.py tests/test_progress_api.py
```

`tests/test_ownership_database_integration.py` kiểm tra cùng các điều kiện trên
MySQL thực khi có `TEST_DATABASE_URL`. Fixture tạo database tạm tên ngẫu nhiên rồi
xóa đúng database đó; không ghi database dự án hoặc gọi LLM thật. Không cần migration
hay seed để áp dụng phần code này.
