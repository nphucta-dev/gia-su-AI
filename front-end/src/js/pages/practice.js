import { onSessionCleared } from '../session.js';
import { el, button, link, heading, panel, field, badge, confirmDialog, notice } from '../components/ui.js';
import { questions, quizPreviewId } from '../data.js';
import { loadCatalog, flattenTopics } from '../catalog.js';
import { submitQuizAnswers } from '../quiz-submission.js';

let lastResult = null;
let lastSelection = null;
const difficultyLabels = { easy: 'Dễ', medium: 'Vừa', hard: 'Khó' };
const difficulties = Object.entries(difficultyLabels);

onSessionCleared(() => {
 lastResult = null;
 lastSelection = null;
});

export function renderPractice() {
 const root = el('div', { className: 'practice-page' },
  heading('Luyện tập kiến thức', 'Chọn chủ đề và độ khó phù hợp trước khi bắt đầu.'));
 const params = new URLSearchParams(location.hash.split('?')[1]);
 const requestedValue = params.get('topic');
 const requestedId = requestedValue !== null && /^[1-9]\d*$/.test(requestedValue)
  ? Number(requestedValue)
  : null;
 const topic = el('select', { className: 'select', disabled: true, required: true },
  el('option', { value: '' }, 'Đang tải chủ đề…'));
 const difficulty = el('select', { className: 'select', disabled: true, required: true },
  el('option', { value: '' }, 'Chọn độ khó'),
  ...difficulties.map(([value, label]) => el('option', { value }, label)));
 const startButton = button('Mở bài xem thử', null, 'primary');
 startButton.type = 'submit';
 startButton.disabled = true;
 const loadStatus = el('div', { role: 'status', 'aria-live': 'polite' });
 const validationStatus = el('p', { className: 'error-text', role: 'status', 'aria-live': 'polite' });
 const form = el('form', { className: 'quiz-setup-form', novalidate: true },
  el('div', { className: 'quiz-setup-fields' },
   field('Chủ đề', topic),
   field('Độ khó', difficulty)),
  validationStatus,
  el('div', { className: 'quiz-setup-actions' }, startButton));
 const start = panel('Tạo bài luyện tập',
  el('p', {}, 'Danh mục bên dưới lấy từ hệ thống. Bài mở tiếp theo chỉ là bản xem thử giao diện và chưa gọi backend sinh quiz.'),
  loadStatus,
  form);
 start.classList.add('quiz-setup');
 root.append(start);

 let items = [];
 let loadVersion = 0;
 let submitController = null;

 window.addEventListener('hashchange', () => submitController?.abort(), { once: true });

 function selectedPayload() {
  const topicId = Number(topic.value);
  return items.some(item => item.id === topicId) && difficultyLabels[difficulty.value]
   ? { topicId, difficulty: difficulty.value }
   : null;
 }

 function updateValidity({ announce = false } = {}) {
  const selection = selectedPayload();
  startButton.disabled = !selection;
  if (selection || !announce) validationStatus.textContent = '';
  else validationStatus.textContent = 'Vui lòng chọn đầy đủ chủ đề và độ khó.';
  return selection;
 }

 function topicOptions() {
  const groups = new Map();
  for (const item of items) {
   const label = `${item.subjectName} · ${item.chapterName}`;
   if (!groups.has(label)) groups.set(label, []);
   groups.get(label).push(el('option', { value: item.id }, item.name));
  }
  return [...groups].map(([label, options]) => el('optgroup', { label }, ...options));
 }

 async function load(force = false) {
  const version = ++loadVersion;
  root.setAttribute('aria-busy', 'true');
  topic.disabled = true;
  difficulty.disabled = true;
  startButton.disabled = true;
  loadStatus.replaceChildren(el('p', {}, 'Đang tải danh sách chủ đề…'));
  try {
   const subjects = await loadCatalog({ force });
   if (!root.isConnected || version !== loadVersion) return;
   items = flattenTopics(subjects);
   if (!items.length) {
    topic.replaceChildren(el('option', { value: '' }, 'Chưa có chủ đề đang mở'));
    loadStatus.replaceChildren(notice('Hiện chưa có chủ đề nào được mở. Vui lòng quay lại sau.', 'warning'));
    return;
   }
   topic.replaceChildren(el('option', { value: '' }, 'Chọn chủ đề'), ...topicOptions());
   topic.disabled = false;
   difficulty.disabled = false;
   const requestedTopic = items.find(item => item.id === requestedId);
   const rememberedTopic = requestedValue === null
    ? items.find(item => item.id === lastSelection?.topicId)
    : null;
   const initialTopic = requestedTopic || rememberedTopic;
   if (initialTopic) topic.value = String(initialTopic.id);
   if (difficultyLabels[lastSelection?.difficulty]) difficulty.value = lastSelection.difficulty;
   if (requestedValue !== null && !requestedTopic) {
    loadStatus.replaceChildren(notice(
     'Chủ đề trong đường dẫn không tồn tại hoặc hiện không còn được mở. Hãy chọn một chủ đề khác.',
     'warning'));
   } else {
    loadStatus.replaceChildren();
   }
   updateValidity();
  } catch (error) {
   if (!root.isConnected || version !== loadVersion) return;
   items = [];
   topic.replaceChildren(el('option', { value: '' }, 'Chưa tải được chủ đề'));
   const retry = button('Thử lại', () => load(true), 'primary');
   loadStatus.replaceChildren(
    notice(error.message || 'Chưa tải được danh sách chủ đề. Vui lòng thử lại.', 'error'),
    retry);
  } finally {
   if (root.isConnected && version === loadVersion) root.removeAttribute('aria-busy');
  }
 }

 topic.addEventListener('change', () => updateValidity());
 difficulty.addEventListener('change', () => updateValidity());
 form.addEventListener('submit', event => {
  event.preventDefault();
  const selection = updateValidity({ announce: true });
  if (!selection) return;
  lastSelection = selection;
  openQuiz(selection);
 });

 function openQuiz(selection) {
  const selectedTopic = items.find(item => item.id === selection.topicId);
  if (!selectedTopic || !difficultyLabels[selection.difficulty]) return;
  const answers = new Map();
  let index = 0;
  let confirming = false;
  let submitting = false;
  let submitted = false;
  const questionArea = el('div', {});
  const navigation = el('div', { className: 'question-nav', 'aria-label': 'Chuyển câu hỏi' });
  const count = el('p', { className: 'helper', role: 'status' });
  const submissionStatus = el('div', { className: 'quiz-submission-status', role: 'status', 'aria-live': 'polite' });
  const submit = button('Nộp đáp án', handleSubmit, 'primary');

  function setSubmitState(label, disabled) {
   submit.textContent = label;
   submit.disabled = disabled;
  }

  function submissionMessage(error) {
   if (error?.status === 403 || error?.status === 404) return 'Không tìm thấy bài luyện tập thuộc tài khoản này. Hãy mở lại bài rồi thử lại.';
   if (error?.status === 409) return 'Bài luyện tập này đã được nộp và không thể nộp lại.';
   if (error?.status === 422) return error.message || 'Dữ liệu đáp án chưa hợp lệ. Hãy kiểm tra lại trước khi nộp.';
   return error?.message || 'Chưa thể gửi đáp án. Đáp án của bạn vẫn được giữ để thử lại.';
  }

  async function handleSubmit() {
   if (confirming || submitting || submitted) return;
   const missing = questions.filter(question => !answers.has(question.id));
   if (missing.length) {
    index = questions.indexOf(missing[0]);
    draw();
    submissionStatus.replaceChildren(notice(
     `Còn ${missing.length} câu chưa trả lời. Hãy hoàn thành đủ 5 câu trước khi nộp.`,
     'warning'));
    requestAnimationFrame(() => questionArea.querySelector('input[type="radio"]')?.focus());
    return;
   }

   confirming = true;
   setSubmitState('Đang chờ xác nhận…', true);
   const confirmed = await confirmDialog(
    'Nộp đáp án bài luyện tập?',
    'Bạn đã trả lời đủ 5 câu. Sau khi gửi, bài này không thể nộp lại trong phiên hiện tại.',
    'Xác nhận nộp');
   confirming = false;
   if (!root.isConnected || submitted) return;
   if (!confirmed) {
    setSubmitState('Nộp đáp án', false);
    submit.focus({ preventScroll: true });
    return;
   }

   submitting = true;
   submitController?.abort();
   submitController = new AbortController();
   setSubmitState('Đang nộp bài…', true);
   submissionStatus.replaceChildren(notice('Đang gửi 5 đáp án. Vui lòng chờ…'));
   try {
    const result = await submitQuizAnswers(quizPreviewId, questions, answers, { signal: submitController.signal });
    if (!root.isConnected || submitController.signal.aborted) return;
    submitted = true;
    questionArea.querySelectorAll('input[type="radio"]').forEach(input => { input.disabled = true; });
    submissionStatus.replaceChildren(notice(
     result.mode === 'mock'
      ? 'API mock đã tiếp nhận đủ 5 đáp án. Đây chỉ là kiểm thử frontend; backend chưa chấm hoặc lưu bài.'
      : 'Đã gửi đủ 5 đáp án. Kết quả chỉ hiển thị sau khi backend chấm bài.',
     'success'));
    setSubmitState('Đã nộp đáp án', true);
   } catch (error) {
    if (error?.name === 'AbortError' || !root.isConnected) return;
    submissionStatus.replaceChildren(notice(submissionMessage(error), 'error'));
    setSubmitState('Thử nộp lại', false);
    submit.focus({ preventScroll: true });
   } finally {
    submitting = false;
   }
  }

  function draw() {
   const question = questions[index];
   questionArea.replaceChildren(
    el('p', { className: 'quiz-topic' }, `${selectedTopic.subjectName} · ${selectedTopic.chapterName} · ${selectedTopic.name}`),
    el('div', { className: 'panel-header' },
     badge(`Câu ${index + 1} / 5`),
     badge(`Độ khó: ${difficultyLabels[selection.difficulty]}`)),
    el('fieldset', {},
     el('legend', {}, question.text),
     el('div', { className: 'answer-list' }, ...question.options.map((text, optionIndex) => {
      const key = 'ABCD'[optionIndex];
      const radio = el('input', {
       type: 'radio',
       name: `answer-${question.id}`,
       value: key,
       checked: answers.get(question.id) === key,
       disabled: submitted,
      });
      radio.addEventListener('change', () => {
       if (!submitted && radio.checked) answers.set(question.id, key);
       submissionStatus.replaceChildren();
       drawNav();
      });
      return el('label', { className: 'answer-option' }, radio, `${'ABCD'[optionIndex]}. ${text}`);
     }))),
    el('div', { className: 'page-actions section-gap' },
     button('Câu trước', () => { index = Math.max(0, index - 1); draw(); }, 'ghost'),
     button('Câu tiếp', () => { index = Math.min(questions.length - 1, index + 1); draw(); }, 'secondary')));
   drawNav();
  }

  function drawNav() {
   navigation.replaceChildren(...questions.map((_, questionIndex) => {
    const control = button(String(questionIndex + 1), () => {
     index = questionIndex;
     draw();
    }, `question-dot ${index === questionIndex ? 'selected' : ''} ${answers.has(questions[questionIndex].id) ? 'answered' : ''}`);
    control.setAttribute('aria-label', `Câu ${questionIndex + 1}, ${answers.has(questions[questionIndex].id) ? 'đã trả lời' : 'chưa trả lời'}`);
    if (questionIndex === index) control.setAttribute('aria-current', 'step');
    return control;
   }));
   count.textContent = `Đã trả lời ${answers.size}/${questions.length} câu`;
  }

  const changeSelection = button('Đổi chủ đề hoặc độ khó', () => {
   layout.replaceWith(start);
   topic.focus({ preventScroll: true });
  }, 'ghost');
  const layout = el('div', {},
   notice('Bản xem thử dùng quiz #57001 và mã câu hỏi fixture. API nộp bài chỉ được kiểm chứng bằng mock; backend chưa chấm hoặc lưu quiz.', 'warning'),
   el('div', { className: 'quiz-layout' },
    el('section', { className: 'question-card' }, questionArea),
    panel('Tiến độ bài', navigation, count, submissionStatus, submit, changeSelection)));
  start.replaceWith(layout);
  draw();
 }

 load();
 return root;
}

export function renderResults() {
 if (!lastResult) return el('div', {}, heading('Kết quả luyện tập', 'Hoàn thành bài luyện tập để xem kết quả.'), el('div', { className: 'empty-state' }, 'Chưa có bài đã nộp.', el('div', { className: 'section-gap' }, link('Mở bài luyện tập', '#practice', 'button primary'))));
 const correct = lastResult.answers.filter((a, i) => a === questions[i].correct).length;
 return el('div', {}, heading('Kết quả luyện tập', 'Đối chiếu cách làm và ôn lại những điểm chưa rõ.'), el('div', { className: 'grid-2' }, panel('', el('div', { className: 'result-score' }, el('strong', {}, `${correct * 20}`), el('span', {}, `${correct}/5 câu đúng · điểm`))), panel('Bước tiếp theo', el('p', {}, 'Ôn lại những câu chưa đúng hoặc tiếp tục hỏi gia sư để hiểu rõ hơn.'), el('div', { className: 'page-actions' }, link('Luyện tập lại', '#practice', 'button primary'), link('Hỏi gia sư', '#chat', 'button ghost')))), el('h2', { className: 'section-title' }, 'Đáp án và giải thích'), el('div', { className: 'result-list' }, ...questions.map((q, i) => el('article', { className: `result-item ${lastResult.answers[i] === q.correct ? 'correct' : 'wrong'}` }, badge(lastResult.answers[i] === q.correct ? 'Đúng' : 'Cần ôn lại', lastResult.answers[i] === q.correct ? 'success' : 'warning'), el('h3', {}, `Câu ${i + 1}. ${q.text}`), el('p', {}, `Bạn chọn: ${lastResult.answers[i] === null ? 'Chưa trả lời' : 'ABCD'[lastResult.answers[i]]} · Đáp án: ${'ABCD'[q.correct]}`), el('p', {}, q.explanation)))));
}
