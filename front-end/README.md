# Gia Sư AI frontend

HTML/CSS/JavaScript thuần dùng ES modules. Mã giao diện thống nhất trong thư mục này.

## Chạy

Từ front-end/: chạy node serve.cjs rồi mở http://127.0.0.1:4173. Có thể đặt biến môi trường PORT để đổi cổng. Không mở index.html bằng file://.

## Tài khoản và phân quyền

- src/js/session.js quản lý trạng thái checking, anonymous, authenticated và error.
- Menu lấy trạng thái phiên chung: khách thấy Đăng nhập/Đăng ký; LEARNER thấy Hồ sơ/Lịch sử/Đăng xuất; ADMIN có thêm Quản trị nội dung.
- Các route chat, practice, results, dashboard, profile, history cần phiên được xác minh; admin cần role ADMIN. Role không nhận diện được bị từ chối.
- Hồ sơ hiển thị tên/email/role từ máy chủ; không hard-code sinh viên hoặc quyền quản trị.
- Mỗi lần tải lại, đổi hash hoặc quay lại tab, token được kiểm tra qua GET /api/auth/me trước khi render nội dung cá nhân. Lỗi mạng giữ token để thử lại, nhưng không mở nội dung cá nhân. HTTP 401/403 xóa phiên phía trình duyệt.
- POST /api/auth/login gửi JSON email/password theo hợp đồng ở origin/feature/auth-and-database (routes/auth.py, schemas/auth.py). Frontend chỉ cấp quyền sau khi GET /api/auth/me xác minh lại người dùng; không tin role trong payload login hoặc localStorage.
- Base URL cấu hình trong meta api-base ở index.html, mặc định http://localhost:8000. Backend phải cho phép CORS đúng origin frontend.
- Token Bearer lưu trong sessionStorage của tab, không lưu mật khẩu. Khi storage bị chặn, phiên chỉ tồn tại trong bộ nhớ. Dữ liệu người dùng không được lưu riêng ở localStorage.
- Đăng xuất xóa token, trạng thái người dùng, kết quả luyện tập trong bộ nhớ và nội dung dialog rồi về #login. Đây là đăng xuất trên tab hiện tại; không thu hồi token trên máy chủ hoặc đăng xuất thiết bị/tab khác. Backend hiện chưa có hợp đồng thu hồi token/logout.

**Giới hạn backend hiện tại:** Nhánh tích hợp này có đăng ký và /me nhưng chưa có /login. Cần tích hợp backend đăng nhập đã có trên nhánh feature/auth-and-database để đăng nhập thật; lỗi 404 hiển thị thông báo cụ thể, không tạo phiên giả. Đăng ký vẫn chỉ kiểm tra form tại trình duyệt. Các trang học tập và quản trị dùng nội dung minh họa trong bộ nhớ, chưa gọi API dữ liệu. Bảo vệ router chỉ phục vụ điều hướng; API quản trị tương lai phải dùng dependency require_roles ở backend.

## Cấu trúc

- index.html: shell, điều hướng, menu, dialog và vùng thông báo.
- src/js/app.js: router, menu theo phiên, chặn truy cập và điều hướng.
- src/js/session.js: kết nối API xác thực và quản lý phiên.
- src/js/pages/auth-screen.js, auth-templates.js: form tài khoản, validation và trạng thái đang gửi/lỗi.
- src/css/auth.css: CSS tài khoản giới hạn trong .account-screen.
- src/js/pages/: học tập, hội thoại, luyện tập, hồ sơ, lịch sử và quản trị tài liệu.
- login.html/register.html: chuyển hướng tương thích về #login/#register.

## Kiểm thử

Khởi động server rồi chạy từ front-end/:

    node tests/browser.cjs
    node tests/login.cjs
    node tests/auth.cjs
    node tests/session.cjs

Đặt BASE_URL nếu server dùng cổng khác, ví dụ http://127.0.0.1:4183. Test hiện dùng đường dẫn Playwright runtime và Edge theo máy phát triển. Các phản hồi đăng nhập, /me và role trong test được giả lập bằng Playwright route; fixture chỉ tồn tại trong tests/, không được import bởi ứng dụng. Kết quả này không chứng minh backend đăng nhập đã được tích hợp hoặc token đã bị thu hồi trên máy chủ.

Bộ session kiểm tra khách, LEARNER/ADMIN, role thiếu/sai, role login không đáng tin, URL quản trị trực tiếp, bàn phím/mobile, logout/Back/reload/relogin, backend thiếu endpoint, sai mật khẩu, phiên hết hạn, lỗi mạng/thử lại và yêu cầu đăng nhập hoàn tất sau khi đã chuyển trang. Ảnh kiểm tra tài khoản lưu trong tests/test-output/ (Git bỏ qua).

## Đăng nhập thử giao diện trên localhost

Tại #login, dùng “Vào thử tài khoản sinh viên” hoặc “Vào thử tài khoản quản trị”, không cần nhập email/mật khẩu. Chế độ xem thử chỉ hiện trên localhost/127.0.0.1, có banner nhận diện và dùng dữ liệu minh họa; không tạo token/API session. Vai trò xem thử lưu riêng trong sessionStorage để giữ khi reload. Đăng xuất xóa chế độ này. Không dùng cơ chế này làm phân quyền backend; triển khai qua hostname khác sẽ không bật xem thử.

## Khu vực ADMIN

Theo SRS FR-05/FR-08, ADMIN quản lý môn học, chủ đề và tài liệu nguồn. Điều hướng ADMIN gồm ba mục riêng trong sidebar tối trên desktop và menu thu gọn trên mobile, menu tài khoản chỉ có Hồ sơ quản trị và Đăng xuất. URL chuẩn là #admin?tab=subjects, #admin?tab=topics, #admin?tab=documents. Tab không hợp lệ trở về subjects. Back/Forward/reload đồng bộ mục đang chọn. Các URL học tập được đưa về quản trị khi role ADMIN; LEARNER vẫn bị chặn trước khi render admin.

Hồ sơ quản trị chỉ hiển thị tên/email/role từ session, chưa hỗ trợ lưu hồ sơ lên API. Danh mục minh họa giữ trong bộ nhớ qua các lần chuyển tab, reset khi reload, đăng xuất hoặc thay đổi người dùng/role. Đổi tên môn/chủ đề cập nhật tham chiếu liên quan; tạo chủ đề dùng danh sách môn thực tế. Upload chỉ kiểm tra tệp và thêm bản ghi chờ minh họa; retry/bật tắt không gọi backend. Backend hiện chưa có API quản trị nên kết quả test chỉ xác minh UI và bảo vệ route, không khẳng định API trả 403.

Kiểm tra thêm: node tests/admin.cjs và node tests/preview.cjs. Test admin bao phủ điều hướng/hồ sơ theo role, ba tab ở 360/390/768/1440px, URL/Back/Forward/reload, thêm/sửa/bật tắt, liên kết môn/chủ đề, lọc và upload/retry tài liệu minh họa, logout/Back. Ảnh kiểm tra ở tests/test-output/admin-*.png (Git bỏ qua).

### Thiết kế ADMIN từ Figma

Tham chiếu: https://www.figma.com/design/7XFlHxljV34po4s9ERuwVS?node-id=2-2. Figma MCP hết hạn mức Starter khi triển khai; đã đối chiếu board trực tiếp qua trình duyệt, chưa trích xuất được token/asset để cam kết khớp từng pixel. Giữ màu chàm và font hệ thống của dự án. `src/css/admin-shell.css` chỉ áp dụng theo role ADMIN; `src/css/admin.css` áp dụng cho nội dung quản trị. Desktop dùng sidebar tối, mobile dùng drawer có Escape, trả focus, chặn thao tác nền khi mở. Môn học có danh sách, tìm kiếm, số chủ đề thực tế; chủ đề được nhóm theo môn/chương. Form thêm mở qua CTA, form sửa dùng lại validation. Không thêm dashboard tổng quan hoặc thống kê giả.
