import { api } from './api.js';
import { getSession } from './session.js';

// Lớp dữ liệu của trang chat (tương tự catalog.js): trang chỉ gọi các hàm ở đây.
// Chế độ xem thử (localhost) dùng dữ liệu minh hoạ trong bộ nhớ, không gọi API.

export const MAX_HINT_LEVEL = 3;
export const MAX_MESSAGE_LENGTH = 4000;

// Bật từng tính năng khi backend có API tương ứng.
export const FEATURES = Object.freeze({
  fullSolution: false, // TK-036/037: lời giải đầy đủ chưa có API
  feedback: false,     // TK-073/074: đánh giá câu trả lời chưa có API
  sources: false       // TK-047/048/049: trích dẫn nguồn chưa có API
});

export const isPreview = () => getSession().reason === 'preview';

const REQUESTS = Object.freeze({
  example: 'Bạn cho mình một ví dụ minh hoạ nhé.',
  simpler: 'Bạn giải thích đơn giản hơn giúp mình nhé.'
});
export const quickRequest = key => REQUESTS[key];

// Mức gợi ý hiện tại: mức cao nhất đã nhận cho câu hỏi gần nhất của người học.
export function hintState(messages) {
  const lastQuestion = messages.findLastIndex(m => m.role === 'user');
  if (lastQuestion < 0) return { hasQuestion: false, received: 0, next: 1, done: false };
  const received = Math.max(0, ...messages.slice(lastQuestion + 1).filter(m => m.role === 'assistant').map(m => m.hintLevel || 0));
  return { hasQuestion: true, received, next: Math.min(received + 1, MAX_HINT_LEVEL), done: received >= MAX_HINT_LEVEL };
}

// Thông báo cho từng mã lỗi của backend; không lộ nội dung kỹ thuật.
export function describeChatError(error) {
  const byCode = {
    LLM_NOT_CONFIGURED: 'Gia sư AI chưa được cấu hình. Câu hỏi của bạn đã được lưu.',
    LLM_TIMEOUT: 'Gia sư phản hồi quá lâu. Câu hỏi của bạn đã được lưu, hãy thử lại.',
    LLM_RATE_LIMITED: 'Dịch vụ gia sư đang bận. Câu hỏi của bạn đã được lưu, hãy thử lại sau ít phút.',
    LLM_UNAVAILABLE: 'Chưa thể kết nối gia sư. Câu hỏi của bạn đã được lưu, hãy thử lại.',
    LLM_INVALID_RESPONSE: 'Gia sư chưa trả về nội dung hợp lệ. Câu hỏi của bạn đã được lưu, hãy thử lại.',
    LLM_ERROR: 'Gia sư chưa xử lý được yêu cầu. Câu hỏi của bạn đã được lưu, hãy thử lại.',
    HINT_LIMIT_REACHED: 'Bạn đã nhận đủ 3 mức gợi ý cho câu hỏi này. Hãy thử tự giải hoặc đặt câu hỏi mới.',
    CHAT_BUSY: 'Phiên chat đang chờ phản hồi. Vui lòng đợi một chút.',
    CHAT_CHANGED: 'Hội thoại vừa được cập nhật. Đã tải lại lịch sử để bạn xem.',
    TOPIC_CLOSED: 'Chủ đề này đã tắt. Bạn vẫn xem được lịch sử nhưng không gửi thêm được.',
    CHAT_SESSION_NOT_FOUND: 'Không tìm thấy phiên chat này.',
    TOPIC_NOT_FOUND: 'Chủ đề không tồn tại hoặc chưa được mở.'
  };
  return byCode[error?.code] || error?.message || 'Chưa thể xử lý yêu cầu. Vui lòng thử lại.';
}

// Lỗi mà câu hỏi đã nằm trên server (chỉ thiếu câu trả lời) → thử lại bằng /hints.
export const isReplyFailure = error => error?.code?.startsWith('LLM_') || error?.code === 'CHAT_CHANGED';

const realClient = {
  listSessions: ({ limit = 20, offset = 0 } = {}) => api(`/chat/sessions?${new URLSearchParams({ limit, offset })}`),
  createSession: (topicId, title) => api('/chat/sessions', { method: 'POST', body: title ? { topicId, title } : { topicId } }),
  getMessages: (sessionId, { limit = 200, offset = 0 } = {}) => api(`/chat/sessions/${sessionId}/messages?${new URLSearchParams({ limit, offset })}`),
  sendMessage: (sessionId, content) => api(`/chat/sessions/${sessionId}/messages`, { method: 'POST', body: { content } }),
  nextHint: sessionId => api(`/chat/sessions/${sessionId}/hints`, { method: 'POST' })
};

// ---- Dữ liệu minh hoạ (chỉ chế độ xem thử) ----
const demoHints = [
  'Ví dụ minh hoạ: Bạn nhớ công thức tính biệt thức Δ như thế nào?',
  'Ví dụ minh hoạ: Tính Δ = b² − 4ac, sau đó xét dấu của Δ.',
  'Ví dụ minh hoạ: Khi Δ ≥ 0, áp dụng x = (−b ± √Δ) / (2a), với a khác 0.'
];
const demo = { sessions: [], messages: new Map(), nextSession: 1, nextMessage: 1 };
const nowIso = () => new Date().toISOString();
function demoSession(topic, title = null) {
  const session = { id: demo.nextSession++, topicId: topic.id, title, topicName: topic.name, subjectName: topic.subjectName || '', gradeLevel: topic.gradeLevel || '', chapterName: topic.chapterName || '', createdAt: nowIso(), updatedAt: nowIso() };
  demo.sessions.unshift(session);
  demo.messages.set(session.id, []);
  return session;
}
function demoMessage(sessionId, role, content, hintLevel = null) {
  const message = { id: demo.nextMessage++, sessionId, role, content, hintLevel, isFullSolution: false, tokenCount: null, createdAt: nowIso() };
  demo.messages.get(sessionId).push(message);
  const session = demo.sessions.find(s => s.id === sessionId);
  session.updatedAt = nowIso();
  demo.sessions.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  return message;
}
const pause = () => new Promise(resolve => setTimeout(resolve, 350));
const demoClient = {
  seed(topics) {
    if (demo.sessions.length || !topics.length) return;
    topics.slice(0, 3).reverse().forEach(topic => demoSession(topic, topic.name));
  },
  async listSessions() { return { sessions: [...demo.sessions], limit: 20, offset: 0, hasMore: false }; },
  async createSession(topicId, title, topics) { return { session: demoSession(topics.find(t => t.id === topicId) || topics[0], title) }; },
  async getMessages(sessionId) {
    const session = demo.sessions.find(s => s.id === sessionId);
    if (!session) throw Object.assign(new Error('Không tìm thấy phiên chat này.'), { code: 'CHAT_SESSION_NOT_FOUND', status: 404 });
    const messages = demo.messages.get(sessionId);
    if (!messages.length && session.title) {
      demoMessage(sessionId, 'assistant', 'Ví dụ minh hoạ: Mình sẽ gợi ý từng bước để bạn tự giải nhé.', 1);
      demoMessage(sessionId, 'user', 'Làm sao tìm nghiệm của ax² + bx + c = 0?');
    }
    return { session, messages: [...demo.messages.get(sessionId)], limit: 200, offset: 0, hasMore: false };
  },
  async sendMessage(sessionId, content) {
    const userMessage = demoMessage(sessionId, 'user', content);
    const session = demo.sessions.find(s => s.id === sessionId);
    if (!session.title) session.title = content.length > 60 ? `${content.slice(0, 57)}…` : content;
    await pause();
    return { session, userMessage, assistantMessage: demoMessage(sessionId, 'assistant', demoHints[0], 1) };
  },
  async nextHint(sessionId) {
    const { received } = hintState(demo.messages.get(sessionId));
    if (received >= MAX_HINT_LEVEL) throw Object.assign(new Error('Bạn đã nhận đủ 3 mức gợi ý cho câu hỏi này.'), { code: 'HINT_LIMIT_REACHED', status: 409 });
    await pause();
    const level = Math.max(received, 0) + 1;
    return { session: demo.sessions.find(s => s.id === sessionId), userMessage: null, assistantMessage: demoMessage(sessionId, 'assistant', demoHints[level - 1], level) };
  },
  demoSolution(sessionId) {
    return demoMessage(sessionId, 'assistant', 'Lời giải đầy đủ — minh hoạ: Với x² − 5x + 6 = 0, Δ = 25 − 24 = 1. Hai nghiệm là (5 ± 1)/2, tức x = 2 hoặc x = 3.');
  }
};

// Tải toàn bộ tin của một phiên (API trả tối đa 200 tin mỗi lần).
export async function loadHistory(client, sessionId, { pageSize = 200, maxPages = 5 } = {}) {
  let result = await client.getMessages(sessionId, { limit: pageSize, offset: 0 });
  const messages = [...result.messages];
  for (let page = 1; result.hasMore && page < maxPages; page++) {
    result = await client.getMessages(sessionId, { limit: pageSize, offset: page * pageSize });
    messages.push(...result.messages);
  }
  return { session: result.session, messages };
}

// Trang chat luôn gọi qua đây để không phải biết đang ở chế độ nào.
export function chatClient(topics = []) {
  if (!isPreview()) return { ...realClient, preview: false };
  demoClient.seed(topics);
  return {
    preview: true,
    listSessions: demoClient.listSessions,
    createSession: (topicId, title) => demoClient.createSession(topicId, title, topics),
    getMessages: demoClient.getMessages,
    sendMessage: demoClient.sendMessage,
    nextHint: demoClient.nextHint,
    demoSolution: demoClient.demoSolution
  };
}
