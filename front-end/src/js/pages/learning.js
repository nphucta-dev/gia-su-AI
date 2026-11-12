import { el, link, heading, panel, badge, button, notice } from '../components/ui.js';
import { topics } from '../data.js';            // vẫn dùng cho dashboard (dữ liệu minh họa)
import { loadCatalog } from '../catalog.js';

export function renderHome() {
 const search = el('input', { className: 'input', type: 'search', placeholder: 'Tìm chủ đề học tập…', 'aria-label': 'Tìm chủ đề' });
 const aside = el('aside', { className: 'panel subject-panel', hidden: true });
 const body = el('div', { role: 'status' }, 'Đang tải danh mục môn học…');
 let subjects = [];
 let selectedId = null;
 const current = () => subjects.find(s => s.id === selectedId) || subjects[0];
 const topicRow = t => el('article', { className: 'topic-row' },
  el('div', {}, el('h3', {}, t.name), el('p', {}, t.description || 'Chưa có mô tả.')),
  el('div', { className: 'topic-actions' }, link('Hỏi gia sư', `#chat?topic=${t.id}`, 'button primary small'), link('Luyện tập', `#practice?topic=${t.id}`, 'button ghost small')));

 function drawAside() {
  const subject = current();
  const count = subject.chapters.reduce((n, c) => n + c.topics.length, 0);
  aside.replaceChildren(
   el('div', { className: 'subject-symbol', 'aria-hidden': 'true' }, subject.name.charAt(0).toUpperCase()),
   el('h2', {}, subject.name), el('p', {}, `${subject.gradeLevel} · ${count} chủ đề`),
   el('div', { className: 'spacer' }), badge('Đang mở', 'success'),
   el('p', { className: 'subject-note' }, 'Học bằng gợi ý, tự tìm lời giải và luyện tập theo chủ đề.'),
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
  if (!subjects.length) {
   aside.hidden = true; search.disabled = true;
   body.replaceChildren(el('div', { className: 'empty-state', role: 'status' }, 'Chưa có môn học hoặc chủ đề nào được mở. Vui lòng quay lại sau.'));
   return;
  }
  aside.hidden = false; search.disabled = false;
  drawAside(); drawBody();
 }
 async function load(force = false) {
  aside.hidden = true;
  body.setAttribute('role', 'status');
  body.replaceChildren('Đang tải danh mục môn học…');
  try {
   const result = await loadCatalog({ force });
   if (!root.isConnected) return;
   subjects = result; draw();
  } catch (error) {
   if (!root.isConnected) return;
   body.removeAttribute('role');
   body.replaceChildren(notice(error.message, 'error'), button('Thử lại', () => load(true), 'primary'));
  }
 }
 search.addEventListener('input', () => { if (subjects.length) drawBody(); });
 const root = el('div', {}, heading('Hôm nay bạn muốn học gì?', 'Chọn môn học và chủ đề để bắt đầu. Mỗi câu hỏi là một bước hiểu sâu hơn.'),
  el('div', { className: 'catalog-layout' }, aside, el('section', {}, el('div', { className: 'panel-header' }, el('h2', {}, 'Chủ đề theo chương'), search), body)),
  el('div', { className: 'study-note' }, el('h2', {}, 'Hiểu bài theo từng bước'), el('p', {}, 'Gia sư đặt câu hỏi gợi mở trước khi hiện lời giải. Bạn có thể yêu cầu ví dụ hoặc cách giải thích đơn giản hơn.'), link('Bắt đầu phiên học', '#chat', 'button primary')));
 load();
 return root;
}
function progress(topic) { return el('div', { className: 'progress-row' }, el('div', {}, el('span', {}, topic.name), el('strong', {}, `${topic.progress}%`)), el('progress', { max: 100, value: topic.progress, 'aria-label': `Mức thành thạo ${topic.name}` })); }
export function renderDashboard() {
 return el('div', {}, heading('Tổng quan học tập', 'Nhìn lại kết quả và chọn kiến thức cần ôn tiếp.'), el('div', { className: 'stats-grid' }, ...[['08', 'Bài đã hoàn thành'], ['82%', 'Điểm trung bình'], ['12', 'Phiên trò chuyện'], ['03', 'Chủ đề đã học']].map(([n, label]) => el('div', { className: 'stat' }, el('div', { className: 'stat-value' }, n), el('p', {}, label)))), el('div', { className: 'grid-2 section-gap' }, panel('Tiến độ theo chủ đề', el('div', { className: 'stack' }, ...topics.map(progress))), panel('Chủ đề cần ôn', el('p', { className: 'helper' }, 'Ưu tiên những chủ đề có mức thành thạo dưới 60%.'), ...topics.filter(t => t.progress < 60).map(t => el('div', { className: 'activity-row' }, el('strong', {}, t.name), link('Ôn tập', '#practice', 'button secondary small'))))), panel('Hoạt động gần đây', el('div', { className: 'activity-list' }, ...[['Phương trình bậc hai', 'Luyện tập · 80 điểm', 'Hôm nay'], ['Hàm số và đồ thị', 'Hội thoại · 6 tin nhắn', 'Hôm qua']].map(([name, desc, date]) => el('div', { className: 'activity-row' }, el('div', {}, el('strong', {}, name), el('p', { className: 'helper' }, desc)), el('span', { className: 'helper' }, date))))));
}
