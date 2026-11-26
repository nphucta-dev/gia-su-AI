import { el, heading, link, button, notice, eyebrow, inputControl } from '../components/ui.js';
import { icon, socraticPreviewCard } from '../components/icons.js';
import { skeletonState } from '../components/motion.js';
import { getSession } from '../session.js';
import { accountView, activityRow, loadActivity } from '../account-data.js';

export function renderHistory() {
  const list = el('div', { className: 'topic-list' });
  const search = inputControl({ type: 'search', placeholder: 'Tìm phiên học…', 'aria-label': 'Tìm lịch sử học tập' });
  const type = inputControl(
    { kind: 'select', 'aria-label': 'Loại hoạt động' },
    el('option', { value: 'all' }, 'Tất cả hoạt động'),
    el('option', { value: 'chat' }, 'Hội thoại'),
    el('option', { value: 'quiz' }, 'Luyện tập'),
  );
  const root = el(
    'div',
    {},
    heading('Lịch sử học tập', 'Các cuộc hội thoại và bài luyện tập được lưu cho tài khoản của bạn.'),
    el('div', { className: 'filter-bar' }, search, type),
    list,
  );
  const view = accountView(root);
  let records = [], pending = false, loaded = false;

  function draw() {
    if (!loaded) return;
    const query = search.value.trim().toLocaleLowerCase('vi');
    const items = records.filter(record => (type.value === 'all' || type.value === record.kind)
      && `${record.title} ${record.subjectName} ${record.topicName}`.toLocaleLowerCase('vi').includes(query));
    list.replaceChildren(...items.map(activityRow));
    if (!items.length) {
      list.append(el(
        'div',
        { className: 'empty-state', role: 'status' },
        icon('inbox', { size: 26 }),
        el('p', {}, records.length ? 'Chưa có hoạt động phù hợp với bộ lọc.' : 'Bạn chưa có hoạt động học tập.'),
      ));
    }
  }

  async function load() {
    if (pending || !view.current()) return;
    pending = true; loaded = false; root.setAttribute('aria-busy', 'true');
    list.replaceChildren(skeletonState('Đang tải lịch sử học tập…', 'list'));
    try {
      const data = await loadActivity({ signal: view.signal });
      if (!view.current()) return;
      records = data.records; loaded = true; draw();
    } catch (error) {
      if (error.name !== 'AbortError' && view.current()) {
        list.replaceChildren(notice(error.message || 'Chưa thể tải lịch sử học tập.', 'error'), button('Tải lại lịch sử', load, 'primary'));
      }
    } finally {
      pending = false;
      if (view.current()) root.removeAttribute('aria-busy');
    }
  }

  search.addEventListener('input', draw);
  type.addEventListener('change', draw);
  queueMicrotask(() => {
    if (!view.current()) return;
    if (getSession().reason === 'preview') {
      list.replaceChildren(notice('Đăng nhập tài khoản thật để xem lịch sử học tập.', 'warning'), link('Đăng nhập', '#login'));
    } else {
      load();
    }
  });
  return root;
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
