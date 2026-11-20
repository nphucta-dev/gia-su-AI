import { api, ApiError } from '../api.js';
import { loadCatalog, flattenTopics } from '../catalog.js';
import { el, button, heading, notice, confirmDialog, link } from '../components/ui.js';
import { validateChatQuestion } from '../chat-question.js';
import { createMessageFeedback } from '../components/message-feedback.js';

let activeController;

function positiveId(value) {
 const text = String(value ?? '');
 const number = Number(text);
 return /^[1-9]\d*$/.test(text) && Number.isSafeInteger(number) && number <= 2 ** 31 - 1 ? number : null;
}

function titleFor(session) { return session.title || `Phiên về ${session.topicName || 'chủ đề đã chọn'}`; }
function timeFor(value) {
 const date = new Date(value);
 return value && !Number.isNaN(date.getTime()) ? date.toLocaleString('vi-VN') : '';
}

export function renderLiveChat() {
 activeController?.abort();
 const controller = new AbortController();
 activeController = controller;
 const params = new URLSearchParams(location.hash.split('?')[1]);
 const requestedSession = positiveId(params.get('session'));
 const requestedTopic = positiveId(params.get('topic'));
 let topics = [], sessions = [], selectedSession = null, selectedMessages = [];
 let topicId = requestedTopic, nextOffset = 0, hasMore = false, listPending = false;
 let busy = false, confirming = false, loaded = false, quota = null;
 const topic = el('select', { className: 'select', 'aria-label': 'Chủ đề học', disabled: true });
 const sidebarStatus = el('div', { role: 'status' });
 const sessionList = el('nav', { className: 'session-list', 'aria-label': 'Các phiên chat đã lưu' });
 const pagination = el('div', { className: 'session-pagination' });
 const title = el('h2', {}, 'Chọn chủ đề để bắt đầu');
 const description = el('p', { className: 'helper' });
 const quotaStatus = el('p', { className: 'helper', role: 'status', 'aria-label': 'Hạn mức AI' });
 const actionStatus = el('div', { className: 'chat-hint-status', role: 'status', 'aria-live': 'polite' });
 const messages = el('div', { className: 'messages chat-history-messages', 'aria-label': 'Nội dung phiên chat', 'aria-live': 'polite' });
 const input = el('textarea', { className: 'textarea', maxlength: 4000, placeholder: 'Nhập câu hỏi của bạn…', 'aria-label': 'Câu hỏi cho gia sư' });
 const send = el('button', { type: 'submit', className: 'button primary' }, 'Gửi câu hỏi');
 const hint = button('Hãy gửi câu hỏi trước', () => runAction('hints'), 'secondary');
 const solution = button('Xem lời giải', requestSolution, 'ghost');
 const simplify = button('Giải thích đơn giản', () => runAction('simplify'), 'ghost small');
 const example = button('Cho ví dụ', () => runAction('example'), 'ghost small');
 const controls = el('div', { className: 'chat-hint-controls' }, hint, solution, simplify, example);
 const form = el('form', { className: 'chat-composer', novalidate: true },
  el('div', { className: 'composer-row' }, input, send),
  el('p', { className: 'chat-footer' }, 'Câu trả lời do AI tạo, hãy đối chiếu với tài liệu học tập.'));
 const newSession = button('+ Phiên mới', () => {
  if (busy || confirming) return;
  selectedSession = null; selectedMessages = []; input.value = ''; actionStatus.replaceChildren();
  history.replaceState(null, '', topicId ? `#chat?topic=${topicId}` : '#chat');
  drawSession();
 });
 const root = el('div', {},
  heading('Hỏi gia sư AI', 'Gợi mở từng bước và mở lại hội thoại đã lưu của bạn.'),
  el('div', { className: 'chat-layout chat-history-layout' },
   el('aside', { className: 'chat-sidebar', 'aria-label': 'Lịch sử phiên chat' },
    el('div', { className: 'chat-sidebar-header' }, el('h2', {}, 'Lịch sử phiên'), newSession, link('Chọn chủ đề mới', '#home', 'button ghost small')),
    topic, sidebarStatus, sessionList, pagination),
   el('section', { className: 'chat-main' }, el('div', { className: 'chat-header chat-session-header' },
    el('div', {}, title, description, quotaStatus), controls, actionStatus), messages, form)));

 function current() { return !controller.signal.aborted && root.isConnected; }
 const renderFeedback = createMessageFeedback({ signal: controller.signal, isCurrent: sessionId => current() && selectedSession?.id === sessionId });
 function openTopic() { return topics.find(item => Number(item.id) === Number(selectedSession?.topicId || topicId)); }
 function hasQuestion() { return selectedMessages.some(item => item.role === 'user'); }
 function hintLevel() {
  let start = -1;
  selectedMessages.forEach((item, index) => { if (item.role === 'user') start = index; });
  return Math.max(0, ...selectedMessages.slice(start + 1).filter(item => item.role === 'assistant').map(item => Number(item.hintLevel) || 0));
 }
 function drawControls() {
  const blocked = busy || confirming || !loaded || !openTopic() || quota?.remaining === 0;
  input.disabled = busy || confirming || !loaded || !openTopic();
  send.disabled = blocked;
  send.textContent = busy ? 'Đang xử lý…' : 'Gửi câu hỏi';
  topic.disabled = busy || confirming || !topics.length;
  newSession.disabled = busy || confirming;
  hint.textContent = hintLevel() >= 3 ? 'Đã nhận đủ 3 mức gợi ý' : hasQuestion() ? `Gợi ý tiếp · Mức ${hintLevel() + 1}` : 'Hãy gửi câu hỏi trước';
  hint.disabled = blocked || !hasQuestion() || hintLevel() >= 3;
  for (const control of [solution, simplify, example]) control.disabled = blocked || !hasQuestion();
  form.setAttribute('aria-busy', String(busy));
 }
 async function loadQuota() {
  try {
   const result = await api('/ai/quota', { signal: controller.signal });
   if (!current()) return;
   quota = result;
   quotaStatus.textContent = `Còn ${result.remaining}/${result.limit} lượt AI · Đặt lại ${timeFor(result.nextResetAt)}`;
   drawControls();
  } catch (error) { if (error.name !== 'AbortError' && current()) quotaStatus.textContent = ''; }
 }
 function renderMessage(message) {
  if (!message || !['user', 'assistant'].includes(message.role) || typeof message.content !== 'string') throw new ApiError('Tin nhắn từ máy chủ chưa hợp lệ.');
  const node = el('article', { className: `message ${message.role}`, 'data-message-id': message.id, 'data-hint-level': message.hintLevel },
   el('p', { className: 'message-meta' }, [message.role === 'user' ? 'Bạn' : 'Gia sư AI', timeFor(message.createdAt), message.isFullSolution ? 'Lời giải đầy đủ' : message.hintLevel ? `Gợi ý mức ${message.hintLevel}` : ''].filter(Boolean).join(' · ')),
   el('p', {}, message.content));
  if (message.role === 'assistant') {
   const refs = Array.isArray(message.sourceRefs) ? message.sourceRefs : [];
   node.append(refs.length ? el('details', { className: 'message-sources' }, el('summary', {}, 'Nguồn tham khảo'),
    el('ul', {}, ...refs.map(ref => el('li', {}, `${ref.title || 'Tài liệu'} · đoạn ${Number(ref.chunkIndex) + 1}${ref.available === false ? ' · Nguồn hiện không khả dụng' : ''}`))))
    : el('p', { className: 'helper' }, 'Chưa có nguồn tài liệu phù hợp.'));
   node.append(renderFeedback(message, selectedSession.id));
  }
  return node;
 }
 function drawMessages() {
  messages.replaceChildren(...selectedMessages.map(renderMessage));
  if (!selectedMessages.length) messages.append(el('div', { className: 'empty-state' }, selectedSession ? 'Phiên này chưa có tin nhắn.' : 'Nhập câu hỏi để bắt đầu phiên học mới.'));
  requestAnimationFrame(() => { if (current()) messages.scrollTop = messages.scrollHeight; });
 }
 function drawSession() {
  const selected = openTopic();
  title.textContent = selectedSession ? titleFor(selectedSession) : selected?.name || 'Chưa có chủ đề đang mở';
  description.textContent = selectedSession
   ? [selectedSession.subjectName, selectedSession.chapterName, selectedSession.topicName].filter(Boolean).join(' · ')
   : selected ? [selected.subjectName, selected.chapterName, selected.name].filter(Boolean).join(' · ') : 'Chọn chủ đề trên trang học để bắt đầu.';
  if (selectedSession && !selected) description.textContent += ' · Chủ đề đã đóng, bạn vẫn có thể đọc lịch sử.';
  drawMessages(); drawSessions(); drawControls();
 }
 function drawSessions() {
  const visible = [...sessions];
  if (selectedSession && !visible.some(item => item.id === selectedSession.id)) visible.unshift(selectedSession);
  sessionList.replaceChildren(...visible.map(item => {
   const active = item.id === selectedSession?.id;
   return el('a', { href: `#chat?session=${item.id}`, className: `session-button${active ? ' active' : ''}`, 'aria-current': active ? 'page' : null },
    el('span', { className: 'session-title' }, titleFor(item)),
    el('span', { className: 'session-topic' }, item.topicName || ''), el('time', { className: 'session-time' }, timeFor(item.updatedAt)));
  }));
  if (!visible.length && !listPending) sessionList.append(el('div', { className: 'empty-state compact' }, 'Bạn chưa có phiên chat nào.'));
  pagination.replaceChildren();
  if (hasMore) {
   const more = button(listPending ? 'Đang tải thêm…' : 'Tải thêm phiên', () => loadSessions(true), 'secondary small');
   more.disabled = listPending; pagination.append(more);
  }
 }
 async function loadSessions(append = false) {
  if (listPending || !current()) return;
  listPending = true;
  if (!append) { nextOffset = 0; sessions = []; }
  sidebarStatus.replaceChildren(el('p', {}, 'Đang tải lịch sử phiên…')); drawSessions();
  try {
   const result = await api(`/chat/sessions?limit=20&offset=${nextOffset}`, { signal: controller.signal });
   if (!current()) return;
   if (!Array.isArray(result?.sessions) || (result.hasMore && !result.sessions.length)) throw new ApiError('Lịch sử phiên chưa hợp lệ.');
   const ids = new Set(sessions.map(item => item.id));
   sessions.push(...result.sessions.filter(item => positiveId(item.id) && !ids.has(item.id)));
   nextOffset += result.sessions.length; hasMore = result.hasMore === true;
   sidebarStatus.replaceChildren();
  } catch (error) {
   if (error.name !== 'AbortError' && current()) sidebarStatus.replaceChildren(notice(error.message, 'error'), button('Thử lại', () => loadSessions(append), 'secondary small'));
  } finally { listPending = false; if (current()) drawSessions(); }
 }
 async function loadMessages(sessionId) {
  messages.setAttribute('aria-busy', 'true');
  try {
   const stored = []; let offset = 0, more = true, session;
   for (let page = 0; more; page++) {
    if (page >= 100) throw new ApiError('Lịch sử vượt giới hạn tải.');
    const result = await api(`/chat/sessions/${sessionId}/messages?limit=200&offset=${offset}`, { signal: controller.signal });
    if (!Array.isArray(result?.messages) || Number(result.session?.id) !== sessionId || (result.hasMore && !result.messages.length)) throw new ApiError('Nội dung phiên chưa hợp lệ.');
    session = result.session; stored.push(...result.messages); offset += result.messages.length; more = result.hasMore === true;
   }
   if (!current()) return;
   selectedSession = session; topicId = session.topicId;
   selectedMessages = [...new Map(stored.map(item => [item.id, item])).values()];
   drawSession();
  } finally { if (current()) messages.setAttribute('aria-busy', 'false'); }
 }
 async function ensureSession() {
  if (selectedSession) return;
  const result = await api('/chat/sessions', { method: 'POST', body: { topicId: Number(topicId) }, signal: controller.signal });
  if (!current()) return;
  if (!positiveId(result.session?.id)) throw new ApiError('Không thể tạo phiên học.');
  selectedSession = result.session; selectedMessages = [];
  history.replaceState(null, '', `#chat?session=${selectedSession.id}`);
  drawSession();
 }
 function acceptReply(result, kind) {
  const assistant = result?.assistantMessage;
  if (!result?.session || result.session.id !== selectedSession?.id || !assistant || !positiveId(assistant.id)
   || assistant.sessionId !== selectedSession.id || assistant.role !== 'assistant' || typeof assistant.content !== 'string'
   || !assistant.content.trim() || (assistant.hintLevel != null && ![1, 2, 3].includes(assistant.hintLevel))
   || (kind === 'solution' && assistant.isFullSolution !== true)) throw new ApiError('Phản hồi từ gia sư chưa hợp lệ.');
  selectedSession = result.session;
  for (const message of [result.userMessage, result.assistantMessage].filter(Boolean)) {
   if (!selectedMessages.some(item => item.id === message.id)) selectedMessages.push(message);
  }
  const position = sessions.findIndex(item => item.id === selectedSession.id);
  if (position >= 0) sessions.splice(position, 1);
  sessions.unshift(selectedSession);
  drawSession();
 }
 async function runAction(kind, content = '') {
  if (busy || confirming || !loaded || !openTopic() || quota?.remaining === 0) return;
  busy = true; actionStatus.replaceChildren(el('p', {}, 'Đang chuẩn bị phản hồi…')); drawControls();
  let retryKind = kind;
  try {
   await ensureSession();
   if (!current()) return;
   let path = kind, body;
   if (kind === 'send') { path = 'messages'; body = { content }; }
   else if (kind === 'solution') body = { confirmed: true };
   else if (kind === 'simplify' || kind === 'example') { path = 'explanations'; body = { mode: kind }; }
   const result = await api(`/chat/sessions/${selectedSession.id}/${path}`, { method: 'POST', body, signal: controller.signal });
   if (!current()) return;
   acceptReply(result, kind);
   if (kind === 'send') input.value = '';
   actionStatus.replaceChildren();
  } catch (error) {
   if (error.name === 'AbortError' || !current()) return;
   if (kind === 'send' && error.fields?.messageSaved === 'true') {
    input.value = ''; retryKind = 'retry';
    try { await loadMessages(selectedSession.id); } catch { /* Câu hỏi đã lưu vẫn đọc lại được bằng lịch sử. */ }
   }
   const retry = () => runAction(retryKind, retryKind === 'send' ? content : '');
   const changed = error.code === 'CHAT_CHANGED' || error.code === 'CHAT_REPLY_EXISTS';
   actionStatus.replaceChildren(notice(error.message || 'Chưa thể nhận phản hồi.', 'error'),
    changed ? button('Tải lại phiên', async () => { try { await loadMessages(selectedSession.id); actionStatus.replaceChildren(); } catch (failure) { actionStatus.replaceChildren(notice(failure.message, 'error')); } }, 'secondary small')
     : error.status === 404 || error.code === 'TOPIC_CLOSED' ? null : button('Thử lại', retry, 'secondary small'));
  } finally {
   busy = false;
   if (current()) { drawControls(); loadQuota(); }
  }
 }
 async function requestSolution() {
  if (busy || confirming || !hasQuestion() || !openTopic()) return;
  confirming = true; drawControls();
  const confirmed = await confirmDialog('Xem lời giải đầy đủ?', 'Bạn có chắc muốn xem lời giải đầy đủ cho câu hỏi này?', 'Xem lời giải');
  confirming = false;
  if (!current()) return;
  drawControls();
  if (confirmed) await runAction('solution');
 }
 form.addEventListener('submit', event => {
  event.preventDefault();
  const validation = validateChatQuestion(input.value);
  if (!validation.valid) {
   actionStatus.replaceChildren(notice(validation.error, 'error')); input.focus(); return;
  }
  runAction('send', validation.text);
 });
 topic.addEventListener('change', () => { location.hash = `chat?topic=${topic.value}`; });
 queueMicrotask(async () => {
  if (!current()) return;
  const observer = new MutationObserver(() => { if (!root.isConnected) { controller.abort(); observer.disconnect(); } });
  observer.observe(document.body, { childList: true, subtree: true });
  loadSessions(); loadQuota();
  try {
   try { topics = flattenTopics(await loadCatalog()); }
   catch (error) {
    if (!requestedSession || error.name === 'AbortError') throw error;
    description.textContent = 'Chưa tải được danh mục. Bạn vẫn có thể đọc lịch sử đã lưu.';
   }
   if (!current()) return;
   if (params.has('session') && !requestedSession) throw new ApiError('Mã phiên chat không hợp lệ.', 404);
   if (params.has('topic') && !requestedTopic) throw new ApiError('Mã chủ đề không hợp lệ.', 404);
   if (requestedTopic && !topics.some(item => Number(item.id) === requestedTopic)) throw new ApiError('Chủ đề này không tồn tại hoặc đã được tắt.', 404);
   topicId = requestedTopic || Number(topics[0]?.id) || null;
   topic.replaceChildren(...topics.map(item => el('option', { value: item.id, selected: Number(item.id) === topicId }, `${item.subjectName} · ${item.name}`)));
   loaded = true;
   if (requestedSession) { await loadMessages(requestedSession); topic.value = String(selectedSession?.topicId || ''); }
   else drawSession();
  } catch (error) {
   if (error.name !== 'AbortError' && current()) {
    loaded = false; title.textContent = 'Chưa thể mở phiên học';
    messages.replaceChildren(notice(error.message, 'error'), link('Về trang học', '#home', 'button secondary'));
   }
  } finally { if (current()) drawControls(); }
 });
 drawControls();
 return root;
}
