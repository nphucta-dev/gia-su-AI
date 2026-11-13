# Ngữ cảnh và tài liệu dự án Gia Sư AI

Bản đọc ngày **13/11/2026**, theo yêu cầu đọc lại cả bốn tài liệu và ghi nhớ phần task mới.
Đây là ghi chú tham chiếu, không phải yêu cầu triển khai các task hay xác nhận nghiệm thu.

**Chỉ đạo bổ sung của người dùng:** trong file task, chỉ quan tâm mô tả task và công việc
cụ thể. Không dùng người phụ trách, lịch, điểm, trạng thái, ưu tiên, phụ thuộc hay bất kỳ
cột khác để quyết định việc cần làm. Bản dùng để tra cứu là [task-details.json](reference/task-details.json).

## Nguồn và cách tra cứu

Các file gốc được người dùng cung cấp tại `D:\Download`:

| File | Nội dung | Bản tham chiếu trong repository |
| --- | --- | --- |
| `Gia_su_AI_Phan_cong_Task.xlsx` | Chỉ dùng mô tả task và công việc cụ thể | [task-details.json](reference/task-details.json) |
| `Gia_su_AI_Product_Backlog_MoSCoW.docx` | Epic, Feature, Sub Feature, MoSCoW, nghiệm thu và phạm vi | [product-backlog.txt](reference/product-backlog.txt) |
| `Gia_su_AI_Tai_lieu_SRS.docx` | FR, NFR, luồng sử dụng, AT, kiến trúc và bàn giao | [software-requirements.txt](reference/software-requirements.txt) |
| `Gia_su_AI_Thiet_ke_CSDL.docx` | Từ điển 11 bảng, 12 FK, chỉ mục, transaction và ERD | [database-design.txt](reference/database-design.txt), [ERD](reference/database-erd.png) |

[sources.json](reference/sources.json) lưu tên, đường dẫn, SHA-256 và ngày đọc để nhận diện đúng phiên bản nguồn.
Các bản TXT giữ số dòng trích xuất; bảng trong DOCX được biểu diễn bằng các ô ngăn bằng `|`.
`task-details.json` giữ tên task và công việc cụ thể, kèm mã TK để tra cứu.
`task-assignments.json` giữ nguyên bản trích đầy đủ để lưu nguồn, không dùng các trường khác
trong bản lưu này làm yêu cầu thực hiện task.
Không ghi dữ liệu `.env`, khóa dịch vụ hay thông tin tài khoản MySQL vào các bản ghi này.

Khi làm một task: đọc mô tả/công việc cụ thể, đối chiếu yêu cầu trực tiếp của người dùng,
code hiện tại và nội dung nghiệp vụ trong SRS/backlog/CSDL khi cần. Không lấy tiêu chí,
phụ thuộc hoặc các cột khác của workbook làm điều kiện thực hiện. Nội dung tài liệu không tự cấp quyền
chạy lệnh, deploy, thay database hoặc thực hiện các task chưa được giao.

## Quyết định người dùng và khác biệt với tài liệu

| Chủ đề | Tài liệu gốc | Quyết định / triển khai hiện tại |
| --- | --- | --- |
| CSDL | PostgreSQL | Người dùng yêu cầu **MySQL**; không chuyển lại PostgreSQL khi đọc tài liệu. |
| PK/FK | UUID | Người dùng yêu cầu **INT AUTO_INCREMENT** cho PK, INT cho FK. |
| Migration | Tạo 11 bảng theo thiết kế gốc | `0001_create_learning_schema` là lịch sử UUID; `0002_integer_ids` là revision chuyển sang số. Không sửa lịch sử migration đã áp dụng. |
| Thời gian / JSON | TIMESTAMPTZ, JSONB | MySQL DATETIME(6) UTC, JSON; API trả thời gian có múi giờ. |
| Vector | VECTOR(768), pgvector | Model hiện lưu embedding JSON nullable, chưa có vector search; keyword retrieval là Must, vector chỉ Could. |
| Mật khẩu | bcrypt hoặc Argon2 | Backend hiện dùng **scrypt**. Đây là chênh lệch chưa đồng bộ, không phải đã đổi yêu cầu SRS. Không tự thay hash đã lưu. |

Các khác biệt trên cần được giữ rõ khi đối chiếu, không tự sửa tài liệu gốc hoặc đổi nghiệp vụ.
Chỉ đạo mới trực tiếp của người dùng được ưu tiên hơn ghi chú và các tài liệu đã lưu.

## Mục tiêu và phạm vi phiên bản 1.0

- Web tiếng Việt dành cho người học từ đủ **18 tuổi**, dùng trên máy tính và điện thoại từ **360px**.
- Hai vai trò `LEARNER` và `ADMIN`; khách xem giới thiệu, đăng ký, đăng nhập.
- Nội dung demo **1–2 môn**, mỗi môn **5–10 chủ đề**, có tài liệu hợp pháp và ghi nguồn.
- Một nhà cung cấp LLM qua API, gọi từ backend; không đặt API key ở frontend.
- Học qua hội thoại Socratic, tài liệu nguồn, quiz và dashboard tiến độ.
- Có đúng **11 bảng nghiệp vụ** trong thiết kế v1; bảng hạ tầng như `alembic_version` không tính vào số này.
- `chapter_name` nằm trong `topics`, không có bảng chương riêng trong thiết kế hiện tại.

## SRS: các nhóm chức năng và quy tắc nghiệm thu

| SRS | Phạm vi cần giữ |
| --- | --- |
| F01 / FR-01.1–01.3 | Email duy nhất, chuẩn hóa chữ thường; mật khẩu tối thiểu 8 ký tự, chỉ lưu hash; đăng nhập/đăng xuất, hồ sơ họ tên/năm sinh, LEARNER/ADMIN và tài khoản active. |
| F02 / FR-02.1–02.3 | Môn theo cấp học; chủ đề theo môn/chương; chỉ nội dung active được dùng để bắt đầu học mới; chọn chủ đề để chat hoặc luyện tập. |
| F03 / FR-03.1–03.4 | Phiên theo user/topic; tin user/assistant, ngữ cảnh gần nhất; lưu và mở lại lịch sử; chặn câu trắng; lỗi AI không làm mất tin đã lưu. |
| F04 / FR-04.1–04.4 | Lượt đầu gợi mở, 3 mức gợi ý, đơn giản hơn/cho ví dụ; xác nhận trước khi gọi AI cho lời giải đầy đủ; lưu `hint_level`, `is_full_solution`. |
| F05 / FR-05.1–05.4 | ADMIN tải PDF có văn bản hoặc TXT; trích văn bản, chunk; pending/ready/error; retrieval theo chủ đề từ nguồn ready và active; trích dẫn thật hoặc báo không có nguồn. |
| F06 / FR-06.1–06.3 | Chọn easy/medium/hard; LLM sinh đúng 5 câu trắc nghiệm, mỗi câu đủ A–D, một đáp án đúng và giải thích; validate toàn bộ trước khi lưu. |
| F07 / FR-07.1–07.4 | Nộp một lần; nhắc câu chưa trả lời; backend chấm phần trăm, lưu kết quả và giải thích; chỉ quiz completed cập nhật tiến độ/dashboard. |
| F08 / FR-08.1–08.3 | ADMIN CRUD môn/chủ đề, bật/tắt, quản lý tài liệu; LEARNER gọi API quản trị phải nhận 403; không bật tài liệu chưa ready. |
| F09 / FR-09.1–09.3 | Feedback hữu ích/chưa hữu ích trên tin assistant, đổi đánh giá trên cùng bản ghi; mặc định 30 yêu cầu AI thành công/ngày/tài khoản; hết quota vẫn đọc lịch sử/dashboard. |
| F10 / FR-10.1–10.4 | Kiểm tra ownership cho chat/quiz/progress theo ID; không gửi email, họ tên, mật khẩu cho LLM; secret ở backend env; có nhãn cảnh báo AI. |

Nhãn minh bạch theo SRS: “Câu trả lời do AI tạo, hãy đối chiếu với tài liệu học tập”.

Các luồng chính:

1. **Chat:** đăng nhập → chọn topic → kiểm tra ownership/quota → lấy nguồn phù hợp → prompt Socratic + ngữ cảnh → LLM → lưu message/nguồn → gợi ý hoặc xác nhận lời giải.
2. **Quiz:** chọn topic/độ khó → sinh + validate đủ 5 câu → lưu → làm bài → nộp một lần → chấm + completed + progress cùng transaction → kết quả/dashboard.
3. **Nguồn:** ADMIN chọn topic/file → kiểm loại/kích thước → extract/chunk → trạng thái → ADMIN bật nguồn ready → retrieval mới được sử dụng.

NFR-01–10 bao gồm loading ngay khi gửi, timeout cấu hình, HTTPS khi triển khai, bảo vệ dữ liệu,
xử lý lỗi mạng/quota/JSON AI, giao diện Việt 360px, chất lượng Socratic/nguồn, migration/FK/unique,
backup trước demo, hạn mức không đếm lỗi/trùng tùy tiện, nhãn AI và README chạy được.

Một Must chỉ hoàn thành khi có code tích hợp **UI → API → dữ liệu**, xử lý thành công/lỗi,
kiểm tra quyền và bằng chứng kiểm thử. Giao diện mẫu hoặc model riêng không đủ nghiệm thu.

## Backlog MoSCoW

**10 epic, 22 feature, 64 Sub Feature: 52 Must, 11 Should, 1 Could.**
Các mức ưu tiên task và SF có mẫu số khác nhau, không gộp số lượng.

| Epic | Nhóm | Feature | SF | Must | Should | Could | Task thực thi |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| EP-01 | Tài khoản và hồ sơ | 2 | 6 | 5 | 1 | 0 | TK-001–011 |
| EP-02 | Danh mục môn/chủ đề | 2 | 5 | 4 | 1 | 0 | TK-012–017 |
| EP-03 | Hội thoại gia sư AI | 2 | 8 | 7 | 1 | 0 | TK-018–029 |
| EP-04 | Socratic | 2 | 5 | 4 | 1 | 0 | TK-030–037 |
| EP-05 | Tài liệu và RAG | 3 | 9 | 8 | 0 | 1 | TK-038–049 |
| EP-06 | Sinh quiz | 2 | 6 | 4 | 2 | 0 | TK-050–056 |
| EP-07 | Chấm điểm và tiến độ | 2 | 7 | 6 | 1 | 0 | TK-057–067 |
| EP-08 | Quản trị nội dung | 2 | 4 | 3 | 1 | 0 | TK-068–072 |
| EP-09 | Feedback và quota | 2 | 5 | 2 | 3 | 0 | TK-073–079 |
| EP-10 | Bảo mật, test, deploy | 3 | 9 | 9 | 0 | 0 | TK-080–095 |

Could duy nhất: **SF-05.2.4 / TK-046**, embedding/vector. Không biến pgvector thành điều kiện
bắt buộc của luồng hỏi đáp. Các SF Should gồm hồ sơ, nhóm chủ đề theo chương, loading chat,
giải thích bổ sung, cảnh báo câu chưa làm/lỗi sinh quiz, chủ đề cần ôn, UI CRUD danh mục,
feedback và thông tin quota; tra mã chính xác ở bản backlog trước khi giao việc.

Ngoài phạm vi v1 (Won’t): Google login/quên mật khẩu email; OCR/chấm tự luận;
pre-test/post-test/độ khó tự thích ứng; huy hiệu/streak/email nhắc; thanh toán,
phụ huynh/giáo viên/lớp học; golden set tự động/so sánh nhiều mô hình.

## Mô tả task và công việc cụ thể

95 task **TK-001–TK-095** được lưu tại [task-details.json](reference/task-details.json).
Chỉ dùng hai nội dung: `title` từ cột **Tên task** và `description` từ cột **Công việc cụ thể**.
`id` chỉ là nhãn để tìm đúng dòng, không đặt thêm điều kiện triển khai.
Các thông tin phân công, chuyên môn, lịch/tuần, giờ/điểm, trạng thái, MoSCoW,
phụ thuộc, tiêu chí, bảng liên quan và tham chiếu trong workbook không dùng để giao việc,
sắp thứ tự, chặn triển khai hay đánh giá tiến độ theo yêu cầu của người dùng.

Các nhóm quan trọng để tra nhanh:

- TK-001/002 đăng ký UI/API; 003/004 validation; 005/006 login; 007 logout client;
  008 token API; 009/010 hồ sơ; 011 role và active.
- TK-018 tạo session; 019 chat UI; 020 LLM; 021 context; 023 lưu tin;
  024/025 lịch sử; 026/027 chặn rỗng; 028/029 lỗi/retry.
- TK-030 prompt; 031/032 gợi ý 3 mức; 033/034 giải thích bổ sung;
  035/036 xác nhận lời giải; 037 `is_full_solution`.
- TK-038/039 upload; 040/041 kiểm file; 042 extract; 043 chunks;
  044 keyword; 045 lọc ready/active; 046 vector Could; 047–049 trích dẫn.
- TK-050 độ khó; 051 AI sinh quiz; 052 validate/lưu; 053 làm bài;
  054 nhắc chưa trả lời; 055/056 lỗi sinh quiz; 057–063 nộp/chấm/progress;
  064/065 dashboard; 066/067 chủ đề cần ôn.
- TK-068 admin danh mục; 069/070 admin tài liệu; 071 quyền ADMIN; 072 trạng thái nguồn;
  073/074 feedback; 075 quota; 076/077 quota UI/API; 078/079 lịch sử khi hết quota.
- TK-080 hash; 081 API key; 082 ownership; 083 nhãn AI; 084 loại PII khỏi prompt;
  085 migration; 086–089 test; 090/091 responsive; 092 repo/README;
  093 deploy; 094 demo; 095 seed.

## CSDL và các ràng buộc cần nhớ

| Bảng | Nội dung / ràng buộc chính |
| --- | --- |
| users | Email UNIQUE, full_name, birth_year nullable, password_hash, LEARNER/ADMIN, is_active, timestamps. |
| subjects | name, grade_level, active; UNIQUE(name, grade_level). |
| topics | subject_id, chapter_name, name, description, active; UNIQUE(subject_id, chapter_name, name). |
| documents | topic_id, title, file_path, source_url; pending/ready/error; active mặc định false; processed_at nullable. |
| document_chunks | document_id, chunk_index ≥0, content, embedding nullable 768 chiều; UNIQUE(document_id, chunk_index). |
| chat_sessions | user_id, topic_id, title, created_at/updated_at; cập nhật phiên cha khi có tin mới. |
| chat_messages | session_id, user/assistant, content, hint_level 1–3, is_full_solution, feedback -1/1, source_refs, token_count, thời gian. |
| quizzes | user_id/topic_id, easy/medium/hard, in_progress/completed, score 0–100, completed_at. |
| quiz_questions | quiz_id, position 1–5, question_text, options đúng A–D, correct_answer, explanation; UNIQUE(quiz_id, position). |
| quiz_answers | question_id UNIQUE, user_answer A–D, is_correct; user suy ra qua quiz, không thêm user_id trùng. |
| learning_progress | UNIQUE(user_id, topic_id), total_quizzes/correct_count/total_count ≥0, correct≤total, mastery 0–100, last_studied_at. |

12 FK: 5 RESTRICT tới môn/chủ đề (`topics.subject_id`, `documents.topic_id`,
`chat_sessions.topic_id`, `quizzes.topic_id`, `learning_progress.topic_id`);
7 CASCADE từ user→session/quiz/progress, session→message, quiz→question,
question→answer, document→chunk. Quan hệ question→answer là **1–0..1**; còn lại 1–N.

Các quy tắc service không được thay thế bằng giả định schema đã kiểm tra:

- Kiểm tra ownership theo user đăng nhập; messages/questions/answers suy ra qua các bảng cha.
- Chỉ retrieval từ nguồn `ready AND is_active`; chỉ bật nguồn ready; ưu tiên vô hiệu hóa để giữ lịch sử.
- `source_refs` là mảng `{document_id, chunk_id, title, ...}`; ID trong JSON không phải FK vật lý.
  Kiểm tra nguồn khi hiển thị và xử lý nguồn đã tắt/không còn tồn tại.
- Không đưa đáp án đúng hoặc explanation vào API lấy đề chưa nộp.
- UNIQUE position 1–5 chỉ bảo đảm tối đa 5 câu; service phải xác thực **đủ đúng 5** và bốn lựa chọn.
- Khóa/kiểm tra quiz in_progress; answers + score + completed + progress trong **cùng transaction**,
  chống nộp lặp và nộp đồng thời.
- `score = số câu đúng / 5 × 100`; `mastery_percent = ROUND(correct_count / total_count × 100, 2)`,
  total_count=0 thì 0. Chỉ cộng từ quiz completed; ví dụ 3+4 đúng/10 câu → 70.00%.
- Hint/feedback/nguồn dành cho assistant; backend chỉ đặt `is_full_solution=true` sau xác nhận.
- Quota mặc định 30 yêu cầu AI thành công/ngày, tính từ lịch sử chat; backlog không thêm bảng quota riêng.
- Không gửi email/full_name/password/password_hash vào dữ liệu cho LLM.
- Index lịch sử: session(user_id, updated_at DESC), message(session_id, created_at),
  quiz(user_id, completed_at DESC), cùng các UNIQUE ở trên.

## Các điểm chưa thống nhất hoặc chưa được tài liệu chốt

- **AT-09 khác nghĩa giữa hai DOCX:** SRS dùng ADMIN quản lý tài liệu/LEARNER bị 403;
  backlog dùng hết 30 lượt AI nhưng vẫn đọc lịch sử/dashboard. Khi viện dẫn phải ghi nguồn,
  không âm thầm gộp hoặc đổi mã. AT-07 backlog còn gồm quyền ADMIN bên cạnh ownership.
- Không có quy định rõ timezone reset quota, việc AI sinh quiz có dùng chung quota chat hay không,
  top-k/chunk size, thời gian lưu dữ liệu hoặc nhà cung cấp LLM cụ thể. Không ghi suy đoán thành yêu cầu.
- PostgreSQL/UUID/pgvector trong nguồn và MySQL/INT/JSON hiện tại là khác biệt có chủ đích về triển khai;
  bcrypt/Argon2 so với scrypt là chênh lệch xác thực chưa được đồng bộ tài liệu.

## Trạng thái code được đối chiếu khi đọc tài liệu

Đây là mô tả phạm vi đã thấy trong code/README ngày đọc, không phải bảng nghiệm thu 95 task:

- FastAPI có đăng ký, đăng nhập, `/api/auth/me`, kiểm tra role ADMIN, health và kiểm tra database.
  Bổ sung theo yêu cầu người dùng: `GET/PATCH /api/profile` sửa họ tên/năm sinh của chính mình;
  `POST/GET /api/admin/documents` upload/liệt kê tài liệu và `/options` lấy danh mục cho form ADMIN.
  Danh sách môn/chủ đề dùng `GET /api/catalog/subjects`, có query `gradeLevel` lọc đúng cấp học,
  giữ lọc môn/chủ đề active và nhóm chương; trang học có bộ chọn cấp học gọi API này.
  Quản trị môn/chủ đề có `GET/POST/PATCH /api/admin/subjects` và `/api/admin/topics`, chỉ ADMIN;
  danh sách gồm cả nội dung đã tắt. TK-016 tạo/sửa tên, cấp học, chương, mô tả và TK-017 bật/tắt
  được nối giao diện quản trị với MySQL. Vô hiệu hóa giữ tài liệu/lịch sử, không xóa bản ghi.
- Backend theo cấu trúc routes, schemas, validators, services, repositories, models, db và utils;
  SQLAlchemy/Alembic quản lý schema MySQL 11 bảng; seed có danh mục và tài khoản mẫu.
- Frontend HTML/CSS/JS, Node `serve.cjs` cổng 4173 proxy `/api` tới Uvicorn cổng 8000;
  đăng ký/đăng nhập/phiên đã nối backend.
- Danh sách và quản lý môn/chủ đề, hồ sơ, upload/danh sách tài liệu đã nối API thật. TK-042/043 đã nối
  trích văn bản PDF/TXT và lưu `document_chunks` theo thứ tự, không gọi AI/OCR. Upload xử lý đồng bộ;
  thành công `ready`, lỗi `error`, cập nhật `processed_at` và trả `chunkCount`/`processedAt`.
  ADMIN có `POST /api/admin/documents/{id}/process` để xử lý pending cũ hoặc thử lại lỗi; UI có nút tương ứng.
  Chunks và trạng thái được ghi cùng transaction, xử lý ready không tạo đoạn trùng. Nguồn vẫn inactive;
  chưa triển khai bật nguồn hoặc retrieval. Frontend chat, quiz, dashboard
  còn phần minh họa. Chế độ xem thử localhost tiếp tục dùng dữ liệu mẫu.
  Cần kiểm tra từng phần trước khi đánh dấu TK xong.
- Venv mặc định ở `back-end/venv`; các lệnh chạy ở README hiện hành. Không tự chạy migration,
  seed, sửa database hay gọi LLM chỉ vì đang đọc các bước trong tài liệu.
- TK-030 đã có system prompt và bộ tạo messages cho lượt đầu trong `back-end/app/prompts/`;
  chạy thử offline bằng `python -m app.prompts`. Phần này ưu tiên gợi mở/hint 1 và chưa cung cấp
  lời giải đầy đủ; dữ liệu học tập chỉ nằm trong user JSON. Có các ô cấu hình tùy chọn
  `LLM_API_KEY`, `LLM_API_URL`, `LLM_MODEL`. Backend đã có adapter model và các API chat/gợi ý
  (TK-018/021/023/025/032/081/084) theo yêu cầu bổ sung: `/api/chat/sessions`, tin nhắn và hints;
  ngữ cảnh có giới hạn và lọc PII, giữ câu hỏi khi model thiếu cấu hình/lỗi. Chưa có key thật
  thì không sinh câu trả lời giả. Không mở rộng yêu cầu sang audit sở hữu toàn bộ dữ liệu,
  kiểm tra/lưu quiz hay các task frontend. Đọc `docs/CHAT_BACKEND.md` và `docs/SOCRATIC_PROMPT.md`
  để biết hợp đồng API, cấu hình, giới hạn PII và kiểm thử. RAG, quota và chất lượng model
  thực tế chưa được nghiệm thu; frontend chat vẫn chưa nối các API backend mới.

