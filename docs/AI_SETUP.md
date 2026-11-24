# Cấu hình model AI

Các luồng chat Socratic, gợi ý 3 mức, giải thích đơn giản/ví dụ, lời giải có xác
nhận và sinh quiz dùng chung một client model ở backend. Frontend của tài khoản
đăng nhập gọi API thật. Chế độ đăng nhập xem thử đã tắt; dữ liệu cá nhân, lịch sử
và số liệu học tập luôn lấy từ API theo tài khoản đang đăng nhập.

## Chỉ cần cấu hình khi đã có API

Điền vào **`back-end/.env`**, không điền vào frontend:

```dotenv
LLM_API_KEY=key-do-nha-cung-cap-cap
LLM_API_URL=https://dia-chi-api-cua-ban/v1/chat/completions
LLM_MODEL=ten-model-trong-tai-khoan-cua-ban
LLM_PROVIDER=auto
LLM_TIMEOUT_SECONDS=60
```

Sau đó khởi động lại Uvicorn. Không cần sửa route, service hay mã frontend để đổi
model dùng cùng giao thức. `LLM_API_URL` nhận endpoint đầy đủ hoặc base URL theo
bảng dưới. Không đặt key trong URL. Các tên model dưới đây là chỗ điền, không phải
model đã chọn sẵn hay lời hứa mọi model đều được tài khoản của bạn cấp quyền.

| Chuẩn API | `LLM_PROVIDER` | Ví dụ URL | `LLM_MODEL` |
| --- | --- | --- | --- |
| OpenAI Chat Completions / API tương thích | `auto` hoặc `openai_compatible` | `https://api.openai.com/v1` hoặc endpoint `/chat/completions` của dịch vụ | Tên text/chat model được cấp quyền |
| OpenAI Responses | `responses` | `https://api.openai.com/v1/responses` | Tên model hỗ trợ Responses |
| Gemini GenerateContent | `gemini` | `https://generativelanguage.googleapis.com/v1beta` | Tên Gemini model, có hoặc không tiền tố `models/` |
| Gemini qua OpenAI compatibility | `openai_compatible` | `https://generativelanguage.googleapis.com/v1beta/openai/` | Tên model tương thích |
| Anthropic Messages | `anthropic` | `https://api.anthropic.com/v1/messages` | Tên Claude model được cấp quyền |
| Ollama native | `ollama` | `http://localhost:11434` | Tên model đã tải trong Ollama |
| Server local tương thích OpenAI | `openai_compatible` | `http://localhost:1234/v1` | Tên model đang được server local phục vụ |

`auto` nhận diện các endpoint `/responses`, `/api/chat`, `/messages`,
`:generateContent` và domain Gemini/Anthropic; các địa chỉ khác mặc định dùng Chat
Completions. Với gateway hoặc base URL không thể nhận diện, đặt `LLM_PROVIDER` rõ
ràng. Server local trên localhost/loopback và Ollama cho phép để trống key. Model
cục bộ vẫn phải được một server API đang chạy phục vụ; đường dẫn file weights
không thay thế được API URL.

Anthropic yêu cầu giới hạn đầu ra: `LLM_MAX_TOKENS=4096` mặc định (1–32768),
`LLM_API_VERSION=2023-06-01` có thể thay khi endpoint yêu cầu phiên bản khác.
Timeout cho phép 1–120 giây. Model chạy chậm có thể cần tăng timeout trong phạm vi
này. Client không tự gửi lại yêu cầu có thể tính phí; người dùng bấm thử lại.
Proxy `front-end/serve.cjs` cho các POST sinh nội dung AI chờ tối đa 150 giây,
đủ cho timeout model 120 giây; các API khác giữ timeout proxy 30 giây.

Hỗ trợ đổi **model sinh văn bản dùng các chuẩn trên**, bao gồm qua một gateway
tương thích. API riêng, model chỉ embedding/ảnh/âm thanh, yêu cầu Azure deployment
đặc thù hay giao thức streaming riêng cần adapter bổ sung. Không có cách chỉ nhập
một tên model bất kỳ mà bỏ qua khả năng, quyền truy cập và giao thức của dịch vụ.

Nếu provider hỗ trợ `GET /models`, dùng đúng ID model có trong danh mục của tài
khoản. Một tên model tồn tại ở dịch vụ khác không bảo đảm hoạt động với URL/key
đang dùng. Khi nhận `LLM_ERROR`, cần kiểm tra cả quyền dùng model và số dư provider;
backend giữ thông báo cố định, không chuyển lỗi thô hay thông tin thanh toán ra UI.

## Luồng sử dụng

1. Chạy MySQL/schema hiện có, backend và frontend theo README của dự án.
2. Đăng nhập LEARNER, chọn chủ đề ở trang chủ rồi mở chat hoặc luyện tập.
3. Chat lưu câu hỏi, lấy nguồn đúng chủ đề đang `ready` và bật sử dụng, gọi model,
   lưu phản hồi và các nguồn thực tế. Sidebar mở lại hội thoại từ backend.
4. Gợi ý tăng lần lượt 1–3; đơn giản hơn/ví dụ là thao tác riêng. Lời giải đầy đủ
   chỉ gọi model sau xác nhận. Feedback được cập nhật trên chính tin assistant.
5. Luyện tập chọn chủ đề/độ khó, yêu cầu model sinh đúng 5 câu, kiểm tra rồi lưu.
   Khi nộp, backend chấm và lưu tiến độ; trang kết quả đọc điểm/giải thích đã lưu.

ADMIN có thể bật/tắt tài liệu bằng `PATCH /api/admin/documents/{id}` với
`{"isActive":true}` hoặc `false`. Chỉ tài liệu `ready` có chunk mới bật được.
Tài liệu tắt hoặc thuộc môn/chủ đề tắt không được truy xuất cho yêu cầu mới;
nguồn đã lưu trong lịch sử được đánh dấu không còn khả dụng khi đọc lại. Các
source refs do server lấy từ chunk thực, không tin ID/trích dẫn model tự sinh.
Việc chọn chunk không chứng minh mọi câu model viết được nguồn hỗ trợ.

Không có model: tạo phiên/đọc lịch sử vẫn được, gửi tin trả
`503 LLM_NOT_CONFIGURED` và giữ câu hỏi; thử lại qua `/retry` không nhân đôi câu
hỏi. Sinh quiz thất bại không tạo đề mẫu. JSON không đủ 5 câu/đáp án/giải thích
không được lưu. Điểm quiz do code backend tính, không dùng model chấm trắc nghiệm.

Phản hồi bị cắt do giới hạn token, chưa kết thúc hoặc yêu cầu tool không được lưu
như một kết quả thành công. Các adapter kiểm tra metadata kết thúc khi provider
có cung cấp; trả `502 LLM_INVALID_RESPONSE` nếu trạng thái không hoàn tất.
Chat/quiz phải có nội dung nhìn thấy được. Quiz được kiểm tra đủ 5 câu và các lựa
chọn khác nhau trước và sau khi lọc thông tin cá nhân.

## Quota, lưu trữ và quyền

`GET /api/ai/quota` trả `limit`, `used`, `remaining`, `nextResetAt`,
`resetTimezone`. Mặc định **30 lượt AI thành công/ngày/tài khoản**, reset
**00:00 UTC** (07:00 Việt Nam). Chat, gợi ý, lời giải, giải thích và sinh quiz dùng
chung quota. Đây là lựa chọn triển khai thống nhất theo yêu cầu tích hợp AI mới;
tài liệu gốc không chỉ rõ múi giờ hoặc việc chia sẻ quota chat/quiz.

Lượt dùng được đếm từ assistant messages và quizzes đã lưu trong ngày, không
thêm bảng quota. Quiz cũ được tạo qua service cũng được tính theo ngày tạo vì
schema hiện có không lưu nguồn tạo quiz. Lỗi provider, JSON quiz không hợp lệ,
đọc lịch sử/kết quả, feedback và chấm bài không tiêu thêm lượt. MySQL advisory
lock theo tài khoản bảo vệ kiểm tra quota và tạo kết quả khi có nhiều worker;
không giữ transaction khóa bản ghi trong lúc chờ mạng model. Đang có yêu cầu AI
cùng tài khoản trả `409 AI_REQUEST_BUSY`. Hết quota vẫn đọc dữ liệu đã lưu.

Các API kiểm tra token, tài khoản active và ownership; ADMIN không được đọc dữ
liệu học của tài khoản khác. Secret chỉ nằm ở backend; payload gửi model lọc tên/
email tài khoản, hash và các bí mật có nhãn đã biết. Bộ lọc quy tắc không nhận
diện được mọi dữ liệu cá nhân không có nhãn. Cấu hình, header và lỗi thô của
provider không trả cho trình duyệt. Không đổi MySQL, ID số tự tăng hoặc scrypt.

## Kiểm chứng

Kiểm thử HTTP MockTransport bao phủ 5 giao thức và luồng API thật chat → nguồn →
sinh quiz → chấm → kết quả → quota. Kiểm thử trình duyệt dùng provider giả lập
riêng; kiểm thử MySQL dùng database tạm ngẫu nhiên. Bộ kiểm thử mặc định không gọi
provider thật. Kiểm tra TK-020/TK-051, trạng thái hoàn tất, nội dung vô hình và
quota/retry bằng:

```powershell
cd D:\gia-su-AI\back-end
.\venv\Scripts\python.exe -m pytest -q tests/test_llm_task_contracts.py tests/test_ai_provider_workflows.py
```

Khi URL/key/model và tài khoản provider sẵn sàng, kiểm tra trực tiếp hai API bằng
hai lần gọi model thật với dữ liệu học tập giả lập, không ghi MySQL:

```powershell
$env:RUN_LIVE_LLM_TESTS = '1'
try {
    .\venv\Scripts\python.exe -m pytest -q tests/test_llm_live.py
} finally {
    Remove-Item Env:RUN_LIVE_LLM_TESTS -ErrorAction SilentlyContinue
}
```

Bài kiểm tra này xác nhận chat có nội dung tiếng Việt, quiz đủ 5 câu A–D, lưu đáp
án/giải thích phía server và không lộ đáp án trước nộp. Vẫn cần người học đối chiếu
chất lượng gợi mở và kiến thức với tài liệu. Nếu provider từ chối vì model/quyền
hoặc hết số dư, chưa thể kết luận chất lượng phản hồi thật.

Định dạng adapter đối chiếu tài liệu chính thức:
[OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
[OpenAI Responses](https://developers.openai.com/api/reference/resources/responses/methods/create),
[Gemini GenerateContent](https://aistudio.google.com/api-reference/generate-content),
[Anthropic Messages](https://platform.claude.com/docs/en/api/messages/create?version=2023-06-01),
[Anthropic stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons),
[Ollama Chat](https://docs.ollama.com/api/chat),
[Ollama OpenAI compatibility](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx).
