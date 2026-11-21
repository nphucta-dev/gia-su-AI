# Tài liệu nguồn demo Gia Sư AI

Mười file TXT trong thư mục này là nội dung giáo dục minh họa gốc được viết cho
gói dữ liệu demo Gia Sư AI, không sao chép sách giáo khoa hoặc bài viết bên ngoài.
Nội dung gồm kiến thức nền, điều kiện áp dụng công thức, ví dụ tính toán và câu hỏi
tự kiểm tra. Đây không phải tài liệu chính thức của cơ sở giáo dục hay bộ đề thi.

Các file TXT được cung cấp theo CC0 1.0: trong phạm vi pháp luật cho phép, bên
cung cấp từ bỏ quyền tác giả và quyền liên quan đối với phần nội dung minh họa
này để mọi người có thể sử dụng, sửa đổi và phân phối. Tuyên bố này chỉ áp dụng
cho mười file TXT trong thư mục, không thay đổi giấy phép của phần còn lại dự án.
Không có bảo đảm về chất lượng nội dung; cần kiểm tra trước khi sử dụng giảng dạy.

`manifest.json` là mảng mười bản ghi, mỗi bản ghi gồm `subject`, `grade_level`,
`chapter_name`, `topic_name`, `title`, `file_name`. Có hai môn, mỗi môn năm chủ đề.
Ba chủ đề mẫu có từ trước được giữ nguyên tên và chương để seed bổ sung dữ liệu
vào cùng danh mục hiện có.

Nguồn của tài liệu là file TXT đi kèm repository, không phải URL bên ngoài. Khi
seed, có thể để `source_url` là NULL; không tạo URL giả. Văn bản giữ dòng ghi
nguồn và giấy phép để thông tin xuất xứ vẫn còn trong nội dung được trích xuất.
Trạng thái xử lý, chunks và quyền sử dụng nguồn do luồng seed của ứng dụng quản lý.
