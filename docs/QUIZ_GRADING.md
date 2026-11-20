# API chấm điểm quiz (TK-059)

Đối chiếu tên/mô tả TK-059, SRS FR-07.1–07.3 và phần giao dịch trong thiết kế
CSDL: backend so sánh đáp án đã lưu trên server, tính điểm phần trăm và chỉ chấm
một lần. Câu trả lời, điểm, trạng thái hoàn tất và tiến độ được lưu cùng transaction.

## Nộp và chấm bài

`POST /api/quizzes/{quiz_id}/submit` yêu cầu Bearer token và JSON `answers` gồm đúng
5 phần tử `{questionId, userAnswer}`. ID câu hỏi lấy từ API đọc quiz của chính mình;
mỗi câu xuất hiện đúng một lần, `userAnswer` thuộc `A`, `B`, `C`, `D`.

Backend thực hiện:

1. Kiểm tra tài khoản/chủ sở hữu, quiz còn `in_progress`, đủ đúng 5 câu và chưa có
   lần nộp trước đó.
2. So sánh từng lựa chọn với `correct_answer` trên server, lưu `quiz_answers` và
   tính `score = số câu đúng / 5 × 100`.
3. Đổi quiz sang `completed`, ghi `score`, `completed_at` và cộng thống kê cho cặp
   user/topic vào `learning_progress`. Mức thành thạo tính từ tổng số câu đúng/tổng
   câu đã chấm, làm tròn hai chữ số.
4. Commit tất cả hoặc rollback tất cả nếu ghi dữ liệu/commit thất bại.

Phản hồi giữ `{submission: {...}}`, `status: "accepted"`, `savedCount` và `answers`
để frontend hiện tại tiếp tục dùng được. Các trường bổ sung:

| Trường | Ý nghĩa |
| --- | --- |
| `quizStatus` | `completed`. |
| `score` | Điểm số 0–100. |
| `correctCount` / `totalCount` | Số câu đúng và tổng 5 câu. |
| `completedAt` | Thời gian UTC khi chấm thành công. |

`status: accepted` xác nhận yêu cầu đã được tiếp nhận; trạng thái bài nằm ở
`quizStatus`. Các lựa chọn được trả lại theo thứ tự câu hỏi. Phản hồi này không trả
đáp án chuẩn hay giải thích; API kết quả chi tiết là TK-061.

## Quiz đã lưu đáp án theo TK-058 trước đây

`POST /api/quizzes/{quiz_id}/grade` không nhận body. Endpoint chấm đúng 5 lựa chọn
đã lưu của quiz còn `in_progress`, tính lại `is_correct` từ đáp án chuẩn và hoàn
tất cùng giao dịch điểm/tiến độ. Không nhận lựa chọn thay thế. Phản hồi có cùng
envelope như `/submit`.

Quiz chưa đủ đáp án đã lưu trả `409 ANSWERS_REQUIRED`. Không có thao tác tự động
chấm hàng loạt hay sửa dữ liệu hiện có khi khởi động ứng dụng.

## Bảo vệ dữ liệu và nộp đồng thời

- ID không tồn tại hoặc thuộc tài khoản khác trả cùng `404 QUIZ_NOT_FOUND`, kể cả
  với ADMIN. Tài khoản phải được xác thực và active.
- Bài đã nộp/chấm trả `409 ALREADY_SUBMITTED`; câu hỏi trùng/sai bài hoặc dữ liệu
  không hợp lệ trả `422`. Điểm/trạng thái do client tự gửi bị từ chối.
- SQL khóa tài khoản trước, rồi quiz. Hai yêu cầu cùng quiz chỉ một yêu cầu thành
  công; hai quiz cùng user/topic cộng tiến độ đúng một lần cho từng bài.
- Chủ sở hữu vẫn được hoàn thành quiz đã tạo khi môn/chủ đề bị tắt sau đó.
- Lỗi SQL trả `503 QUIZ_SAVE_FAILED`; không trả nội dung lỗi CSDL. API đọc quiz
  hiện có vẫn không lộ đáp án chuẩn/giải thích.

Không thêm bảng, migration, thư viện hoặc gọi model AI. Backend dùng schema MySQL
và ID số tự tăng hiện có.

## Kiểm thử

`tests/test_quiz_grading_api.py` kiểm tra điểm từ 0 đến 100, dữ liệu sai, ownership,
chấm/nộp lặp và quiz cũ. `tests/test_task_api_wiring.py` kiểm tra tiến độ sau chấm
được đọc qua cùng API `/api/progress` trong kho bộ nhớ.

`tests/test_two_tasks_database_integration.py` dùng database MySQL tạm tên ngẫu
nhiên để kiểm tra dữ liệu thật, lỗi ghi/commit, rollback và các yêu cầu đồng thời.
Không ghi database dự án đang sử dụng.
