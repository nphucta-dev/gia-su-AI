import { el, button, heading, notice, confirmDialog, link } from '../components/ui.js';
import { loadCatalog, flattenTopics } from '../catalog.js';
import { setupValidation, validateFields } from '../components/validation.js';
import { messageNode, relativeDay } from '../components/chat-message.js';
import { topics as demoTopics } from '../data.js';
import { chatClient, isPreview, hintState, describeChatError, isReplyFailure, quickRequest, loadHistory, FEATURES, MAX_MESSAGE_LENGTH } from '../chat.js';

const setHash = value => history.replaceState(null, '', `#${value}`); // đổi URL, không dựng lại trang

export function renderChat() {
  const root = el('div', {}, el('div', { role: 'status' }, 'Đang tải hội thoại…'));
  const showError = (title, text, retry) => root.replaceChildren(heading(title, text), retry ? button('Thử lại', retry, 'primary') : null, link('Về trang học', '#home'));
  (async function open() {
    try {
      await null; // đợi trang gắn root vào DOM (chế độ xem thử không có request nào để chờ)
      const topics = isPreview()
        ? demoTopics.map(t => ({ id: t.id, name: t.name, subjectName: 'Toán học', gradeLevel: '', chapterName: t.chapter }))
        : flattenTopics(await loadCatalog());
      if (!root.isConnected) return;
      const client = chatClient(topics);
      const params = new URLSearchParams(location.hash.split('?')[1]);
      const list = await client.listSessions();
      if (!root.isConnected) return;
      const sessionParam = params.get('session');
      const topicParam = params.get('topic');
      let startId = sessionParam ? Number(sessionParam) : null;
      if (sessionParam && !Number.isInteger(startId)) return showError('Không tìm thấy phiên chat', 'Phiên này không tồn tại hoặc không thuộc tài khoản của bạn.');
      if (!sessionParam && !topicParam && list.sessions.length) startId = list.sessions[0].id;
      let current = null;
      if (startId) {
        try { current = await loadHistory(client, startId); } catch (error) {
          if (!root.isConnected) return;
          if (error.status === 404) return showError('Không tìm thấy phiên chat', 'Phiên này không tồn tại hoặc không thuộc tài khoản của bạn.');
          throw error;
        }
        if (!root.isConnected) return;
        if (!sessionParam) setHash(`chat?session=${startId}`);
      }
      let topic = null;
      if (!current) {
        topic = topicParam ? topics.find(t => String(t.id) === topicParam) : topics[0];
        if (!topics.length) return showError('Chưa có chủ đề', 'Hiện chưa có chủ đề nào được mở để học.');
        if (!topic) return showError('Chủ đề không khả dụng', 'Chủ đề này không tồn tại hoặc đã được tắt.');
      }
      root.replaceChildren(buildChat({ client, topics, list, current, topic }));
    } catch (error) {
      if (root.isConnected) showError('Chưa tải được hội thoại', describeChatError(error), open);
    }
  })();
  return root;
}

function buildChat({ client, topics, list, current, topic: initialTopic }) {
  // ---- Trạng thái ----
  let sessions = [...list.sessions];
  let hasMoreSessions = list.hasMore;
  let session = current?.session || null;
  let messages = current?.messages || [];
  let topic = initialTopic || topics.find(t => t.id === session.topicId) || { id: session.topicId, name: session.topicName };
  let closed = Boolean(session) && !topics.some(t => t.id === session.topicId);
  let busy = false;
  let pendingText = '';
  let previewLock = false;
  const preview = client.preview;

  // ---- Thành phần giao diện ----
  const sessionList = el('div', { className: 'session-list' });
  const moreSessions = button('Xem thêm phiên', loadMoreSessions, 'ghost small session-more');
  const sidebar = el('aside', { className: 'chat-sidebar' }, el('h2', {}, 'Lịch sử phiên'), button('+ Phiên mới', newSession, 'secondary small new-session'), sessionList, moreSessions);

  const title = el('h2', {});
  const topicSelect = el('select', { className: 'select chat-topic-select', 'aria-label': 'Chủ đề của phiên mới' }, ...topics.map(t => el('option', { value: String(t.id) }, t.subjectName ? `${t.subjectName} · ${t.name}` : t.name)));
  topicSelect.addEventListener('change', () => { topic = topics.find(t => String(t.id) === topicSelect.value) || topic; if (!session) setHash(`chat?topic=${topic.id}`); drawHeader(); });
  const hint = button('Gợi ý tiếp (1/3)', requestHint);
  const solution = button('Xem lời giải', showSolution, 'ghost');
  const example = button('Cho ví dụ', () => submit(quickRequest('example')), 'ghost small');
  const simpler = button('Giải thích đơn giản', () => submit(quickRequest('simpler')), 'ghost small');
  const sources = el('details', {}, el('summary', {}, preview ? 'Nguồn tham khảo minh hoạ' : 'Nguồn tham khảo'),
    el('p', { className: 'helper' }, preview ? 'Ví dụ cách hiển thị: Tài liệu Đại số · phần Phương trình bậc hai. Chưa có tài liệu thực được truy xuất.' : 'Chưa có tài liệu nguồn nào được truy xuất cho câu trả lời này.'));

  const messagesEl = el('div', { className: 'messages', 'aria-live': 'polite', 'aria-label': 'Nội dung hội thoại' });
  const feedback = el('div', { className: 'message-actions' }, ...['Hữu ích', 'Chưa hữu ích'].map(label => {
    const b = button(label, () => feedback.querySelectorAll('button').forEach(n => n.setAttribute('aria-pressed', String(n === b))), 'ghost small');
    b.setAttribute('aria-pressed', 'false');
    if (!preview && !FEATURES.feedback) { b.disabled = true; b.title = 'Tính năng đánh giá câu trả lời sắp có'; }
    return b;
  }));
  const feedbackRow = el('div', { className: 'chat-header' }, feedback);

  const input = el('textarea', { className: 'textarea', placeholder: 'Nhập câu hỏi của bạn…', 'aria-label': 'Câu hỏi cho gia sư', maxlength: MAX_MESSAGE_LENGTH });
  const send = el('button', { className: 'button primary', type: 'submit' }, 'Gửi câu hỏi');
  const statusArea = el('div', { role: 'status', className: 'chat-status' });
  const footerParts = [statusArea, el('div', { className: 'composer-row' }, input, send), el('p', { className: 'chat-footer' }, 'Câu trả lời do AI tạo, hãy đối chiếu với tài liệu học tập.')];
  if (preview) footerParts.push(previewStatePicker());
  const form = el('form', { className: 'chat-composer' }, ...footerParts);
  setupValidation(form, [input]);
  form.addEventListener('submit', event => {
    event.preventDefault();
    const text = input.value.trim();
    if (!validateFields([[input, !text ? 'Vui lòng nhập câu hỏi trước khi gửi.' : '']])) return;
    submit(text, { fromInput: true });
  });
  // Enter gửi, Shift+Enter xuống dòng; không chặn bộ gõ tiếng Việt đang soạn dấu.
  input.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); form.requestSubmit(); } });

  // ---- Vẽ lại theo trạng thái ----
  const locked = () => busy || previewLock;
  function drawSessions() {
    sessionList.replaceChildren(...sessions.map(s => {
      const item = el('button', { type: 'button', className: `session-button ${session?.id === s.id ? 'active' : ''}`, onclick: () => openSession(s.id), disabled: busy },
        el('span', { className: 'session-title' }, s.title || s.topicName),
        el('span', { className: 'session-meta' }, [s.title && s.title !== s.topicName ? s.topicName : '', relativeDay(s.updatedAt)].filter(Boolean).join(' · ')));
      if (session?.id === s.id) item.setAttribute('aria-current', 'true');
      return item;
    }));
    if (!sessions.length) sessionList.append(el('p', { className: 'helper session-empty' }, 'Chưa có phiên nào. Hãy đặt câu hỏi đầu tiên.'));
    moreSessions.hidden = !hasMoreSessions;
  }
  function drawHeader() {
    title.textContent = session ? session.topicName : topic.name;
    topicSelect.value = String(topic.id);
    topicSelect.hidden = Boolean(session) || topics.length < 2;
  }
  function drawMessages() {
    const nodes = messages.map(messageNode);
    if (pendingText) nodes.push(messageNode({ role: 'user', content: pendingText }));
    if (busy) nodes.push(el('div', { className: 'message assistant pending', role: 'status' }, el('span', { className: 'typing-dots', 'aria-hidden': 'true' }, el('i'), el('i'), el('i')), ' Gia sư đang suy nghĩ…'));
    if (!nodes.length) nodes.push(el('div', { className: 'empty-state' }, closed ? 'Phiên này chưa có tin nhắn.' : 'Chưa có câu hỏi nào. Nhập câu hỏi bên dưới để bắt đầu phiên học.'));
    messagesEl.replaceChildren(...nodes);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    feedbackRow.hidden = !messages.some(m => m.role === 'assistant');
  }
  function drawControls() {
    const state = hintState(messages);
    const idle = !locked() && !closed;
    hint.textContent = state.done ? 'Đã xem 3 mức gợi ý' : `Gợi ý tiếp (${state.next}/3)`;
    hint.disabled = !idle || !session || !state.hasQuestion || state.done;
    example.disabled = simpler.disabled = !idle || !session || !state.hasQuestion;
    solution.disabled = busy;
    input.disabled = send.disabled = !idle;
    document.querySelectorAll('.new-session').forEach(b => { b.disabled = busy; });
    form.setAttribute('aria-busy', String(busy));
  }
  function sync() { drawSessions(); drawHeader(); drawMessages(); drawControls(); }
  const showStatus = (...nodes) => statusArea.replaceChildren(...nodes);
  const closedNotice = () => notice('Chủ đề này đã tắt. Bạn vẫn xem được lịch sử nhưng không gửi thêm được.', 'warning');

  function upsertSession(item) {
    if (!item) return;
    sessions = [item, ...sessions.filter(s => s.id !== item.id)];
  }

  // ---- Thao tác ----
  async function loadMoreSessions() {
    moreSessions.disabled = true;
    try {
      const page = await client.listSessions({ offset: sessions.length });
      const known = new Set(sessions.map(s => s.id));
      sessions = [...sessions, ...page.sessions.filter(s => !known.has(s.id))];
      hasMoreSessions = page.hasMore;
      drawSessions();
    } catch (error) { showStatus(notice(describeChatError(error), 'error')); }
    finally { moreSessions.disabled = false; }
  }
  async function openSession(id) {
    if (busy || session?.id === id) return;
    showStatus();
    try {
      const result = await loadHistory(client, id);
      if (!form.isConnected) return;
      session = result.session; messages = result.messages;
      const known = topics.find(t => t.id === session.topicId);
      topic = known || { id: session.topicId, name: session.topicName };
      closed = !known;
      setHash(`chat?session=${id}`);
      sync();
      if (closed) showStatus(closedNotice());
    } catch (error) { showStatus(notice(describeChatError(error), 'error')); }
  }
  function newSession() {
    if (busy) return;
    session = null; messages = []; closed = false; pendingText = '';
    if (!topics.some(t => t.id === topic.id)) topic = topics[0];
    setHash(`chat?topic=${topic.id}`);
    showStatus();
    sync();
    input.focus();
  }
  async function ensureSession() {
    if (session) return;
    session = (await client.createSession(topic.id)).session;
    setHash(`chat?session=${session.id}`);
  }
  // Chạy một thao tác gọi gia sư: khoá giao diện, hiện "đang phản hồi", rồi cập nhật hoặc xử lý lỗi.
  async function run(action, { text = '' } = {}) {
    if (busy || closed) return;
    busy = true; pendingText = text; showStatus(); sync();
    try {
      const result = await action();
      if (!form.isConnected) return;
      if (result.userMessage) messages = [...messages, result.userMessage];
      messages = [...messages, result.assistantMessage];
      session = result.session;
      upsertSession(result.session);
      busy = false; pendingText = ''; sync();
    } catch (error) {
      if (!form.isConnected) return;
      await recover(error, text);
    } finally {
      if (busy) { busy = false; pendingText = ''; sync(); }
    }
  }
  // Sau lỗi: đồng bộ lại lịch sử thật để biết câu hỏi đã được lưu hay chưa, tránh gửi trùng.
  async function recover(error, text) {
    let saved = false;
    if (session) {
      try {
        const result = await loadHistory(client, session.id);
        messages = result.messages; session = result.session; upsertSession(result.session);
        saved = messages.at(-1)?.role === 'user' && (!text || messages.at(-1).content === text);
      } catch { /* mất kết nối: giữ nguyên trạng thái đang có */ }
    }
    busy = false; pendingText = '';
    if (error.code === 'TOPIC_CLOSED') closed = true;
    if (text && !saved && !input.value) input.value = text; // giữ lại nội dung đã nhập
    sync();
    const nodes = [notice(describeChatError(error), error.code === 'CHAT_CHANGED' ? 'warning' : 'error')];
    const retryable = (isReplyFailure(error) && error.code !== 'CHAT_CHANGED') || error.code === 'NETWORK_ERROR' || error.code === 'CHAT_BUSY' || error.code === 'INVALID_RESPONSE';
    if (retryable && !closed) nodes.push(button('Thử lại', saved || !text ? requestHint : () => submit(text, { fromInput: false }), 'secondary small'));
    showStatus(...nodes);
  }
  function submit(text, { fromInput = false } = {}) {
    if (locked() || closed || !text) return;
    if (fromInput) { input.value = ''; }
    return run(async () => { await ensureSession(); return client.sendMessage(session.id, text); }, { text });
  }
  function requestHint() {
    if (!session) return;
    return run(() => client.nextHint(session.id));
  }
  async function showSolution() {
    if (!(await confirmDialog('Xem lời giải đầy đủ?', preview ? 'Thử tự giải thêm một bước trước khi đối chiếu. Nội dung dưới đây là ví dụ minh hoạ.' : 'Thử tự giải thêm một bước trước khi đối chiếu với lời giải đầy đủ.', 'Xem lời giải'))) return;
    if (preview) {
      try { await ensureSession(); } catch (error) { showStatus(notice(describeChatError(error), 'error')); return; }
      messages = [...messages, client.demoSolution(session.id)];
      upsertSession(session);
      sync();
      return;
    }
    // TK-036/037: backend chưa có API lời giải đầy đủ; không tạo nội dung giả.
    showStatus(notice('Lời giải đầy đủ chưa được mở. Bạn có thể xin gợi ý tiếp để được hướng dẫn thêm.', 'warning'));
  }

  function previewStatePicker() {
    const mode = el('select', { className: 'select', 'aria-label': 'Xem trạng thái giao diện' }, el('option', { value: 'normal' }, 'Sẵn sàng'), el('option', { value: 'loading' }, 'Đang phản hồi'), el('option', { value: 'error' }, 'Lỗi kết nối'), el('option', { value: 'quota' }, 'Hết hạn mức'));
    const reset = () => { mode.value = 'normal'; mode.dispatchEvent(new Event('change')); };
    mode.addEventListener('change', () => {
      previewLock = mode.value === 'loading' || mode.value === 'quota';
      drawControls();
      showStatus();
      if (mode.value === 'loading') showStatus(notice('Đang chuẩn bị phản hồi… Bạn có thể tiếp tục xem lịch sử.'));
      if (mode.value === 'error') showStatus(notice('Chưa thể kết nối gia sư. Nội dung đã nhập vẫn được giữ lại.', 'error'), button('Thử lại', reset, 'secondary small'));
      if (mode.value === 'quota') showStatus(notice('Bạn đã dùng hết 30 lượt yêu cầu hôm nay. Bạn vẫn có thể xem lịch sử học tập.', 'warning'));
    });
    return el('details', { className: 'state-picker' }, el('summary', {}, 'Xem trước trạng thái giao diện'), mode);
  }

  sync();
  if (closed) showStatus(closedNotice());
  return el('div', {}, heading('Hỏi gia sư AI', 'Gợi mở từng bước, hiểu bài bằng chính cách nghĩ của bạn.'),
    el('div', { className: 'chat-layout' }, sidebar, el('section', { className: 'chat-main' },
      el('div', { className: 'chat-header' }, title, topicSelect, el('div', { className: 'message-actions' }, hint, solution, example, simpler), sources),
      messagesEl, feedbackRow, form)));
}
