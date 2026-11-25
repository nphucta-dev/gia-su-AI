import { el, heading, link, panel, badge, eyebrow, inputControl } from '../components/ui.js';
import { icon, socraticPreviewCard } from '../components/icons.js';

export function renderHistory() {
  const list = el('div', { className: 'topic-list' });
  const search = inputControl({ type: 'search', placeholder: 'Tìm phiên học…', 'aria-label': 'Tìm lịch sử học tập' });
  const type = inputControl(
    { kind: 'select', 'aria-label': 'Loại hoạt động' },
    el('option', { value: 'all' }, 'Tất cả hoạt động'),
    el('option', { value: 'chat' }, 'Hội thoại'),
    el('option', { value: 'quiz' }, 'Luyện tập'),
  );
  const records = [
    { title: 'Phương trình bậc hai', description: 'Hội thoại · 6 tin nhắn', kind: 'chat', date: 'Hôm nay', href: '#chat' },
    { title: 'Phương trình bậc hai', description: 'Bài luyện tập đã hoàn thành · 80 điểm', kind: 'quiz', date: 'Hôm qua', href: '#history?result=sample' },
    { title: 'Hàm số và đồ thị', description: 'Hội thoại · 4 tin nhắn', kind: 'chat', date: 'Tuần này', href: '#chat' },
  ];
  function draw() {
    const items = records.filter(r => (type.value === 'all' || type.value === r.kind)
      && r.title.toLocaleLowerCase('vi').includes(search.value.trim().toLocaleLowerCase('vi')));
    list.replaceChildren(...items.map(r => el(
      'article',
      { className: 'topic-row' },
      el('div', {},
        badge(r.kind === 'chat' ? 'Hội thoại' : 'Luyện tập', r.kind === 'chat' ? 'primary' : 'success'),
        el('h3', {}, r.title),
        el('p', {}, r.description),
        el('small', { className: 'helper' }, r.date)),
      link('Xem lại', r.href, 'button secondary', { trailingIcon: 'arrowRight' }),
    )));
    if (!items.length) {
      list.append(el('div', { className: 'empty-state', role: 'status' }, icon('inbox', { size: 26 }), el('p', {}, 'Chưa có hoạt động phù hợp với bộ lọc.')));
    }
  }
  search.addEventListener('input', draw);
  type.addEventListener('change', draw);
  draw();
  const result = new URLSearchParams(location.hash.split('?')[1]).get('result');
  return el(
    'div',
    {},
    heading('Lịch sử học tập', 'Xem lại các cuộc hội thoại và bài luyện tập đã hoàn thành.'),
    el('div', { className: 'filter-bar' }, search, type),
    list,
    result
      ? panel('Kết quả bài luyện tập đã lưu',
        el('div', { className: 'result-score' }, el('strong', { className: 'num-enter' }, '80'), el('span', {}, '4/5 câu đúng · Phương trình bậc hai')),
        el('p', { className: 'helper' }, 'Xem lại kết quả và tiếp tục luyện tập để củng cố kiến thức.'),
        link('Làm bài luyện tập mới', '#practice', 'button primary', { trailingIcon: 'arrowRight' }))
      : null,
  );
}

export function renderIntro() {
  const pillars = [
    ['01', 'brain', 'Hỏi để tự hiểu', 'Gia sư đặt câu hỏi gợi mở và cung cấp tối đa ba mức gợi ý trước khi bạn quyết định xem lời giải đầy đủ.'],
    ['02', 'target', 'Luyện tập theo chủ đề', 'Bài trắc nghiệm 5 câu theo ba mức độ khó, chấm điểm một lần kèm giải thích chi tiết từng câu.'],
    ['03', 'trending', 'Nhìn rõ tiến bộ', 'Theo dõi số bài hoàn thành, điểm trung bình và các phiên hội thoại đã lưu theo từng môn học.'],
  ];
  return el(
    'div',
    { className: 'intro-landing' },
    el(
      'section',
      { className: 'intro-hero' },
      el(
        'div',
        { className: 'intro-copy' },
        eyebrow('Gia sư AI phương pháp Socratic', 'main'),
        el('h1', {}, 'Tự tin hiểu bài, ', el('span', { className: 'intro-em' }, 'từng bước một.')),
        el('p', {}, 'Đặt câu hỏi tiếng Việt, nhận gợi ý từng mức từ tài liệu học tập chính thống và luyện tập trắc nghiệm để nắm vững bản chất kiến thức.'),
        el('div', { className: 'page-actions' }, link('Khám phá các chủ đề', '#home', 'button primary', { trailingIcon: 'arrowRight', pulse: true })),
        el(
          'div',
          { className: 'intro-metrics', 'aria-label': 'Điểm nổi bật phương pháp học' },
          el('div', { className: 'intro-metric' }, el('strong', {}, '03 mức'), el('span', {}, 'Gợi ý Socratic tuần tự')),
          el('div', { className: 'intro-metric' }, el('strong', {}, '05 câu'), el('span', {}, 'Trắc nghiệm mỗi lượt ôn')),
          el('div', { className: 'intro-metric' }, el('strong', {}, '100%'), el('span', {}, 'Đối chiếu nguồn học tập')),
        ),
      ),
      el('div', { className: 'intro-visual' }, socraticPreviewCard()),
    ),
    el(
      'section',
      { className: 'intro-pillars', 'aria-label': 'Tính năng học tập' },
      ...pillars.map(([num, ic, title, desc]) => el(
        'article',
        { className: 'intro-pillar reveal' },
        el('div', { className: 'intro-pillar-num' }, icon(ic, { size: 15 }), el('span', {}, num)),
        el('h3', {}, title),
        el('p', {}, desc),
      )),
    ),
  );
}
