# Backend hội thoại và gợi ý

Phạm vi thực hiện: TK-018 tạo phiên, TK-021 ngữ cảnh, TK-023 lưu tin nhắn,
TK-025 lịch sử, TK-032 điều phối gợi ý, TK-081 bảo vệ key và TK-084 lọc PII.
Dữ liệu dùng các bảng `chat_sessions`/`chat_messages` hiện có trong MySQL, không thêm migration.

## API

Các API yêu cầu Bearer token của tài khoản đang hoạt động. Tài khoản chỉ lấy được
phiên của chính mình; phiên không thuộc tài khoản trả 404. Các phản hồi chat có
`Cache-Control: no-store`. Backend kiểm tra quyền độc lập với giao diện.

| API | Kết quả |
| --- | --- |
| `POST /api/chat/sessions` | JSON `{"topicId":1,"title":"Ôn tập"}`; `title` tùy chọn; trả 201 `{session}`. Môn/chủ đề phải active. |
| `GET /api/chat/sessions?limit=20&offset=0` | Trả `{sessions,limit,offset,hasMore}`, phiên hoạt động gần nhất trước. `limit` 1–100. |
| `GET /api/chat/sessions/{id}` | Thông tin phiên của chính tài khoản. |
| `GET /api/chat/sessions/{id}/messages?limit=50&offset=0` | Trả `{session,messages,limit,offset,hasMore}`, tin cũ đến mới. `limit` 1–200. |
| `POST /api/chat/sessions/{id}/messages` | JSON `{"content":"Em nên bắt đầu giải phương trình này thế nào?"}`; lưu câu hỏi rồi gọi model; trả 201 `{session,userMessage,assistantMessage}`. |
| `POST /api/chat/sessions/{id}/hints` | Không cần body; tạo gợi ý tiếp theo, trả 201 `{session,userMessage:null,assistantMessage}`. |

`session` gồm ID, thông tin môn/chủ đề, tiêu đề, `createdAt`, `updatedAt`.
`message` gồm ID, `sessionId`, `role`, `content`, `createdAt`, `hintLevel`,
`isFullSolution`, `tokenCount`. Các vai trò và mức gợi ý do server đặt. Nếu phiên
chưa có tiêu đề, câu hỏi đầu tiên được dùng làm tiêu đề rút gọn.

Thử API tại `http://localhost:8000/docs`: đăng nhập bằng `/api/auth/login`, dùng JWT
nhận được cho nút Authorize, tạo phiên với ID chủ đề thật rồi gửi tin hoặc lấy lịch sử.
API key của model chỉ đặt trong backend, không dùng làm token đăng nhập website.

## Khi chưa cấu hình model

Tạo phiên và đọc lịch sử vẫn hoạt động. Gửi tin sẽ lưu tin `user` trước; nếu chưa
có cấu hình model thì trả 503 `LLM_NOT_CONFIGURED`, không tạo câu trả lời giả.
Tin đã lưu vẫn xem được qua API lịch sử. Sau khi cấu hình model và khởi động lại
backend, có thể gọi `/hints` để phản hồi câu hỏi gần nhất ở mức 1 nếu câu đó chưa có phản hồi.

Các lỗi timeout (504), giới hạn dịch vụ model (429), mất mạng hoặc phản hồi không hợp lệ
(502) cũng giữ nguyên câu hỏi. Không tạo tin assistant hoặc tăng mức gợi ý khi model thất bại.

## Cấu hình và adapter model

Đặt trong `back-end/.env`, sau đó khởi động lại backend:

```dotenv
LLM_API_KEY=
LLM_API_URL=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=30
```

`LLM_API_URL` là **endpoint đầy đủ**, ví dụ endpoint chat-completions do nhà cung cấp
đưa, không chỉ là domain/base URL. Adapter gửi JSON `model`/`messages` và Bearer key
trong header; đọc `choices[0].message.content` theo định dạng
[Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).
Không chọn sẵn nhà cung cấp hay tên model. Nếu API dùng định dạng hoặc cách xác thực khác,
thay adapter triển khai `LLMClient.generate()`; không cần đổi service quản lý chat.

Cấu hình để trống không làm backend lỗi khi khởi động. Key/URL được ẩn khỏi `repr`,
không trả về API và không đưa vào prompt. Adapter không tự theo redirect, giới hạn
thời gian 1–120 giây, phản hồi tối đa 256 KiB và nội dung tối đa 8.000 ký tự.
Các log HTTP của lời gọi model được lọc theo execution context, không in URL/header/key.
Thông báo lỗi không chứa nội dung lỗi thô của nhà cung cấp.

## Ngữ cảnh và mức gợi ý

Service lấy các tin gần nhất của đúng phiên. Bộ tạo prompt giữ câu hỏi mới nhất,
đúng thứ tự hội thoại và giới hạn tối đa 12 messages/20.000 ký tự nội dung, kể cả
system prompt và ngữ cảnh môn học. Dữ liệu học tập không được chèn vào phần chỉ dẫn hệ thống.

Phản hồi cho câu hỏi mới dùng mức 1. Hai lần xin gợi ý tiếp theo lần lượt là mức 2 và 3;
sau đó API trả 409 `HINT_LIMIT_REACHED`. Gửi câu hỏi mới bắt đầu lại ở mức 1.
Mức 1 gợi mở khái niệm; mức 2 cụ thể hóa hướng kiểm tra; mức 3 chỉ dẫn một bước tiếp
theo. Các mức vẫn yêu cầu người học tự suy luận, chưa mở luồng lời giải đầy đủ.
Mức đã thực sự trả về được lưu vào `chat_messages.hint_level`.

Trong một tiến trình, gửi chồng vào phiên đang chờ trả 409 `CHAT_BUSY`. Ở MySQL,
transaction khóa bản ghi phiên và so ID tin gần nhất trước khi lưu assistant:
ngữ cảnh đã đổi sẽ trả 409 `CHAT_CHANGED`, tránh phản hồi cũ hoặc trùng mức khi chạy
nhiều worker. Không giữ transaction/khóa database trong lúc chờ mạng model.
Thời gian hoạt động của phiên cập nhật cùng transaction ghi tin nhắn.

Tắt môn/chủ đề không làm mất lịch sử; phiên cũ vẫn đọc được. Gửi tin hoặc xin gợi ý
cho nội dung đã tắt trả 409 `TOPIC_CLOSED`.

## Dữ liệu cá nhân

Chỉ bản sao gửi model được lọc: tên/email tài khoản đã biết, email trong văn bản,
giá trị bí mật đã biết và các đoạn có nhãn họ tên, mật khẩu, API key, token,
Bearer/Authorization hoặc JWT. Việc lọc áp dụng cả ngữ cảnh chủ đề và lịch sử;
phản hồi model cũng được lọc trước khi lưu/trả về. Không gửi đối tượng User, ID tài
khoản, hash mật khẩu hoặc cấu hình server trong payload.

Nội dung user gốc vẫn được lưu trong lịch sử riêng của tài khoản. Bộ lọc quy tắc
không bảo đảm nhận diện mọi tên người hay mật khẩu tùy ý không có nhãn; cần đánh giá
và bổ sung theo dữ liệu thực tế trước khi mở rộng phạm vi sử dụng.

## Phạm vi kiểm thử

Kiểm thử sử dụng model giả lập và HTTP MockTransport, không dùng key thật hoặc gửi
người học sang dịch vụ ngoài. Các kiểm thử MySQL tùy chọn dùng database tạm để kiểm
tra lưu phiên/tin, rollback, mức gợi ý và tranh chấp ghi. Chất lượng câu trả lời
Socratic thực tế cần đánh giá tiếp khi có model theo [các tình huống prompt](SOCRATIC_PROMPT.md).

Frontend chat hiện vẫn là giao diện minh họa; các nút gửi/hint/sidebar chưa gọi bộ
API mới. Quota hằng ngày, RAG và luồng xác nhận lời giải đầy đủ là các phần riêng.
