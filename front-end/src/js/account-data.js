import { api, ApiError } from './api.js';
import { flattenTopics, loadCatalog } from './catalog.js';
import { getAccessToken, getSession, onSessionCleared } from './session.js';
import { el, link, badge } from './components/ui.js';

export function accountView(root) {
 const owner = getSession().user?.id, token = getAccessToken();
 const controller = new AbortController();
 const current = () => root.isConnected && !controller.signal.aborted
  && getSession().user?.id === owner && getAccessToken() === token;
 const unsubscribe = onSessionCleared(() => controller.abort());
 queueMicrotask(() => {
  if (!current()) { controller.abort(); unsubscribe(); return; }
  const observer = new MutationObserver(() => {
   if (!current()) { controller.abort(); observer.disconnect(); unsubscribe(); }
  });
  observer.observe(document.body, { childList: true, subtree: true });
 });
 return { current, signal: controller.signal };
}

async function pages(path, key, signal) {
 const rows = [], seen = new Set();
 for (let offset = 0; offset <= 100000;) {
  const result = await api(`${path}?limit=100&offset=${offset}`, { signal });
  const items = result?.[key];
  if (!Array.isArray(items) || typeof result.hasMore !== 'boolean'
   || items.some(item => !item || !Number.isSafeInteger(item.id) || item.id < 1 || seen.has(item.id))) {
   throw new ApiError('Dữ liệu học tập từ máy chủ chưa hợp lệ.', 0, 'INVALID_RESPONSE');
  }
  for (const item of items) { seen.add(item.id); rows.push(item); }
  if (!result.hasMore) return rows;
  if (!items.length) break;
  offset += items.length;
 }
 throw new ApiError('Chưa thể đọc đầy đủ lịch sử. Vui lòng thử lại.', 0, 'INVALID_RESPONSE');
}

export function formatDate(value) {
 const date = new Date(value);
 return value && Number.isFinite(date.getTime()) ? date.toLocaleString('vi-VN') : 'Chưa có thời gian';
}

export function formatScore(value) {
 return new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 }).format(value);
}

export async function loadActivity({ signal } = {}) {
 const [sessions, quizzes] = await Promise.all([
  pages('/chat/sessions', 'sessions', signal), pages('/quizzes', 'quizzes', signal),
 ]);
 for (const session of sessions) {
  if (!Number.isSafeInteger(session.topicId) || session.topicId < 1 || typeof session.topicName !== 'string'
   || typeof session.subjectName !== 'string' || !Number.isFinite(Date.parse(session.updatedAt))) {
   throw new ApiError('Lịch sử hội thoại từ máy chủ chưa hợp lệ.', 0, 'INVALID_RESPONSE');
  }
 }
 for (const quiz of quizzes) {
  if (!Number.isSafeInteger(quiz.topicId) || quiz.topicId < 1 || typeof quiz.topicName !== 'string'
   || typeof quiz.subjectName !== 'string' || !['completed', 'in_progress'].includes(quiz.status)
   || !Number.isFinite(Date.parse(quiz.createdAt))
   || (quiz.status === 'completed' && (!Number.isFinite(quiz.score) || quiz.score < 0 || quiz.score > 100 || !Number.isFinite(Date.parse(quiz.completedAt))))) {
   throw new ApiError('Lịch sử bài luyện tập từ máy chủ chưa hợp lệ.', 0, 'INVALID_RESPONSE');
  }
 }
 const records = [
  ...sessions.map(item => ({ id: item.id, kind: 'chat', topicId: item.topicId,
   title: item.title || item.topicName, subjectName: item.subjectName, topicName: item.topicName,
   description: 'Hội thoại đã lưu', date: item.updatedAt, href: `#chat?session=${item.id}` })),
  ...quizzes.map(item => ({ id: item.id, kind: 'quiz', topicId: item.topicId,
   title: item.topicName, subjectName: item.subjectName, topicName: item.topicName,
   description: item.status === 'completed' ? `Đã hoàn thành · ${formatScore(item.score)} điểm` : 'Đang làm · Chưa nộp đáp án',
   date: item.completedAt || item.createdAt,
   href: item.status === 'completed' ? `#results?quiz=${item.id}` : `#practice?quiz=${item.id}` })),
 ];
 records.sort((a, b) => Date.parse(b.date) - Date.parse(a.date) || b.id - a.id || a.kind.localeCompare(b.kind));
 return { records, quizzes, sessions };
}

export function activityRow(record) {
 return el('article', { className: 'topic-row activity-record', 'data-activity-kind': record.kind },
  el('div', {}, badge(record.kind === 'chat' ? 'Hội thoại' : 'Luyện tập'),
   el('h3', {}, record.title), el('p', {}, `${record.subjectName} · ${record.description}`),
   el('small', { className: 'helper' }, formatDate(record.date))),
  link(record.kind === 'quiz' && record.href.startsWith('#practice') ? 'Tiếp tục làm bài' : 'Xem lại', record.href, 'button secondary small'));
}

export async function loadDashboard({ signal } = {}) {
 const [response, progress, review, activity, catalog] = await Promise.all([
  api('/dashboard', { signal }), pages('/progress', 'progress', signal),
  pages('/progress/review-topics', 'topics', signal), loadActivity({ signal }),
  loadCatalog().then(flattenTopics).catch(() => []),
 ]);
 const stats = response?.dashboard;
 if (!stats || !Number.isSafeInteger(stats.totalQuizzes) || stats.totalQuizzes < 0
  || !Number.isSafeInteger(stats.totalChatSessions) || stats.totalChatSessions < 0
  || !Number.isFinite(stats.averageScore) || stats.averageScore < 0 || stats.averageScore > 100) {
  throw new ApiError('Thống kê từ máy chủ chưa hợp lệ.', 0, 'INVALID_RESPONSE');
 }
 const names = new Map(catalog.map(topic => [topic.id, topic]));
 for (const item of [...activity.sessions, ...activity.quizzes]) {
  names.set(item.topicId, { ...names.get(item.topicId), name: item.topicName, subjectName: item.subjectName });
 }
 const describe = item => {
  if (!Number.isSafeInteger(item.topicId) || item.topicId < 1 || !Number.isFinite(item.masteryPercent)
   || item.masteryPercent < 0 || item.masteryPercent > 100
   || !Number.isSafeInteger(item.totalQuizzes) || item.totalQuizzes < 0) {
   throw new ApiError('Tiến độ từ máy chủ chưa hợp lệ.', 0, 'INVALID_RESPONSE');
  }
  const topic = names.get(item.topicId);
  return { ...item, name: topic?.name || `Chủ đề #${item.topicId}`, subjectName: topic?.subjectName || '' };
 };
 return { stats, progress: progress.map(describe), review: review.map(describe), records: activity.records };
}
