# Hướng dẫn deploy Gia Sư AI lên Render + Aiven MySQL (Miễn phí, HTTPS)

Kiến trúc triển khai sử dụng **1 container Docker duy nhất trên Render** (chạy đồng thời FastAPI trên `127.0.0.1:8000` và Node frontend proxy `serve.cjs` trên cổng công khai của Render) kết nối tới **Aiven for MySQL 8 (gói Free)**:

- **Không bị lỗi CORS hay timeout gọi chéo giữa 2 service** (do frontend và backend nằm chung 1 container, proxy qua `127.0.0.1:8000`).
- **Tự động HTTPS** do Render cấp chứng chỉ SSL miễn phí.
- **Tự động chạy Alembic migration** và (tùy chọn) **seed dữ liệu demo** khi khởi động.

---

## Bước 1: Tạo MySQL 8 miễn phí trên Aiven

> Khuyên dùng **Aiven for MySQL** (chạy MySQL 8.0 thật, tương thích 100% với collation `utf8mb4_0900_as_cs`, `CHECK`, `JSON_ARRAY()` và `GET_LOCK` của dự án).

1. Truy cập https://console.aiven.io và đăng ký/đăng nhập (có thể dùng GitHub/Google).
2. Chọn **Create service** -> **MySQL**.
3. Chọn **Free Plan** -> chọn Cloud & Region gần Việt Nam nhất (ví dụ Singapore nếu có, hoặc AWS/GCP gần nhất) -> đặt tên service (ví dụ `gia-su-ai-db`) -> nhấn **Create free service**.
4. Đợi vài phút tới khi trạng thái chuyển sang **Running**.
5. Trong trang **Overview** của service, copy **Service URI**, có dạng:
   ```text
   mysql://avnadmin:<MAT_KHAU>@mysql-xxxx.aivencloud.com:<PORT>/defaultdb?ssl-mode=REQUIRED
   ```
   *(Backend đã tự chuyển `mysql://` sang `mysql+pymysql://` và xử lý `?ssl-mode=REQUIRED`, bạn dán nguyên chuỗi này vào `DATABASE_URL` là chạy được ngay).*

---

## Bước 2: Push các file deploy lên GitHub

Kiểm tra và đẩy các file cấu hình vừa tạo (`Dockerfile`, `.dockerignore`, `render.yaml`, `deploy/start.sh`, `docs/DEPLOY_RENDER.md`) lên GitHub:

```powershell
git add Dockerfile .dockerignore render.yaml deploy/start.sh docs/DEPLOY_RENDER.md
git commit -m "Add Docker and Render deployment configuration"
git push origin main
```

*(Thay `main` bằng nhánh bạn đang dùng nếu khác).*

---

## Bước 3: Deploy lên Render

### Cách A: Dùng Render Blueprint (nhanh nhất, tự đọc `render.yaml`)

1. Truy cập https://dashboard.render.com và đăng nhập bằng GitHub.
2. Nhấn **New +** -> **Blueprint**.
3. Chọn repository `nphucta-dev/gia-su-AI` -> nhấn **Connect**.
4. Đặt tên Blueprint (ví dụ `gia-su-ai`) -> nhập các biến môi trường mà Render yêu cầu (`sync: false`):

| Biến môi trường | Giá trị cần điền |
| :--- | :--- |
| `DATABASE_URL` | Dán nguyên **Service URI** lấy từ Aiven ở Bước 1 |
| `CORS_ORIGIN` | Để tạm `https://gia-su-ai.onrender.com` (sau khi có URL chính thức trên Render thì cập nhật khớp) |
| `LLM_API_KEY` | API key của bạn (Gemini / OpenAI / Groq / Anthropic...) |
| `LLM_API_URL` | Endpoint của nhà cung cấp AI (xem bảng mẫu bên dưới) |
| `LLM_MODEL` | Tên model AI (xem bảng mẫu bên dưới) |

*(Biến `JWT_SECRET` sẽ được Render tự sinh ngẫu nhiên an toàn).*

### Bảng cấu hình mẫu cho một số nhà cung cấp LLM

| Nhà cung cấp | `LLM_PROVIDER` | `LLM_API_URL` | `LLM_MODEL` (ví dụ) |
| :--- | :--- | :--- | :--- |
| **Google Gemini** | `gemini` | `https://generativelanguage.googleapis.com/v1beta` | `gemini-2.5-flash` |
| **OpenAI** | `openai` | `https://api.openai.com/v1` | `gpt-4o-mini` |
| **Groq** | `openai_compatible` | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| **OpenRouter** | `openai_compatible` | `https://openrouter.ai/api/v1` | `google/gemini-2.0-flash-001` |

*(Xem thêm chi tiết tại `docs/AI_SETUP.md`).*

5. Nhấn **Apply** để Render bắt đầu build Docker image và chạy dịch vụ (lần đầu mất khoảng 3–5 phút).

### Cách B: Tạo Web Service thủ công (nếu không dùng Blueprint)

1. Nhấn **New +** -> **Web Service** -> chọn repo `nphucta-dev/gia-su-AI`.
2. **Language / Runtime**: chọn **Docker**.
3. **Instance Type**: chọn **Free**.
4. Thêm các **Environment Variables** giống bảng ở Cách A, cộng thêm:
   - `JWT_SECRET`: chuỗi ngẫu nhiên dài ít nhất 32 ký tự.
   - `RUN_MIGRATIONS`: `true`
   - `RUN_SEED`: `true`
   - `LLM_PROVIDER`: `auto` (hoặc tên chuẩn ở bảng trên).
5. Nhấn **Deploy Web Service**.

---

## Bước 4: Kiểm tra sau khi deploy xong

Khi Render báo **Live**, mở URL dạng `https://<ten-service>.onrender.com`:

1. Kiểm tra backend: mở `https://<ten-service>.onrender.com/api/health` -> trả `{"status":"ok"}`.
2. Kiểm tra kết nối Aiven MySQL: mở `https://<ten-service>.onrender.com/api/database` -> trả `{"status":"ok","database":"connected",...}`.
3. Mở trang chủ `https://<ten-service>.onrender.com` và đăng nhập thử bằng tài khoản mẫu:
   - Người học: `learner@example.com` / `Learner@123`
   - Quản trị viên: `admin@example.com` / `Admin@123`

> **Khuyến nghị bảo mật sau lần deploy đầu tiên:**
> - Có thể thêm `SEED_ADMIN_EMAIL` và `SEED_ADMIN_PASSWORD` để tạo tài khoản ADMIN riêng với mật khẩu mạnh.
> - Sau khi dữ liệu mẫu đã được nạp xong, bạn có thể đổi `RUN_SEED` thành `false` trên Render để khởi động nhanh hơn ở các lần sau.

---

## Lưu ý khi dùng gói miễn phí (Render Free)

1. **Cold start (ngủ đông):** Sau 15 phút không có người truy cập, Render Free sẽ tạm ngủ container. Lần truy cập tiếp theo sẽ mất khoảng 30–50 giây để đánh thức lại.
2. **Ổ đĩa tạm (Ephemeral disk):** Tài liệu PDF/TXT do ADMIN upload mới vào `storage/documents` sẽ bị xóa file gốc khi Render restart/redeploy, **nhưng nội dung chunks đã trích xuất vẫn nằm bền vững trong Aiven MySQL** nên tính năng hỏi đáp RAG và quiz vẫn hoạt động bình thường. Nếu cần lưu file PDF gốc vĩnh viễn, cần gắn Persistent Disk (gói trả phí) hoặc lưu lên object storage (S3/R2).
