# Backend hội thoại và gợi ý

Phạm vi thực hiện: TK-018 tạo phiên, TK-021 ngữ cảnh, TK-023 lưu tin nhắn,
TK-025 lịch sử, TK-032 điều phối gợi ý, TK-034 giải thích bổ sung,
TK-081 bảo vệ key và TK-084 lọc PII.
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
| `POST /api/chat/sessions/{id}/retry` | Phản hồi lại câu hỏi cuối chưa có assistant; không tạo thêm tin user. |
| `POST /api/chat/sessions/{id}/explanations` | JSON `{"mode":"simplify"}` hoặc `{"mode":"example"}`. |
| `POST /api/chat/sessions/{id}/solution` | JSON `{"confirmed":true}`; chỉ gọi sau xác nhận. |
| `PATCH /api/chat/sessions/{id}/messages/{message_id}/feedback` | JSON `{"feedback":1}`, `-1` hoặc `null`, chỉ trên assistant của mình. |
| `GET /api/ai/quota` | Hạn mức chung chat/quiz, thời điểm reset UTC. |

`session` gồm ID, thông tin môn/chủ đề, tiêu đề, `createdAt`, `updatedAt`.
`message` gồm ID, `sessionId`, `role`, `content`, `createdAt`, `hintLevel`,
`isFullSolution`, `tokenCount`, `feedback`, `sourceRefs`, `sourcesStatus`. Nguồn có
ID tài liệu/chunk, tiêu đề, thứ tự đoạn và `available`; trạng thái nguồn là
`available`, `none` hoặc `unavailable`. Các vai trò và mức gợi ý do server đặt. Nếu phiên
chưa có tiêu đề, câu hỏi đầu tiên được dùng làm tiêu đề rút gọn.

Thử API tại `http://localhost:8000/docs`: đăng nhập bằng `/api/auth/login`, dùng JWT
nhận được cho nút Authorize, tạo phiên với ID chủ đề thật rồi gửi tin hoặc lấy lịch sử.
API key của model chỉ đặt trong backend, không dùng làm token đăng nhập website.

## Khi chưa cấu hình model

Tạo phiên và đọc lịch sử vẫn hoạt động. Gửi tin sẽ lưu tin `user` trước; nếu chưa
có cấu hình model thì trả 503 `LLM_NOT_CONFIGURED`, không tạo câu trả lời giả.
Tin đã lưu vẫn xem được qua API lịch sử. Sau khi cấu hình model và khởi động lại
backend, gọi `/retry` để phản hồi câu hỏi gần nhất mà không nhân đôi tin user.

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

`LLM_API_URL` nhận endpoint đầy đủ hoặc base URL. Adapter hỗ trợ OpenAI-compatible
Chat Completions, Responses, Gemini GenerateContent, Anthropic Messages và Ollama;
`LLM_PROVIDER=auto` nhận diện theo URL hoặc đặt giao thức rõ ràng. Không chọn sẵn tên
model. Xem [cấu hình từng nhà cung cấp và giới hạn hỗ trợ](AI_SETUP.md). API có giao
thức riêng cần thêm adapter triển khai `LLMClient.generate()`.

Cấu hình để trống không làm backend lỗi khi khởi động. Key/URL được ẩn khỏi `repr`,
không trả về API và không đưa vào prompt. Adapter không tự theo redirect, giới hạn
thời gian 1–120 giây, phản hồi tối đa 256 KiB và text client tối đa 32.000 ký tự
để nhận JSON quiz; service chat giới hạn phản hồi riêng ở 8.000 ký tự.
Các log HTTP của lời gọi model được lọc theo execution context, không in URL/header/key.
Thông báo lỗi không chứa nội dung lỗi thô của nhà cung cấp.

## Ngữ cảnh và mức gợi ý

Service lấy các tin gần nhất của đúng phiên. Bộ tạo prompt giữ câu hỏi mới nhất,
đúng thứ tự hội thoại và giới hạn tối đa 12 messages/20.000 ký tự nội dung, kể cả
system prompt và ngữ cảnh môn học. Dữ liệu học tập không được chèn vào phần chỉ dẫn hệ thống.

Phản hồi cho câu hỏi mới dùng mức 1. Hai lần xin gợi ý tiếp theo lần lượt là mức 2 và 3;
sau đó API trả 409 `HINT_LIMIT_REACHED`. Gửi câu hỏi mới bắt đầu lại ở mức 1.
Mức 1 gợi mở khái niệm; mức 2 cụ thể hóa hướng kiểm tra; mức 3 chỉ dẫn một bước tiếp
theo. Các mức vẫn yêu cầu người học tự suy luận; lời giải đầy đủ dùng endpoint xác nhận riêng.
Mức đã thực sự trả về được lưu vào `chat_messages.hint_level`.

Trong một tiến trình, gửi chồng vào phiên đang chờ trả 409 `CHAT_BUSY`. Ở MySQL,
transaction khóa bản ghi phiên và so ID tin gần nhất trước khi lưu assistant:
ngữ cảnh đã đổi sẽ trả 409 `CHAT_CHANGED`, tránh phản hồi cũ hoặc trùng mức khi chạy
nhiều worker. Không giữ transaction/khóa database trong lúc chờ mạng model.
Thời gian hoạt động của phiên cập nhật cùng transaction ghi tin nhắn.

Tắt môn/chủ đề không làm mất lịch sử; phiên cũ vẫn đọc được. Gửi tin hoặc xin gợi ý
cho nội dung đã tắt trả 409 `TOPIC_CLOSED`.

## Giải thích bổ sung (TK-034)

`POST /api/chat/sessions/{id}/explanations` nhận JSON `{"mode":"simplify"}`
(Đơn giản hơn) hoặc `{"mode":"example"}` (Cho ví dụ), cùng Bearer token.
Backend lấy ngữ cảnh của đúng phiên: chủ đề, câu hỏi mới nhất, phản hồi gần nhất
và nguồn phù hợp. Nếu câu hỏi cuối chưa có phản hồi, yêu cầu hướng đến câu hỏi đó.
Client chỉ chọn mode; các trường tự đặt owner, ngữ cảnh hoặc xác nhận lời giải bị từ chối.

Prompt có chỉ dẫn riêng cho từng cách giải thích, tiếp tục gợi mở bằng tiếng Việt.
Trong giới hạn 12 messages/20.000 ký tự, câu hỏi và phản hồi cần giải thích được giữ;
phản hồi dài có thể rút gọn kèm dấu báo thay vì bị loại hoàn toàn. Bản gốc trong
database giữ nguyên. Chủ đề, lịch sử và nguồn đều qua bộ lọc dữ liệu nhạy cảm.

Thành công trả 201 `{session,userMessage:null,assistantMessage}` và lưu đúng một
tin assistant với `hintLevel:null`, `isFullSolution:false`, nguồn thực tế nếu có.
Thao tác không thêm tin user hoặc tăng thang gợi ý; lời giải đầy đủ vẫn dùng
`/solution` với xác nhận riêng. Một phản hồi lưu thành công tiêu một lượt quota chung.

Mode/body không hợp lệ trả 422, sai Content-Type trả 415; phiên thiếu/khác chủ cùng
404 (kể cả với ADMIN), chưa có câu hỏi trả 409 `CHAT_QUESTION_REQUIRED`, môn/chủ đề
đã đóng trả 409 `TOPIC_CLOSED`. Request chồng bị chặn bằng 409; hết quota trả 429.
Lỗi đọc ngữ cảnh trả 503 `CHAT_UNAVAILABLE`, lỗi lưu trả 503 `CHAT_SAVE_FAILED`.
Lỗi model, text không hợp lệ hoặc giao dịch lưu bị rollback không tiêu thêm quota;
thử lại cùng endpoint/mode. Chưa cấu hình model trả 503 `LLM_NOT_CONFIGURED`.

Nút Đơn giản hơn/Cho ví dụ trong chat đăng nhập đã gọi endpoint này. Kiểm thử riêng:
`test_chat_explanations_context.py`, `test_chat_explanations_api.py` và
`test_chat_explanations_database_integration.py` trong `back-end/tests/`.
Kiểm thử dùng model giả lập; chất lượng nội dung cần đánh giá bằng model thật.

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

Frontend chat của tài khoản đăng nhập đã nối tạo phiên theo chủ đề, gửi tin,
sidebar lịch sử, retry đúng thao tác, hints, giải thích, xác nhận lời giải và feedback.
Nguồn ready/active được tìm theo từ khóa và lưu refs thật trên assistant; đọc lịch
sử kiểm tra nguồn còn khả dụng. Quota dùng chung với sinh quiz, 30 lượt thành công
mỗi ngày UTC. Chế độ xem thử vẫn là dữ liệu minh họa riêng. Xem [AI_SETUP.md](AI_SETUP.md).
