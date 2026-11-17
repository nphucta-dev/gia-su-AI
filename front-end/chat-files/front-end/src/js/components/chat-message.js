import { el } from './ui.js';

// Nội dung tin nhắn luôn được dựng bằng text node: không bao giờ chèn HTML từ người dùng hay model.
// Chỉ hỗ trợ định dạng nhẹ thường gặp trong câu trả lời: **đậm**, `mã` và xuống dòng.
const INLINE = /(\*\*[^*\n]+\*\*|`[^`\n]+`)/g;

function inline(text) {
  return text.split(INLINE).filter(Boolean).map(part => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) return el('strong', {}, part.slice(2, -2));
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) return el('code', {}, part.slice(1, -1));
    return part;
  });
}

export function messageBody(content) {
  return String(content).split(/\n{2,}/).map(block => block.trim()).filter(Boolean)
    .map(block => el('p', {}, ...block.split('\n').flatMap((line, index) => (index ? [el('br'), ...inline(line)] : inline(line)))));
}

const dateFormat = new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit' });

// "Hôm nay" / "Hôm qua" / dd/mm cho danh sách phiên.
export function relativeDay(iso, now = new Date()) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const startOf = value => new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
  const days = Math.round((startOf(now) - startOf(date)) / 86400000);
  return days === 0 ? 'Hôm nay' : days === 1 ? 'Hôm qua' : dateFormat.format(date);
}

export function messageNode(message) {
  const hint = message.role === 'assistant' && message.hintLevel ? `Gợi ý mức ${message.hintLevel}/3` : '';
  return el('article', { className: `message ${message.role}`, 'data-message-id': message.id ?? false },
    hint ? el('div', { className: 'message-meta' }, hint) : null,
    ...messageBody(message.content));
}
