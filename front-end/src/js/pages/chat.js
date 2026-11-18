import { api, ApiError } from '../api.js';
import { el, button, heading, notice, confirmDialog, link } from '../components/ui.js';
import { topics } from '../data.js';
import { getSession } from '../session.js';
import { setupValidation, validateFields } from '../components/validation.js';

const SESSION_LIMIT = 20;
const MESSAGE_LIMIT = 200;
const MAX_MESSAGE_PAGES = 100;
let activeChatController;

function sessionTitle(session) {
 const title = typeof session?.title === 'string' ? session.title.trim() : '';
 const topicName = typeof session?.topicName === 'string' ? session.topicName.trim() : '';
 return title || (topicName ? `Phiên về ${topicName}` : 'Phiên chưa có câu hỏi');
}

function formatSessionTime(value) {
 const date = new Date(value);
 if (!value || Number.isNaN(date.getTime())) return { label: 'Chưa rõ thời gian', iso: '' };
 return {
  label: new Intl.DateTimeFormat('vi-VN', { dateStyle: 'medium', timeStyle: 'short' }).format(date),
  iso: date.toISOString(),
 };
}

function requestedSessionId() {
 const raw = new URLSearchParams(location.hash.split('?')[1]).get('session');
 if (raw === null) return { id: null, invalid: false };
 if (!/^[1-9]\d*$/.test(raw)) return { id: null, invalid: true };
 const id = Number(raw);
 return Number.isSafeInteger(id) && id <= 2 ** 31 - 1 ? { id, invalid: false } : { id: null, invalid: true };
}

function renderStoredMessage(message) {
 if (!message || !Number.isSafeInteger(Number(message.id)) || !['user', 'assistant'].includes(message.role) || typeof message.content !== 'string') {
  throw new ApiError('Dữ liệu tin nhắn từ máy chủ chưa hợp lệ.', 0, 'INVALID_RESPONSE');
 }
 if (message.hintLevel != null && (message.role !== 'assistant' || !Number.isInteger(message.hintLevel) || message.hintLevel < 1 || message.hintLevel > 3)) {
  throw new ApiError('Mức gợi ý từ máy chủ chưa hợp lệ.', 0, 'INVALID_RESPONSE');
 }
 const isUser = message.role === 'user';
 const sentAt = formatSessionTime(message.createdAt);
 const details = [isUser ? 'Bạn' : 'Gia sư AI', sentAt.label];
 if (!isUser && Number.isInteger(message.hintLevel)) details.push(`Gợi ý mức ${message.hintLevel}`);
 if (!isUser && message.isFullSolution) details.push('Lời giải đầy đủ');
 return el('article', {
  className: `message ${message.role}`,
  'data-hint-level': !isUser && Number.isInteger(message.hintLevel) ? message.hintLevel : null,
  'aria-label': `${isUser ? 'Tin nhắn của bạn' : 'Phản hồi của gia sư'}, ${sentAt.label}`,
 },
 el('p', { className: 'message-meta' }, details.join(' · ')),
 el('p', {}, message.content));
}

function renderPreviewChat() {
 const selectedId = new URLSearchParams(location.hash.split('?')[1]).get('topic');
 const topic = topics.find(item => item.id === selectedId) || topics[0];
 const messages = el('div', { className: 'messages', 'aria-live': 'polite', 'aria-label': 'Nội dung hội thoại minh họa' });
 let hintLevel = 0;
 const add = (text, role = 'assistant') => {
  const message = el('div', { className: `message ${role}` }, el('p', {}, text));
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
 const sidebar = el('aside', { className: 'chat-sidebar', 'aria-label': 'Lịch sử phiên minh họa' },
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
 const input = el('textarea', { className: 'textarea', placeholder: 'Nhập câu hỏi của bạn…', 'aria-label': 'Câu hỏi cho gia sư', maxlength: 4000 });
 const send = el('button', { className: 'button primary', type: 'submit' }, 'Gửi câu hỏi');
 const statusArea = el('div', { role: 'status' });
 const mode = el('select', { className: 'select', 'aria-label': 'Xem trạng thái giao diện' },
  el('option', { value: 'normal' }, 'Sẵn sàng'), el('option', { value: 'loading' }, 'Đang phản hồi'),
  el('option', { value: 'error' }, 'Lỗi kết nối'), el('option', { value: 'quota' }, 'Hết hạn mức'));
 const resetStatus = () => { mode.value = 'normal'; mode.dispatchEvent(new Event('change')); };
 mode.addEventListener('change', () => {
  statusArea.replaceChildren();
  input.disabled = send.disabled = mode.value === 'loading' || mode.value === 'quota';
  if (mode.value === 'loading') statusArea.append(notice('Đang chuẩn bị phản hồi… Bạn có thể tiếp tục xem lịch sử.'));
  if (mode.value === 'error') statusArea.append(notice('Chưa thể kết nối gia sư. Nội dung đã nhập vẫn được giữ lại.', 'error'), button('Thử lại', resetStatus, 'secondary small'));
  if (mode.value === 'quota') statusArea.append(notice('Bạn đã dùng hết 30 lượt yêu cầu hôm nay. Bạn vẫn có thể xem lịch sử học tập.', 'warning'));
 });
 const form = el('form', { className: 'chat-composer' }, statusArea,
  el('div', { className: 'composer-row' }, input, send),
  el('p', { className: 'chat-footer' }, 'Câu trả lời do AI tạo, hãy đối chiếu với tài liệu học tập.'),
  el('details', { className: 'state-picker' }, el('summary', {}, 'Xem trước trạng thái giao diện'), mode));
 setupValidation(form, [input]);
 form.addEventListener('submit', event => {
  event.preventDefault();
  const text = input.value.trim();
  if (!validateFields([[input, !text ? 'Vui lòng nhập câu hỏi trước khi gửi.' : '']])) return;
  statusArea.replaceChildren();
  add(text, 'user');
  input.value = '';
  input.focus();
 });
 const sources = el('details', {}, el('summary', {}, 'Nguồn tham khảo minh hoạ'),
  el('p', { className: 'helper' }, 'Ví dụ cách hiển thị: Tài liệu Đại số · phần Phương trình bậc hai. Chưa có tài liệu thực được truy xuất.'));
 return el('div', {},
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

function renderChatHistory() {
 activeChatController?.abort();
 const controller = new AbortController();
 activeChatController = controller;
 const request = requestedSessionId();
 let sessions = [];
 let sessionsLoaded = false;
 let nextOffset = 0;
 let hasMoreSessions = false;
 let loadingSessions = false;
 let sessionsFailed = false;
 let selectedSession = null;
 let selectedMessages = [];
 let hintPending = false;
 let solutionPending = false;
 let confirmingSolution = false;
 let hintLockedCode = '';

 const sidebarStatus = el('div', { className: 'chat-sidebar-status', role: 'status', 'aria-live': 'polite' });
 const sessionList = el('nav', { className: 'session-list', 'aria-label': 'Các phiên chat đã lưu' });
 const pagination = el('div', { className: 'session-pagination' });
 const sidebar = el('aside', { className: 'chat-sidebar', 'aria-label': 'Lịch sử phiên chat' },
  el('div', { className: 'chat-sidebar-header' }, el('h2', {}, 'Lịch sử phiên'), link('Chọn chủ đề mới', '#home', 'button ghost small')),
  sidebarStatus, sessionList, pagination);

 const chatTitle = el('h2', {}, 'Nội dung phiên chat');
 const chatDescription = el('p', { className: 'helper' }, 'Chọn một phiên trong lịch sử để xem lại nội dung đã lưu.');
 const hintButton = button('Chọn một phiên để xin gợi ý', () => requestHint(), 'secondary');
 hintButton.disabled = true;
 const solutionButton = button('Xem lời giải', () => requestSolution(), 'ghost');
 solutionButton.disabled = true;
 const hintStatus = el('div', { className: 'chat-hint-status', role: 'status', 'aria-live': 'polite' });
 const hintControls = el('div', { className: 'chat-hint-controls' }, hintButton, solutionButton, hintStatus);
 const messages = el('div', { className: 'messages chat-history-messages', 'aria-label': 'Nội dung phiên chat', 'aria-live': 'polite', 'aria-busy': 'false' },
  el('div', { className: 'empty-state' }, 'Chọn một phiên để xem lại hội thoại.'));
 const main = el('section', { className: 'chat-main' }, el('div', { className: 'chat-header chat-session-header' },
  el('div', { className: 'chat-session-copy' }, chatTitle, chatDescription), hintControls), messages);
 const root = el('div', {}, heading('Lịch sử trò chuyện', 'Mở lại những phiên học đã lưu trong tài khoản của bạn.'),
  el('div', { className: 'chat-layout chat-history-layout' }, sidebar, main));

 function isCurrent() { return !controller.signal.aborted && root.isConnected; }

 function hintState() {
  if (!selectedSession) return { disabled: true, label: 'Chọn một phiên để xin gợi ý' };
  if (hintLockedCode === 'TOPIC_CLOSED') return { disabled: true, label: 'Chủ đề đã đóng' };
  if (hintLockedCode === 'HINT_LIMIT_REACHED') return { disabled: true, label: 'Đã nhận đủ 3 mức gợi ý' };
  if (hintLockedCode === 'CHAT_QUESTION_REQUIRED') return { disabled: true, label: 'Hãy gửi câu hỏi trước' };
  let questionIndex = -1;
  for (let index = selectedMessages.length - 1; index >= 0; index--) {
   if (selectedMessages[index].role === 'user') { questionIndex = index; break; }
  }
  if (questionIndex < 0) return { disabled: true, label: 'Hãy gửi câu hỏi trước' };
  const levels = selectedMessages.slice(questionIndex + 1)
   .filter(item => item.role === 'assistant' && Number.isInteger(item.hintLevel) && item.hintLevel >= 1 && item.hintLevel <= 3)
   .map(item => item.hintLevel);
  const highest = Math.max(0, ...levels);
  if (highest >= 3) return { disabled: true, label: 'Đã nhận đủ 3 mức gợi ý', nextLevel: 4 };
  const nextLevel = highest + 1;
  return { disabled: false, nextLevel, label: nextLevel === 1 ? 'Nhận gợi ý mức 1' : `Gợi ý tiếp · Mức ${nextLevel}` };
 }

 function drawHintControl() {
  const state = hintState();
  const busy = hintPending || solutionPending || confirmingSolution;
  const hasQuestion = selectedMessages.some(item => item.role === 'user');
  hintButton.textContent = hintPending && state.nextLevel ? `Đang lấy gợi ý mức ${state.nextLevel}…` : state.label;
  hintButton.disabled = busy || state.disabled;
  hintButton.setAttribute('aria-label', hintButton.textContent);
  solutionButton.textContent = solutionPending ? 'Đang tạo lời giải…' : 'Xem lời giải';
  solutionButton.disabled = busy || !selectedSession || !hasQuestion || hintLockedCode === 'TOPIC_CLOSED' || hintLockedCode === 'CHAT_QUESTION_REQUIRED';
  solutionButton.setAttribute('aria-label', solutionButton.textContent);
  if (busy) hintControls.setAttribute('aria-busy', 'true');
  else hintControls.removeAttribute('aria-busy');
 }

 function showHintError(error, sessionId) {
  if (error instanceof ApiError && error.code === 'HINT_LIMIT_REACHED') {
   hintLockedCode = error.code;
   hintStatus.replaceChildren(notice('Bạn đã nhận đủ 3 mức gợi ý cho câu hỏi này.', 'warning'));
  } else if (error instanceof ApiError && error.code === 'CHAT_QUESTION_REQUIRED') {
   hintLockedCode = error.code;
   hintStatus.replaceChildren(notice('Hãy gửi một câu hỏi trước khi xin gợi ý.', 'warning'));
  } else if (error instanceof ApiError && error.code === 'TOPIC_CLOSED') {
   hintLockedCode = error.code;
   hintStatus.replaceChildren(notice('Chủ đề đã đóng. Bạn vẫn có thể xem lại lịch sử nhưng không thể xin gợi ý mới.', 'warning'));
  } else if (error instanceof ApiError && error.code === 'CHAT_CHANGED') {
   hintStatus.replaceChildren(notice('Phiên chat vừa thay đổi. Hãy tải lại nội dung trước khi xin gợi ý tiếp.', 'error'),
    button('Tải lại phiên', () => loadMessages(sessionId), 'secondary small'));
  } else if (error instanceof ApiError && error.status === 404) {
   showMessageError(error, sessionId);
  } else {
   const message = error instanceof ApiError && error.code === 'CHAT_BUSY'
    ? 'Phiên đang xử lý một yêu cầu khác. Vui lòng thử lại sau.'
    : (error?.message || 'Chưa thể lấy gợi ý. Vui lòng thử lại.');
   hintStatus.replaceChildren(notice(message, 'error'), button('Thử lại', () => requestHint(), 'secondary small'));
  }
  drawHintControl();
 }

 async function requestHint() {
  const state = hintState();
  const sessionId = Number(selectedSession?.id);
  if (hintPending || state.disabled || !Number.isSafeInteger(sessionId)) return;
  hintPending = true;
  hintStatus.replaceChildren(el('p', { className: 'helper' }, `Đang lấy gợi ý mức ${state.nextLevel}…`));
  drawHintControl();
  try {
   const result = await api(`/chat/sessions/${sessionId}/hints`, { method: 'POST', signal: controller.signal });
   if (!isCurrent() || requestedSessionId().id !== sessionId) return;
   const assistant = result?.assistantMessage;
   if (!result?.session || Number(result.session.id) !== sessionId || result.userMessage != null
    || !assistant || Number(assistant.sessionId) !== sessionId || assistant.role !== 'assistant'
    || !Number.isInteger(assistant.hintLevel) || assistant.hintLevel < 1 || assistant.hintLevel > 3) {
    throw new ApiError('Phản hồi gợi ý từ máy chủ chưa hợp lệ. Vui lòng thử lại.', 0, 'INVALID_RESPONSE');
   }
   const messageNode = renderStoredMessage(assistant);
   const duplicate = selectedMessages.some(item => Number(item.id) === Number(assistant.id));
   if (!duplicate) {
    selectedMessages.push(assistant);
    messages.append(messageNode);
   }
   selectedSession = result.session;
   const sessionIndex = sessions.findIndex(item => Number(item.id) === sessionId);
   if (sessionIndex >= 0) sessions[sessionIndex] = result.session;
   hintLockedCode = '';
   chatTitle.textContent = sessionTitle(result.session);
   chatDescription.textContent = [result.session.subjectName, result.session.chapterName, result.session.topicName].filter(Boolean).join(' · ') || 'Phiên chat đã lưu';
   hintStatus.replaceChildren(el('p', { className: 'helper' }, `Đã nhận gợi ý mức ${assistant.hintLevel}.`));
   drawSessions();
   requestAnimationFrame(() => { if (isCurrent()) messages.scrollTop = messages.scrollHeight; });
  } catch (error) {
   if (error.name !== 'AbortError' && isCurrent() && requestedSessionId().id === sessionId) showHintError(error, sessionId);
  } finally {
   hintPending = false;
   if (isCurrent()) drawHintControl();
  }
 }

 async function requestSolution() {
  const sessionId = Number(selectedSession?.id);
  const hasQuestion = selectedMessages.some(item => item.role === 'user');
  if (hintPending || solutionPending || confirmingSolution || !Number.isSafeInteger(sessionId) || !hasQuestion) return;
  confirmingSolution = true;
  drawHintControl();
  const confirmed = await confirmDialog(
   'Xem lời giải đầy đủ?',
   'Thử tự giải thêm một bước trước khi đối chiếu. Bạn có chắc muốn xem lời giải đầy đủ cho câu hỏi này?',
   'Xem lời giải',
  );
  confirmingSolution = false;
  if (!isCurrent() || requestedSessionId().id !== sessionId) return;
  if (!confirmed) {
   drawHintControl();
   solutionButton.focus({ preventScroll: true });
   return;
  }
  solutionPending = true;
  hintStatus.replaceChildren(el('p', { className: 'helper' }, 'Đang lấy lời giải đầy đủ…'));
  drawHintControl();
  try {
   const result = await api(`/chat/sessions/${sessionId}/solution`, {
    method: 'POST',
    body: { confirmed: true },
    signal: controller.signal,
   });
   if (!isCurrent() || requestedSessionId().id !== sessionId) return;
   const assistant = result?.assistantMessage;
   if (!result?.session || Number(result.session.id) !== sessionId || result.userMessage != null
    || !assistant || Number(assistant.sessionId) !== sessionId || assistant.role !== 'assistant'
    || assistant.isFullSolution !== true) {
    throw new ApiError('Phản hồi lời giải từ máy chủ chưa hợp lệ. Vui lòng thử lại.', 0, 'INVALID_RESPONSE');
   }
   const messageNode = renderStoredMessage(assistant);
   const duplicate = selectedMessages.some(item => Number(item.id) === Number(assistant.id));
   if (!duplicate) {
    selectedMessages.push(assistant);
    messages.append(messageNode);
   }
   selectedSession = result.session;
   const sessionIndex = sessions.findIndex(item => Number(item.id) === sessionId);
   if (sessionIndex >= 0) sessions[sessionIndex] = result.session;
   hintStatus.replaceChildren(el('p', { className: 'helper' }, 'Đã hiển thị lời giải đầy đủ.'));
   drawSessions();
   requestAnimationFrame(() => { if (isCurrent()) messages.scrollTop = messages.scrollHeight; });
  } catch (error) {
   if (error.name !== 'AbortError' && isCurrent() && requestedSessionId().id === sessionId) showHintError(error, sessionId);
  } finally {
   solutionPending = false;
   if (isCurrent()) drawHintControl();
  }
 }

 function showSidebarError(error, append) {
  const text = append ? 'Chưa tải thêm được phiên. Danh sách hiện tại vẫn được giữ.' : (error?.message || 'Chưa tải được lịch sử phiên.');
  sidebarStatus.replaceChildren(notice(text, 'error'), button('Thử lại', () => loadSessions(append), 'secondary small'));
 }

 function sessionLink(item) {
  const id = Number(item.id);
  const active = request.id === id;
  const updated = formatSessionTime(item.updatedAt);
  const control = el('a', {
   href: `#chat?session=${encodeURIComponent(id)}`,
   className: `session-button${active ? ' active' : ''}`,
   'aria-label': `${sessionTitle(item)}. Chủ đề ${item.topicName || 'chưa xác định'}. Cập nhật ${updated.label}${active ? '. Đang xem' : ''}`,
  },
  el('span', { className: 'session-title' }, sessionTitle(item)),
  el('span', { className: 'session-topic' }, item.topicName || 'Chưa xác định chủ đề'),
  el('time', { className: 'session-time', datetime: updated.iso || null }, updated.label),
  active ? el('span', { className: 'session-current' }, 'Đang xem') : null);
  if (active) control.setAttribute('aria-current', 'page');
  return control;
 }

 function drawSessions() {
  if (!sessionsLoaded) return;
  const visible = [...sessions];
  if (selectedSession && !visible.some(item => Number(item.id) === Number(selectedSession.id))) visible.unshift(selectedSession);
  sessionList.replaceChildren(...visible.map(sessionLink));
  if (!visible.length && !sessionsFailed) sessionList.append(el('div', { className: 'empty-state compact' }, 'Bạn chưa có phiên chat nào.'));
  pagination.replaceChildren();
  if (hasMoreSessions) {
   const more = button(loadingSessions ? 'Đang tải thêm…' : 'Tải thêm phiên', () => loadSessions(true), 'secondary small');
   more.disabled = loadingSessions;
   pagination.append(more);
  } else if (visible.length) pagination.append(el('p', { className: 'helper' }, 'Đã hiển thị tất cả phiên.'));
 }

 async function loadSessions(append = false) {
  if (loadingSessions || controller.signal.aborted) return;
  loadingSessions = true;
  if (!append) {
   sessions = [];
   sessionsLoaded = false;
   sessionsFailed = false;
   nextOffset = 0;
   hasMoreSessions = false;
   sessionList.replaceChildren();
   pagination.replaceChildren();
   sidebarStatus.replaceChildren(el('p', {}, 'Đang tải lịch sử phiên…'));
  } else {
   sidebarStatus.replaceChildren(el('p', {}, 'Đang tải thêm phiên…'));
   drawSessions();
  }
  try {
   const result = await api(`/chat/sessions?limit=${SESSION_LIMIT}&offset=${nextOffset}`, { signal: controller.signal });
   if (!Array.isArray(result?.sessions)) throw new ApiError('Dữ liệu lịch sử từ máy chủ chưa hợp lệ.', 0, 'INVALID_RESPONSE');
   if (result.hasMore && result.sessions.length === 0) throw new ApiError('Máy chủ không thể tiếp tục phân trang lịch sử.', 0, 'INVALID_RESPONSE');
   const known = new Set(sessions.map(item => Number(item.id)));
   for (const item of result.sessions) {
    const id = Number(item?.id);
    if (Number.isSafeInteger(id) && id > 0 && !known.has(id)) { sessions.push(item); known.add(id); }
   }
   nextOffset += result.sessions.length;
   hasMoreSessions = result.hasMore === true;
   sessionsLoaded = true;
   sessionsFailed = false;
   if (!isCurrent()) return;
   sidebarStatus.replaceChildren();
  } catch (error) {
   if (error.name === 'AbortError' || !isCurrent()) return;
   if (!append) { sessionsLoaded = true; sessionsFailed = true; }
   showSidebarError(error, append);
  } finally {
   loadingSessions = false;
   if (isCurrent()) drawSessions();
  }
 }

 function showMessageError(error, id) {
  const missing = error instanceof ApiError && error.status === 404 && error.code === 'CHAT_SESSION_NOT_FOUND';
  selectedSession = null;
  selectedMessages = [];
  hintLockedCode = '';
  hintStatus.replaceChildren();
  drawHintControl();
  chatTitle.textContent = missing ? 'Không tìm thấy phiên chat' : 'Chưa tải được phiên chat';
  chatDescription.textContent = missing ? 'Phiên này không tồn tại hoặc không thuộc tài khoản của bạn.' : 'Bạn có thể thử tải lại mà không ảnh hưởng đến danh sách phiên.';
  const retry = Number.isSafeInteger(id) ? button('Thử lại', () => loadMessages(id), 'secondary') : null;
  messages.replaceChildren(notice(missing ? 'Không tìm thấy phiên chat của bạn.' : (error?.message || 'Chưa tải được nội dung phiên.'), 'error'), retry);
 }

 async function loadMessages(id) {
  selectedSession = null;
  selectedMessages = [];
  hintLockedCode = '';
  hintStatus.replaceChildren();
  drawHintControl();
  messages.setAttribute('aria-busy', 'true');
  messages.replaceChildren(el('div', { className: 'empty-state' }, 'Đang tải nội dung phiên…'));
  chatTitle.textContent = 'Đang mở phiên chat…';
  chatDescription.textContent = 'Nội dung đã lưu đang được tải từ tài khoản của bạn.';
  drawSessions();
  try {
   const stored = [];
   const known = new Set();
   const offsets = new Set();
   let offset = 0;
   let currentSession = null;
   let hasMore = true;
   for (let page = 0; hasMore; page++) {
    if (page >= MAX_MESSAGE_PAGES || offsets.has(offset)) throw new ApiError('Máy chủ không thể tiếp tục phân trang tin nhắn.', 0, 'INVALID_RESPONSE');
    offsets.add(offset);
    const result = await api(`/chat/sessions/${id}/messages?limit=${MESSAGE_LIMIT}&offset=${offset}`, { signal: controller.signal });
    if (!Array.isArray(result?.messages) || !result?.session) throw new ApiError('Dữ liệu phiên chat từ máy chủ chưa hợp lệ.', 0, 'INVALID_RESPONSE');
    currentSession = result.session;
    for (const item of result.messages) {
     const messageId = Number(item?.id);
     if (!Number.isSafeInteger(messageId) || messageId <= 0) throw new ApiError('Dữ liệu tin nhắn từ máy chủ chưa hợp lệ.', 0, 'INVALID_RESPONSE');
     if (!known.has(messageId)) { known.add(messageId); stored.push(item); }
    }
    hasMore = result.hasMore === true;
    if (hasMore && result.messages.length === 0) throw new ApiError('Máy chủ không thể tiếp tục phân trang tin nhắn.', 0, 'INVALID_RESPONSE');
    offset += result.messages.length;
   }
   if (!isCurrent() || requestedSessionId().id !== id) return;
   selectedSession = currentSession;
   selectedMessages = stored;
   chatTitle.textContent = sessionTitle(currentSession);
   chatDescription.textContent = [currentSession.subjectName, currentSession.chapterName, currentSession.topicName].filter(Boolean).join(' · ') || 'Phiên chat đã lưu';
   messages.replaceChildren(...stored.map(renderStoredMessage));
   if (!stored.length) messages.append(el('div', { className: 'empty-state' }, 'Phiên này chưa có tin nhắn.'));
   drawSessions();
   drawHintControl();
   requestAnimationFrame(() => { if (isCurrent()) messages.scrollTop = messages.scrollHeight; });
  } catch (error) {
   if (error.name === 'AbortError' || !isCurrent() || requestedSessionId().id !== id) return;
   selectedSession = null;
   selectedMessages = [];
   showMessageError(error, id);
   drawSessions();
  } finally {
   if (isCurrent()) messages.setAttribute('aria-busy', 'false');
  }
 }

 loadSessions();
 drawHintControl();
 if (request.invalid) {
  showMessageError(new ApiError('Mã phiên chat trên đường dẫn không hợp lệ.', 404, 'CHAT_SESSION_NOT_FOUND'), null);
 } else if (request.id !== null) loadMessages(request.id);

 queueMicrotask(() => {
  if (!root.isConnected) return;
  const observer = new MutationObserver(() => {
   if (!root.isConnected) { controller.abort(); observer.disconnect(); }
  });
  observer.observe(document.body, { childList: true, subtree: true });
 });
 return root;
}

export function renderChat() {
 return getSession().reason === 'preview' ? renderPreviewChat() : renderChatHistory();
}
