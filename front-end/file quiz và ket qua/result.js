import { api, ApiError } from '../api.js';
import { getSession } from '../session.js';
import { getLastQuizId, getPreviewQuizResult } from '../quiz-result-state.js';
import { el, link, heading, panel, badge, button, notice } from '../components/ui.js';

const answerKeys = new Set(['A', 'B', 'C', 'D']);

function validId(value) {
  const text = String(value ?? '');
  const number = Number(text);
  return /^[1-9]\d*$/.test(text) && Number.isSafeInteger(number) && number <= 2 ** 31 - 1 ? number : null;
}

function formatScore(score) {
  return new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 }).format(score);
}

function formatDate(value) {
  const date = new Date(value);
  return value && !Number.isNaN(date.getTime())
    ? new Intl.DateTimeFormat('vi-VN', { dateStyle: 'long', timeStyle: 'short' }).format(date)
    : 'Thời gian hoàn thành chưa có';
}

function validateResult(result, expectedId = null) {
  if (!result || result.status !== 'completed' || !Number.isSafeInteger(result.quizId) || result.quizId <= 0
    || (expectedId !== null && result.quizId !== expectedId)
    || !Number.isSafeInteger(result.topicId) || result.topicId <= 0
    || !Number.isFinite(result.score) || result.score < 0 || result.score > 100
    || !Number.isSafeInteger(result.correctCount) || result.correctCount < 0 || result.correctCount > 5
    || result.totalCount !== 5 || !Array.isArray(result.questions) || result.questions.length !== 5) {
    throw new ApiError('Kết quả từ máy chủ chưa hợp lệ. Vui lòng tải lại bài.');
  }

  const seen = new Set();
  let countedCorrect = 0;
  for (const [index, question] of result.questions.entries()) {
    if (!question || !Number.isSafeInteger(question.id) || question.id <= 0 || seen.has(question.id)
      || question.position !== index + 1 || typeof question.questionText !== 'string' || !question.questionText.trim()
      || !question.options || ![...answerKeys].every(key => typeof question.options[key] === 'string' && question.options[key].trim())
      || !answerKeys.has(question.userAnswer) || !answerKeys.has(question.correctAnswer)
      || typeof question.isCorrect !== 'boolean' || typeof question.explanation !== 'string' || !question.explanation.trim()) {
      throw new ApiError('Chi tiết câu trả lời từ máy chủ chưa hợp lệ. Vui lòng tải lại kết quả.');
    }
    if (question.isCorrect !== (question.userAnswer === question.correctAnswer)) {
      throw new ApiError('Dữ liệu chấm điểm từ máy chủ chưa nhất quán.');
    }
    if (question.isCorrect) countedCorrect++;
    seen.add(question.id);
  }
  if (countedCorrect !== result.correctCount || Math.abs(result.score - (countedCorrect / 5) * 100) > 0.01) {
    throw new ApiError('Điểm tổng kết không khớp với chi tiết bài làm. Vui lòng tải lại.');
  }
  return result;
}

function resultOption(question, key) {
  const isCorrectAnswer = key === question.correctAnswer;
  const isUserAnswer = key === question.userAnswer;
  const classNames = ['result-option'];
  if (isCorrectAnswer) classNames.push('correct-answer');
  if (isUserAnswer && !isCorrectAnswer) classNames.push('selected-wrong');
  return el('div', { className: classNames.join(' '), 'data-option-key': key },
    el('span', { className: 'result-option-key' }, key),
    el('span', { className: 'result-option-text' }, question.options[key]),
    el('span', { className: 'result-option-tags' },
      isCorrectAnswer ? badge('Đáp án đúng', 'success') : null,
      isUserAnswer ? badge(isCorrectAnswer ? 'Bạn đã chọn' : 'Bạn chọn', isCorrectAnswer ? 'success' : 'warning') : null));
}

function resultQuestion(question, index) {
  return el('article', { className: `result-item ${question.isCorrect ? 'correct' : 'wrong'}` },
    el('div', { className: 'result-question-heading' },
      el('h3', {}, `Câu ${index + 1}. ${question.questionText}`),
      badge(question.isCorrect ? 'Trả lời đúng' : 'Trả lời chưa đúng', question.isCorrect ? 'success' : 'warning')),
    el('div', { className: 'result-options' }, ...['A', 'B', 'C', 'D'].map(key => resultOption(question, key))),
    el('div', { className: 'result-answer-summary' },
      el('p', {}, el('strong', {}, 'Bạn đã chọn: '), `${question.userAnswer}. ${question.options[question.userAnswer]}`),
      el('p', {}, el('strong', {}, 'Đáp án đúng: '), `${question.correctAnswer}. ${question.options[question.correctAnswer]}`)),
    el('div', { className: 'result-explanation' },
      el('h4', {}, 'Giải thích'),
      el('p', {}, question.explanation)));
}

function resultView(result, preview) {
  const score = formatScore(result.score);
  const scorePercent = Math.max(0, Math.min(100, result.score));
  const overview = panel('Tổng kết bài luyện tập',
    el('div', { className: 'result-overview' },
      el('div', { className: 'result-score' },
        el('strong', {}, score),
        el('span', {}, '/ 100 điểm'),
        el('div', { className: 'result-score-track', role: 'img', 'aria-label': `Điểm số ${score} trên 100` },
          el('span', { style: `width:${scorePercent}%` }))),
      el('div', { className: 'result-summary-grid' },
        el('div', { className: 'result-summary-item' }, el('strong', {}, `${result.correctCount}/5`), el('span', {}, 'Câu đúng')),
        el('div', { className: 'result-summary-item' }, el('strong', {}, `${5 - result.correctCount}/5`), el('span', {}, 'Câu cần xem lại')),
        el('div', { className: 'result-summary-item' }, el('strong', {}, '5'), el('span', {}, 'Tổng số câu')))),
    el('p', { className: 'result-completed-at' }, `Hoàn thành: ${formatDate(result.completedAt)}`));
  overview.classList.add('result-overview-panel');

  const actions = panel('Học tiếp',
    el('p', {}, 'Dựa vào những câu chưa đúng, bạn có thể luyện lại chủ đề hoặc trao đổi với gia sư AI.'),
    el('div', { className: 'result-actions' },
      link('Luyện tập lại', `#practice?topic=${result.topicId}`, 'button primary'),
      link('Hỏi gia sư AI', `#chat?topic=${result.topicId}`, 'button ghost'),
      link('Về dashboard', '#dashboard', 'button secondary')));
  actions.classList.add('result-next-panel');

  return el('div', { className: 'results-page' },
    heading('Kết quả luyện tập', 'Xem điểm số, đối chiếu từng lựa chọn và đọc giải thích cho mỗi câu.'),
    preview ? notice('Kết quả minh họa trong chế độ xem thử, không được lưu vào tài khoản.', 'warning') : null,
    el('div', { className: 'result-top-grid' }, overview, actions),
    el('div', { className: 'result-list-heading' },
      el('h2', {}, 'Đáp án và lời giải'),
      badge(`${result.questions.filter(item => item.isCorrect).length} câu đúng · ${result.questions.length} câu`, 'neutral')),
    el('div', { className: 'result-list' }, ...result.questions.map(resultQuestion)));
}

export function renderResults() {
  const preview = getSession().reason === 'preview';
  const params = new URLSearchParams(location.hash.split('?')[1]);
  const requested = params.get('quiz');
  const id = validId(requested) || (requested === null ? getLastQuizId() : null);
  const root = el('div', { className: 'results-page' }, heading('Kết quả luyện tập', 'Kết quả chỉ hiển thị sau khi bài được máy chủ chấm hoàn tất.'));

  if (preview && getPreviewQuizResult()) {
    root.replaceChildren(resultView(getPreviewQuizResult(), true));
    return root;
  }
  if (!id || preview) {
    root.append(el('div', { className: 'empty-state' },
      el('p', {}, 'Chưa có bài luyện tập đã nộp để hiển thị kết quả.'),
      link('Mở bài luyện tập', '#practice', 'button primary')));
    return root;
  }

  const status = el('div', { className: 'result-load-status', role: 'status', 'aria-live': 'polite' });
  root.append(status);
  let controller = null;
  async function load() {
    controller?.abort();
    controller = new AbortController();
    status.replaceChildren(el('p', {}, 'Đang tải kết quả đã lưu…'));
    root.setAttribute('aria-busy', 'true');
    try {
      const response = await api(`/quizzes/${id}/result`, { signal: controller.signal });
      if (!root.isConnected || controller.signal.aborted) return;
      const result = validateResult(response?.result, id);
      root.replaceChildren(resultView(result, false));
    } catch (error) {
      if (error.name !== 'AbortError' && root.isConnected) {
        status.replaceChildren(notice(error.message || 'Chưa thể tải kết quả.', 'error'), button('Thử tải lại', load, 'secondary'));
      }
    } finally {
      if (root.isConnected && !controller.signal.aborted) root.removeAttribute('aria-busy');
    }
  }

  queueMicrotask(() => {
    if (!root.isConnected) return;
    const observer = new MutationObserver(() => {
      if (!root.isConnected) {
        controller?.abort();
        observer.disconnect();
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    load();
  });
  return root;
}