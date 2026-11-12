# Cơ sở dữ liệu Gia sư AI

MySQL 8.0.16 trở lên, SQLAlchemy 2 và Alembic. Giữ 11 bảng và các quan hệ theo tài liệu thiết kế, chuyển kiểu dữ liệu sang MySQL theo yêu cầu sử dụng của dự án.

## Tổ chức mã nguồn

```text
back-end/
├── app/
│   ├── config.py                       # DATABASE_URL và cấu hình khác
│   ├── db/
│   │   ├── base.py                     # DeclarativeBase
│   │   ├── database.py                 # Engine, SessionLocal, get_db
│   │   ├── types.py                    # DATETIME(6), chuyển đổi UTC
│   │   ├── init_db.py                  # Tạo database và chạy migration
│   │   └── seed.py                     # Seed môn/chủ đề, ADMIN tùy chọn
│   ├── models/                        # Mỗi bảng một model riêng
│   └── repositories/
│       └── sqlalchemy_user_repository.py
├── alembic/versions/                   # Lịch sử thay đổi schema
├── alembic.ini
└── .env.example
database/
├── README.md
└── schema.sql                          # Schema hiện tại cho database trống
```

## Dùng MySQL đã cài trên máy

Bật dịch vụ MySQL, sau đó chạy trong thư mục `back-end/`:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Nếu đã có `venv` hoặc `.env` thì dùng lại. Cập nhật `DATABASE_URL` trong `.env` bằng tài khoản MySQL của bạn, ví dụ:

```dotenv
DATABASE_URL=mysql+pymysql://root:your_password@localhost:3306/gia_su_ai?charset=utf8mb4
```

Thay `your_password` bằng mật khẩu thật. Nếu mật khẩu chứa ký tự đặc biệt như `@`, `:`, `/`, `#`, cần URL-encode phần mật khẩu. Thay `JWT_SECRET` mẫu bằng khóa riêng ít nhất 32 ký tự. `.env` đã được bỏ qua trong Git.

Khởi tạo database, bảng và dữ liệu mẫu:

```powershell
.\venv\Scripts\python.exe -m app.db.init_db
.\venv\Scripts\python.exe -m app.db.seed
.\venv\Scripts\python.exe -m app.db.seed --admin
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

`init_db` kiểm tra và tạo database `gia_su_ai` nếu thiếu, dùng charset `utf8mb4`, sau đó chạy Alembic đến `head`. Tài khoản cần quyền tạo database khi chưa có database và quyền tạo/sửa bảng trong database đó. Nếu database đã được cấp sẵn, có thể chạy trực tiếp `python -m alembic upgrade head`.

Sau khi khởi tạo, mở MySQL Workbench, refresh Schemas rồi xem `gia_su_ai`: có 11 bảng nghiệp vụ và bảng hạ tầng `alembic_version`.

Seed thêm 2 môn, 3 chủ đề và hai tài khoản mẫu để thử chức năng:

| Vai trò | Email | Mật khẩu mẫu |
| --- | --- | --- |
| LEARNER | `learner@example.com` | `Learner@123` |
| ADMIN | `admin@example.com` | `Admin@123` |

Mật khẩu được băm trước khi lưu. Chạy lại không tạo trùng, không đổi mật khẩu, tên, vai trò hoặc trạng thái tài khoản đã có. Nếu email đã thuộc một vai trò khác, seed báo lỗi để tránh nâng quyền ngoài ý muốn.

`--admin` tạo thêm ADMIN bằng email/mật khẩu tự nhập (ẩn mật khẩu lúc nhập), hoặc đọc `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD` từ môi trường/`.env`. Trên database chưa có tài khoản, nếu dùng đúng email ADMIN mẫu thì mật khẩu tự nhập được ưu tiên. Nếu ADMIN đó đã tồn tại, seed giữ nguyên mật khẩu đang lưu.

API đăng ký và đọc tài khoản mặc định dùng MySQL. API giữ trường `name`, database lưu `full_name`; ID trả về là số nguyên dương và thời gian UTC có hậu tố `Z`. Các test API độc lập vẫn có thể inject `InMemoryUserRepository`.

## Dùng Docker nếu chưa cài MySQL

Từ thư mục gốc:

```powershell
docker compose up -d db
docker compose ps
```

Đợi service `db` báo healthy. Compose chạy MySQL 8.4 với database/tài khoản phát triển khớp `.env.example`:

```dotenv
DATABASE_URL=mysql+pymysql://gia_su_ai:gia_su_ai_dev@localhost:3306/gia_su_ai?charset=utf8mb4
```

Có thể đổi `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `MYSQL_PORT` qua môi trường của Compose; cập nhật `DATABASE_URL` tương ứng. Nếu cổng 3306 đã được MySQL trên máy sử dụng, dùng MySQL đó hoặc đổi `MYSQL_PORT`, ví dụ 3307. Volume `mysql_data` giữ dữ liệu khi khởi động lại; đổi biến môi trường không tự đổi mật khẩu của database đã khởi tạo.

## Kiểu dữ liệu và quy tắc

| Dữ liệu | Cách lưu trong MySQL |
| --- | --- |
| ID khóa chính | `INT NOT NULL AUTO_INCREMENT`; MySQL tự cấp số khi INSERT |
| Khóa ngoại | `INT`, tham chiếu số ID của bảng cha |
| Thời gian | `DATETIME(6)` theo UTC; `UTCDateTime` chuyển về datetime có múi giờ khi đọc |
| Lựa chọn câu hỏi, nguồn trích dẫn | `JSON`; `source_refs` mặc định `(JSON_ARRAY())` |
| Embedding | `JSON` nullable, CHECK mảng đủ 768 phần tử; chưa có vector index hoặc vector search |
| Role, status, difficulty | `VARCHAR` + CHECK |
| Điểm, phần trăm | `NUMERIC(5,2)` |

Mỗi bảng có bộ đếm ID riêng: `1, 2, 3...`. ID có thể có khoảng trống sau khi xóa dữ liệu hoặc rollback; không đánh lại số các bản ghi đang tồn tại. Trong JWT, `sub` vẫn là chuỗi chứa số ID để tuân theo định dạng token.

Tất cả bảng dùng InnoDB, charset `utf8mb4`, collation `utf8mb4_0900_as_cs` để lưu tiếng Việt và kiểm tra các giá trị A/B/C/D, role, status có phân biệt hoa/thường. MySQL 8.0.16 trở lên cần thiết để CHECK được thực thi; expression default cho JSON cần MySQL 8.0.13 trở lên.

Kết nối backend và Alembic đặt session `time_zone = '+00:00'`. Khi chạy SQL ngoài ứng dụng, cũng đặt múi giờ UTC trước khi thêm/cập nhật timestamp. `users.updated_at` và `chat_sessions.updated_at` có ORM `onupdate=CURRENT_TIMESTAMP(6)`; đây không phải trigger cho SQL ngoài ORM. Service chat cần cập nhật phiên cha khi thêm tin nhắn.

## Các bảng

| Bảng | Vai trò | Ràng buộc chính |
| --- | --- | --- |
| `users` | Tài khoản | UNIQUE email; role LEARNER/ADMIN |
| `subjects` | Môn học | UNIQUE name + grade_level |
| `topics` | Chủ đề trong chương | UNIQUE subject_id + chapter_name + name |
| `documents` | Metadata tài liệu | status pending/ready/error; is_active mặc định false |
| `document_chunks` | Đoạn RAG | UNIQUE document_id + chunk_index; embedding nullable, đủ 768 phần tử |
| `chat_sessions` | Phiên theo user/topic | Index user_id + updated_at DESC |
| `chat_messages` | Tin nhắn và trích dẫn | Role user/assistant; hint 1–3; feedback -1/1; source_refs JSON |
| `quizzes` | Lần luyện tập | Độ khó/trạng thái hợp lệ; score 0–100 |
| `quiz_questions` | Câu hỏi | UNIQUE quiz_id + position; position 1–5; đáp án A–D |
| `quiz_answers` | Đáp án đã nộp | UNIQUE question_id; đáp án A–D |
| `learning_progress` | Tổng hợp tiến độ | UNIQUE user_id + topic_id; số đếm không âm; correct_count <= total_count |

Xóa user kéo theo chat, quiz và tiến độ; xóa phiên kéo theo tin nhắn; xóa quiz kéo theo câu hỏi/đáp án; xóa tài liệu kéo theo chunk. Các FK tới môn/chủ đề dùng RESTRICT. Vô hiệu hóa tài khoản, môn, chủ đề, tài liệu bằng `is_active` để giữ lịch sử.

Các quy tắc service cần thực hiện khi triển khai API chat/quiz: kiểm tra chủ sở hữu; chỉ tra cứu tài liệu ready và active; xác thực đủ đúng 5 câu và 4 lựa chọn; khóa quiz khi nộp; lưu đáp án, điểm và tiến độ trong một transaction. UNIQUE chỉ bảo đảm tối đa 5 vị trí và một đáp án/câu. ID nguồn trong JSON không phải FK vật lý.

## Migration và file SQL

Chạy tại `back-end/`:

```powershell
.\venv\Scripts\python.exe -m alembic current
.\venv\Scripts\python.exe -m alembic upgrade head
.\venv\Scripts\python.exe -m alembic revision --autogenerate -m "mo_ta_thay_doi"
```

Rà soát revision được sinh trước khi áp dụng. Model không gọi `create_all()` khi import. MySQL DDL có implicit commit nên lỗi giữa migration có thể để lại một phần bảng; cần kiểm tra trạng thái trước khi chạy lại.

`schema.sql` là schema hiện tại với 11 bảng dùng ID tự tăng và bảng `alembic_version` ở revision `0002_integer_ids`. Chỉ áp dụng một lần vào database MySQL trống. Trong Workbench, tạo/chọn schema `gia_su_ai`, mở file và chạy; không nhập file này vào database đã có dữ liệu.

Xuất lại schema từ `back-end/`, không cần kết nối MySQL:

```powershell
.\venv\Scripts\python.exe -m app.db.export_schema
```

### Chuyển database cũ từ UUID sang ID tự tăng

Migration `0001_create_learning_schema` được giữ nguyên để không sửa lịch sử đã áp dụng. Migration `0002_integer_ids` đổi toàn bộ ID và 12 khóa ngoại sang số, đồng thời ánh xạ `document_id`, `chunk_id` đã biết trong `chat_messages.source_refs`. Các cột nội dung, tài khoản, mật khẩu và các quan hệ được giữ nguyên.

Trước khi áp dụng: dừng Uvicorn và các tiến trình đang ghi database, xuất backup đầy đủ bằng MySQL Workbench và bảo đảm có thể khôi phục backup. MySQL DDL tự commit nên không thể rollback cả migration bằng transaction. Nếu phát hiện trạng thái schema ngoài thiết kế, migration dừng; không chạy lại tùy ý khi còn cột `_ai_*`/`_old_*`, hãy kiểm tra và khôi phục backup trước.

Sau khi đã sao lưu, chạy từ `back-end/`:

```powershell
.\venv\Scripts\python.exe -m app.db.init_db
.\venv\Scripts\python.exe -m alembic current
```

Kết quả phải là `0002_integer_ids (head)`. Migration giữ nguyên số lượng bản ghi, ánh xạ lại các liên kết và không xóa bảng dữ liệu. ID số của dữ liệu cũ được cấp khi thêm cột tự tăng; không cam kết thứ tự theo ngày tạo. Người dùng cần đăng nhập lại vì token cũ chứa UUID không còn dùng được.

Revision 0002 cần đọc database thật nên không hỗ trợ `alembic upgrade head --sql`. Không có downgrade tự động về UUID; muốn quay lại cần khôi phục backup trước migration. Các test offline/metadata đã kiểm tra kiểu số và API, nhưng không thay thế kiểm thử migration trên bản sao database trước khi áp dụng dữ liệu quan trọng.

## Kiểm thử

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Test không cần server kiểm tra mapping, DDL MySQL, SQL migration, timezone và các test API/password/token. Để chạy test tích hợp MySQL, cấu hình tài khoản test có quyền tạo/xóa database:

```powershell
$env:TEST_DATABASE_URL = 'mysql+pymysql://root:your_password@localhost:3306/gia_su_ai?charset=utf8mb4'
.\venv\Scripts\python.exe -m pytest tests/test_database_integration.py -q
```

Test tạo database tạm `gia_su_ai_test_<uuid>` trên cùng server rồi xóa đúng database tạm đó sau khi chạy; không sửa database trong URL. Không đặt `TEST_DATABASE_URL` thì các test tích hợp được skipped.

Mật khẩu hiện có của backend tiếp tục dùng scrypt; yêu cầu bcrypt/Argon2 trong SRS cần được xử lý trong phần xác thực kèm phương án tương thích hash đã lưu.
