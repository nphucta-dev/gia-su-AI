import { onSessionCleared } from '../session.js';
import { el, button, link, heading, panel, field, badge, confirmDialog, notice } from '../components/ui.js';
import { questions } from '../data.js';
import { loadCatalog, flattenTopics } from '../catalog.js';

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
  const answers = Array(questions.length).fill(null);
  let index = 0;
  const questionArea = el('div', {});
  const navigation = el('div', { className: 'question-nav', 'aria-label': 'Chuyển câu hỏi' });
  const count = el('p', { className: 'helper', role: 'status' });
  const submit = button('Nộp bài', async () => {
   const missing = answers.filter(answer => answer === null).length;
   if (!(await confirmDialog(
    'Nộp bài luyện tập?',
    missing ? `Còn ${missing} câu chưa trả lời. Những câu này được tính là chưa đúng.` : 'Sau khi nộp, bạn có thể xem đáp án và giải thích.',
    'Nộp bài'))) return;
   lastResult = { answers: [...answers], difficulty: selection.difficulty };
   location.hash = 'results';
  }, 'primary');

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
      const radio = el('input', {
       type: 'radio',
       name: 'answer',
       value: optionIndex,
       checked: answers[index] === optionIndex,
      });
      radio.addEventListener('change', () => {
       answers[index] = optionIndex;
       drawNav();
      });
      return el('label', { className: 'answer-option' }, radio, `${'ABCD'[optionIndex]}. ${text}`);
     }))),
    el('div', { className: 'page-actions section-gap' },
     button('Câu trước', () => { index = Math.max(0, index - 1); draw(); }, 'ghost'),
     button('Câu tiếp', () => { index = Math.min(4, index + 1); draw(); }, 'secondary')));
   drawNav();
  }

  function drawNav() {
   navigation.replaceChildren(...questions.map((_, questionIndex) => {
    const control = button(String(questionIndex + 1), () => {
     index = questionIndex;
     draw();
    }, `question-dot ${index === questionIndex ? 'selected' : ''} ${answers[questionIndex] !== null ? 'answered' : ''}`);
    control.setAttribute('aria-label', `Câu ${questionIndex + 1}, ${answers[questionIndex] === null ? 'chưa trả lời' : 'đã trả lời'}`);
    if (questionIndex === index) control.setAttribute('aria-current', 'step');
    return control;
   }));
   count.textContent = `Đã trả lời ${answers.filter(answer => answer !== null).length}/5 câu`;
  }

  const changeSelection = button('Đổi chủ đề hoặc độ khó', () => {
   layout.replaceWith(start);
   topic.focus({ preventScroll: true });
  }, 'ghost');
  const layout = el('div', {},
   notice('Bản xem thử dùng câu hỏi cố định để kiểm tra giao diện. Chưa có yêu cầu sinh hoặc lưu quiz nào được gửi tới backend.', 'warning'),
   el('div', { className: 'quiz-layout' },
    el('section', { className: 'question-card' }, questionArea),
    panel('Tiến độ bài', navigation, count, submit, changeSelection)));
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
