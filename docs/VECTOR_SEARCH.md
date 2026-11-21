# Tìm kiếm vector (TK-046)

Đối chiếu mô tả **TK-046** (*"Tạo embedding và tìm kiếm vector pgvector nếu dữ liệu cho phép"*),
SRS FR-05.3 và bối cảnh triển khai hiện tại trong `docs/PROJECT_CONTEXT.md`.

## Khác biệt CSDL so với tài liệu gốc

- Tài liệu gốc thiết kế `VECTOR(768)` trên PostgreSQL (`pgvector`).
- Dự án hiện tại dùng **MySQL** (theo chỉ đạo người dùng, không chuyển sang PostgreSQL).
- Cột `document_chunks.embedding` đã có sẵn kiểu `JSON` nullable với ràng buộc
  `JSON_TYPE(embedding) = 'ARRAY' AND JSON_LENGTH(embedding) = 768`.
- **Không biến embedding/vector thành điều kiện bắt buộc**: khi chưa cấu hình API embedding,
  provider lỗi, hoặc đoạn tài liệu chưa có embedding, hệ thống tự động fallback an toàn về
  tra cứu từ khóa (`keyword`, TK-044/TK-045).

## Cấu hình tùy chọn (Backend `.env`)

- `EMBEDDING_API_URL`: endpoint OpenAI-compatible `/embeddings` (mặc định trống = tắt).
- `EMBEDDING_MODEL`: tên model embedding (ví dụ model hỗ trợ output 768 chiều).
- `EMBEDDING_API_KEY`: API key riêng cho embedding (nếu trống sẽ dùng `LLM_API_KEY`).
- `EMBEDDING_DIMENSIONS`: số chiều vector, mặc định `768` (khớp ràng buộc MySQL).
- `EMBEDDING_TIMEOUT_SECONDS`: timeout gọi API embedding (1–120 giây, mặc định `15`).

## Luồng hoạt động

1. **Tạo embedding khi xử lý tài liệu (`DocumentService.process`)**:
   - Sau khi tách văn bản thành `chunks`, nếu `embedding_provider` đã cấu hình thì gọi
     `embed_texts(chunks)` và kiểm tra đủ 768 chiều, hữu hạn, khác vector 0.
   - Lưu `chunks` và `embeddings` trong cùng transaction vào `document_chunks`.
   - Nếu gọi embedding thất bại, chỉ ghi log cảnh báo và lưu `embedding=NULL` để tài liệu
     vẫn đạt trạng thái `ready`.
2. **Tìm kiếm vector (`DocumentRetrievalService.search` / `search_vector`)**:
   - Giữ nguyên bộ lọc nguồn hợp lệ TK-045: đúng `topic_id`, `status='ready'`,
     `is_active=True`, môn và chủ đề đều `is_active=True`.
   - Tính `cosine_similarity` giữa vector câu truy vấn và vector các chunk hợp lệ, xếp hạng
     giảm dần theo độ tương đồng.
   - API `GET /api/catalog/topics/{topic_id}/chunks` hỗ trợ tham số `mode`:
     - `keyword` (mặc định, tương thích ngược hoàn toàn với TK-044).
     - `vector`: dùng tìm kiếm vector, tự fallback sang `keyword` nếu chưa có provider/dữ liệu.
     - `hybrid`: kết hợp điểm vector (0.7) và từ khóa (0.3), fallback `keyword` nếu chưa có vector.

## Kiểm thử

- `back-end/tests/test_vector_search.py` kiểm thử validate vector 768 chiều, cosine similarity,
  tạo embedding khi xử lý tài liệu, fallback khi provider lỗi hoặc thiếu dữ liệu, lọc nguồn hợp lệ,
  và API `mode=vector` / `mode=hybrid`.
