# Gia Sư AI — Back-end

API Python 3.10+ dùng FastAPI. Có đăng ký, đăng nhập, xác thực JWT, hồ sơ cá nhân, quản lý môn/chủ đề và tải tài liệu cho ADMIN; lưu dữ liệu trong MySQL.

TK-082 bảo vệ dữ liệu theo tài khoản: chat, `GET /api/quizzes/{id}`,
`GET /api/progress` và `GET /api/progress/{id}`. Xem [quyền sở hữu dữ liệu](../docs/OWNERSHIP.md)
để biết quy tắc truy cập và kiểm thử. API nộp quiz đã chấm điểm và cập nhật tiến độ cùng giao dịch;
xem [TK-059](../docs/QUIZ_GRADING.md). Tra cứu đoạn theo từ khóa dùng
`GET /api/catalog/topics/{id}/chunks?q=...&limit=5`; xem [TK-044](../docs/KEYWORD_RETRIEVAL.md).

Schema hiện tại dùng `INT AUTO_INCREMENT` cho ID của 11 bảng; API trả `id` dạng số. Database cũ đang dùng UUID cần chạy migration `0002_integer_ids` sau khi dừng server và sao lưu, theo [hướng dẫn chuyển ID](../database/README.md#chuyển-database-cũ-từ-uuid-sang-id-tự-tăng).

Xem [hướng dẫn database](../database/README.md) để kết nối MySQL, cấu hình `.env`, tạo đủ 11 bảng bằng migration và seed dữ liệu.

## Chạy

Trong Git Bash (Windows), từ thư mục `back-end/`:

```bash
python -m venv venv
source venv/Scripts/activate           # macOS/Linux: source venv/bin/activate
pip install -r requirements-dev.txt    # chỉ chạy API: pip install -r requirements.txt
cp .env.example .env                 # nếu chưa có .env; đặt JWT_SECRET riêng
python -m app.db.init_db              # MySQL phải đang chạy, DATABASE_URL đã cấu hình
python -m app.db.seed

uvicorn app.main:app --reload --port 8000   # http://localhost:8000
pytest                                      # chạy toàn bộ test
```

Tài liệu API tự sinh (thử gọi trực tiếp được): http://localhost:8000/docs

Frontend chạy bằng `node serve.cjs` trong `front-end/`, mở http://127.0.0.1:4173. Server frontend proxy `/api/*` tới backend cổng 8000; đăng ký/đăng nhập gọi API thật.

| Biến môi trường | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `CORS_ORIGIN` | `http://127.0.0.1:4173,http://localhost:4173` | Các origin front-end được phép, cách nhau bằng dấu phẩy |
| `JWT_SECRET` | khóa ngẫu nhiên mỗi lần khởi động | Khóa ký token, tối thiểu 32 ký tự. **Bắt buộc đặt khi chạy thật** |
| `ACCESS_TOKEN_MINUTES` | `30` | Thời hạn access token, tính bằng phút |
| `DATABASE_URL` | MySQL cục bộ theo `.env.example` | Chuỗi kết nối `mysql+pymysql://...` |

Tạo khóa bí mật: `python -c "import secrets; print(secrets.token_urlsafe(48))"`, rồi đặt trước khi chạy, ví dụ `export JWT_SECRET=...` trong Git Bash. Không đặt `JWT_SECRET` thì server vẫn chạy (kèm cảnh báo) nhưng token mất hiệu lực mỗi lần khởi động lại và không dùng được khi chạy nhiều worker. Không commit khóa lên GitHub.

## Cấu trúc

```text
back-end/
├── app/
│   ├── main.py                     # create_app(): nối các tầng, middleware, CORS
│   ├── config.py                   # Đọc biến môi trường
│   ├── db/                         # Base, engine/session, khởi tạo và seed
│   ├── models/                     # 11 model SQLAlchemy theo thiết kế CSDL
│   ├── error_handlers.py           # Định dạng lỗi thống nhất
│   ├── routes/auth.py              # POST /api/auth/register
│   ├── routes/me.py                # GET /api/auth/me
│   ├── services/auth_service.py    # Luồng đăng ký
│   ├── services/token_service.py   # Tạo và kiểm tra token JWT
│   ├── dependencies/auth.py        # get_current_user, require_roles, require_admin
│   ├── repositories/user_repository.py   # DTO và repository bộ nhớ dùng cho test
│   ├── repositories/sqlalchemy_user_repository.py  # Lưu/đọc tài khoản MySQL
│   ├── validators/register_validator.py  # Kiểm tra dữ liệu đăng ký
│   ├── schemas/auth.py             # Schema phản hồi và mô tả /docs
│   ├── middlewares/                # Giới hạn body, header bảo mật
│   └── utils/                      # password (băm scrypt), errors
├── tests/
├── alembic/                        # Migration schema
├── alembic.ini
├── requirements.txt                # Thư viện chạy API
├── requirements-dev.txt            # Thêm pytest, httpx để test
└── pytest.ini
```

## API

### `GET /api/health`

`200 {"status": "ok"}`

### `GET /api/database`

Endpoint đặt trong `app/main.py`, mở session và thực hiện `SELECT 1` để kiểm tra MySQL:

```json
{"status":"ok","database":"connected","message":"Kết nối database thành công."}
```

Mất kết nối trả `503 DATABASE_UNAVAILABLE`, không trả host, mật khẩu hoặc traceback cho client.

### `POST /api/auth/login`

Gửi JSON:

```json
{"email":"an@example.com","password":"MatKhau@123"}
```

Backend chuẩn hóa email, kiểm tra mật khẩu đã băm bằng scrypt và trạng thái tài khoản. Thành công trả `200` với `message`, `access_token`, `token_type: "Bearer"`, `expires_in` và `user` gồm `id`, `name`, `email`, `role`, `createdAt`.

- Sai email hoặc mật khẩu: `401 INVALID_CREDENTIALS` với cùng thông báo.
- Tài khoản đã vô hiệu hóa và mật khẩu đúng: `403 FORBIDDEN`.
- Dữ liệu sai: `422 VALIDATION_ERROR`, có `fields` để frontend hiển thị cạnh ô nhập.

Đăng nhập không cắt khoảng trắng của mật khẩu. Trường `role` do client tự gửi bị bỏ qua; token được cấp theo tài khoản đã lưu.

### `GET /api/admin/access`

Endpoint đặt trong `app/main.py`, sử dụng `AdminUser` từ `app/dependencies/auth.py`.
Gửi Bearer token: ADMIN nhận `200 {"role":"ADMIN","message":"Bạn có quyền quản trị."}`,
LEARNER nhận 403, thiếu token nhận 401. Frontend kiểm tra endpoint này trước khi mở
trang quản trị; backend kiểm tra quyền riêng trên từng API quản trị.

### Phân quyền API ADMIN (TK-071)

Danh mục, tài liệu và `/api/admin/access` dùng chung dependency `require_admin`.
Các router danh mục/tài liệu bảo vệ toàn bộ route bằng dependency này. `AdminUser`
là kiểu dependency khi handler cần lấy đối tượng ADMIN đã xác thực.

| Tài khoản/token | Kết quả khi gọi API quản trị |
| --- | --- |
| ADMIN đang hoạt động | Được xử lý yêu cầu theo quy tắc API |
| LEARNER | `403 FORBIDDEN` |
| Tài khoản đã bị khóa | `403 FORBIDDEN` |
| Chưa đăng nhập | `401 NOT_AUTHENTICATED` |
| Token sai, hết hạn hoặc tài khoản đã xóa | `401 INVALID_TOKEN` hoặc `TOKEN_EXPIRED` |

Phạm vi gồm 12 thao tác: `GET /api/admin/access`; GET/POST/PATCH môn học và chủ đề;
GET danh sách/lựa chọn tài liệu, POST upload/xử lý và PATCH bật/tắt tài liệu.
Role và `is_active` được đọc lại từ database mỗi request. Hạ quyền ADMIN xuống
LEARNER hoặc khóa tài khoản có hiệu lực với token đã cấp, kể cả token chưa hết hạn.
Các trường role ở header/query/body hoặc claim JWT không thay được quyền lưu trên
server. Đăng ký luôn tạo LEARNER, PATCH hồ sơ chỉ cập nhật các trường hồ sơ cho phép.
Yêu cầu bị từ chối quyền không chạy service quản trị, không ghi danh mục/file/chunk.
Các phản hồi `/api/admin/*`, kể cả lỗi, có `Cache-Control: no-store`.

Đối chiếu TK-071 và SRS FR-08.3. Kiểm thử API:
`tests/test_admin_permissions_api.py`; kiểm thử quyền với MySQL và token cũ:
`tests/test_admin_permissions_database_integration.py` (database thử nghiệm riêng).

### `POST /api/auth/register`

Header: `Content-Type: application/json`

Body:

```json
{
  "name": "Nguyễn Văn An",
  "email": "an@example.com",
  "password": "MatKhau@123",
  "confirmPassword": "MatKhau@123",
  "consent": true
}
```

| Trường | Quy tắc |
| --- | --- |
| `name` | Bắt buộc, tối đa 120 ký tự. Tự bỏ khoảng trắng thừa. |
| `email` | Bắt buộc, đúng định dạng, tối đa 255 ký tự. Tự chuyển về chữ thường. |
| `password` | Bắt buộc, 8 đến 128 ký tự. Không bị cắt khoảng trắng. |
| `confirmPassword` | Bắt buộc, phải giống `password`. |
| `consent` | Phải là boolean `true` (đồng ý quy định sử dụng từ đủ 18 tuổi). |

Các trường khác trong body (ví dụ `role`) bị bỏ qua. Tài khoản mới luôn có vai trò `LEARNER`.

**Thành công — `201`**

```json
{
  "message": "Đăng ký tài khoản thành công.",
  "user": {
    "id": 1,
    "name": "Nguyễn Văn An",
    "email": "an@example.com",
    "role": "LEARNER",
    "createdAt": "2026-11-10T06:26:40.579Z"
  }
}
```

Đăng ký chưa tạo phiên đăng nhập và không trả token; việc đó thuộc API đăng nhập (TK-006).

**Lỗi** luôn có dạng `{"error": {"code", "message", "fields"?}}`. `fields` là map tên trường → thông báo để hiện cạnh ô nhập tương ứng ở front-end.

| Mã HTTP | `code` | Khi nào |
| --- | --- | --- |
| 400 | `INVALID_JSON` | Body không phải JSON hợp lệ |
| 405 | `METHOD_NOT_ALLOWED` | Sai phương thức HTTP |
| 413 | `PAYLOAD_TOO_LARGE` | Body lớn hơn 10 KB |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Không gửi `Content-Type: application/json` |
| 422 | `VALIDATION_ERROR` | Dữ liệu sai, `fields` liệt kê từng trường lỗi |
| 409 | `EMAIL_ALREADY_EXISTS` | Email đã đăng ký, `fields.email` có thông báo |
| 500 | `INTERNAL_ERROR` | Lỗi phía máy chủ, không lộ chi tiết |

Thông báo lỗi do `app/validators/register_validator.py` tạo ra (không dùng thông báo mặc định tiếng Anh của Pydantic) và khớp với nội dung form đăng ký ở front-end.

### `GET /api/auth/me`

Trả về người dùng đang đăng nhập. Dùng để kiểm tra token còn hiệu lực, ví dụ khi mở lại trang.

Header: `Authorization: Bearer <access_token>`

**Thành công — `200`**

```json
{
  "user": {
    "id": 1,
    "name": "Nguyễn Văn An",
    "email": "an@example.com",
    "role": "LEARNER",
    "createdAt": "2026-11-10T06:26:40.579Z"
  }
}
```

**Lỗi xác thực** (mọi API cần đăng nhập đều trả cùng các mã này):

| Mã HTTP | `code` | Khi nào | Front-end nên |
| --- | --- | --- | --- |
| 401 | `NOT_AUTHENTICATED` | Không gửi token hoặc sai dạng `Bearer <token>` | Chuyển tới trang đăng nhập |
| 401 | `TOKEN_EXPIRED` | Token hết hạn | Báo phiên hết hạn, yêu cầu đăng nhập lại |
| 401 | `INVALID_TOKEN` | Token sai chữ ký, sai định dạng, sai loại, hoặc tài khoản không còn tồn tại | Xoá token đã lưu, chuyển tới trang đăng nhập |
| 403 | `FORBIDDEN` | Đã đăng nhập nhưng không đủ quyền | Hiện thông báo không có quyền |

Phản hồi 401 có header `WWW-Authenticate`. Thông báo `INVALID_TOKEN` cố ý không nói rõ lý do cụ thể.

## Xác thực token

Access token là JWT ký HS256. Trong token chỉ có `sub` (id người dùng), `type` (`access`), `iss`, `iat`, `exp`. **Vai trò không nằm trong token** mà được đọc lại từ kho dữ liệu mỗi request, nên đổi vai trò hoặc xoá tài khoản có hiệu lực ngay.

`TokenService` chỉ chấp nhận đúng thuật toán đã cấu hình (token `alg: none` hay đổi thuật toán đều bị từ chối), bắt buộc có `exp`, `iat`, `sub`, `iss`, kiểm tra `iss`, loại token và giới hạn độ dài token.

**Bảo vệ một route** bằng dependency:

```python
from typing import Annotated
from fastapi import Depends
from app.dependencies.auth import get_current_user, require_admin
from app.repositories.user_repository import User

@router.get("/lich-su")
async def history(user: Annotated[User, Depends(get_current_user)]):
    ...                                   # user.id, user.role

@router.get("/quan-tri", dependencies=[Depends(require_admin)])
async def admin_area():
    ...                                   # chỉ ADMIN, người khác nhận 403
```

**Phát hành token** (API đăng nhập đang sử dụng):

```python
issued = request.app.state.token_service.create_access_token(user.id)
# issued.access_token, issued.token_type == "Bearer", issued.expires_in (giây)
```

Thử trên `/docs`: bấm **Authorize**, dán access token, rồi gọi `GET /api/auth/me`.

Frontend gửi `Authorization: Bearer <token>` ở mỗi request cần đăng nhập. Token nằm trong bộ nhớ và `sessionStorage`, không lưu mật khẩu. Khi tải lại trang, frontend gọi `/api/auth/me` để xác thực phiên; token hết hạn hoặc tài khoản vô hiệu hóa được xóa khỏi trình duyệt. Đăng xuất hiện xóa phiên phía client; JWT đã cấp vẫn có hiệu lực đến khi hết hạn.

## Mật khẩu

Băm bằng scrypt (`hashlib.scrypt` có sẵn trong Python), salt ngẫu nhiên 16 byte, N=2^15, r=8, p=3. Chuỗi lưu có dạng `scrypt$N$r$p$salt$hash`, tham số nằm trong chuỗi nên có thể tăng độ khó sau này mà không làm hỏng hash cũ. Dùng `verify_password` (so sánh thời gian cố định) khi đăng nhập và `needs_rehash` để nâng cấp hash cũ sau khi đăng nhập thành công. Việc băm chạy trong thread pool để không chặn các request khác.

## Danh sách môn học

`GET /api/catalog/subjects` yêu cầu token của LEARNER hoặc ADMIN đang hoạt động. API đọc MySQL, chỉ trả môn và chủ đề active, nhóm chủ đề theo chương; môn chưa có chủ đề active không có trong danh sách.

Lọc theo cấp học bằng query tùy chọn `gradeLevel`:

```http
GET /api/catalog/subjects?gradeLevel=THCS
Authorization: Bearer <access_token>
```

`gradeLevel` tối đa 50 ký tự, bỏ khoảng trắng hai đầu và so khớp đúng giá trị cấp học trong database. Không gửi, gửi rỗng hoặc chỉ khoảng trắng thì trả toàn bộ danh mục đang mở. Không có cấp học phù hợp trả `200` với `{"subjects": []}`; quá 50 ký tự trả `422`. Thiếu token trả `401`, tài khoản vô hiệu hóa trả `403`.

Phản hồi giữ cấu trúc `subjects → chapters → topics`; mỗi môn có `id`, `name`, `gradeLevel`, `chapters`, mỗi chủ đề có `id`, `name`, `description`. `GET /api/catalog/topics/{topic_id}` tiếp tục kiểm tra môn/chủ đề active trước khi mở luồng học.

## Quản lý môn và chủ đề (ADMIN)

Các API sau yêu cầu Bearer token của ADMIN đang hoạt động. Thiếu token trả 401, LEARNER trả 403. Danh sách quản trị gồm cả nội dung đã tắt và môn chưa có chủ đề.

| API | Nội dung |
| --- | --- |
| `GET /api/admin/subjects` | Trả `subjects`, mỗi môn có `id`, `name`, `gradeLevel`, `isActive`. |
| `POST /api/admin/subjects` | Tạo môn bằng JSON `{"name":"Toán","gradeLevel":"THPT"}`; trả 201 và `subject`. |
| `PATCH /api/admin/subjects/{id}` | Sửa các trường được gửi: `name`, `gradeLevel`, `isActive`; trả `subject`. |
| `GET /api/admin/topics` | Trả `topics`, gồm `id`, `subjectId`, `subjectName`, `gradeLevel`, `chapterName`, `name`, `description`, `isActive`. |
| `POST /api/admin/topics` | Tạo chủ đề bằng JSON `{"subjectId":1,"chapterName":"Chương 1","name":"Hàm số","description":"Mô tả"}`; trả 201 và `topic`. |
| `PATCH /api/admin/topics/{id}` | Sửa các trường được gửi: `subjectId`, `chapterName`, `name`, `description`, `isActive`; trả `topic`. |

`description` có thể bỏ qua khi tạo, hoặc gửi `null` để xóa mô tả khi sửa. Tên môn tối đa 120 ký tự, cấp học 50, tên chương 150, tên chủ đề 180. Backend chuẩn hóa khoảng trắng, từ chối trường lạ và dữ liệu sai (422), báo trùng tên trong cùng phạm vi bằng 409, bản ghi không tồn tại bằng 404. Cùng tên môn khác cấp học, hoặc cùng tên chủ đề khác chương/môn vẫn hợp lệ.

Bật/tắt dùng `PATCH` với `{"isActive":false}` hoặc `true`. Tắt môn ẩn các chủ đề của môn khỏi danh mục học và lựa chọn upload; không đổi trạng thái riêng của từng chủ đề. Bật lại môn vẫn giữ những chủ đề đã tắt. Các thao tác này giữ nguyên tài liệu và lịch sử đã lưu, không xóa bản ghi.

## Hồ sơ cá nhân

`GET /api/profile` trả đối tượng `user` gồm `id`, `name`, `email`, `role`, `createdAt`, `birthYear` của tài khoản đang đăng nhập, gồm cả LEARNER và ADMIN.

`PATCH /api/profile` nhận JSON và Bearer token:

```json
{"name": "Nguyễn Văn An", "birthYear": 2000}
```

Có thể gửi riêng từng trường; bỏ qua năm sinh để giữ nguyên hoặc gửi `null` để xóa năm sinh. Họ tên hợp lệ, tối đa 120 ký tự; năm sinh là số nguyên từ 1900 đến năm hiện tại. API không cho chỉnh sửa ID, email, role, mật khẩu hoặc trạng thái tài khoản. User ID luôn lấy từ token. Thành công trả `200` với `message` và `user`; lỗi dữ liệu `422`, thiếu/sai token `401`, tài khoản vô hiệu hóa `403`.

`GET /api/auth/me` giữ định dạng cũ để khôi phục phiên; hồ sơ đầy đủ dùng `/api/profile`. Không cần migration mới vì cột `birth_year` đã có trong bảng `users`.

## Quản trị tài liệu ADMIN (TK-070)

Các API sau yêu cầu token của **ADMIN đang hoạt động**; LEARNER nhận `403`, thiếu token nhận `401`:

| API | Công dụng |
| --- | --- |
| `GET /api/admin/documents/options` | Môn và chủ đề active từ MySQL cho form upload; trả `subjects`, mỗi môn có `topics`. |
| `GET /api/admin/documents` | Danh sách mọi tài liệu đã lưu, gồm `status`, `isActive`, `processedAt`, `chunkCount`; trả `documents`. |
| `POST /api/admin/documents` | Tải PDF/TXT, trích văn bản và lưu các đoạn; trả `201` với `message`, `document`. |
| `POST /api/admin/documents/{id}/process` | Xử lý tài liệu cũ đang chờ hoặc thử lại tài liệu lỗi; không cần body, trả `200`. |
| `PATCH /api/admin/documents/{id}` | `{"isActive":true}` hoặc `false`; chỉ bật nguồn ready đã có chunk. |

Đối chiếu mô tả TK-070 và SRS FR-08.2/08.3: ADMIN xem trạng thái và bật/tắt nguồn;
trạng thái `pending`/`ready`/`error` do upload hoặc `/process` cập nhật sau khi xử lý
file. PATCH yêu cầu `Content-Type: application/json`, chỉ nhận boolean `isActive`
(giữ tương thích tên `is_active` đã có), từ chối `status`, `topicId`, đường dẫn file
hoặc trường khác do client gửi. Bật tài liệu chưa ready/chưa có chunk trả
`409 DOCUMENT_NOT_READY`; ID thiếu trả 404, ID hoặc body sai trả 422, sai Content-Type
trả 415. Tắt tài liệu không xóa file, chunk hay lịch sử; gửi lại cùng trạng thái
không xử lý lại file hoặc tạo thêm chunk.

Danh sách quản trị dùng chung cho các ADMIN, gồm cả tài liệu lỗi/chờ xử lý, đang
tắt và thuộc môn/chủ đề đã tắt; danh sách rỗng trả `{"documents":[]}`. Không trả
đường dẫn lưu trữ nội bộ, nội dung chunk hoặc embedding. Lỗi truy cập/ghi database
trả `503 DATABASE_UNAVAILABLE` với thông báo cố định; lỗi ghi bật/tắt được rollback.
Giao diện quản trị hiện có gọi các API listing, xử lý và PATCH này.

POST dùng **multipart/form-data** với `file`, `topic_id`, `title` (1–200 ký tự). File tối đa **10 MiB**, không rỗng, đuôi và MIME phải khớp PDF/TXT. PDF kiểm tra chữ ký `%PDF-`; TXT phải là UTF-8 hợp lệ. Chủ đề và môn cha phải tồn tại, đang active. Swagger `/docs` có form chọn file sau khi Authorize bằng token ADMIN.

File lưu bằng tên ngẫu nhiên trong `back-end/storage/documents/`, metadata ban đầu có `status=pending`, `is_active=false`. Sau đó backend xử lý ngay trong yêu cầu upload: đọc TXT UTF-8/BOM hoặc trích văn bản PDF bằng `pypdf`, chuẩn hóa văn bản và chia đoạn. Thành công chuyển sang `ready`; tệp không thể xử lý chuyển sang `error` và vẫn giữ file để kiểm tra/thử lại. `document` trả thêm `processedAt` và `chunkCount`. `file_path` lưu tên file tương đối trong kho riêng, không nhận đường dẫn từ client và không trả đường dẫn nội bộ. Nếu ghi metadata ban đầu thất bại, file mới tạo được dọn bỏ. Thư mục này không phục vụ như tài nguyên tĩnh và đã được Git bỏ qua.

TK-042 và TK-043 không gọi model AI hoặc OCR. PDF cần có lớp văn bản và không mã hóa. Các giới hạn xử lý hiện tại: 200 trang PDF, 1.000.000 ký tự văn bản, luồng nội dung mỗi trang tối đa 4 MiB; mỗi đoạn tối đa 1.000 ký tự, chồng lấp tối đa 150 ký tự, tối đa 2.000 đoạn. Đây là các lựa chọn triển khai, có hằng số trong `app/services/document_text.py`.

Các đoạn được lưu vào `document_chunks` theo `chunk_index` bắt đầu từ 0, cùng transaction với `status` và `processed_at` trong `documents`. Ghi lỗi sẽ rollback để tránh `ready` khi thiếu đoạn. Xử lý lại một tài liệu đã `ready` không tạo trùng đoạn; các yêu cầu đồng thời được bảo vệ bằng khóa bản ghi cha. Nguồn sau xử lý vẫn tắt; ADMIN bật sử dụng tại giao diện hoặc PATCH. Retrieval chỉ lấy nguồn ready/active thuộc môn/chủ đề active.

Đặt `UPLOAD_DIR` để đổi nơi lưu; đường dẫn tương đối tính từ `back-end/`. Khi chuyển môi trường cần mang theo cả kho file và database. Tài liệu cũ đang `pending` có thể gọi API `/process` hoặc bấm **Xử lý** ở trang quản trị. Không cần migration mới.

Middleware giữ giới hạn 10 KB cho JSON; riêng POST upload nhận tối đa 10 MiB cộng 64 KiB multipart. Service vẫn kiểm tra giới hạn file riêng, kể cả request chunked. CORS cho phép PATCH. Phản hồi tài khoản, hồ sơ và tài liệu quản trị có `Cache-Control: no-store`.

Kiểm thử task: `tests/test_admin_documents_api.py` và
`tests/test_admin_documents_database_integration.py`; kiểm thử MySQL sử dụng
database tạm tên ngẫu nhiên và tự dọn sau khi chạy, không ghi database dự án.

## Prompt Socratic (TK-030)

Prompt lượt đầu nằm ở `app/prompts/socratic_system.txt`; `build_first_turn_messages()` tạo messages độc lập với nhà cung cấp/model. Prompt ưu tiên một câu hỏi gợi mở hoặc gợi ý mức 1, giữ lời giải đầy đủ cho luồng xác nhận riêng. Xem thử offline từ `back-end/`:

```powershell
.\venv\Scripts\python.exe -m app.prompts
```

`LLM_API_KEY`, `LLM_API_URL`, `LLM_MODEL` có trong `.env.example` và `Settings`, cho phép để trống. Adapter hỗ trợ OpenAI-compatible, Responses, Gemini, Anthropic và Ollama; xem [hướng dẫn cấu hình model](../docs/AI_SETUP.md), [API chat](../docs/CHAT_BACKEND.md) và [các tình huống đánh giá prompt](../docs/SOCRATIC_PROMPT.md).

## API hội thoại và gợi ý

Backend có tạo phiên, gửi/lưu tin, lịch sử có phân trang, ngữ cảnh gần nhất, gợi ý 1–3, giải thích/ví dụ, xác nhận lời giải và feedback tại `/api/chat`. Lọc dữ liệu cá nhân áp dụng cho payload gửi model. Chưa cấu hình model thì gửi tin trả 503 và giữ câu hỏi; `/retry` phản hồi lại mà không tạo tin trùng. Frontend chat và quiz đã nối API thật. `POST /api/quizzes` sinh/validate/lưu đề; nộp bài chấm bằng backend; `GET /api/quizzes/{id}/result` đọc kết quả của mình. `GET /api/ai/quota` trả hạn mức chung 30 lượt thành công/ngày UTC. Chi tiết: [AI_SETUP.md](../docs/AI_SETUP.md).

## API thống kê dashboard (TK-065)

`GET /api/dashboard` yêu cầu Bearer token của tài khoản đang hoạt động, lấy user ID
từ token. LEARNER và ADMIN chỉ đọc thống kê của chính mình; query `userId`/`user_id`
không đổi chủ sở hữu. Có thể thử tại Swagger `/docs` sau khi Authorize.

```json
{
  "dashboard": {
    "totalQuizzes": 3,
    "averageScore": 53.33,
    "totalChatSessions": 4
  }
}
```

- `totalQuizzes`: số quiz có `status=completed`, không tính bài đang làm.
- `averageScore`: trung bình `score` của quiz completed trên thang 0–100, làm tròn
  hai chữ số theo ROUND_HALF_UP. Điểm `NULL` của dữ liệu cũ không tham gia trung
  bình; chưa có điểm thì trả 0. Quiz completed có điểm 0 vẫn được tính.
- `totalChatSessions`: số bản ghi `chat_sessions`, kể cả phiên chưa có tin nhắn;
  số tin nhắn không làm tăng số phiên.

Chưa có hoạt động trả cả ba số bằng 0. Môn/chủ đề đã tắt vẫn nằm trong thống kê
lịch sử. MySQL tổng hợp trong một câu SQL, không tải nội dung câu hỏi/tin nhắn,
không lấy tổng từ `learning_progress`. API không gọi model, không kiểm tra hay
tiêu quota AI, vẫn đọc được khi hết quota. Phản hồi có `Cache-Control: no-store`.
Thiếu/sai token trả 401, tài khoản bị tắt trả 403, lỗi database trả 503
`DASHBOARD_UNAVAILABLE` với thông báo cố định.

Đối chiếu mô tả TK-065, SRS FR-07.4/FR-10.1 và backlog SF-07.2.3. Task này bổ sung
API backend; trang dashboard frontend hiện vẫn dùng dữ liệu minh họa (TK-064).
Không cần migration mới. Kiểm thử: `tests/test_dashboard_api.py` và
`tests/test_dashboard_database_integration.py` (MySQL dùng database thử nghiệm ngẫu nhiên).

## Việc cần làm tiếp

- Các API ghi danh mục, chat và quiz sử dụng model trong `app/models/` và session transaction của `app/db/database.py`; kiểm tra chủ sở hữu và quy tắc nghiệp vụ theo tài liệu SRS trước khi lưu dữ liệu.
- Chưa có refresh token và đăng xuất thu hồi token: token đã phát hành vẫn dùng được đến khi hết hạn. Nếu cần thu hồi ngay, thêm danh sách token bị thu hồi hoặc số phiên bản token theo người dùng.
- Giới hạn số lần gọi theo IP cho `/api/auth/register` (mỗi lần băm tốn CPU và 32 MiB bộ nhớ).
- Danh mục, hồ sơ, upload/xử lý/bật nguồn, chat và quiz đã nối API thật. Dashboard và một số trang lịch sử học tập còn dữ liệu minh họa; chất lượng phản hồi model cần kiểm chứng khi có key/model thật. Xem phạm vi hỗ trợ tại [AI_SETUP.md](../docs/AI_SETUP.md).
