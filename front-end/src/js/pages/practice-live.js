import { api, ApiError } from '../api.js';
import { getSession, onSessionCleared } from '../session.js';
import { loadCatalog, flattenTopics } from '../catalog.js';
import { questions as demoQuestions, topics as demoTopics } from '../data.js';
import { submitQuizAnswers } from '../quiz-submission.js';
import { quizGenerationError } from '../quiz-generation-error.js';
import { loadQuizDraft, saveQuizDraft, clearQuizDraft } from '../quiz-drafts.js';
import { el, button, link, heading, panel, field, badge, confirmDialog, notice } from '../components/ui.js';

const difficulties = { easy: 'Dễ', medium: 'Vừa', hard: 'Khó' };
let lastSelection = null, previewResult = null, lastQuizId = null;
onSessionCleared(() => { lastSelection = previewResult = lastQuizId = null; });

function validId(value) { const number = Number(value); return /^[1-9]\d*$/.test(String(value ?? '')) && Number.isSafeInteger(number) && number <= 2 ** 31 - 1 ? number : null; }
function previewQuiz(topicId, difficulty) {
 return { id: 57001, topicId, difficulty, status: 'in_progress', questions: demoQuestions.map((item, index) => ({ id: item.id, position: index + 1, questionText: item.text, options: Object.fromEntries(item.options.map((value, position) => ['ABCD'[position], value])) })) };
}
function safeQuiz(quiz, expected) {
 const invalid = () => new ApiError('Bài luyện tập từ máy chủ chưa hợp lệ.', 0, 'INVALID_QUIZ_RESPONSE');
 if (!quiz || !validId(quiz.id) || !difficulties[quiz.difficulty] || !['in_progress', 'completed'].includes(quiz.status) || !Array.isArray(quiz.questions) || quiz.questions.length !== 5) throw invalid();
 if (expected && (quiz.topicId !== expected.topicId || quiz.difficulty !== expected.difficulty || quiz.status !== 'in_progress')) throw invalid();
 const ids = new Set(), positions = new Set();
 for (const question of quiz.questions) {
  if (!validId(question?.id) || ids.has(question.id) || typeof question.questionText !== 'string' || !question.questionText.trim()
   || !Number.isInteger(question.position) || question.position < 1 || question.position > 5 || positions.has(question.position)
   || !question.options || Object.keys(question.options).length !== 4
   || !['A', 'B', 'C', 'D'].every(key => typeof question.options[key] === 'string' && question.options[key].trim())) throw invalid();
  ids.add(question.id);
  positions.add(question.position);
 }
 return quiz;
}

export function renderPractice() {
 const preview = getSession().reason === 'preview';
 const ownerId = getSession().user?.id;
 const params = new URLSearchParams(location.hash.split('?')[1]);
 const requestedQuiz = validId(params.get('quiz'));
 const requestedTopic = params.get('topic');
 const controller = new AbortController();
 const topic = el('select', { className: 'select', disabled: true, required: true }, el('option', { value: '' }, 'Đang tải chủ đề…'));
 const difficulty = el('select', { className: 'select', disabled: true, required: true }, el('option', { value: '' }, 'Chọn độ khó'), ...Object.entries(difficulties).map(([value, label]) => el('option', { value }, label)));
 const startButton = el('button', { type: 'submit', className: 'button primary', disabled: true }, preview ? 'Mở bài xem thử' : 'Tạo bài luyện tập');
 const setupStatus = el('div', { role: 'status', 'aria-live': 'polite' });
 const setupForm = el('form', { className: 'quiz-setup-form', novalidate: true }, el('div', { className: 'quiz-setup-fields' }, field('Chủ đề', topic), field('Độ khó', difficulty)), setupStatus, el('div', { className: 'quiz-setup-actions' }, startButton));
 const setup = panel('Tạo bài luyện tập', el('p', {}, preview ? 'Dữ liệu minh họa, không gọi model hoặc lưu bài.' : 'AI tạo 5 câu hỏi theo chủ đề và độ khó bạn chọn.'), setupForm);
 const root = el('div', { className: 'practice-page' }, heading('Luyện tập kiến thức', 'Chọn chủ đề, làm bài và xem kết quả được chấm trên máy chủ.'), setup);
 let topics = [], generating = false, failure = null, retrying = false;
 function current() { return root.isConnected && !controller.signal.aborted; }
 function selection() {
  return topics.find(item => String(item.id) === topic.value) && difficulties[difficulty.value]
   ? { topicId: preview ? topic.value : Number(topic.value), difficulty: difficulty.value } : null;
 }
 function setupControls() {
  topic.disabled = generating || !topics.length; difficulty.disabled = generating || !topics.length;
  startButton.disabled = generating || !selection() || (failure && !failure.retryable);
  startButton.textContent = generating ? retrying ? 'Đang tạo lại bài…' : 'Đang tạo 5 câu hỏi…' : preview ? 'Mở bài xem thử' : 'Tạo bài luyện tập';
  setupForm.setAttribute('aria-busy', String(generating));
 }
 topic.addEventListener('change', () => { failure = null; setupStatus.replaceChildren(); setupControls(); });
 difficulty.addEventListener('change', () => { failure = null; setupStatus.replaceChildren(); setupControls(); });
 async function loadTopics(force = false) {
  setupStatus.replaceChildren(el('p', {}, 'Đang tải danh sách chủ đề…'));
  try {
   topics = preview ? demoTopics.map(item => ({ ...item, subjectName: 'Toán học', chapterName: item.chapter })) : flattenTopics(await loadCatalog({ force }));
   if (!current()) return;
   const groups = new Map();
   for (const item of topics) {
    const name = `${item.subjectName} · ${item.chapterName || item.chapter || 'Chủ đề'}`;
    if (!groups.has(name)) groups.set(name, el('optgroup', { label: name }));
    groups.get(name).append(el('option', { value: item.id }, item.name));
   }
   topic.replaceChildren(el('option', { value: '' }, topics.length ? 'Chọn chủ đề' : 'Chưa có chủ đề đang mở'), ...groups.values());
   const initial = requestedTopic ?? lastSelection?.topicId;
   if (topics.some(item => String(item.id) === String(initial))) topic.value = String(initial);
   if (difficulties[lastSelection?.difficulty]) difficulty.value = lastSelection.difficulty;
   setupStatus.replaceChildren();
   if (requestedTopic && !topics.some(item => String(item.id) === requestedTopic)) setupStatus.append(notice('Chủ đề trong đường dẫn không tồn tại hoặc đã tắt. Hãy chọn chủ đề khác.', 'warning'));
   if (!topics.length) setupStatus.append(notice('Hiện chưa có chủ đề nào được mở.', 'warning'));
  } catch (error) {
   if (error.name !== 'AbortError' && current()) setupStatus.replaceChildren(notice(error.message, 'error'), button('Thử lại', () => loadTopics(true), 'secondary'));
  } finally { if (current()) setupControls(); }
 }
 async function generate(chosen, isRetry = false) {
  if (generating || !current() || (failure && !failure.retryable)) return;
  if (!chosen) { setupStatus.replaceChildren(notice('Vui lòng chọn đầy đủ chủ đề và độ khó.', 'error')); return; }
  const restoreFocus = setupStatus.contains(document.activeElement);
  generating = true; retrying = isRetry; lastSelection = { ...chosen }; setupControls();
  setupStatus.querySelectorAll('button').forEach(control => { control.disabled = true; });
  setupStatus.replaceChildren(notice(isRetry ? 'Đang tạo lại bài…' : 'Đang chuẩn bị bài luyện tập…'));
  try {
   const result = preview ? { quiz: previewQuiz(chosen.topicId, chosen.difficulty) }
    : await api('/quizzes', { method: 'POST', body: chosen, signal: controller.signal });
   if (!current()) return;
   const quiz = safeQuiz(result?.quiz, chosen);
   if (!preview) history.replaceState(null, '', `#practice?quiz=${quiz.id}`);
   failure = null; setupStatus.replaceChildren(); openQuiz(quiz);
  } catch (error) {
   if (error.name !== 'AbortError' && current()) {
    failure = quizGenerationError(error);
    const retry = failure.retryable ? button('Tạo lại bài', () => generate({ ...chosen }, true), 'secondary') : null;
    setupStatus.replaceChildren(el('div', { className: 'notice error quiz-generation-error' },
     el('strong', {}, 'Chưa tạo được bài luyện tập'), el('p', {}, failure.message), retry));
    if (restoreFocus && retry) retry.focus({ preventScroll: true });
   }
  } finally { generating = false; if (current()) setupControls(); }
 }
 setupForm.addEventListener('submit', event => {
  event.preventDefault();
  generate(selection(), Boolean(failure));
 });

 function openQuiz(quiz) {
  if (quiz.status === 'completed' && !preview) { clearQuizDraft(ownerId, quiz.id); location.hash = `results?quiz=${quiz.id}`; return; }
  const selectedTopic = topics.find(item => String(item.id) === String(quiz.topicId));
  const answers = preview ? new Map() : loadQuizDraft(ownerId, quiz);
  let index = 0, confirming = false, submitting = false, submitted = false;
  const questionArea = el('div', {});
  const navigation = el('div', { className: 'question-nav', 'aria-label': 'Chuyển câu hỏi' });
  const count = el('p', { className: 'helper', role: 'status' });
  const status = el('div', { className: 'quiz-submission-status', role: 'status', 'aria-live': 'polite' });
  const submit = button('Nộp đáp án', handleSubmit, 'primary');
  const change = button('Đổi chủ đề hoặc độ khó', () => {
   if (submitting || confirming) return;
   layout.replaceWith(setup); history.replaceState(null, '', '#practice'); setupControls();
  }, 'ghost');
  const layout = el('div', {}, preview ? notice('Dữ liệu minh họa — không gọi API hoặc lưu kết quả.', 'warning') : null,
   el('div', { className: 'quiz-layout' }, el('section', { className: 'question-card' }, questionArea), panel('Tiến độ bài', navigation, count, status, submit, change)));
  setup.replaceWith(layout);
  function controls() {
   const locked = submitting || confirming || submitted;
   layout.querySelectorAll('input[type="radio"]').forEach(input => { input.disabled = locked; });
   submit.disabled = locked; change.disabled = locked;
   submit.textContent = submitted ? 'Đã nộp đáp án' : submitting ? 'Đang nộp bài…' : confirming ? 'Đang chờ xác nhận…' : 'Nộp đáp án';
   layout.setAttribute('aria-busy', String(submitting));
  }
  function drawNav() {
   navigation.replaceChildren(...quiz.questions.map((question, questionIndex) => {
    const control = button(String(questionIndex + 1), () => { index = questionIndex; draw(); }, `question-dot ${index === questionIndex ? 'selected' : ''} ${answers.has(question.id) ? 'answered' : ''}`);
    control.setAttribute('aria-label', `Câu ${questionIndex + 1}, ${answers.has(question.id) ? 'đã trả lời' : 'chưa trả lời'}`);
    if (questionIndex === index) control.setAttribute('aria-current', 'step');
    return control;
   }));
   count.textContent = `Đã trả lời ${answers.size}/5 câu`;
  }
  function draw() {
   const question = quiz.questions[index];
   questionArea.replaceChildren(el('p', { className: 'quiz-topic' }, selectedTopic ? `${selectedTopic.subjectName} · ${selectedTopic.chapterName} · ${selectedTopic.name}` : `Chủ đề ${quiz.topicId}`),
    el('div', { className: 'panel-header' }, badge(`Câu ${index + 1} / 5`), badge(`Độ khó: ${difficulties[quiz.difficulty]}`)),
    el('fieldset', {}, el('legend', {}, question.questionText), el('div', { className: 'answer-list' }, ...Object.entries(question.options).map(([key, value]) => {
     const radio = el('input', { type: 'radio', name: `answer-${question.id}`, value: key, checked: answers.get(question.id) === key, disabled: submitting || confirming || submitted });
     radio.addEventListener('change', () => {
      if (submitting || confirming || submitted || !radio.checked) return;
      answers.set(question.id, key);
      if (!preview) saveQuizDraft(ownerId, quiz, answers);
      status.replaceChildren(); drawNav();
     });
     return el('label', { className: 'answer-option' }, radio, `${key}. ${value}`);
    }))), el('div', { className: 'page-actions section-gap' }, button('Câu trước', () => { index = Math.max(0, index - 1); draw(); }, 'ghost'), button('Câu tiếp', () => { index = Math.min(4, index + 1); draw(); }, 'secondary')));
   drawNav(); controls();
  }
  async function handleSubmit() {
   if (submitting || confirming || submitted) return;
   const missing = quiz.questions.findIndex(item => !answers.has(item.id));
   if (missing >= 0) { index = missing; draw(); status.replaceChildren(notice(`Còn ${5 - answers.size} câu chưa trả lời. Hãy hoàn thành đủ 5 câu trước khi nộp.`, 'warning')); return; }
   confirming = true; controls();
   const confirmed = await confirmDialog('Nộp đáp án bài luyện tập?', 'Bài được chấm một lần. Hãy kiểm tra các lựa chọn trước khi nộp.', 'Xác nhận nộp');
   confirming = false;
   if (!current()) return;
   if (!confirmed) { controls(); return; }
   submitting = true; controls(); status.replaceChildren(notice('Đang gửi 5 đáp án. Vui lòng chờ…'));
   try {
    if (preview) {
     const resultQuestions = quiz.questions.map((item, position) => ({ ...item, userAnswer: answers.get(item.id), correctAnswer: 'ABCD'[demoQuestions[position].correct], explanation: demoQuestions[position].explanation, isCorrect: answers.get(item.id) === 'ABCD'[demoQuestions[position].correct] }));
     const correctCount = resultQuestions.filter(item => item.isCorrect).length;
     previewResult = { quizId: quiz.id, topicId: quiz.topicId, score: correctCount * 20, correctCount, totalCount: 5, questions: resultQuestions };
    } else {
     const result = await submitQuizAnswers(quiz.id, quiz.questions, answers, { signal: controller.signal });
     if (result.quizStatus !== 'completed') throw new ApiError('Máy chủ chưa xác nhận bài đã được chấm. Hãy tải lại bài để kiểm tra.');
     clearQuizDraft(ownerId, quiz.id);
    }
    if (!current()) return;
    submitted = true; lastQuizId = quiz.id; location.hash = `results?quiz=${quiz.id}`;
   } catch (error) {
    if (error.name === 'AbortError' || !current()) return;
    if (!preview && error.status === 409) {
     try {
      const latest = await api(`/quizzes/${quiz.id}`, { signal: controller.signal });
      if (latest.quiz?.status === 'completed') { clearQuizDraft(ownerId, quiz.id); location.hash = `results?quiz=${quiz.id}`; return; }
     } catch { /* Giữ lựa chọn và hiển thị lỗi gốc khi chưa đọc được trạng thái. */ }
     status.replaceChildren(notice(error.message, 'error'), button('Chấm đáp án đã lưu', async () => {
      if (submitting) return;
      submitting = true; controls();
      try { await api(`/quizzes/${quiz.id}/grade`, { method: 'POST', signal: controller.signal }); clearQuizDraft(ownerId, quiz.id); if (current()) location.hash = `results?quiz=${quiz.id}`; }
      catch (failure) { if (current()) status.replaceChildren(notice(failure.message, 'error')); }
      finally { submitting = false; if (current()) controls(); }
     }, 'secondary'));
    } else status.replaceChildren(notice(error.message || 'Chưa thể nộp bài. Lựa chọn của bạn vẫn được giữ.', 'error'));
   } finally { submitting = false; if (current()) controls(); }
  }
  draw();
 }
 queueMicrotask(async () => {
  if (!current()) return;
  const observer = new MutationObserver(() => { if (!root.isConnected) { controller.abort(); observer.disconnect(); } });
  observer.observe(document.body, { childList: true, subtree: true });
  await loadTopics();
  if (!current()) return;
  if (params.has('quiz') && !requestedQuiz) { setupStatus.replaceChildren(notice('Mã bài luyện tập không hợp lệ.', 'error')); return; }
  if (!preview && requestedQuiz) {
   try { const result = await api(`/quizzes/${requestedQuiz}`, { signal: controller.signal }); if (current()) openQuiz(safeQuiz(result.quiz)); }
   catch (error) { if (error.name !== 'AbortError' && current()) setupStatus.replaceChildren(notice(error.message, 'error')); }
  }
 });
 return root;
}

function resultView(result, preview) {
 return el('div', {}, heading('Kết quả luyện tập', 'Đối chiếu cách làm và ôn lại những điểm chưa rõ.'), preview ? notice('Kết quả minh họa, không lưu vào hệ thống.', 'warning') : null,
  el('div', { className: 'grid-2' }, panel('', el('div', { className: 'result-score' }, el('strong', {}, String(result.score)), el('span', {}, `${result.correctCount}/${result.totalCount} câu đúng · điểm`))),
   panel('Bước tiếp theo', el('p', {}, 'Ôn lại những câu chưa đúng hoặc hỏi gia sư để hiểu rõ hơn.'), el('div', { className: 'page-actions' }, link('Luyện tập lại', `#practice?topic=${result.topicId}`, 'button primary'), link('Hỏi gia sư', `#chat?topic=${result.topicId}`, 'button ghost')))),
  el('h2', { className: 'section-title' }, 'Đáp án và giải thích'), el('div', { className: 'result-list' }, ...result.questions.map((question, index) =>
   el('article', { className: `result-item ${question.isCorrect ? 'correct' : 'wrong'}` }, badge(question.isCorrect ? 'Đúng' : 'Cần ôn lại', question.isCorrect ? 'success' : 'warning'),
    el('h3', {}, `Câu ${index + 1}. ${question.questionText}`), el('p', {}, `Bạn chọn: ${question.userAnswer} · Đáp án: ${question.correctAnswer}`), el('p', {}, question.explanation)))));
}

export function renderResults() {
 const preview = getSession().reason === 'preview';
 const requested = new URLSearchParams(location.hash.split('?')[1]).get('quiz');
 const id = validId(requested) || (requested === null ? lastQuizId : null);
 if (preview && previewResult) return resultView(previewResult, true);
 const root = el('div', {}, heading('Kết quả luyện tập', 'Kết quả được lưu và chấm trên máy chủ.'));
 if (!id || preview) { root.append(el('div', { className: 'empty-state' }, 'Chưa có bài đã nộp.', link('Mở bài luyện tập', '#practice', 'button primary'))); return root; }
 const status = el('div', { role: 'status' }); root.append(status);
 async function load() {
  status.replaceChildren(el('p', {}, 'Đang tải kết quả…'));
  try {
   const response = await api(`/quizzes/${id}/result`);
   if (!root.isConnected) return;
   const result = response?.result;
   if (!result || result.quizId !== id || result.status !== 'completed' || !Array.isArray(result.questions) || result.questions.length !== 5) throw new ApiError('Kết quả từ máy chủ chưa hợp lệ.');
   root.replaceChildren(resultView(result, false));
  } catch (error) { if (root.isConnected) status.replaceChildren(notice(error.message, 'error'), button('Thử lại', load, 'secondary')); }
 }
 queueMicrotask(load);
 return root;
}
