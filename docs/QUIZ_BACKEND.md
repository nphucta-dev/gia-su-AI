# Sinh JSON, kiểm tra và lưu quiz (TK-051/TK-052)

Backend có `QuizService.save_generated_quiz(user, topic_id, difficulty, generated_payload)`
để nhận kết quả từ luồng sinh quiz phía server. `app.state.quiz_service` dùng repository
MySQL trong ứng dụng, repository bộ nhớ trong kiểm thử.

`user` là tài khoản đã xác thực; chủ đề và độ khó do luồng server truyền vào. Kết quả
AI chỉ chứa nội dung câu hỏi, không được tự đặt `user_id`, điểm hay trạng thái bài.

Ví dụ định dạng một câu trong payload JSON:

```json
{
  "questions": [
    {
      "question_text": "1 + 1 bằng bao nhiêu?",
      "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
      "correct_answer": "B",
      "explanation": "Một cộng một bằng hai."
    }
  ]
}
```

Ví dụ trên chỉ minh họa một câu; payload hợp lệ phải có **đúng 5 câu**. Mỗi câu có
đủ bốn lựa chọn không rỗng, đúng các khóa `A`, `B`, `C`, `D`, một `correct_answer`
thuộc A–D và `question_text`/`explanation` không rỗng. Thứ tự 1–5 do server tạo từ
mảng câu hỏi. Backend chặn trường lạ, sai kiểu, JSON lỗi/trùng khóa và ký tự không
hợp lệ với MySQL. Nội dung câu hỏi/giải thích tối đa 8000 ký tự, mỗi lựa chọn tối đa
2000 ký tự. Câu hỏi/lựa chọn trùng sau chuẩn hóa Unicode, chữ hoa/thường và khoảng
trắng bị từ chối trong bộ kiểm tra chung, kể cả khi gọi service lưu trực tiếp.
Nội dung chỉ gồm ký tự vô hình hoặc dấu kết hợp không được coi là văn bản hợp lệ.
Kiểm tra cấu trúc không chứng minh được đáp án đúng về mặt kiến thức.

Toàn bộ payload được kiểm tra trước khi gọi repository. Sau đó MySQL kiểm tra lại
tài khoản active và môn/chủ đề active, lưu `quizzes` cùng 5 `quiz_questions` trong
một transaction. Lỗi ở bất kỳ câu nào hủy toàn bộ giao dịch. Bài mới có trạng thái
`in_progress`, chưa có điểm/kết quả và chưa cập nhật tiến độ. Không cần migration mới.

Kết quả service chỉ trả ID, chủ đề, độ khó, trạng thái, thời gian và các câu/lựa chọn;
không trả đáp án đúng hoặc giải thích trước khi nộp. Lỗi `QUIZ_INVALID_RESPONSE`
(502), `QUIZ_SAVE_FAILED` (503), `TOPIC_NOT_FOUND` (404) và `ACCOUNT_INACTIVE`
(401) dùng thông báo cố định, không đính kèm nội dung AI hay lỗi SQL.

TK-052 là bộ kiểm tra/lưu phía server; trình duyệt không được gửi đáp án chuẩn.
Theo yêu cầu tích hợp AI bổ sung, `POST /api/quizzes` nhận
`{"topicId":1,"difficulty":"easy"}` (hoặc `medium`/`hard`), gọi model dùng cấu hình
chung với chat rồi chuyển kết quả qua bộ kiểm tra này. Prompt dùng chủ đề active,
nguồn phù hợp đã bật nếu có, lọc thông tin cá nhân; không tạo bài giả khi thiếu model.
Phản hồi 201 là `{"quiz":...}` không lộ đáp án/giải thích. Lỗi provider hoặc JSON
không hợp lệ không tạo quiz và không tiêu thêm quota.

TK-051 dùng prompt tiếng Việt yêu cầu một JSON object chứa đúng 5 câu hỏi,
bốn lựa chọn khác nhau, đáp án và giải thích, theo chủ đề và độ khó đã chọn.
Chỉ chấp nhận JSON thuần hoặc một khối Markdown JSON hoàn chỉnh; không lấy JSON
từ đoạn văn tùy ý. Kết quả được kiểm tra lại sau khi lọc thông tin cá nhân và trước
transaction lưu. Provider báo chưa hoàn tất/bị cắt trả `LLM_INVALID_RESPONSE`,
kể cả khi phần nội dung còn lại tình cờ là JSON hợp lệ. Trình duyệt gọi lại
`POST /api/quizzes` với cùng chủ đề/độ khó để tạo lại sau lỗi.

`GET /api/quizzes/{id}/result` chỉ cho chủ sở hữu đọc quiz `completed`, trả
`{"result":...}` gồm điểm, số đúng/tổng, thời gian và từng câu với lựa chọn đã nộp,
đáp án, `isCorrect`, giải thích. Quiz chưa nộp trả 409; ID thiếu/khác chủ cùng 404.
Frontend đăng nhập đã nối sinh đề, làm bài, nộp và mở kết quả lưu thật qua các API;
không dùng bài mẫu cho tài khoản người học. Cấu hình model và quota tại [AI_SETUP.md](AI_SETUP.md).

`GET /api/quizzes?limit=20&offset=0` trả `quizzes`, `limit`, `offset`, `hasMore`
của chính user lấy từ token, bao gồm bài đang làm và completed. Mỗi dòng gồm
`id`, `topicId`, `topicName`, `subjectName`, `difficulty`, `status`, `createdAt`,
`completedAt`, `score` (null nếu chưa hoàn tất); không có đề/đáp án/giải thích.
Giới hạn limit 1–100, offset 0–100000; sắp created_at DESC rồi id DESC. Môn/chủ đề
đã tắt vẫn có trong lịch sử. ADMIN không đọc được lịch sử của tài khoản khác.
Lỗi storage trả 503 cố định, toàn bộ dữ liệu riêng tư có `Cache-Control: no-store`.

Frontend lịch sử và hồ sơ lấy listing này cùng các phiên chat thật, mở kết quả
qua `#results?quiz={id}` hoặc làm tiếp qua `#practice?quiz={id}`. Dashboard đọc
số tổng/điểm trung bình từ `/api/dashboard`, không tự tạo số hoặc lấy dữ liệu mẫu.
Lựa chọn chưa nộp được giữ theo user/quiz trong sessionStorage để qua reload/rời
trang; chỉ phục hồi nếu khớp câu hỏi/lựa chọn từ server, xóa sau nộp/đăng xuất.
Nháp không chứa điểm/đáp án chuẩn và không thay trạng thái đã nộp từ database.

TK-082 bổ sung `GET /api/quizzes/{quiz_id}` để đọc quiz và câu hỏi của tài khoản
đang đăng nhập, giữ response không chứa đáp án/giải thích. ID khác chủ và ID thiếu
cùng trả 404, kể cả với ADMIN; xem [quyền sở hữu](OWNERSHIP.md).

TK-059 mở rộng `/api/quizzes/{quiz_id}/submit` để nộp và chấm một lần, ghi điểm,
trạng thái hoàn tất và tiến độ cùng transaction. `/api/quizzes/{quiz_id}/grade`
chấm các đáp án cũ đã lưu theo TK-058. Xem [API chấm quiz](QUIZ_GRADING.md).

Kiểm thử offline:

```powershell
cd D:\gia-su-AI\back-end
.\venv\Scripts\python.exe -m pytest -q tests/test_quiz_validation.py tests/test_quiz_service.py
```

`tests/test_quiz_database_integration.py` chạy khi có `TEST_DATABASE_URL`, tái sử dụng
fixture tạo database thử nghiệm ngẫu nhiên. Kiểm tra lưu đủ 5 câu, không lộ đáp án,
không cập nhật tiến độ sớm, từ chối dữ liệu sai/nội dung đã tắt và rollback cả bài
khi giả lập lỗi chèn câu cuối. Fixture không ghi vào database dự án đang sử dụng.

## Lỗi sinh quiz và tạo lại bài (TK-056)

`POST /api/quizzes` trả HTTP **502** với cùng envelope khi nội dung quiz do model
trả về sai JSON, thiếu/thừa câu, thiếu lựa chọn/đáp án/giải thích, trùng câu/lựa chọn,
trùng khóa JSON, quá dài hoặc có ký tự điều khiển không hợp lệ:

```json
{
  "error": {
    "code": "QUIZ_INVALID_RESPONSE",
    "message": "Dữ liệu bài luyện tập chưa hợp lệ. Chưa có bài nào được lưu. Vui lòng tạo lại bài."
  }
}
```

Không trả lại nội dung model, đáp án, thông tin cá nhân hay lỗi SQL trong thông báo.
Đề đã có vẫn được giữ, đề lỗi không được lưu và không tính quota. Để tạo lại, gửi
lại `POST /api/quizzes` với cùng `topicId`/`difficulty`; không cần endpoint retry riêng.
Backend không tự gọi lại model hoặc sửa JSON thành đề giả. Sau lỗi, khóa yêu cầu
được giải phóng để lần gửi sau có thể thành công.

JSON lỗi ở lớp phản hồi HTTP của nhà cung cấp (kể cả lồng quá sâu) trả 502
`LLM_INVALID_RESPONSE`. Giữ các mã provider hiện có: `LLM_TIMEOUT` (504),
`LLM_UNAVAILABLE` (502), `LLM_RATE_LIMITED` (429), `LLM_NOT_CONFIGURED` (503).
Các phản hồi này được mô tả trong OpenAPI của API tạo quiz. JSON do **client** gửi
sai vẫn trả 400 `INVALID_JSON` hoặc 422 `VALIDATION_ERROR`, không nhầm với lỗi model.

## Pytest Auth, Quiz và quyền truy cập (TK-088)

Chạy từ `back-end`, sau khi cài `requirements-dev.txt`:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Các kiểm thử API dùng ứng dụng FastAPI thật, repository bộ nhớ riêng và provider
giả lập; không gọi model bên ngoài. Các regression chính gồm:

- `test_token_auth_api.py`: đăng ký/đăng nhập cấp JWT, quyền lấy lại từ tài khoản
  hiện tại, khóa/xóa tài khoản, không nhận token qua query/cookie/header giả.
- `test_admin_permissions_api.py`: kiểm tra quyền trên toàn bộ route quản trị.
- `test_quiz_generation_errors_api.py`: lỗi model, không ghi dở dang/không trừ
  quota, bảo vệ nội dung lỗi và tạo lại thành công qua adapter HTTP giả lập.
- `test_quiz_authenticated_workflow_api.py`: đăng ký → đăng nhập → sinh 5 câu
  A–D → chặn đọc/nộp khác chủ → nộp/chấm → kết quả riêng tư; đề chưa nộp không
  lộ đáp án hay giải thích.
- `test_quiz_grading_api.py`: chặn nộp lại và nộp đồng thời với đáp án khác nhau;
  đáp án, điểm và tiến độ chỉ ghi theo yêu cầu thắng.

Các test MySQL được bỏ qua khi chưa đặt `TEST_DATABASE_URL`. Khi có MySQL,
fixture tạo database tên ngẫu nhiên `gia_su_ai_test_*` rồi dọn đúng database đó;
không chạy migration/seed vào database dự án. Không coi các test bị skip là đã qua.
