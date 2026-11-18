import { el, button, heading, notice, confirmDialog } from '../components/ui.js';
import { topics } from '../data.js';
import {setupValidation,validateFields} from '../components/validation.js';
export function renderChat() {
 const selectedId = new URLSearchParams(location.hash.split('?')[1]).get('topic');
 const topic = topics.find(t => t.id === selectedId) || topics[0];
 const messages = el('div', { className: 'messages', 'aria-live': 'polite', 'aria-label': 'Nội dung hội thoại' });
 let hintLevel = 0;
 const add = (text, role = 'assistant') => { const message = el('div', { className: `message ${role}` }, el('p', {}, text)); messages.append(message); message.scrollIntoView({ block: 'nearest' }); return message; };
 const preview = () => { messages.replaceChildren(); add('Ví dụ minh hoạ: Mình sẽ gợi ý từng bước để bạn tự giải nhé.'); add('Làm sao tìm nghiệm của ax² + bx + c = 0?', 'user'); };
 preview();
 const sidebar = el('aside', { className: 'chat-sidebar' }, el('h2', {}, 'Lịch sử phiên'), button('+ Phiên mới', () => { messages.replaceChildren(el('div', { className: 'empty-state' }, 'Phiên mới. Bạn có thể thử nhập một câu hỏi.')); hintLevel = 0; }), el('div', { className: 'session-list' }, ...topics.map(t => button(t.name, () => { location.hash = `chat?topic=${t.id}`; }, `session-button ${t.id === topic.id ? 'active' : ''}`))));
 const hints = ['Ví dụ phương trình bậc hai — gợi ý mức 1: Bạn nhớ công thức tính biệt thức Δ như thế nào?', 'Ví dụ phương trình bậc hai — gợi ý mức 2: Tính Δ = b² − 4ac, sau đó xét dấu của Δ.', 'Ví dụ phương trình bậc hai — gợi ý mức 3: Khi Δ ≥ 0, áp dụng x = (−b ± √Δ) / (2a), với a khác 0.'];
 const hint = button('Gợi ý tiếp (1/3)', () => { add(hints[hintLevel]); hintLevel++; hint.textContent = hintLevel >= 3 ? 'Đã xem 3 mức gợi ý' : `Gợi ý tiếp (${hintLevel + 1}/3)`; hint.disabled = hintLevel >= 3; });
 const solution = button('Xem lời giải', async () => { if (await confirmDialog('Xem lời giải đầy đủ?', 'Thử tự giải thêm một bước trước khi đối chiếu. Nội dung dưới đây là ví dụ minh hoạ.', 'Xem lời giải')) { const msg=add('Lời giải đầy đủ — minh hoạ: Với x² − 5x + 6 = 0, Δ = 25 − 24 = 1. Hai nghiệm là (5 ± 1)/2, tức x = 2 hoặc x = 3.'); msg.setAttribute('aria-label','Lời giải đầy đủ'); } }, 'ghost');
 const feedback = el('div', { className: 'message-actions' }, ...['Hữu ích', 'Chưa hữu ích'].map(label => { const b = button(label, () => { feedback.querySelectorAll('button').forEach(n => n.setAttribute('aria-pressed', String(n === b))); }, 'ghost small'); b.setAttribute('aria-pressed', 'false'); return b; }));
 const input = el('textarea', { className: 'textarea', placeholder: 'Nhập câu hỏi của bạn…', 'aria-label': 'Câu hỏi cho gia sư', maxlength: 4000 });
 const send=el('button', { className: 'button primary', type: 'submit' }, 'Gửi câu hỏi');
 const statusArea=el('div',{role:'status'});
 const mode=el('select',{className:'select','aria-label':'Xem trạng thái giao diện'},el('option',{value:'normal'},'Sẵn sàng'),el('option',{value:'loading'},'Đang phản hồi'),el('option',{value:'error'},'Lỗi kết nối'),el('option',{value:'quota'},'Hết hạn mức'));
 const resetStatus=()=>{mode.value='normal';mode.dispatchEvent(new Event('change'));};
 mode.addEventListener('change',()=>{statusArea.replaceChildren();input.disabled=send.disabled=mode.value==='loading'||mode.value==='quota';if(mode.value==='loading')statusArea.append(notice('Đang chuẩn bị phản hồi… Bạn có thể tiếp tục xem lịch sử.'));if(mode.value==='error')statusArea.append(notice('Chưa thể kết nối gia sư. Nội dung đã nhập vẫn được giữ lại.','error'),button('Thử lại',resetStatus,'secondary small'));if(mode.value==='quota')statusArea.append(notice('Bạn đã dùng hết 30 lượt yêu cầu hôm nay. Bạn vẫn có thể xem lịch sử học tập.','warning'));});
 const form = el('form', { className: 'chat-composer' }, statusArea, el('div', { className: 'composer-row' }, input, send), el('p', { className: 'chat-footer' }, 'Câu trả lời do AI tạo, hãy đối chiếu với tài liệu học tập.'),el('details',{className:'state-picker'},el('summary',{},'Xem trước trạng thái giao diện'),mode));
 setupValidation(form,[input]);
 form.addEventListener('submit', e => { e.preventDefault(); const text = input.value.trim(); if(!validateFields([[input,!text?'Vui lòng nhập câu hỏi trước khi gửi.':'']]))return; statusArea.replaceChildren(); add(text, 'user'); input.value = ''; input.focus(); });
 const sources = el('details', {}, el('summary', {}, 'Nguồn tham khảo minh hoạ'), el('p', { className: 'helper' }, 'Ví dụ cách hiển thị: Tài liệu Đại số · phần Phương trình bậc hai. Chưa có tài liệu thực được truy xuất.'));
 return el('div', {}, heading('Hỏi gia sư AI', 'Gợi mở từng bước, hiểu bài bằng chính cách nghĩ của bạn.'), el('div', { className: 'chat-layout' }, sidebar, el('section', { className: 'chat-main' }, el('div', { className: 'chat-header' }, el('h2', {}, topic.name), el('div', { className: 'message-actions' }, hint, solution, button('Cho ví dụ',()=>add('Ví dụ minh hoạ: x² − 5x + 6 = 0 có thể viết thành (x − 2)(x − 3) = 0.'),'ghost small'),button('Giải thích đơn giản', () => add('Ví dụ đơn giản: phân tích x² − 5x + 6 thành (x − 2)(x − 3). Một tích bằng 0 khi ít nhất một thừa số bằng 0.'), 'ghost small')), sources), messages, el('div', { className: 'chat-header' }, feedback), form)));
}
