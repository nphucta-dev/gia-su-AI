import { api, ApiError } from '../api.js';
import { el, button } from './ui.js';

const validFeedback = value => value === null || value === 1 || value === -1;

// One store per mounted chat. Reuse the same controls during message redraws.
export function createMessageFeedback({ signal, isCurrent }) {
 const states = new Map();
 return function renderFeedback(message, sessionId) {
  const key = `${sessionId}:${message.id}`;
  const existing = states.get(key);
  if (existing) { existing.message = message; message.feedback = existing.confirmed; return existing.root; }
  const state = { message, confirmed: validFeedback(message.feedback) ? message.feedback : null, pending: false, error: '', blocked: false, desired: null, success: '' };
  const status = el('div', { className: 'message-feedback-status', role: 'status', 'aria-live': 'polite' });
  const choices = [[1, 'Hữu ích'], [-1, 'Chưa hữu ích']].map(([value, label]) => {
   const control = button(label, () => save(state.confirmed === value ? null : value), 'ghost small');
   control.setAttribute('aria-label', label);
   control.dataset.value = value;
   return control;
  });
  const retry = button('Thử lại', () => save(state.desired), 'secondary small');
  const root = el('div', { className: 'message-feedback', role: 'group', 'aria-label': `Đánh giá phản hồi AI ${message.id}` },
   el('div', { className: 'message-actions' }, choices), status);
  Object.assign(state, { root });
  states.set(key, state);

  function draw() {
   root.setAttribute('aria-busy', String(state.pending));
   for (const control of choices) {
    const selected = Number(control.dataset.value) === state.confirmed;
    control.setAttribute('aria-pressed', String(selected));
    control.textContent = `${selected ? 'Đã chọn: ' : ''}${Number(control.dataset.value) === 1 ? 'Hữu ích' : 'Chưa hữu ích'}`;
    control.disabled = state.pending || state.blocked;
   }
   retry.disabled = state.pending;
   status.classList.toggle('error-text', Boolean(state.error));
   const text = state.pending ? 'Đang lưu đánh giá…' : state.error || state.success;
   status.replaceChildren(...(text ? [el('span', {}, text)] : []));
   if (state.error && !state.blocked && !state.pending) status.append(retry);
  }

  async function save(value) {
   if (state.pending || state.blocked || signal.aborted || !isCurrent(sessionId) || !validFeedback(value)) return;
   const hadFocus = root.contains(document.activeElement);
   state.pending = true; state.desired = value; state.error = ''; state.success = ''; draw();
   try {
    const result = await api(`/chat/sessions/${sessionId}/messages/${message.id}/feedback`, { method: 'PATCH', body: { feedback: value }, signal });
    if (signal.aborted || !isCurrent(sessionId)) return;
    const saved = result?.message;
    if (saved?.id !== message.id || saved?.sessionId !== sessionId || saved?.role !== 'assistant'
     || !validFeedback(saved.feedback) || saved.feedback !== value) throw new ApiError('Phản hồi đánh giá chưa hợp lệ.', 0, 'INVALID_RESPONSE');
    state.confirmed = saved.feedback; state.message.feedback = saved.feedback;
    state.success = value === null ? 'Đã bỏ đánh giá.' : 'Đã lưu đánh giá.';
   } catch (error) {
    if (error.name === 'AbortError' || signal.aborted || !isCurrent(sessionId)) return;
    state.blocked = [401, 403, 404, 422].includes(error.status) || error.code === 'FEEDBACK_ASSISTANT_ONLY';
    state.error = [403, 404].includes(error.status) ? 'Không thể đánh giá phản hồi này. Hãy mở lại hội thoại.'
     : error.code === 'FEEDBACK_ASSISTANT_ONLY' ? 'Chỉ có thể đánh giá phản hồi của gia sư AI.'
      : error.status === 422 ? 'Dữ liệu đánh giá chưa hợp lệ. Hãy tải lại hội thoại.'
       : error.code === 'INVALID_RESPONSE' ? 'Máy chủ trả về đánh giá chưa hợp lệ. Lựa chọn trước đó vẫn được giữ.'
        : 'Chưa xác nhận được đánh giá trên máy chủ. Lựa chọn trước đó vẫn được giữ. Bạn có thể thử lại.';
   } finally {
    state.pending = false;
    if (!signal.aborted && isCurrent(sessionId)) {
     const restore = hadFocus && (document.activeElement === document.body || root.contains(document.activeElement));
     draw();
     if (restore) (state.error && !state.blocked ? retry : choices.find(control => Number(control.dataset.value) === state.confirmed) || choices[0]).focus({ preventScroll: true });
    }
   }
  }
  draw();
  return root;
 };
}
