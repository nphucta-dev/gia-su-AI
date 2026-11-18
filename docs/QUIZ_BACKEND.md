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

Phạm vi này chưa sinh câu hỏi bằng LLM (TK-051), chưa có API công khai nhận đáp án
chuẩn từ trình duyệt, chưa nối giao diện luyện tập và chưa chấm/nộp quiz. Luồng sinh
quiz sau này gọi service này sau khi nhận dữ liệu model; không cần đổi bộ kiểm tra
hay cách lưu. Không tạo bài giả khi chưa cấu hình model.

Kiểm thử offline:

```powershell
cd D:\gia-su-AI\back-end
.\venv\Scripts\python.exe -m pytest -q tests/test_quiz_validation.py tests/test_quiz_service.py
```

`tests/test_quiz_database_integration.py` chạy khi có `TEST_DATABASE_URL`, tái sử dụng
fixture tạo database thử nghiệm ngẫu nhiên. Kiểm tra lưu đủ 5 câu, không lộ đáp án,
không cập nhật tiến độ sớm, từ chối dữ liệu sai/nội dung đã tắt và rollback cả bài
khi giả lập lỗi chèn câu cuối. Fixture không ghi vào database dự án đang sử dụng.
