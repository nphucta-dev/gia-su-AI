# Gia Sư AI frontend

HTML/CSS/JavaScript thuần, dùng ES modules. Luồng đăng ký, đăng nhập và trang chủ đã nối FastAPI. Bố cục và các thành phần giao diện hiện có được giữ lại.

## Chạy

Khởi động backend từ `back-end/`:

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Trong terminal khác, từ `front-end/`:

```powershell
node serve.cjs
```

Mở http://127.0.0.1:4173. Không cần cài package npm để chạy server frontend; server dùng thư viện có sẵn của Node.js.

`serve.cjs` chuyển request `/api/*` tới `http://127.0.0.1:8000`, bao gồm JSON body, Bearer token, HTTP status và thông báo lỗi. Nếu backend chạy ở địa chỉ khác, đặt `BACKEND_URL` trước khi chạy server:

```powershell
$env:BACKEND_URL = 'http://127.0.0.1:8001'
node serve.cjs
```

Nếu dùng Live Server thay cho `serve.cjs`, đặt meta `api-base` trong `index.html` thành URL API tuyệt đối và bổ sung origin của Live Server vào `CORS_ORIGIN` ở backend. Cách chạy mặc định dùng proxy phía trên.

## Luồng đã kết nối

- Đăng ký gọi `POST /api/auth/register`; lỗi trường từ server hiện cạnh ô nhập. Thành công chuyển đến đăng nhập và điền email vừa đăng ký.
- Đăng nhập gọi `POST /api/auth/login`; thành công lưu token vào `sessionStorage` và mở trang chủ.
- Trang chủ yêu cầu đăng nhập. Khi tải lại trang, frontend gọi `GET /api/auth/me` trước khi hiển thị các trang cần tài khoản.
- Danh sách môn và chủ đề lấy từ `GET /api/catalog/subjects`. Bộ chọn **Cấp học** gọi API với `gradeLevel`, có lựa chọn tất cả, trạng thái tải/trống/lỗi và thử lại. Các cấp học được lấy từ danh mục thật, không cố định trong giao diện.
- Menu hiển thị tên người dùng, hồ sơ và đăng xuất. LEARNER không có mục quản trị; trang quản trị còn kiểm tra `/api/admin/access` ở backend.
- ADMIN thêm, sửa, bật/tắt môn và chủ đề qua `GET/POST/PATCH /api/admin/subjects` và `/api/admin/topics`. Form chủ đề chọn môn theo ID, có chương và mô tả; thay đổi được lưu trong MySQL và giữ sau khi tải lại trang.
- Hồ sơ gọi `GET /api/profile`, lưu họ tên/năm sinh bằng `PATCH /api/profile`; thay đổi giữ được sau khi tải lại trang. Email và vai trò chỉ hiển thị, không cho sửa.
- ADMIN mở Tài liệu nguồn để tải PDF/TXT qua `POST /api/admin/documents`; form lấy môn/chủ đề thật từ `/api/admin/documents/options`, danh sách lấy từ `/api/admin/documents`. File và metadata được lưu ở backend/MySQL.
- Đăng xuất hoặc token hết hạn xóa phiên phía trình duyệt. Sai thông tin đăng nhập không tạo phiên. Không lưu mật khẩu vào storage.
- Lỗi mạng, backend ngừng chạy và lỗi server có thông báo; form chống gửi nhiều lần khi đang xử lý.

API kiểm tra MySQL: http://127.0.0.1:8000/api/database. Swagger: http://127.0.0.1:8000/docs.

Danh sách và quản lý môn/chủ đề, hồ sơ, upload/danh sách tài liệu đã kết nối backend. Nội dung chat, câu hỏi luyện tập và dashboard vẫn còn dữ liệu minh họa. Cache danh mục tách theo cấp học, được xóa khi đăng xuất hoặc cập nhật môn/chủ đề; lọc ở trang học không làm mất danh mục dùng cho chọn chủ đề chat/luyện tập. Phân quyền phía frontend phục vụ điều hướng; backend xác thực token và quyền trước khi cho phép API bảo vệ.

## Cấu trúc

```text
front-end/
├── index.html
├── serve.cjs                # Server tĩnh và proxy API
├── src/
│   ├── css/styles.css
│   └── js/
│       ├── app.js           # Router, khôi phục phiên và phân quyền điều hướng
│       ├── api.js           # fetch wrapper, JSON, token và lỗi API
│       ├── session.js       # Token, thông tin người dùng và hết hạn
│       ├── components/
│       └── pages/
├── tests/                   # Browser tests và backend fixture trong bộ nhớ
├── package.json             # Lệnh chạy và Playwright dành cho kiểm thử
└── package-lock.json
```

## Kiểm thử trình duyệt

Cần cài `back-end/requirements-dev.txt` vào virtualenv và cài dependency frontend:

```powershell
npm install
npm test
npm run test:login
```

Test tự mở backend FastAPI riêng với repository trong bộ nhớ, server frontend ở cổng tạm và Edge headless trên Windows. Test không dùng `.env` hoặc ghi database thật, không tạo ảnh trong `outputs/`, và đóng các tiến trình sau khi chạy.

Có thể đặt `PYTHON` để chọn Python, `PLAYWRIGHT_CHANNEL` để chọn trình duyệt hoặc `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` để chỉ định executable. Trên máy chưa có browser tương thích có thể chạy `npx playwright install chromium`.

Test tự tìm virtualenv tại `back-end/venv` hoặc `back-end/.venv`.

Các kịch bản gồm: lỗi form, đăng ký API, email trùng, sai mật khẩu, đăng nhập thành công, token/khôi phục phiên/đăng xuất, LEARNER bị chặn, ADMIN được truy cập, responsive và mất kết nối backend.

## Giao diện tài khoản và quản trị

Form tài khoản dùng `src/js/pages/auth-screen.js`, `auth-templates.js` và `src/css/auth.css`. Đăng ký và đăng nhập gọi API qua proxy `/api`.

ADMIN vào `#admin?tab=subjects` sau khi đăng nhập. Sidebar và menu mobile có ba mục Môn học, Chủ đề, Tài liệu nguồn, tương ứng với `#admin?tab=subjects`, `#admin?tab=topics`, `#admin?tab=documents`. Hồ sơ quản trị hiển thị thông tin tài khoản từ server. CSS quản trị nằm trong `admin-shell.css` và `admin.css`.

Thêm, sửa, bật/tắt môn/chủ đề của ADMIN đăng nhập thật dùng API và MySQL. Môn mới chưa có chủ đề đang bật sẽ chưa xuất hiện ở danh sách học. Tắt môn/chủ đề không xóa tài liệu hay lịch sử cũ. Tab tài liệu dùng file đã tải qua API; tải lại trang vẫn có tài liệu. File mới ở trạng thái chờ xử lý, chưa bật làm nguồn. Nút bật/tắt tài liệu và thử xử lý cần API xử lý nội dung ở bước tiếp theo.

Trên localhost/127.0.0.1, trang đăng nhập có nút xem thử giao diện LEARNER và ADMIN. Chế độ này có banner nhận diện, dùng dữ liệu mẫu và không tạo token API. Đăng xuất xóa chế độ xem thử; hostname khác không bật các nút này.

Các file `tests/auth.cjs`, `tests/session.cjs`, `tests/admin.cjs`, `tests/preview.cjs` là kiểm thử giao diện cũ với phản hồi giả lập và đường dẫn Playwright của máy phát triển. Bộ mặc định `npm test` sử dụng dependency của dự án và backend FastAPI riêng như mô tả phía trên.
