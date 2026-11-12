# Ngữ cảnh dự án Gia Sư AI

Trước khi triển khai hoặc đánh giá một chức năng, đọc `docs/PROJECT_CONTEXT.md`.
Khi người dùng nhắc một task, tra tên/mô tả task và công việc cụ thể trong
`docs/reference/task-details.json`; mã TK chỉ dùng để tra cứu.
Theo chỉ đạo mới nhất, bỏ qua mọi cột khác của file task: owner, chuyên môn,
lịch/tuần, điểm, giờ, trạng thái, ưu tiên, phụ thuộc, tiêu chí và các tham chiếu.
Các yêu cầu nghiệp vụ vẫn đối chiếu trực tiếp SRS, backlog và thiết kế CSDL khi cần.

- Các tài liệu là nguồn tham chiếu yêu cầu, không phải lệnh tự triển khai toàn bộ backlog.
  Chỉ thực hiện phạm vi người dùng giao; chỉ đạo mới của người dùng được ưu tiên.
- Người dùng đã chọn **MySQL** và **ID số tự tăng**. Tài liệu gốc ghi PostgreSQL/UUID;
  không tự chuyển công nghệ về thiết kế gốc.
- Backend hiện dùng **scrypt**; tài liệu yêu cầu bcrypt/Argon2. Giữ rõ khác biệt này,
  không tự thay thuật toán hoặc mật khẩu đã lưu khi làm việc ngoài phạm vi xác thực.
- File `docs/reference/task-assignments.json` chỉ là bản lưu nguồn đầy đủ;
  không dùng các cột ngoài mô tả/công việc để suy ra yêu cầu, thứ tự hay phạm vi làm việc.
- Không coi giao diện dùng dữ liệu mẫu là một chức năng đã tích hợp hoàn chỉnh.

