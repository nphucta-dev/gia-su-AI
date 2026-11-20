import { getSession } from '../session.js';
import { loadDashboardData } from '../dashboard-data.js';
import { el, link, heading, panel, badge, button, notice } from '../components/ui.js';

function formatPercent(value) {
  return `${new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 }).format(value)}%`;
}

function formatDate(value) {
  const date = new Date(value);
  return value && !Number.isNaN(date.getTime())
    ? new Intl.DateTimeFormat('vi-VN', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
    : 'Chưa có thời gian';
}

function statCard(value, label, description) {
  return el('article', { className: 'stat dashboard-stat' },
    el('p', { className: 'dashboard-stat-label' }, label),
    el('strong', { className: 'stat-value dashboard-stat-value' }, value),
    el('p', { className: 'dashboard-stat-description' }, description));
}

function progressRow(topic) {
  const label = [topic.subjectName, topic.chapterName, topic.name].filter(Boolean).join(' · ');
  return el('div', { className: 'dashboard-progress-row' },
    el('div', { className: 'dashboard-progress-heading' },
      el('span', {}, label),
      el('strong', {}, formatPercent(topic.masteryPercent))),
    el('progress', { max: 100, value: topic.masteryPercent, 'aria-label': `Mức thành thạo ${topic.name}` }),
    el('p', { className: 'helper' }, `${topic.totalQuizzes} bài đã hoàn thành · ${topic.correctCount}/${topic.totalCount} câu đúng`));
}

function reviewRow(topic) {
  const subtitle = [topic.subjectName, topic.chapterName].filter(Boolean).join(' · ');
  return el('article', { className: 'dashboard-review-row' },
    el('div', { className: 'dashboard-review-copy' },
      el('strong', {}, topic.name),
      subtitle ? el('p', { className: 'helper' }, subtitle) : null,
      el('p', { className: 'helper' }, `${topic.totalQuizzes} bài · ${topic.correctCount}/${topic.totalCount} câu đúng`)),
    el('div', { className: 'dashboard-review-actions' },
      badge(formatPercent(topic.masteryPercent), topic.masteryPercent < 60 ? 'warning' : 'neutral'),
      link('Ôn tập', `#practice?topic=${topic.topicId}`, 'button secondary small')));
}

function recentSessionRow(session) {
  const title = session.title || `Phiên về ${session.topicName || 'chủ đề đã chọn'}`;
  return el('a', { href: `#chat?session=${session.id}`, className: 'dashboard-session-row' },
    el('span', { className: 'dashboard-session-icon', 'aria-hidden': 'true' }, '↗'),
    el('span', { className: 'dashboard-session-copy' },
      el('strong', {}, title),
      el('span', { className: 'helper' }, [session.subjectName, session.chapterName, session.topicName].filter(Boolean).join(' · '))),
    el('time', {}, formatDate(session.updatedAt)));
}

export function renderDashboard() {
  const root = el('div', { className: 'dashboard-page' },
    heading('Tổng quan học tập', 'Số liệu được tổng hợp từ các bài quiz, tiến độ và phiên chat đã lưu của bạn.'));
  const status = el('div', { className: 'dashboard-status', role: 'status', 'aria-live': 'polite' });
  const content = el('div', { className: 'dashboard-content' });
  root.append(status, content);

  let controller = null;
  let loading = false;
  let observer;
  const isCurrent = () => root.isConnected && !controller?.signal.aborted;

  function draw(data) {
    const { stats } = data;
    const average = stats.averageScore === null ? '—' : formatPercent(stats.averageScore);
    const statsGrid = el('section', { className: 'stats-grid dashboard-stats', 'aria-label': 'Thống kê học tập' },
      statCard(String(stats.totalQuizzes), 'Bài quiz hoàn thành', 'Chỉ tính bài đã được máy chủ chấm'),
      statCard(average, 'Điểm trung bình', stats.totalQuizzes ? 'Tính theo tổng số câu đã chấm' : 'Chưa có bài quiz hoàn thành'),
      statCard(String(stats.chatSessions), 'Phiên chat', 'Các phiên hội thoại đã lưu'),
      statCard(String(stats.studiedTopics), 'Chủ đề đã luyện', 'Chủ đề có kết quả quiz'));

    const progressPanel = panel('Mức thành thạo theo chủ đề');
    progressPanel.classList.add('dashboard-panel');
    if (data.progress.length) {
      progressPanel.append(el('div', { className: 'dashboard-progress-list' }, ...data.progress.map(progressRow)));
    } else {
      progressPanel.append(el('div', { className: 'empty-state compact' },
        el('p', {}, 'Bạn chưa có kết quả quiz để thống kê tiến độ.'),
        link('Bắt đầu luyện tập', '#practice', 'button primary small')));
    }

    const reviewPanel = panel('Chủ đề nên ôn tiếp');
    reviewPanel.classList.add('dashboard-panel');
    if (data.reviewTopics.length) {
      reviewPanel.append(el('div', { className: 'dashboard-review-list' }, ...data.reviewTopics.slice(0, 5).map(reviewRow)));
    } else {
      reviewPanel.append(el('div', { className: 'empty-state compact' }, 'Chưa có chủ đề cần ôn. Hãy hoàn thành một bài quiz để bắt đầu theo dõi.'));
    }

    const sessionsPanel = panel('Phiên chat gần đây');
    sessionsPanel.classList.add('dashboard-panel', 'dashboard-sessions-panel');
    if (data.recentSessions.length) {
      sessionsPanel.append(el('div', { className: 'dashboard-session-list' }, ...data.recentSessions.map(recentSessionRow)));
    } else {
      sessionsPanel.append(el('div', { className: 'empty-state compact' },
        el('p', {}, 'Bạn chưa có phiên chat nào được lưu.'),
        link('Hỏi gia sư AI', '#chat', 'button primary small')));
    }

    const note = data.catalogUnavailable
      ? notice('Chưa tải được tên một số chủ đề. Số liệu tiến độ vẫn được lấy từ máy chủ; tên chủ đề được hiển thị theo mã.', 'warning')
      : null;
    content.replaceChildren(statsGrid, note,
      el('div', { className: 'dashboard-panels' }, progressPanel, reviewPanel),
      sessionsPanel);
  }

  async function load() {
    if (loading) return;
    loading = true;
    controller?.abort();
    controller = new AbortController();
    status.replaceChildren(el('p', {}, 'Đang tải số liệu học tập…'));
    content.replaceChildren();
    root.setAttribute('aria-busy', 'true');
    try {
      const data = await loadDashboardData({ signal: controller.signal });
      if (!isCurrent()) return;
      status.replaceChildren();
      draw(data);
    } catch (error) {
      if (error.name !== 'AbortError' && isCurrent()) {
        status.replaceChildren(notice(error.message || 'Chưa thể tải dashboard.', 'error'), button('Tải lại số liệu', load, 'secondary'));
      }
    } finally {
      loading = false;
      if (isCurrent()) root.removeAttribute('aria-busy');
    }
  }

  if (getSession().reason === 'preview') {
    status.replaceChildren(notice('Đang xem thử: dashboard không hiển thị số liệu cá nhân giả lập. Đăng nhập tài khoản thật và hoàn thành quiz/chat để xem dữ liệu được lưu.', 'warning'));
    content.replaceChildren(el('div', { className: 'dashboard-empty-grid' },
      statCard('—', 'Bài quiz hoàn thành', 'Chưa có dữ liệu tài khoản thật'),
      statCard('—', 'Điểm trung bình', 'Chưa có dữ liệu tài khoản thật'),
      statCard('—', 'Phiên chat', 'Chưa có dữ liệu tài khoản thật'),
      statCard('—', 'Chủ đề đã luyện', 'Chưa có dữ liệu tài khoản thật')));
  } else {
    queueMicrotask(() => {
      if (!root.isConnected) return;
      observer = new MutationObserver(() => {
        if (!root.isConnected) {
          controller?.abort();
          observer.disconnect();
        }
      });
      observer.observe(document.body, { childList: true, subtree: true });
      load();
    });
  }

  return root;
}