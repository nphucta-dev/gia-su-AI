# Tra cứu đoạn theo từ khóa (TK-044)

Đối chiếu mô tả TK-044, SRS FR-05.3 và thiết kế `document_chunks`: tìm những đoạn
liên quan trong một chủ đề bằng từ khóa. Bộ lọc nguồn hợp lệ TK-045 được giữ lại.

## API

`GET /api/catalog/topics/{topic_id}/chunks?q=phuong%20trinh&limit=5`

API yêu cầu Bearer token của tài khoản active. `q` bắt buộc, tối đa 400 ký tự và
1–20 từ khóa khác nhau sau chuẩn hóa. `limit` mặc định 5, từ 1 đến 20. ID chủ đề là
số nguyên từ 1 đến 2³¹−1.

Phản hồi gồm `topicId`, `query`, `limit`, `chunks`. Mỗi đoạn có `id`, `documentId`,
`documentTitle`, `topicId`, `chunkIndex`, `content`, `score`. Không trả đường dẫn
file trên server. Không có đoạn phù hợp thì `chunks` là mảng rỗng.

Môn/chủ đề phải còn active. Tài liệu phải đúng chủ đề, `status=ready` và
`is_active=true`. Chủ đề thiếu/đã tắt trả `404 TOPIC_NOT_FOUND`; query hoặc giới hạn
không hợp lệ trả `422`; kho tài liệu chưa sẵn sàng/lỗi SQL trả `503 SOURCES_UNAVAILABLE`.
Các phản hồi có `Cache-Control: no-store`.

## Quy tắc tìm kiếm

- Chuẩn hóa Unicode NFKC, hoa/thường, dấu tiếng Việt và `đ`/`d`; hỗ trợ văn bản NFC/NFD.
- Tách thành từ và khớp toàn từ trong nội dung đoạn. Đoạn có ít nhất một từ khóa
  khớp được xem xét; dấu câu không phải ký tự đại diện SQL.
- Xếp theo số từ khóa khác nhau khớp được, tiếp theo tổng số lần xuất hiện.
  Khi bằng nhau, dùng document ID, thứ tự đoạn và chunk ID để kết quả ổn định.
- `score` là số từ khóa khác nhau khớp trong đoạn. Áp dụng `limit` sau khi đã lọc
  và xếp hạng, không cắt trước những đoạn đầu tài liệu.

SQL dùng tham số có escape cho LIKE và lọc đúng chủ đề/nguồn hợp lệ. Ứng viên có
Unicode được giữ để bộ so khớp Python xử lý thống nhất các trường hợp chuẩn hóa.
Cách này có thể đọc toàn bộ ứng viên Unicode hợp lệ trong một chủ đề trước khi
xếp hạng; chưa thêm chỉ mục full-text, embedding hoặc vector search.

Service `DocumentRetrievalService.search(topic_id, query, limit=5)` dùng lại được
cho luồng chat sau này. Task này chưa thêm nội dung truy xuất vào prompt, chưa lưu
`source_refs` và chưa triển khai API trích dẫn TK-047/TK-049. Không gọi model AI hay
tự bật tài liệu đang tắt. Không cần migration hoặc thư viện mới.

## Kiểm thử

`tests/test_keyword_retrieval.py` và `tests/test_keyword_search_api.py` kiểm tra
chuẩn hóa, thứ tự/giới hạn, loại bỏ nguồn sai trạng thái/chủ đề, quyền truy cập và
lỗi dữ liệu. Các kiểm thử TK-045 cũ vẫn chạy.

`tests/test_two_tasks_database_integration.py` kiểm tra cùng hành vi trên MySQL,
gồm NFC/NFD, có/không dấu, `đ`, casefold và các đoạn khớp nằm sau nhiều đoạn không
liên quan. Fixture chỉ tạo/xóa database thử nghiệm ngẫu nhiên riêng.
