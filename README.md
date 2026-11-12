# Gia Sư AI

Ứng dụng gia sư AI với frontend HTML/CSS/JavaScript và backend FastAPI.

- [Backend và API](back-end/README.md)
- [Khởi tạo MySQL, migration và dữ liệu mẫu](database/README.md)
- [Frontend](front-end/README.md)

Database dùng MySQL 8.0.16 trở lên, gồm 11 bảng theo tài liệu thiết kế. Cấu hình kết nối MySQL trên máy trong `back-end/.env`, sau đó thực hiện các lệnh khởi tạo trong hướng dẫn database. Có thể dùng `docker compose up -d db` nếu muốn chạy MySQL bằng Docker.

## Chạy backend và frontend

Mở terminal thứ nhất tại `back-end/`:

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Mở terminal thứ hai tại `front-end/`:

```powershell
node serve.cjs
```

Mở http://127.0.0.1:4173 để đăng ký, đăng nhập và vào trang học. Frontend chuyển các request `/api/*` tới backend cổng 8000. Xem Swagger tại http://127.0.0.1:8000/docs và kiểm tra kết nối MySQL tại http://127.0.0.1:8000/api/database.
