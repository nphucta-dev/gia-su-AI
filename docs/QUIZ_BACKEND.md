# Kiểm tra và lưu quiz (TK-052)

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
2000 ký tự. Kiểm tra cấu trúc không chứng minh được đáp án đúng về mặt kiến thức.

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

`GET /api/quizzes/{id}/result` chỉ cho chủ sở hữu đọc quiz `completed`, trả
`{"result":...}` gồm điểm, số đúng/tổng, thời gian và từng câu với lựa chọn đã nộp,
đáp án, `isCorrect`, giải thích. Quiz chưa nộp trả 409; ID thiếu/khác chủ cùng 404.
Frontend đăng nhập đã nối sinh đề, làm bài, nộp và mở kết quả lưu thật qua các API;
chế độ xem thử vẫn dùng bài mẫu. Cấu hình model và quota tại [AI_SETUP.md](AI_SETUP.md).

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
