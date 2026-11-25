import { el, button, heading, notice, confirmDialog, link } from '../components/ui.js';
import { topics } from '../data.js';
import { getSession } from '../session.js';
import { renderLiveChat } from './chat-live.js';
import { createChatQuestionField } from '../components/chat-question-field.js';
import { chatSidebar } from '../components/chat-sidebar.js';
import { thinkingStatus } from '../components/motion.js';
export { validateChatQuestion } from '../chat-question.js';

function renderPreviewChat() {
 const selectedId = new URLSearchParams(location.hash.split('?')[1]).get('topic');
 const topic = topics.find(item => item.id === selectedId) || topics[0];
 const messages = el('div', { className: 'messages', 'aria-live': 'polite', 'aria-label': 'Nội dung hội thoại minh họa' });
 let hintLevel = 0;
 const add = (text, role = 'assistant') => {
  const message = el('div', { className: `message ${role} msg-enter` }, el('p', { className: 'message-meta' }, role === 'user' ? 'Bạn' : 'Gia sư AI'), el('p', {}, text));
  messages.append(message);
  message.scrollIntoView({ block: 'nearest' });
  return message;
 };
 const preview = () => {
  messages.replaceChildren();
  add('Ví dụ minh hoạ: Mình sẽ gợi ý từng bước để bạn tự giải nhé.');
  add('Làm sao tìm nghiệm của ax² + bx + c = 0?', 'user');
 };
 preview();
 const sidebar = chatSidebar('Lịch sử phiên minh họa',
  el('h2', {}, 'Lịch sử phiên'),
  button('+ Phiên mới', () => {
   messages.replaceChildren(el('div', { className: 'empty-state' }, 'Phiên mới. Bạn có thể thử nhập một câu hỏi.'));
   hintLevel = 0;
  }),
  el('div', { className: 'session-list' }, ...topics.map(item => button(item.name, () => {
   location.hash = `chat?topic=${item.id}`;
  }, `session-button ${item.id === topic.id ? 'active' : ''}`))));
 const hints = [
  'Ví dụ phương trình bậc hai — gợi ý mức 1: Bạn nhớ công thức tính biệt thức Δ như thế nào?',
  'Ví dụ phương trình bậc hai — gợi ý mức 2: Tính Δ = b² − 4ac, sau đó xét dấu của Δ.',
  'Ví dụ phương trình bậc hai — gợi ý mức 3: Khi Δ ≥ 0, áp dụng x = (−b ± √Δ) / (2a), với a khác 0.',
 ];
 const hint = button('Gợi ý tiếp (1/3)', () => {
  add(hints[hintLevel]);
  hintLevel++;
  hint.textContent = hintLevel >= 3 ? 'Đã xem 3 mức gợi ý' : `Gợi ý tiếp (${hintLevel + 1}/3)`;
  hint.disabled = hintLevel >= 3;
 });
 const solution = button('Xem lời giải', async () => {
  if (await confirmDialog('Xem lời giải đầy đủ?', 'Thử tự giải thêm một bước trước khi đối chiếu. Nội dung dưới đây là ví dụ minh hoạ.', 'Xem lời giải')) {
   const message = add('Lời giải đầy đủ — minh hoạ: Với x² − 5x + 6 = 0, Δ = 25 − 24 = 1. Hai nghiệm là (5 ± 1)/2, tức x = 2 hoặc x = 3.');
   message.setAttribute('aria-label', 'Lời giải đầy đủ');
  }
 }, 'ghost');
 const feedback = el('div', { className: 'message-actions' }, ...['Hữu ích', 'Chưa hữu ích'].map(label => {
  const control = button(label, () => {
   feedback.querySelectorAll('button').forEach(node => node.setAttribute('aria-pressed', String(node === control)));
  }, 'ghost small');
  control.setAttribute('aria-pressed', 'false');
  return control;
 }));
 const { field, input, readQuestion, bindEnter } = createChatQuestionField();
 const send = el('button', { className: 'button primary', type: 'submit' }, 'Gửi câu hỏi');
 const statusArea = el('div', { role: 'status' });
 const mode = el('select', { className: 'select', 'aria-label': 'Xem trạng thái giao diện' },
  el('option', { value: 'normal' }, 'Sẵn sàng'), el('option', { value: 'loading' }, 'Đang phản hồi'),
  el('option', { value: 'error' }, 'Lỗi kết nối'), el('option', { value: 'quota' }, 'Hết hạn mức'));
 const resetStatus = () => { mode.value = 'normal'; mode.dispatchEvent(new Event('change')); };
 mode.addEventListener('change', () => {
  statusArea.replaceChildren();
  input.disabled = send.disabled = mode.value === 'loading' || mode.value === 'quota';
  if (mode.value === 'loading') statusArea.append(thinkingStatus('Đang chuẩn bị phản hồi… Bạn có thể tiếp tục xem lịch sử.'));
  if (mode.value === 'error') statusArea.append(notice('Chưa thể kết nối gia sư. Nội dung đã nhập vẫn được giữ lại.', 'error'), button('Thử lại', resetStatus, 'secondary small'));
  if (mode.value === 'quota') statusArea.append(notice('Bạn đã dùng hết 30 lượt yêu cầu hôm nay. Bạn vẫn có thể xem lịch sử học tập.', 'warning'));
 });
 const form = el('form', { className: 'chat-composer', novalidate: true }, statusArea,
  el('div', { className: 'composer-row' }, field, send),
  el('p', { className: 'chat-footer' }, 'Câu trả lời do AI tạo, hãy đối chiếu với tài liệu học tập.'),
  el('details', { className: 'state-picker' }, el('summary', {}, 'Xem trước trạng thái giao diện'), mode));
 form.addEventListener('submit', event => {
  event.preventDefault();
  const question = readQuestion();
  if (question === null) return;
  statusArea.replaceChildren();
  add(question, 'user');
  input.value = '';
  input.focus();
 });
 bindEnter(form, send);
 const sources = el('details', {}, el('summary', {}, 'Nguồn tham khảo minh hoạ'),
  el('p', { className: 'helper' }, 'Ví dụ cách hiển thị: Tài liệu Đại số · phần Phương trình bậc hai. Chưa có tài liệu thực được truy xuất.'));
 return el('div', { className: 'chat-view' },
  heading('Hỏi gia sư AI', 'Gợi mở từng bước, hiểu bài bằng chính cách nghĩ của bạn.'),
  notice('Dữ liệu minh họa — chưa kết nối tài khoản thật.', 'warning'),
  el('div', { className: 'chat-layout' }, sidebar,
   el('section', { className: 'chat-main' },
    el('div', { className: 'chat-header' }, el('h2', {}, topic.name),
     el('div', { className: 'message-actions' }, hint, solution,
      button('Cho ví dụ', () => add('Ví dụ minh hoạ: x² − 5x + 6 = 0 có thể viết thành (x − 2)(x − 3) = 0.'), 'ghost small'),
      button('Giải thích đơn giản', () => add('Ví dụ đơn giản: phân tích x² − 5x + 6 thành (x − 2)(x − 3). Một tích bằng 0 khi ít nhất một thừa số bằng 0.'), 'ghost small')), sources),
    messages, el('div', { className: 'chat-header' }, feedback), form)));
}


export function renderChat() {
 return getSession().reason === 'preview' ? renderPreviewChat() : renderLiveChat();
}
