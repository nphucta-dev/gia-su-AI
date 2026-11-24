# Gia Sư AI frontend

HTML/CSS/JavaScript thuần dùng ES modules. Mã giao diện thống nhất trong thư mục này.

## Chạy

Chạy backend bằng Uvicorn trên cổng 8000 theo README gốc của dự án. Từ `front-end/`, chạy `node serve.cjs` rồi mở http://127.0.0.1:4173. Không mở `index.html` bằng `file://`.

Server frontend chuyển tiếp `/api` tới `http://127.0.0.1:8000`. Có thể đặt `PORT` để đổi cổng frontend hoặc `BACKEND_URL` để đổi địa chỉ backend. Backend cần kết nối MySQL và đã tạo schema để các chức năng lưu dữ liệu hoạt động.

Server mặc định nghe tại `0.0.0.0`, in địa chỉ IP để thiết bị cùng Wi-Fi/LAN mở
`http://<IP-máy-chạy>:4173`. Đặt `HOST=127.0.0.1` nếu chỉ muốn truy cập trên máy đó.
API vẫn dùng `/api` cùng origin qua proxy; không đặt localhost làm API URL trên
thiết bị khác. Cách cấp quyền tường lửa Windows tại [README gốc](../README.md#cho-các-thiết-bị-cùng-wi-filan-truy-cập).
`npm run test:lan` kiểm tra truy cập qua IP LAN và đăng nhập trên backend cô lập;
cần máy đang kết nối Wi-Fi/LAN.

## Tài khoản và phân quyền

- src/js/session.js quản lý trạng thái checking, anonymous, authenticated và error.
- Menu lấy trạng thái phiên chung: khách thấy Đăng nhập/Đăng ký; LEARNER thấy Hồ sơ/Lịch sử/Đăng xuất; ADMIN có thêm Quản trị nội dung.
- Các route home, chat, practice, results, dashboard, profile, history cần phiên được xác minh; admin cần role ADMIN. Role không nhận diện được bị từ chối.
- Hồ sơ hiển thị tên/email/role từ máy chủ; không hard-code sinh viên hoặc quyền quản trị.
- Khi tải trang, token được kiểm tra qua GET /api/auth/me. Chuyển tab/cửa sổ chỉ kiểm tra thời hạn token tại trình duyệt, giữ nguyên form đang nhập và file đang chọn. API tiếp tục kiểm tra token và quyền cho từng yêu cầu; phản hồi 401 hoặc /auth/me trả 403 sẽ xóa phiên.
- POST /api/auth/register tạo tài khoản; POST /api/auth/login gửi JSON email/password. Frontend chỉ cấp quyền sau khi GET /api/auth/me xác minh lại người dùng; không tin role trong payload login hoặc localStorage.
- Base URL cấu hình trong meta api-base ở index.html, mặc định `/api`. Nếu dùng URL backend trực tiếp, giá trị phải bao gồm `/api` và backend phải cho phép CORS đúng origin frontend.
- Token Bearer lưu trong sessionStorage của tab, không lưu mật khẩu. Khi storage bị chặn, phiên chỉ tồn tại trong bộ nhớ. Dữ liệu người dùng không được lưu riêng ở localStorage.
- Đăng xuất xóa token, trạng thái người dùng, kết quả luyện tập trong bộ nhớ và nội dung dialog rồi về #login. Đây là đăng xuất trên tab hiện tại; không thu hồi token trên máy chủ hoặc đăng xuất thiết bị/tab khác. Backend hiện chưa có hợp đồng thu hồi token/logout.

**Phạm vi đã kết nối:** đăng ký/đăng nhập, hồ sơ, danh mục, quản trị môn/chủ đề, tải/xử lý/bật tài liệu, chat Socratic/lịch sử/gợi ý/giải thích/lời giải xác nhận/feedback/quota và sinh/làm/chấm/xem kết quả quiz gọi API thật. Backend kiểm tra phân quyền độc lập với router frontend. Model cấu hình tại [AI_SETUP.md](../docs/AI_SETUP.md).

**Giới hạn giao diện:** dashboard và một số trang lịch sử học tập còn minh họa. Chế độ xem thử localhost dùng dữ liệu mẫu riêng. Với tài khoản đăng nhập, chat/quiz không tạo kết quả giả khi thiếu model; lỗi cấu hình hiện thông báo và cho thử lại. Chưa kiểm chứng chất lượng model thật khi chưa có API key.

## Cấu trúc

- index.html: shell, điều hướng, menu, dialog và vùng thông báo.
- src/js/app.js: router, menu theo phiên, chặn truy cập và điều hướng.
- src/js/session.js: kết nối API xác thực và quản lý phiên.
- src/js/pages/auth-screen.js, auth-templates.js: form tài khoản, validation và trạng thái đang gửi/lỗi.
- src/css/auth.css: CSS tài khoản giới hạn trong .account-screen.
- src/js/pages/: học tập, hội thoại, luyện tập, hồ sơ, lịch sử và quản trị tài liệu.
- login.html/register.html: chuyển hướng tương thích về #login/#register.

## Kiểm thử

Cài `back-end/requirements-dev.txt` trong venv backend và dependencies frontend. Từ `front-end/` trên PowerShell:

    npm.cmd install
    npm.cmd test
    npm.cmd run test:login

Bộ test tự mở frontend/backend trên cổng tạm, dùng repository trong bộ nhớ và đóng server khi xong; không cần bật server 4173/8000, không ghi database dự án. Playwright lấy từ dependencies của dự án. Trên Windows mặc định dùng Edge; có thể đặt `PLAYWRIGHT_CHANNEL` hoặc `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` để chọn trình duyệt đã cài.

`npm.cmd test` kiểm tra đăng ký/đăng nhập thật với API fixture, JWT, quyền, layout, danh mục/cấp học, quản trị, hồ sơ, upload/xử lý tài liệu, giữ form khi chuyển tab, hết hạn phiên và lỗi backend. `test:login` chỉ chạy nhóm tài khoản. Kiểm thử này không xác nhận kết nối MySQL thật hoặc chất lượng phản hồi model AI.

## Đăng nhập thử giao diện trên localhost

Tại #login, dùng “Vào thử tài khoản sinh viên” hoặc “Vào thử tài khoản quản trị”, không cần nhập email/mật khẩu. Chế độ xem thử chỉ hiện trên localhost/127.0.0.1, có banner nhận diện và dùng dữ liệu minh họa; không tạo token/API session. Vai trò xem thử lưu riêng trong sessionStorage để giữ khi reload. Đăng xuất xóa chế độ này. Không dùng cơ chế này làm phân quyền backend; triển khai qua hostname khác sẽ không bật xem thử.

## Khu vực ADMIN

Theo SRS FR-05/FR-08, ADMIN quản lý môn học, chủ đề và tài liệu nguồn. Điều hướng ADMIN gồm ba mục riêng trong sidebar tối trên desktop và menu thu gọn trên mobile, menu tài khoản chỉ có Hồ sơ quản trị và Đăng xuất. URL chuẩn là #admin?tab=subjects, #admin?tab=topics, #admin?tab=documents. Tab không hợp lệ trở về subjects. Back/Forward/reload đồng bộ mục đang chọn. Các URL học tập được đưa về quản trị khi role ADMIN; LEARNER vẫn bị chặn trước khi render admin.

Với tài khoản thật, hồ sơ quản trị lưu qua API hồ sơ; tạo/sửa/bật tắt môn và chủ đề gọi API quản trị theo ID. Upload PDF/TXT được backend kiểm tra, trích văn bản và tách đoạn; tài liệu pending/error có thao tác xử lý/thử lại. Nguồn sau xử lý chưa bật tự động; nút sử dụng gọi PATCH và chỉ bật tài liệu ready có chunk. Chat dùng nguồn đúng chủ đề đang bật. LEARNER gọi API quản trị nhận 403.

Với chế độ xem thử, thay đổi danh mục và tài liệu chỉ nằm trong bộ nhớ; tải lại hoặc đăng xuất sẽ đặt lại dữ liệu. Bộ `npm.cmd test` bao gồm kiểm tra tách biệt chế độ này với các thao tác ghi API thật.

### Thiết kế ADMIN từ Figma

Tham chiếu: https://www.figma.com/design/7XFlHxljV34po4s9ERuwVS?node-id=2-2. Figma MCP hết hạn mức Starter khi triển khai; đã đối chiếu board trực tiếp qua trình duyệt, chưa trích xuất được token/asset để cam kết khớp từng pixel. Giữ màu chàm và font hệ thống của dự án. `src/css/admin-shell.css` chỉ áp dụng theo role ADMIN; `src/css/admin.css` áp dụng cho nội dung quản trị. Desktop dùng sidebar tối, mobile dùng drawer có Escape, trả focus, chặn thao tác nền khi mở. Môn học có danh sách, tìm kiếm, số chủ đề thực tế; chủ đề được nhóm theo môn/chương. Form thêm mở qua CTA, form sửa dùng lại validation. Không thêm dashboard tổng quan hoặc thống kê giả.
