# Đối chiếu task với dự án hiện tại

Ngày rà soát: **24/11/2026**.

Phạm vi gồm **95 task gốc** trong [task-details.json](reference/task-details.json)
và **2 task bổ sung** trong [task-additions.json](reference/task-additions.json).
Chỉ đối chiếu tên task, mô tả công việc, yêu cầu nghiệp vụ và code hiện tại.
Không dùng cột phân công, lịch, điểm, trạng thái hoặc tiêu chí của workbook để kết luận.

**Có triển khai** nghĩa là đã tìm thấy code thực hiện công việc và đường tích hợp liên quan,
không đồng nghĩa đã nghiệm thu trên môi trường triển khai hoặc với mọi model.
Các tệp test là bằng chứng phạm vi đã được kiểm tra; sự tồn tại của tệp không tự chứng minh test vừa chạy.
Báo cáo không thay đổi logic ứng dụng, chạy migration hay triển khai các task còn thiếu.

## Kết quả cần làm tiếp

| Task | Phần chưa có hoặc cần hoàn tất |
| --- | --- |
| TK-093 — Triển khai demo | Chưa thấy cấu hình/bằng chứng triển khai public và HTTPS; server frontend hiện bind 127.0.0.1. Trước đó người dùng mới hỏi cách chia sẻ để test, chưa giao triển khai. |
| TK-094 — Kịch bản demo ứng dụng | Chưa tìm thấy tài liệu kịch bản thao tác từ đăng nhập tới quiz trong repository. README khởi động và test tự động chưa thay thế kịch bản trình bày. |
| TK-096 — Giao diện xem tài liệu học tập | Đã thêm mô tả task, chưa có UI người học xem danh sách và đọc toàn bộ PDF/TXT. |
| TK-097 — API xem tài liệu học tập | Đã thêm mô tả task, chưa có API danh sách/chi tiết/nội dung tài liệu cho người học. API quản trị và trích dẫn chat hiện có không thay thế chức năng này. |

| Task | Điểm còn thiếu hoặc khác yêu cầu |
| --- | --- |
| TK-046 — Tìm kiếm vector pgvector | Có client embedding thật, kiểm tra vector 768 chiều và cosine/hybrid trên MySQL JSON. Cấu hình embedding hiện chưa đầy đủ nên fallback keyword; chat gọi search mặc định keyword. Tài liệu ready có chunk được trả về sớm khi process, chưa có thao tác tạo lại embedding cho nguồn cũ. Cần hoàn tất cấu hình/dữ liệu và kiểm chứng luồng thực tế. Giữ MySQL theo chỉ đạo người dùng; không yêu cầu chuyển sang PostgreSQL. |
| TK-080 — Băm và kiểm tra mật khẩu | Hash/verify scrypt đã hoạt động và có test. Mô tả gốc ghi bcrypt/Argon2; đây là khác biệt cần chốt yêu cầu, không phải thiếu băm mật khẩu. Không tự thay thuật toán hay hash đã lưu. |
| TK-086 / TK-087 — Kiểm thử UI thủ công | Có nhiều test trình duyệt tự động, nhưng chưa tìm thấy biên bản chạy thủ công cho auth/chat và quiz/admin/dashboard/responsive. Cần ghi nhận kết quả thủ công đúng công việc đã mô tả. |

TK-092 đã có repository, README, .env.example và hướng dẫn local. Tuy nhiên,
[front-end/README.md](../front-end/README.md) và
[project_state_fe.md](../front-end/project_state_fe.md) còn mô tả dashboard/lịch sử/preview
hoặc API theo phiên bản cũ; không dùng các ghi chú đó để kết luận runtime hiện tại còn dữ liệu mẫu.

Các task AI TK-020, TK-030, TK-051 và TK-089 đã có code tích hợp/test liên quan.
Vẫn cần kiểm chứng với provider thật và đánh giá chất lượng nội dung; test giả lập
không xác nhận khả năng trả lời tiếng Việt, chất lượng Socratic hoặc độ đúng kiến thức của model thực tế.

## Hai task AI được hỏi riêng

- **TK-020 — API hỏi đáp LLM:** `POST /api/chat/sessions/{session_id}/messages`
  nhận câu hỏi, kiểm tra phiên/quyền/quota, gọi model và lưu/trả phản hồi.
  Route nối ChatService, LLM client và giao diện chat thật.
- **TK-051 — AI sinh quiz JSON:** `POST /api/quizzes` gọi model theo topic/độ khó;
  prompt yêu cầu 5 câu, lựa chọn A–D, đáp án đúng và giải thích.
  Payload được kiểm tra trước khi lưu; giao diện luyện tập đã gọi API này.

Nhóm kiểm thử liên quan được chạy trong lần rà soát này: **209 passed**,
gồm `test_chat_api.py`, `test_ai_chat_complete.py`, `test_ai_quiz_api.py`,
`test_quiz_validation.py`, `test_llm_task_contracts.py` và
`test_ai_provider_workflows.py`. Các bài này dùng provider/HTTP giả lập;
**không gọi model thật** và không xác nhận nghiệm thu chất lượng AI.
`test_llm_live.py` có sẵn nhưng chỉ chạy khi bật `RUN_LIVE_LLM_TESTS=1`;
không chạy bài live trong lần kiểm tra này.

## Ma trận 97 task

Tổng hợp: **89 có triển khai**, **2 còn thiếu/khác yêu cầu**,
**2 chưa đủ bằng chứng test thủ công**, **4 chưa thấy triển khai**.
Hai task bổ sung được lưu riêng để không thay đổi bản trích 95 task gốc.

| Mã tra cứu | Tên task | Kết quả rà soát | Bằng chứng và ghi chú |
| --- | --- | --- | --- |
| TK-001 | Form đăng ký | Có triển khai | [auth-screen.js](../front-end/src/js/pages/auth-screen.js), [auth.cjs](../front-end/tests/auth.cjs). Form gọi API và hiển thị lỗi dữ liệu/xác thực. |
| TK-002 | API đăng ký | Có triển khai | [auth.py](../back-end/app/routes/auth.py), [auth_service.py](../back-end/app/services/auth_service.py), [test_register_api.py](../back-end/tests/test_register_api.py), [test_login_api.py](../back-end/tests/test_login_api.py). Luồng đăng ký/đăng nhập, repository và validation server. |
| TK-003 | Kiểm tra form đăng ký | Có triển khai | [auth-screen.js](../front-end/src/js/pages/auth-screen.js), [auth.cjs](../front-end/tests/auth.cjs). Form gọi API và hiển thị lỗi dữ liệu/xác thực. |
| TK-004 | Kiểm tra dữ liệu đăng ký (API) | Có triển khai | [auth.py](../back-end/app/routes/auth.py), [auth_service.py](../back-end/app/services/auth_service.py), [test_register_api.py](../back-end/tests/test_register_api.py), [test_login_api.py](../back-end/tests/test_login_api.py). Luồng đăng ký/đăng nhập, repository và validation server. |
| TK-005 | Form đăng nhập | Có triển khai | [auth-screen.js](../front-end/src/js/pages/auth-screen.js), [auth.cjs](../front-end/tests/auth.cjs). Form gọi API và hiển thị lỗi dữ liệu/xác thực. |
| TK-006 | API đăng nhập | Có triển khai | [auth.py](../back-end/app/routes/auth.py), [auth_service.py](../back-end/app/services/auth_service.py), [test_register_api.py](../back-end/tests/test_register_api.py), [test_login_api.py](../back-end/tests/test_login_api.py). Luồng đăng ký/đăng nhập, repository và validation server. |
| TK-007 | Đăng xuất phía client | Có triển khai | [session.js](../front-end/src/js/session.js), [session.cjs](../front-end/tests/session.cjs). Đăng xuất xóa token và state tài khoản. |
| TK-008 | Xác thực token API | Có triển khai | [auth.py](../back-end/app/dependencies/auth.py), [test_token_auth_api.py](../back-end/tests/test_token_auth_api.py). Xác thực token, kiểm tra user hiện tại/role/active. |
| TK-009 | Trang hồ sơ cá nhân | Có triển khai | [account.js](../front-end/src/js/pages/account.js), [account-data-ui.cjs](../front-end/tests/account-data-ui.cjs). Hồ sơ và dữ liệu người dùng lấy qua API. |
| TK-010 | API hồ sơ cá nhân | Có triển khai | [profile.py](../back-end/app/routes/profile.py), [test_profile_api.py](../back-end/tests/test_profile_api.py). GET/PATCH hồ sơ tài khoản đang đăng nhập. |
| TK-011 | Phân quyền tài khoản | Có triển khai | [auth.py](../back-end/app/dependencies/auth.py), [test_token_auth_api.py](../back-end/tests/test_token_auth_api.py). Xác thực token, kiểm tra user hiện tại/role/active. |
| TK-012 | Danh sách môn học | Có triển khai | [learning.js](../front-end/src/js/pages/learning.js), [catalog.js](../front-end/src/js/catalog.js), [catalog.cjs](../front-end/tests/catalog.cjs). Danh mục thật, chương/chủ đề và điều hướng học. |
| TK-013 | API danh sách môn | Có triển khai | [catalog.py](../back-end/app/routes/catalog.py), [test_catalog_api.py](../back-end/tests/test_catalog_api.py). Danh sách subjects/topics active và bộ lọc. |
| TK-014 | Nhóm chủ đề theo chương | Có triển khai | [learning.js](../front-end/src/js/pages/learning.js), [catalog.js](../front-end/src/js/catalog.js), [catalog.cjs](../front-end/tests/catalog.cjs). Danh mục thật, chương/chủ đề và điều hướng học. |
| TK-015 | Chọn chủ đề học | Có triển khai | [learning.js](../front-end/src/js/pages/learning.js), [catalog.js](../front-end/src/js/catalog.js), [catalog.cjs](../front-end/tests/catalog.cjs). Danh mục thật, chương/chủ đề và điều hướng học. |
| TK-016 | CRUD môn học và chủ đề | Có triển khai | [admin_catalog.py](../back-end/app/routes/admin_catalog.py), [test_admin_catalog_api.py](../back-end/tests/test_admin_catalog_api.py). Tạo/sửa và cập nhật is_active môn/chủ đề. |
| TK-017 | Bật/tắt môn học và chủ đề | Có triển khai | [admin_catalog.py](../back-end/app/routes/admin_catalog.py), [test_admin_catalog_api.py](../back-end/tests/test_admin_catalog_api.py). Tạo/sửa và cập nhật is_active môn/chủ đề. |
| TK-018 | API tạo phiên chat | Có triển khai | [chat.py](../back-end/app/routes/chat.py), [test_chat_api.py](../back-end/tests/test_chat_api.py). Phiên và lịch sử lấy đúng tài khoản qua service/repository. |
| TK-019 | Giao diện chat AI | Có triển khai | [chat-live.js](../front-end/src/js/pages/chat-live.js), [chat-history.cjs](../front-end/tests/chat-history.cjs), [chat-empty-question-ui.cjs](../front-end/tests/chat-empty-question-ui.cjs). Giao diện chat thật, sidebar, loading và kiểm tra nội dung. |
| TK-020 | API hỏi đáp LLM | Có triển khai | [chat.py](../back-end/app/routes/chat.py), [llm_client.py](../back-end/app/services/llm_client.py), [chat-live.js](../front-end/src/js/pages/chat-live.js), [test_llm_task_contracts.py](../back-end/tests/test_llm_task_contracts.py). POST /api/chat/sessions/{session_id}/messages gọi model và trả lời tiếng Việt; chưa xác nhận chất lượng provider thật. |
| TK-021 | Quản lý ngữ cảnh chat | Có triển khai | [chat_context.py](../back-end/app/services/chat_context.py), [test_chat_context.py](../back-end/tests/test_chat_context.py). Giới hạn ngữ cảnh, giữ câu hỏi hiện tại và mạch gợi ý. |
| TK-022 | Trạng thái chờ phản hồi | Có triển khai | [chat-live.js](../front-end/src/js/pages/chat-live.js), [chat-history.cjs](../front-end/tests/chat-history.cjs), [chat-empty-question-ui.cjs](../front-end/tests/chat-empty-question-ui.cjs). Giao diện chat thật, sidebar, loading và kiểm tra nội dung. |
| TK-023 | Lưu tin nhắn hội thoại | Có triển khai | [sqlalchemy_chat_repository.py](../back-end/app/repositories/sqlalchemy_chat_repository.py), [test_chat_repository.py](../back-end/tests/test_chat_repository.py). Lưu tin user/assistant và metadata hội thoại. |
| TK-024 | Sidebar lịch sử chat | Có triển khai | [chat-live.js](../front-end/src/js/pages/chat-live.js), [chat-history.cjs](../front-end/tests/chat-history.cjs), [chat-empty-question-ui.cjs](../front-end/tests/chat-empty-question-ui.cjs). Giao diện chat thật, sidebar, loading và kiểm tra nội dung. |
| TK-025 | API lịch sử hội thoại | Có triển khai | [chat.py](../back-end/app/routes/chat.py), [test_chat_api.py](../back-end/tests/test_chat_api.py). Phiên và lịch sử lấy đúng tài khoản qua service/repository. |
| TK-026 | Chặn câu hỏi rỗng (UI) | Có triển khai | [chat-live.js](../front-end/src/js/pages/chat-live.js), [chat-history.cjs](../front-end/tests/chat-history.cjs), [chat-empty-question-ui.cjs](../front-end/tests/chat-empty-question-ui.cjs). Giao diện chat thật, sidebar, loading và kiểm tra nội dung. |
| TK-027 | Chặn câu hỏi rỗng (API) | Có triển khai | [chat.py](../back-end/app/schemas/chat.py), [test_chat_empty_question_api.py](../back-end/tests/test_chat_empty_question_api.py). Server từ chối câu hỏi trắng/rỗng. |
| TK-028 | Thông báo lỗi AI (UI) | Có triển khai | [ai-error.js](../front-end/src/js/components/ai-error.js), [chat-live.js](../front-end/src/js/pages/chat-live.js), [ai-error-ui.cjs](../front-end/tests/ai-error-ui.cjs). Hiển thị lỗi và thao tác retry, giữ câu hỏi. |
| TK-029 | Xử lý lỗi và retry AI | Có triển khai | [llm_client.py](../back-end/app/services/llm_client.py), [chat_service.py](../back-end/app/services/chat_service.py), [test_chat_retry_api.py](../back-end/tests/test_chat_retry_api.py). Chuẩn hóa timeout/429/mạng; retry câu đã lưu. |
| TK-030 | Thiết kế prompt Socratic | Có triển khai | [socratic_system.txt](../back-end/app/prompts/socratic_system.txt), [socratic.py](../back-end/app/prompts/socratic.py), [test_socratic_prompt.py](../back-end/tests/test_socratic_prompt.py). Prompt Socratic đã dùng trong luồng gọi model; cần đánh giá nội dung với model thật. |
| TK-031 | Nút gợi ý 3 mức | Có triển khai | [chat-live.js](../front-end/src/js/pages/chat-live.js), [chat-hints-ui.cjs](../front-end/tests/chat-hints-ui.cjs), [chat-solution-modal.cjs](../front-end/tests/chat-solution-modal.cjs). Nút gợi ý/giải thích và xác nhận lời giải gọi API. |
| TK-032 | Điều phối gợi ý 3 mức | Có triển khai | [chat_service.py](../back-end/app/services/chat_service.py), [test_hint_orchestration.py](../back-end/tests/test_hint_orchestration.py). Server điều phối hint_level 1–3. |
| TK-033 | Nút giải thích bổ sung | Có triển khai | [chat-live.js](../front-end/src/js/pages/chat-live.js), [chat-hints-ui.cjs](../front-end/tests/chat-hints-ui.cjs), [chat-solution-modal.cjs](../front-end/tests/chat-solution-modal.cjs). Nút gợi ý/giải thích và xác nhận lời giải gọi API. |
| TK-034 | API giải thích bổ sung | Có triển khai | [chat.py](../back-end/app/routes/chat.py), [test_chat_explanations_api.py](../back-end/tests/test_chat_explanations_api.py). API simplify/example dùng ngữ cảnh hội thoại. |
| TK-035 | Modal xác nhận lời giải | Có triển khai | [chat-live.js](../front-end/src/js/pages/chat-live.js), [chat-hints-ui.cjs](../front-end/tests/chat-hints-ui.cjs), [chat-solution-modal.cjs](../front-end/tests/chat-solution-modal.cjs). Nút gợi ý/giải thích và xác nhận lời giải gọi API. |
| TK-036 | API xem lời giải | Có triển khai | [chat_service.py](../back-end/app/services/chat_service.py), [test_chat_solution_api.py](../back-end/tests/test_chat_solution_api.py). Yêu cầu xác nhận và lưu is_full_solution. |
| TK-037 | Đánh dấu lời giải đầy đủ | Có triển khai | [chat_service.py](../back-end/app/services/chat_service.py), [test_chat_solution_api.py](../back-end/tests/test_chat_solution_api.py). Yêu cầu xác nhận và lưu is_full_solution. |
| TK-038 | Giao diện tải tài liệu | Có triển khai | [admin.js](../front-end/src/js/pages/admin.js), [profile-upload.cjs](../front-end/tests/profile-upload.cjs), [upload.cjs](../front-end/tests/upload.cjs). Trang quản trị upload/kiểm file, xử lý và bật/tắt tài liệu qua API. |
| TK-039 | API tải tài liệu | Có triển khai | [documents.py](../back-end/app/routes/documents.py), [document_service.py](../back-end/app/services/document_service.py), [test_document_upload_api.py](../back-end/tests/test_document_upload_api.py). Upload PDF/TXT, kiểm tra ADMIN/MIME/kích thước/topic. |
| TK-040 | Kiểm tra file tải lên (UI) | Có triển khai | [admin.js](../front-end/src/js/pages/admin.js), [profile-upload.cjs](../front-end/tests/profile-upload.cjs), [upload.cjs](../front-end/tests/upload.cjs). Trang quản trị upload/kiểm file, xử lý và bật/tắt tài liệu qua API. |
| TK-041 | Kiểm tra file tải lên (API) | Có triển khai | [documents.py](../back-end/app/routes/documents.py), [document_service.py](../back-end/app/services/document_service.py), [test_document_upload_api.py](../back-end/tests/test_document_upload_api.py). Upload PDF/TXT, kiểm tra ADMIN/MIME/kích thước/topic. |
| TK-042 | Trích xuất văn bản tài liệu | Có triển khai | [document_text.py](../back-end/app/services/document_text.py), [document_service.py](../back-end/app/services/document_service.py), [test_document_processing_api.py](../back-end/tests/test_document_processing_api.py). Trích văn bản, chunk_index và cập nhật pending/ready/error. |
| TK-043 | Tách đoạn tài liệu | Có triển khai | [document_text.py](../back-end/app/services/document_text.py), [document_service.py](../back-end/app/services/document_service.py), [test_document_processing_api.py](../back-end/tests/test_document_processing_api.py). Trích văn bản, chunk_index và cập nhật pending/ready/error. |
| TK-044 | Tra cứu đoạn theo từ khóa | Có triển khai | [document_retrieval.py](../back-end/app/services/document_retrieval.py), [test_keyword_search_api.py](../back-end/tests/test_keyword_search_api.py), [test_document_source_filter.py](../back-end/tests/test_document_source_filter.py). Tra cứu từ khóa theo topic và nguồn ready/active. |
| TK-045 | Lọc nguồn hợp lệ | Có triển khai | [document_retrieval.py](../back-end/app/services/document_retrieval.py), [test_keyword_search_api.py](../back-end/tests/test_keyword_search_api.py), [test_document_source_filter.py](../back-end/tests/test_document_source_filter.py). Tra cứu từ khóa theo topic và nguồn ready/active. |
| TK-046 | Tìm kiếm vector pgvector | Còn thiếu/khác yêu cầu | [embedding_client.py](../back-end/app/services/embedding_client.py), [document_retrieval.py](../back-end/app/services/document_retrieval.py), [document_service.py](../back-end/app/services/document_service.py), [VECTOR_SEARCH.md](../docs/VECTOR_SEARCH.md). Có embedding/cosine/hybrid trên MySQL JSON; cấu hình chưa bật, chat mặc định keyword, chưa có reembedding tài liệu ready. |
| TK-047 | Lưu nguồn trích dẫn | Có triển khai | [chat_service.py](../back-end/app/services/chat_service.py), [sqlalchemy_chat_repository.py](../back-end/app/repositories/sqlalchemy_chat_repository.py), [test_chat_source_refs.py](../back-end/tests/test_chat_source_refs.py). Lưu/trả source_refs thật, kiểm soát nguồn không còn khả dụng. |
| TK-048 | Hiển thị nguồn tham khảo | Có triển khai | [messages.js](../front-end/src/js/components/messages.js), [ai-workflows.cjs](../front-end/tests/ai-workflows.cjs). Hiển thị nguồn tham khảo hoặc thông báo thiếu nguồn. |
| TK-049 | API nguồn trích dẫn | Có triển khai | [chat_service.py](../back-end/app/services/chat_service.py), [sqlalchemy_chat_repository.py](../back-end/app/repositories/sqlalchemy_chat_repository.py), [test_chat_source_refs.py](../back-end/tests/test_chat_source_refs.py). Lưu/trả source_refs thật, kiểm soát nguồn không còn khả dụng. |
| TK-050 | Chọn chủ đề và độ khó quiz | Có triển khai | [practice-live.js](../front-end/src/js/pages/practice-live.js), [quiz-submission.js](../front-end/src/js/quiz-submission.js), [quiz-selection-ui.cjs](../front-end/tests/quiz-selection-ui.cjs), [quiz-submit.cjs](../front-end/tests/quiz-submit.cjs). Chọn topic/độ khó, làm bài và gửi đáp án theo question ID. |
| TK-051 | AI sinh quiz JSON | Có triển khai | [quiz.py](../back-end/app/prompts/quiz.py), [quiz_service.py](../back-end/app/services/quiz_service.py), [practice-live.js](../front-end/src/js/pages/practice-live.js), [test_ai_quiz_api.py](../back-end/tests/test_ai_quiz_api.py). POST /api/quizzes gọi model sinh JSON đủ 5 câu; kiểm thử provider giả lập. |
| TK-052 | Kiểm tra và lưu quiz | Có triển khai | [quiz.py](../back-end/app/validators/quiz.py), [quiz_service.py](../back-end/app/services/quiz_service.py), [test_quiz_validation.py](../back-end/tests/test_quiz_validation.py). Validate toàn bộ 5 câu/A–D/đáp án/giải thích trước transaction lưu. |
| TK-053 | Giao diện làm quiz | Có triển khai | [practice-live.js](../front-end/src/js/pages/practice-live.js), [quiz-submission.js](../front-end/src/js/quiz-submission.js), [quiz-selection-ui.cjs](../front-end/tests/quiz-selection-ui.cjs), [quiz-submit.cjs](../front-end/tests/quiz-submit.cjs). Chọn topic/độ khó, làm bài và gửi đáp án theo question ID. |
| TK-054 | Cảnh báo câu chưa trả lời | Có triển khai | [practice-live.js](../front-end/src/js/pages/practice-live.js), [quiz-submission.js](../front-end/src/js/quiz-submission.js), [quiz-selection-ui.cjs](../front-end/tests/quiz-selection-ui.cjs), [quiz-submit.cjs](../front-end/tests/quiz-submit.cjs). Chọn topic/độ khó, làm bài và gửi đáp án theo question ID. |
| TK-055 | Lỗi sinh quiz (UI) | Có triển khai | [quiz-generation-error.js](../front-end/src/js/quiz-generation-error.js), [quiz-generation-error-ui.cjs](../front-end/tests/quiz-generation-error-ui.cjs). Lỗi sinh quiz có thông báo và thử lại. |
| TK-056 | Lỗi sinh quiz (API) | Có triển khai | [quiz_service.py](../back-end/app/services/quiz_service.py), [llm_client.py](../back-end/app/services/llm_client.py), [test_quiz_generation_errors_api.py](../back-end/tests/test_quiz_generation_errors_api.py). Lỗi cấu hình/provider/JSON dùng hợp đồng lỗi chuẩn, không lưu quiz dở. |
| TK-057 | Gửi đáp án quiz | Có triển khai | [practice-live.js](../front-end/src/js/pages/practice-live.js), [quiz-submission.js](../front-end/src/js/quiz-submission.js), [quiz-selection-ui.cjs](../front-end/tests/quiz-selection-ui.cjs), [quiz-submit.cjs](../front-end/tests/quiz-submit.cjs). Chọn topic/độ khó, làm bài và gửi đáp án theo question ID. |
| TK-058 | API lưu câu trả lời | Có triển khai | [quiz.py](../back-end/app/routes/quiz.py), [quiz_service.py](../back-end/app/services/quiz_service.py), [test_quiz_answers_api.py](../back-end/tests/test_quiz_answers_api.py), [test_quiz_grading_api.py](../back-end/tests/test_quiz_grading_api.py). Lưu đáp án, chấm 0–100, chặn nộp lặp. |
| TK-059 | API chấm điểm quiz | Có triển khai | [quiz.py](../back-end/app/routes/quiz.py), [quiz_service.py](../back-end/app/services/quiz_service.py), [test_quiz_answers_api.py](../back-end/tests/test_quiz_answers_api.py), [test_quiz_grading_api.py](../back-end/tests/test_quiz_grading_api.py). Lưu đáp án, chấm 0–100, chặn nộp lặp. |
| TK-060 | Trang kết quả quiz | Có triển khai | [practice-live.js](../front-end/src/js/pages/practice-live.js), [account-data-ui.cjs](../front-end/tests/account-data-ui.cjs). Trang kết quả đọc API theo quiz của tài khoản. |
| TK-061 | API trả kết quả quiz | Có triển khai | [quiz.py](../back-end/app/routes/quiz.py), [test_quiz_result_api.py](../back-end/tests/test_quiz_result_api.py). Kết quả chi tiết chỉ sau completed, có ownership. |
| TK-062 | Cập nhật thống kê học | Có triển khai | [sqlalchemy_quiz_repository.py](../back-end/app/repositories/sqlalchemy_quiz_repository.py), [mastery.py](../back-end/app/services/mastery.py), [test_progress_stats.py](../back-end/tests/test_progress_stats.py), [test_mastery_percent.py](../back-end/tests/test_mastery_percent.py). Cập nhật tiến độ trong transaction chấm, tính tỷ lệ đúng. |
| TK-063 | Tính mức thành thạo | Có triển khai | [sqlalchemy_quiz_repository.py](../back-end/app/repositories/sqlalchemy_quiz_repository.py), [mastery.py](../back-end/app/services/mastery.py), [test_progress_stats.py](../back-end/tests/test_progress_stats.py), [test_mastery_percent.py](../back-end/tests/test_mastery_percent.py). Cập nhật tiến độ trong transaction chấm, tính tỷ lệ đúng. |
| TK-064 | Trang dashboard | Có triển khai | [account.js](../front-end/src/js/pages/account.js), [account-data-live.cjs](../front-end/tests/account-data-live.cjs). Dashboard và gợi ý ôn lấy dữ liệu thật theo tài khoản. |
| TK-065 | API thống kê dashboard | Có triển khai | [dashboard.py](../back-end/app/routes/dashboard.py), [test_dashboard_api.py](../back-end/tests/test_dashboard_api.py). Thống kê quiz completed và chat_sessions theo user. |
| TK-066 | Danh sách chủ đề cần ôn | Có triển khai | [account.js](../front-end/src/js/pages/account.js), [account-data-live.cjs](../front-end/tests/account-data-live.cjs). Dashboard và gợi ý ôn lấy dữ liệu thật theo tài khoản. |
| TK-067 | API gợi ý chủ đề ôn | Có triển khai | [progress.py](../back-end/app/routes/progress.py), [test_review_topics_api.py](../back-end/tests/test_review_topics_api.py). Sắp chủ đề cần ôn theo mastery_percent. |
| TK-068 | Trang quản trị môn/chủ đề | Có triển khai | [admin.js](../front-end/src/js/pages/admin.js), [admin-catalog-ui.cjs](../front-end/tests/admin-catalog-ui.cjs). UI CRUD/trạng thái môn và chủ đề dùng API ADMIN. |
| TK-069 | Trang quản trị tài liệu | Có triển khai | [admin.js](../front-end/src/js/pages/admin.js), [profile-upload.cjs](../front-end/tests/profile-upload.cjs), [upload.cjs](../front-end/tests/upload.cjs). Trang quản trị upload/kiểm file, xử lý và bật/tắt tài liệu qua API. |
| TK-070 | API quản trị tài liệu | Có triển khai | [documents.py](../back-end/app/routes/documents.py), [document_service.py](../back-end/app/services/document_service.py), [test_admin_documents_api.py](../back-end/tests/test_admin_documents_api.py), [test_document_source_control.py](../back-end/tests/test_document_source_control.py). Listing/update tài liệu, chỉ bật ready có chunk, tắt nguồn khỏi retrieval. |
| TK-071 | Phân quyền API ADMIN | Có triển khai | [auth.py](../back-end/app/dependencies/auth.py), [test_admin_permissions_api.py](../back-end/tests/test_admin_permissions_api.py). ADMIN active; LEARNER bị từ chối HTTP403 ở API quản trị. |
| TK-072 | Kiểm soát trạng thái nguồn | Có triển khai | [documents.py](../back-end/app/routes/documents.py), [document_service.py](../back-end/app/services/document_service.py), [test_admin_documents_api.py](../back-end/tests/test_admin_documents_api.py), [test_document_source_control.py](../back-end/tests/test_document_source_control.py). Listing/update tài liệu, chỉ bật ready có chunk, tắt nguồn khỏi retrieval. |
| TK-073 | UI đánh giá phản hồi AI | Có triển khai | [message-feedback.js](../front-end/src/js/components/message-feedback.js), [message-feedback-ui.cjs](../front-end/tests/message-feedback-ui.cjs). Đánh giá từng tin assistant và đổi/bỏ đánh giá qua PATCH. |
| TK-074 | API cập nhật phản hồi | Có triển khai | [chat.py](../back-end/app/routes/chat.py), [test_chat_feedback_api.py](../back-end/tests/test_chat_feedback_api.py). Cập nhật feedback cùng message của chính mình. |
| TK-075 | Hạn mức lượt gọi AI | Có triển khai | [ai_quota.py](../back-end/app/services/ai_quota.py), [test_ai_daily_quota.py](../back-end/tests/test_ai_daily_quota.py). Hạn mức 30 lần AI thành công/ngày theo tài khoản. |
| TK-076 | UI hiển thị quota | Có triển khai | [chat-quota.js](../front-end/src/js/chat-quota.js), [chat-quota-ui.cjs](../front-end/tests/chat-quota-ui.cjs), [quota-access-ui.cjs](../front-end/tests/quota-access-ui.cjs). Quota UI; hết lượt vẫn mở lịch sử/dashboard. |
| TK-077 | API thông tin quota | Có triển khai | [ai_quota.py](../back-end/app/routes/ai_quota.py), [test_quota_info_api.py](../back-end/tests/test_quota_info_api.py), [test_quota_read_access_api.py](../back-end/tests/test_quota_read_access_api.py). GET quota và tách hạn mức khỏi các API chỉ đọc. |
| TK-078 | UI truy cập khi hết quota | Có triển khai | [chat-quota.js](../front-end/src/js/chat-quota.js), [chat-quota-ui.cjs](../front-end/tests/chat-quota-ui.cjs), [quota-access-ui.cjs](../front-end/tests/quota-access-ui.cjs). Quota UI; hết lượt vẫn mở lịch sử/dashboard. |
| TK-079 | API truy cập khi hết quota | Có triển khai | [ai_quota.py](../back-end/app/routes/ai_quota.py), [test_quota_info_api.py](../back-end/tests/test_quota_info_api.py), [test_quota_read_access_api.py](../back-end/tests/test_quota_read_access_api.py). GET quota và tách hạn mức khỏi các API chỉ đọc. |
| TK-080 | Băm và kiểm tra mật khẩu | Còn thiếu/khác yêu cầu | [password.py](../back-end/app/utils/password.py), [test_password.py](../back-end/tests/test_password.py). Scrypt đang hoạt động; khác tên thuật toán bcrypt/Argon2 trong mô tả task. |
| TK-081 | Bảo vệ khóa API LLM | Có triển khai | [config.py](../back-end/app/config.py), [llm_client.py](../back-end/app/services/llm_client.py), [llm_protocols.py](../back-end/app/services/llm_protocols.py), [test_auth_privacy_regressions.py](../back-end/tests/test_auth_privacy_regressions.py). Secret server env và lọc dữ liệu cá nhân trước khi gọi model. |
| TK-082 | Kiểm tra quyền sở hữu dữ liệu | Có triển khai | [OWNERSHIP.md](../docs/OWNERSHIP.md), [test_chat_ownership_api.py](../back-end/tests/test_chat_ownership_api.py), [test_quiz_ownership_api.py](../back-end/tests/test_quiz_ownership_api.py), [test_progress_api.py](../back-end/tests/test_progress_api.py). Ownership tại service/repository cho chat/quiz/tiến độ. |
| TK-083 | Nhãn cảnh báo nội dung AI | Có triển khai | [chat-live.js](../front-end/src/js/pages/chat-live.js), [messages.js](../front-end/src/js/components/messages.js). Nhãn cảnh báo AI trong giao diện chat. |
| TK-084 | Ẩn dữ liệu cá nhân khỏi prompt | Có triển khai | [config.py](../back-end/app/config.py), [llm_client.py](../back-end/app/services/llm_client.py), [llm_protocols.py](../back-end/app/services/llm_protocols.py), [test_auth_privacy_regressions.py](../back-end/tests/test_auth_privacy_regressions.py). Secret server env và lọc dữ liệu cá nhân trước khi gọi model. |
| TK-085 | Migration 11 bảng CSDL | Có triển khai | [0001_create_learning_schema.py](../back-end/alembic/versions/0001_create_learning_schema.py), [0002_integer_ids.py](../back-end/alembic/versions/0002_integer_ids.py), [test_migration_schema_delivery.py](../back-end/tests/test_migration_schema_delivery.py). 11 bảng/FK/unique/check trên MySQL và INT theo quyết định người dùng. |
| TK-086 | Kiểm thử UI đăng nhập/chat | Chưa đủ bằng chứng test thủ công | [auth.cjs](../front-end/tests/auth.cjs), [ai-workflows.cjs](../front-end/tests/ai-workflows.cjs), [account-data-ui.cjs](../front-end/tests/account-data-ui.cjs). Có kiểm thử tự động; chưa tìm thấy biên bản thực hiện test thủ công đúng mô tả. |
| TK-087 | Kiểm thử UI quiz/admin | Chưa đủ bằng chứng test thủ công | [auth.cjs](../front-end/tests/auth.cjs), [ai-workflows.cjs](../front-end/tests/ai-workflows.cjs), [account-data-ui.cjs](../front-end/tests/account-data-ui.cjs). Có kiểm thử tự động; chưa tìm thấy biên bản thực hiện test thủ công đúng mô tả. |
| TK-088 | Pytest Auth, Quiz, quyền truy cập | Có triển khai | [test_register_api.py](../back-end/tests/test_register_api.py), [test_quiz_authenticated_workflow_api.py](../back-end/tests/test_quiz_authenticated_workflow_api.py), [test_ownership_database_integration.py](../back-end/tests/test_ownership_database_integration.py). Bộ pytest auth, quyền, quiz 5 câu và nộp một lần. |
| TK-089 | Kiểm thử AI và RAG | Có triển khai | [test_ai_provider_workflows.py](../back-end/tests/test_ai_provider_workflows.py), [test_chat_sources_api.py](../back-end/tests/test_chat_sources_api.py), [test_llm_live.py](../back-end/tests/test_llm_live.py). Có test AI/RAG mô phỏng và test live tùy chọn; lần này không gọi provider thật. |
| TK-090 | Responsive giao diện chat | Có triển khai | [styles.css](../front-end/src/css/styles.css), [responsive-chat-ui.cjs](../front-end/tests/responsive-chat-ui.cjs). Responsive auth/danh mục/chat, có test viewport 360px. |
| TK-091 | Responsive quiz/dashboard | Có triển khai | [styles.css](../front-end/src/css/styles.css), [account-data-ui.cjs](../front-end/tests/account-data-ui.cjs). Quiz/dashboard/admin dùng responsive layout và kiểm thử trình duyệt. |
| TK-092 | Khởi tạo repository và README | Có triển khai | [README.md](../README.md), [.env.example](../back-end/.env.example), [README.md](../front-end/README.md), [project_state_fe.md](../front-end/project_state_fe.md). Có hướng dẫn chạy local; một số ghi chú FE cũ chưa đồng bộ runtime. |
| TK-093 | Triển khai demo | Chưa thấy triển khai | [serve.cjs](../front-end/serve.cjs), [README.md](../README.md). Chỉ cấu hình chạy local; chưa có bằng chứng deploy public/HTTPS. |
| TK-094 | Kịch bản demo ứng dụng | Chưa thấy triển khai | [README.md](../README.md). Hướng dẫn khởi động có; chưa tìm thấy kịch bản thao tác demo riêng trong repo. |
| TK-095 | Seed dữ liệu demo | Có triển khai | [seed.py](../back-end/app/db/seed.py), [manifest.json](../back-end/app/db/demo_documents/manifest.json), [test_seed_demo.py](../back-end/tests/test_seed_demo.py). 2 môn × 5 chủ đề, tài liệu hợp lệ kèm nguồn và tài khoản demo. |
| TK-096 | Giao diện xem tài liệu học tập | Chưa thấy triển khai | [LEARNER_DOCUMENT_TASKS.md](../docs/LEARNER_DOCUMENT_TASKS.md), [task-additions.json](../docs/reference/task-additions.json). Đã bổ sung mô tả công việc; chưa triển khai UI/API người học đọc toàn bộ tài liệu. |
| TK-097 | API xem tài liệu học tập | Chưa thấy triển khai | [LEARNER_DOCUMENT_TASKS.md](../docs/LEARNER_DOCUMENT_TASKS.md), [task-additions.json](../docs/reference/task-additions.json). Đã bổ sung mô tả công việc; chưa triển khai UI/API người học đọc toàn bộ tài liệu. |

