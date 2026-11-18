learning.js 
import { el, link, heading, panel, badge, button, notice, field } from '../components/ui.js';
import { topics } from '../data.js'; // Dữ liệu minh họa hiện chỉ dùng cho dashboard.
import { loadCatalog } from '../catalog.js';

export function renderHome() {
 const search = el('input', {
  className: 'input catalog-search', type: 'search',
  placeholder: 'Tìm tên chủ đề hoặc nội dung…',
  'aria-label': 'Tìm chủ đề'
 });
 const grade = el('select', { className: 'select', disabled: true }, el('option', { value: '' }, 'Tất cả cấp học'));
 const aside = el('aside', { className: 'panel subject-panel', hidden: true, 'aria-label': 'Chọn môn học' });
 const body = el('div', { className: 'catalog-content', role: 'status' }, 'Đang tải danh mục môn học…');
 const resultCount = el('span', { className: 'catalog-result-count', 'aria-live': 'polite' });
 let subjects = [];
 let selectedId = null;
 let loadVersion = 0;

 const current = () => subjects.find(subject => String(subject.id) === String(selectedId)) || subjects[0] || null;
 const countTopics = subject => (subject?.chapters || []).reduce((total, chapter) => total + chapter.topics.length, 0);

 const topicRow = (topic, index) => el('article', { className: 'topic-row topic-card' },
  el('div', { className: 'topic-card-main' },
   el('div', { className: 'topic-card-number', 'aria-hidden': 'true' }, String(index + 1).padStart(2, '0')),
   el('div', { className: 'topic-card-copy' },
    el('h3', {}, topic.name),
    el('p', {}, topic.description || 'Chưa có mô tả cho chủ đề này.'),
    el('div', { className: 'topic-card-meta' }, badge('Chủ đề học', 'neutral'))
   )
  ),
  el('div', { className: 'topic-actions' },
   link('Hỏi gia sư AI', `#chat?topic=${encodeURIComponent(topic.id)}`, 'button primary small'),
   link('Luyện tập', `#practice?topic=${encodeURIComponent(topic.id)}`, 'button ghost small')
  )
 );

 function drawAside() {
  const subject = current();
  if (!subject) { aside.hidden = true; return; }
  const count = countTopics(subject);
  aside.replaceChildren(
   el('div', { className: 'subject-panel-topline' }, badge('MÔN HỌC', 'neutral'), el('span', { className: 'subject-panel-level' }, subject.gradeLevel || '')),
   el('div', { className: 'subject-symbol', 'aria-hidden': 'true' }, subject.name.charAt(0).toUpperCase()),
   el('h2', {}, subject.name),
   el('p', {}, `${count} chủ đề đang mở`),
   el('div', { className: 'subject-panel-divider' }),
   el('p', { className: 'subject-note' }, 'Chọn một chủ đề để bắt đầu trao đổi với gia sư AI hoặc tự kiểm tra kiến thức.'),
   subjects.length > 1 ? el('div', { className: 'subject-switcher' },
    el('h3', {}, 'Môn học khác'),
    ...subjects.map(item => {
     const active = String(item.id) === String(subject.id);
     const switchButton = button(item.name, () => {
      selectedId = item.id;
      draw();
     }, `subject-switch-button ${active ? 'active' : ''}`);
     switchButton.setAttribute('aria-pressed', String(active));
     return switchButton;
    })
   ) : null
  );
 }

 function drawBody() {
  const subject = current();
  if (!subject) {
   resultCount.textContent = '';
   body.replaceChildren(el('div', { className: 'empty-state', role: 'status' }, 'Chưa có môn học hoặc chủ đề nào được mở. Vui lòng quay lại sau.'));
   return;
  }
  const query = search.value.trim().toLocaleLowerCase('vi');
  const groups = subject.chapters
   .map(chapter => ({
    name: chapter.name,
    topics: chapter.topics.filter(topic =>
     `${topic.name} ${topic.description || ''} ${chapter.name}`.toLocaleLowerCase('vi').includes(query)
    )
   }))
   .filter(chapter => chapter.topics.length);
  const visibleCount = groups.reduce((total, chapter) => total + chapter.topics.length, 0);
  resultCount.textContent = `${visibleCount} chủ đề`;
  body.removeAttribute('role');
  if (!groups.length) {
   body.replaceChildren(el('div', { className: 'empty-state catalog-empty', role: 'status' },
    el('div', { className: 'catalog-empty-icon', 'aria-hidden': 'true' }, '⌕'),
    el('strong', {}, 'Không tìm thấy chủ đề phù hợp'),
    el('p', {}, 'Thử từ khóa khác hoặc xóa nội dung tìm kiếm để xem toàn bộ chủ đề.')
   ));
   return;
  }
  let topicIndex = 0;
  body.replaceChildren(...groups.map(chapter => {
   const rows = chapter.topics.map(topic => topicRow(topic, topicIndex++));
   return el('section', { className: 'chapter-section' },
    el('div', { className: 'chapter-heading' },
     el('div', {}, el('span', { className: 'chapter-eyebrow' }, 'NỘI DUNG HỌC'), el('h3', {}, chapter.name)),
     badge(`${rows.length} chủ đề`, 'neutral')
    ),
    el('div', { className: 'topic-list' }, ...rows)
   );
  }));
 }

 function draw() {
  const subject = current();
  body.removeAttribute('role');
  if (!subjects.length || !subject) {
   aside.hidden = true;
   search.disabled = true;
   resultCount.textContent = '';
   body.replaceChildren(el('div', { className: 'empty-state', role: 'status' },
    grade.value ? 'Chưa có môn học hoặc chủ đề nào được mở cho cấp học này.' : 'Chưa có môn học hoặc chủ đề nào được mở. Vui lòng quay lại sau.'
   ));
   return;
  }
  aside.hidden = false;
  search.disabled = false;
  drawAside();
  drawBody();
 }

 async function load(force = false) {
  const requestVersion = ++loadVersion;
  const gradeLevel = grade.value;
  aside.hidden = true;
  search.disabled = true;
  root.setAttribute('aria-busy', 'true');
  body.setAttribute('role', 'status');
  body.replaceChildren(el('div', { className: 'catalog-loading' }, el('span', { className: 'loading-dot', 'aria-hidden': 'true' }), 'Đang tải danh mục môn học…'));
  try {
   const result = await loadCatalog({ force, gradeLevel });
   if (!root.isConnected || requestVersion !== loadVersion) return;
   if (!gradeLevel) {
    const levels = [...new Set(result.map(subject => subject.gradeLevel).filter(Boolean))]
     .sort((a, b) => a.localeCompare(b, 'vi'));
    grade.replaceChildren(
     el('option', { value: '' }, 'Tất cả cấp học'),
     ...levels.map(level => el('option', { value: level }, level))
    );
   }
   if (!result.some(subject => String(subject.id) === String(selectedId))) selectedId = result[0]?.id ?? null;
   subjects = result;
   draw();
  } catch (error) {
   if (!root.isConnected || requestVersion !== loadVersion) return;
   body.removeAttribute('role');
   body.replaceChildren(
    notice(error.message || 'Chưa thể tải danh mục môn học. Vui lòng thử lại.', 'error'),
    button('Thử tải lại', () => load(true), 'primary')
   );
  } finally {
   if (root.isConnected && requestVersion === loadVersion) {
    grade.disabled = false;
    root.removeAttribute('aria-busy');
   }
  }
 }

 grade.addEventListener('change', () => { search.value = ''; load(); });
 search.addEventListener('input', () => { if (subjects.length) drawBody(); });

 const root = el('div', { className: 'learning-home' },
  heading('Hôm nay bạn muốn học gì?', 'Chọn môn học và chủ đề phù hợp. Gia sư AI sẽ đồng hành cùng bạn trong từng bước học tập.'),
  el('div', { className: 'catalog-toolbar' },
   field('Cấp học', grade),
   field('Tìm kiếm', search)
  ),
  el('div', { className: 'catalog-layout' },
   aside,
   el('section', { className: 'catalog-main' },
    el('div', { className: 'catalog-main-heading' },
     el('div', {}, el('span', { className: 'catalog-eyebrow' }, 'DANH MỤC HỌC TẬP'), el('h2', {}, 'Chủ đề theo chương')),
     resultCount
    ),
    body
   )
  ),
  el('section', { className: 'study-note' },
   el('div', { className: 'study-note-icon', 'aria-hidden': 'true' }, '✦'),
   el('div', {}, el('h2', {}, 'Học hiểu, không chỉ học thuộc'),
    el('p', {}, 'Gia sư AI sẽ gợi mở từng bước để bạn tự tìm ra lời giải. Bạn có thể yêu cầu gợi ý, ví dụ hoặc cách giải thích đơn giản hơn.')),
   link('Bắt đầu phiên học', '#chat', 'button primary')
  )
 );
 load();
 return root;
}

function progress(topic) {
 return el('div', { className: 'progress-row' },
  el('div', {}, el('span', {}, topic.name), el('strong', {}, `${topic.progress}%`)),
  el('progress', { max: 100, value: topic.progress, 'aria-label': `Mức thành thạo ${topic.name}` })
 );
}
export function renderDashboard() {
 return el('div', {},
  heading('Tổng quan học tập', 'Nhìn lại kết quả và chọn kiến thức cần ôn tiếp.'),
  el('div', { className: 'stats-grid' },
   ...[['08', 'Bài đã hoàn thành'], ['82%', 'Điểm trung bình'], ['12', 'Phiên trò chuyện'], ['03', 'Chủ đề đã học']]
    .map(([number, label]) => el('div', { className: 'stat' }, el('div', { className: 'stat-value' }, number), el('p', {}, label))
   )
  ),
  el('div', { className: 'grid-2 section-gap' },
   panel('Tiến độ theo chủ đề', el('div', { className: 'stack' }, ...topics.map(progress))),
   panel('Chủ đề cần ôn', el('p', { className: 'helper' }, 'Ưu tiên những chủ đề có mức thành thạo dưới 60%.'),
    ...topics.filter(topic => topic.progress < 60).map(topic =>
     el('div', { className: 'activity-row' }, el('strong', {}, topic.name), link('Ôn tập', '#practice', 'button secondary small'))
    )
   )
  ),
  panel('Hoạt động gần đây', el('div', { className: 'activity-list' },
   ...[['Phương trình bậc hai', 'Luyện tập · 80 điểm', 'Hôm nay'], ['Hàm số và đồ thị', 'Hội thoại · 6 tin nhắn', 'Hôm qua']]
    .map(([name, description, date]) => el('div', { className: 'activity-row' },
     el('div', {}, el('strong', {}, name), el('p', { className: 'helper' }, description)),
     el('span', { className: 'helper' }, date)
    ))
   )
  )
 );
}
