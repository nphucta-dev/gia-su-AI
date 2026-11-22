import { api, ApiError } from '../api.js';
import { getAccessToken, getSession } from '../session.js';
import { el, heading, notice, button, link } from '../components/ui.js';

let activeController;
const number = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });

function validateDashboard(result) {
 const stats = result?.dashboard;
 if (!stats || !Number.isSafeInteger(stats.totalQuizzes) || stats.totalQuizzes < 0
  || !Number.isSafeInteger(stats.totalChatSessions) || stats.totalChatSessions < 0
  || typeof stats.averageScore !== 'number' || !Number.isFinite(stats.averageScore)
  || stats.averageScore < 0 || stats.averageScore > 100) {
  throw new ApiError('Thống kê từ máy chủ chưa hợp lệ. Vui lòng thử lại.', 0, 'INVALID_DASHBOARD');
 }
 return stats;
}

export function renderLiveDashboard() {
 activeController?.abort();
 const controller = new AbortController();
 activeController = controller;
 const owner = getSession().user?.id;
 const token = getAccessToken();
 let pending = false;
 const body = el('section', { className: 'dashboard-summary', 'aria-label': 'Thống kê học tập', 'aria-live': 'polite' });
 const root = el('div', { className: 'dashboard-page' },
  heading('Tổng quan học tập', 'Theo dõi bài đã hoàn thành, điểm trung bình và các phiên trò chuyện của bạn.'), body);
 const current = () => !controller.signal.aborted && root.isConnected
  && getSession().status === 'authenticated' && getSession().reason !== 'preview'
  && getSession().user?.id === owner && getAccessToken() === token;

 async function load() {
  if (pending || !current()) return;
  pending = true;
  root.setAttribute('aria-busy', 'true');
  body.replaceChildren(el('p', { className: 'notice', role: 'status' }, 'Đang tải thống kê học tập…'));
  try {
   const result = await api('/dashboard', { signal: controller.signal });
   if (!current()) return;
   const stats = validateDashboard(result);
   body.replaceChildren(el('dl', { className: 'stats-grid dashboard-stats' },
    ...[
     ['Bài đã hoàn thành', number.format(stats.totalQuizzes)],
     ['Điểm trung bình', stats.totalQuizzes === 0 ? 'Chưa có điểm' : `${number.format(stats.averageScore)}%`],
     ['Phiên trò chuyện', number.format(stats.totalChatSessions)],
    ].map(([label, value]) => el('div', { className: 'stat' }, el('dt', {}, label), el('dd', { className: 'stat-value' }, value)))));
   if (stats.totalQuizzes === 0 && stats.totalChatSessions === 0) {
    body.append(el('div', { className: 'empty-state section-gap' },
     el('p', {}, 'Bạn chưa có hoạt động học tập. Chọn một chủ đề để bắt đầu hỏi gia sư hoặc luyện tập.'),
     link('Chọn chủ đề học', '#home', 'button primary')));
   }
  } catch (error) {
   if (error.name === 'AbortError' || !current()) return;
   body.replaceChildren(notice(error.status === 403 ? `Chưa thể truy cập thống kê. ${error.message}` : error.message || 'Chưa thể tải thống kê học tập. Vui lòng thử lại.', 'error'),
    button('Thử lại', load, 'primary'));
  } finally {
   pending = false;
   if (current()) root.removeAttribute('aria-busy');
  }
 }
 queueMicrotask(() => {
  if (!current()) return;
  const observer = new MutationObserver(() => {
   if (!root.isConnected) { controller.abort(); observer.disconnect(); }
  });
  observer.observe(document.body, { childList: true, subtree: true });
  load();
 });
 return root;
}
