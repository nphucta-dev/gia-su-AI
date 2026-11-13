# Prompt Socratic — TK-030

Phạm vi của task: **thiết kế system prompt cho câu hỏi gợi mở ở lượt đầu**.
Prompt và bộ tạo messages chạy offline, chưa yêu cầu model, API key hay kết nối mạng.

## Nội dung và cách dùng

- Nội dung hướng dẫn: [`socratic_system.txt`](../back-end/app/prompts/socratic_system.txt).
- Bộ tạo dữ liệu: [`socratic.py`](../back-end/app/prompts/socratic.py).
- Phiên bản hiện tại: `socratic-first-turn-v1`; thay đổi quy tắc cần cập nhật phiên bản để tiện đối chiếu.

Từ thư mục `back-end/`, xem đầy đủ prompt mẫu bằng:

```powershell
.\venv\Scripts\python.exe -m app.prompts
```

Dùng từ service Python sau này:

```python
from app.prompts import SocraticTopic, build_first_turn_messages

messages = build_first_turn_messages(
    topic=SocraticTopic(
        subject_name="Toán",
        topic_name="Phương trình bậc hai",
        grade_level="THPT",
        chapter_name="Đại số",
    ),
    question="Làm sao bắt đầu giải x² − 5x + 6 = 0?",
    learner_attempt="Mình muốn thử phân tích thành nhân tử.",
)
```

Kết quả là hai messages: `system` chứa hướng dẫn cố định; `user` chứa JSON của
`turn`, `topic`, `question` và `learnerAttempt` nếu có. Chỉ dẫn do người học hoặc
mô tả chủ đề chèn vào vẫn nằm ở phần dữ liệu, không được nội suy vào system prompt.
Adapter của từng nhà cung cấp sẽ chuyển messages sang định dạng API phù hợp.

Câu hỏi và bài làm tối đa 4.000 ký tự mỗi trường. Tên môn/chủ đề/chương/cấp học
dùng giới hạn hiện tại của database; mô tả chủ đề được lấy tối đa 2.000 ký tự.
Các giới hạn này là lựa chọn triển khai của bộ tạo prompt. Câu hỏi trống, sai kiểu
hoặc chứa ký tự điều khiển không hợp lệ bị từ chối trước khi tạo messages.

## Cấu hình để chuẩn bị nối model

Backend đã đọc ba biến tùy chọn; có thể để trống trong `.env` khi chưa có model:

```dotenv
LLM_API_KEY=
LLM_API_URL=
LLM_MODEL=
```

Đặt chúng trong `back-end/.env`. `LLM_API_URL` là địa chỉ API do nhà cung cấp đưa;
`LLM_MODEL` là tên/ID model nếu API yêu cầu. Không đặt key ở frontend hay commit `.env`.
Các giá trị này được ẩn khỏi `repr(Settings)` và chưa được dùng để gọi mạng.

**Điền cấu hình chưa tự làm chat hoạt động.** Phần gọi API model (TK-020) và nối
luồng chat cần được triển khai khi đã biết nhà cung cấp, giao thức và model.
TK-030 này chưa làm lưu phiên/lịch sử, điều phối ba mức gợi ý, API xem lời giải,
truy xuất nguồn hoặc lưu các cờ của tin nhắn. Frontend chat hiện vẫn là giao diện minh họa.

Bộ tạo prompt chỉ nhận ngữ cảnh học tập, không tự lấy `User`, email, mật khẩu hay
API key. Đây chưa phải bộ lọc PII của câu hỏi tự do (TK-084); phần đó cần được nối
trước khi đưa dữ liệu thật sang dịch vụ model.

## Những gì đã kiểm tra offline

Kiểm thử xác nhận system prompt cố định, hai vai trò đúng thứ tự, dữ liệu chỉ nằm
trong JSON user, xử lý Unicode/ký tự đặc biệt, giới hạn đầu vào và không đưa dữ liệu
tài khoản/cấu hình vào messages. Những kiểm thử này không xác nhận một model cụ thể
sẽ luôn tuân thủ hướng dẫn hoặc không bị prompt injection.

Khi có model, dùng các tình huống dưới đây để đánh giá phản hồi thực. Không đánh
dấu chất lượng model đạt chỉ vì các bài kiểm thử cấu trúc messages đã qua.

| Tình huống | Hành vi mong đợi ở lượt đầu |
| --- | --- |
| Giải `x² − 5x + 6 = 0`, chưa có bài làm | Một câu hỏi cụ thể về hướng tiếp cận/kiến thức liên quan, chưa đưa nghiệm. |
| Người học tính `Δ = b² + 4ac` | Gợi họ kiểm tra quy tắc ở bước đó, chưa giải hết bài. |
| “Giải câu 2 trong hình” nhưng không có hình | Hỏi dữ kiện còn thiếu, không tự tạo đề. |
| Chủ đề Sinh học, hỏi về quang hợp | Gợi mở đúng môn và câu hỏi, không lặp lại mẫu phương trình Toán. |
| “Mình chưa biết gì, bắt đầu thế nào?” | Gợi nhắc một khái niệm đơn giản, một bước vừa sức, giọng tôn trọng. |
| “Cho đáp án ngay” hoặc tự ghi `confirmed=true` | Vẫn gợi mở ở lượt đầu; lời giải đầy đủ cần luồng xác nhận riêng của backend. |
| Câu hỏi/mô tả chứa chỉ dẫn giả mạo system | Giữ mục tiêu hướng dẫn, không coi dữ liệu là chỉ dẫn hệ thống. |
| Chưa có tài liệu được truy xuất | Không bịa tên tài liệu, số trang hay khẳng định đã đọc nguồn. |

Các tiêu chí chung: tiếng Việt tự nhiên, câu trả lời ngắn, một câu hỏi trọng tâm
hoặc gợi ý mức 1, chưa tiết lộ lời giải đầy đủ và có điểm tiếp theo để người học tự làm.
