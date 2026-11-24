import { el, link, heading, panel, badge, button, notice, field } from '../components/ui.js';
import { loadCatalog } from '../catalog.js';
import { getSession } from '../session.js';
import { accountView, activityRow, formatScore, loadDashboard } from '../account-data.js';

export function renderHome() {
 const search = el('input', { className: 'input', type: 'search', placeholder: 'Tìm chủ đề học tập…', 'aria-label': 'Tìm chủ đề' });
 const grade = el('select', { className: 'select', disabled: true }, el('option', { value: '' }, 'Tất cả cấp học'));
 const aside = el('aside', { className: 'panel subject-panel', hidden: true });
 const body = el('div', { role: 'status' }, 'Đang tải danh mục môn học…');
 let subjects = [];
 let selectedId = null;
 let loadVersion = 0;
 const current = () => subjects.find(s => s.id === selectedId) || subjects[0];
 const topicRow = t => el('article', { className: 'topic-row' },
  el('div', {}, el('h3', {}, t.name), el('p', {}, t.description || 'Chưa có mô tả.')),
  el('div', { className: 'topic-actions' }, link('Hỏi gia sư', `#chat?topic=${t.id}`, 'button primary small'), link('Luyện tập', `#practice?topic=${t.id}`, 'button ghost small'), link('Xem tài liệu', `#documents?topic=${t.id}`, 'button ghost small')));

 function drawAside() {
  const subject = current();
  const count = subject.chapters.reduce((n, c) => n + c.topics.length, 0);
  aside.replaceChildren(
   el('div', { className: 'subject-symbol', 'aria-hidden': 'true' }, subject.name.charAt(0).toUpperCase()),
   el('h2', {}, subject.name), el('p', {}, `${subject.gradeLevel} · ${count} chủ đề`),
   el('div', { className: 'spacer' }), badge('Đang mở', 'success'),
   el('p', { className: 'subject-note' }, 'Học bằng gợi ý, tự tìm lời giải và luyện tập theo chủ đề.'),
   link('Xem tài liệu', `#documents?subject=${subject.id}`, 'button ghost small'),
   subjects.length > 1 ? el('div', { className: 'stack' }, ...subjects.map(s => button(`${s.name} · ${s.gradeLevel}`, () => { selectedId = s.id; draw(); }, s.id === subject.id ? 'primary small' : 'ghost small'))) : null);
 }
 function drawBody() {
  const query = search.value.trim().toLocaleLowerCase('vi');
  const groups = current().chapters
   .map(c => ({ name: c.name, topics: c.topics.filter(t => `${t.name} ${t.description || ''}`.toLocaleLowerCase('vi').includes(query)) }))
   .filter(c => c.topics.length);
  body.removeAttribute('role');
  body.replaceChildren(...(groups.length
   ? groups.map(c => el('div', { className: 'section-gap' }, el('h3', {}, c.name), el('div', { className: 'topic-list' }, ...c.topics.map(topicRow))))
   : [el('div', { className: 'empty-state', role: 'status' }, 'Không tìm thấy chủ đề. Thử từ khoá khác.')]));
 }
 function draw() {
  body.removeAttribute('role');
  if (!subjects.length) {
   aside.hidden = true; search.disabled = true;
   body.replaceChildren(el('div', { className: 'empty-state', role: 'status' }, grade.value
    ? 'Chưa có môn học hoặc chủ đề nào được mở cho cấp học này.'
    : 'Chưa có môn học hoặc chủ đề nào được mở. Vui lòng quay lại sau.'));
   return;
  }
  aside.hidden = false; search.disabled = false;
  drawAside(); drawBody();
 }
 async function load(force = false) {
  const requestVersion = ++loadVersion;
  const gradeLevel = grade.value;
  aside.hidden = true;
  search.disabled = true;
  root.setAttribute('aria-busy', 'true');
  body.setAttribute('role', 'status');
  body.replaceChildren('Đang tải danh mục môn học…');
  try {
   const result = await loadCatalog({ force, gradeLevel });
   if (!root.isConnected || requestVersion !== loadVersion) return;
   if (!gradeLevel) {
    const levels = [...new Set(result.map(subject => subject.gradeLevel).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'vi'));
    grade.replaceChildren(el('option', { value: '' }, 'Tất cả cấp học'), ...levels.map(level => el('option', { value: level }, level)));
   }
   if (!result.some(subject => subject.id === selectedId)) selectedId = result[0]?.id ?? null;
   subjects = result; draw();
  } catch (error) {
   if (!root.isConnected || requestVersion !== loadVersion) return;
   body.removeAttribute('role');
   body.replaceChildren(notice(error.message, 'error'), button('Thử lại', () => load(true), 'primary'));
  } finally {
   if (root.isConnected && requestVersion === loadVersion) {
    grade.disabled = false;
    root.removeAttribute('aria-busy');
   }
  }
 }
 grade.addEventListener('change', () => load());
 search.addEventListener('input', () => { if (subjects.length) drawBody(); });
 const root = el('div', { className: 'catalog-page' }, heading('Hôm nay bạn muốn học gì?', 'Chọn môn học và chủ đề để bắt đầu. Mỗi câu hỏi là một bước hiểu sâu hơn.'),
  el('div', { className: 'catalog-filters' }, field('Cấp học', grade)),
  el('div', { className: 'catalog-layout' }, aside, el('section', {}, el('div', { className: 'panel-header' }, el('h2', {}, 'Chủ đề theo chương'), search), body)),
  el('div', { className: 'study-note' }, el('h2', {}, 'Hiểu bài theo từng bước'), el('p', {}, 'Gia sư đặt câu hỏi gợi mở trước khi hiện lời giải. Bạn có thể yêu cầu ví dụ hoặc cách giải thích đơn giản hơn.'), link('Bắt đầu phiên học', '#chat', 'button primary')));
 load();
 return root;
}
function progress(topic) {
 return el('div', { className: 'progress-row' },
  el('div', {}, el('span', {}, topic.subjectName ? `${topic.subjectName} · ${topic.name}` : topic.name), el('strong', {}, `${formatScore(topic.masteryPercent)}%`)),
  el('progress', { max: 100, value: topic.masteryPercent, 'aria-label': `Mức thành thạo ${topic.name}` }));
}
export function renderDashboard() {
 const content = el('div', { role: 'status', 'aria-live': 'polite' });
 const root = el('div', { className: 'dashboard-page' }, heading('Tổng quan học tập', 'Kết quả và tiến độ được lưu cho tài khoản của bạn.'), content);
 const view = accountView(root);
 let pending = false;
 async function load() {
  if (pending || !view.current()) return;
  pending = true; root.setAttribute('aria-busy', 'true');
  content.replaceChildren(el('p', {}, 'Đang tải số liệu học tập…'));
  try {
   const data = await loadDashboard({ signal: view.signal });
   if (!view.current()) return;
   const { stats } = data;
   const values = [[String(stats.totalQuizzes), 'Bài đã hoàn thành'], [`${formatScore(stats.averageScore)}%`, 'Điểm trung bình'],
    [String(stats.totalChatSessions), 'Phiên trò chuyện'], [String(data.progress.length), 'Chủ đề đã học']];
   const empty = text => el('div', { className: 'empty-state', role: 'status' }, text);
   content.replaceChildren(
    el('section', { className: 'stats-grid', 'aria-label': 'Thống kê học tập' }, ...values.map(([value, label]) =>
     el('div', { className: 'stat' }, el('div', { className: 'stat-value' }, value), el('p', {}, label)))),
    el('div', { className: 'grid-2 section-gap' },
     panel('Tiến độ theo chủ đề', data.progress.length ? el('div', { className: 'stack' }, ...data.progress.map(progress)) : empty('Bạn chưa có kết quả luyện tập.')),
     panel('Chủ đề cần ôn', data.review.length ? el('div', { className: 'stack' }, ...data.review.map(topic =>
      el('div', { className: 'activity-row' }, el('div', {}, el('strong', {}, topic.name), el('p', { className: 'helper' }, `${formatScore(topic.masteryPercent)}% thành thạo`)),
       link('Ôn tập', `#practice?topic=${topic.topicId}`, 'button secondary small')))) : empty('Chưa có chủ đề cần ôn.'))),
    panel('Hoạt động gần đây', data.records.length ? el('div', { className: 'activity-list' }, ...data.records.slice(0, 5).map(activityRow)) : empty('Bạn chưa có hoạt động học tập.'),
     link('Xem toàn bộ lịch sử', '#history', 'button ghost small')));
  } catch (error) {
   if (error.name !== 'AbortError' && view.current()) content.replaceChildren(notice(error.message || 'Chưa thể tải số liệu học tập.', 'error'), button('Tải lại số liệu', load));
  } finally { pending = false; if (view.current()) root.removeAttribute('aria-busy'); }
 }
 queueMicrotask(() => {
  if (!view.current()) return;
  if (getSession().reason === 'preview') content.replaceChildren(notice('Đăng nhập tài khoản thật để xem số liệu học tập.', 'warning'), link('Đăng nhập', '#login'));
  else load();
 });
 return root;
}
