import { onSessionCleared } from '../session.js';
import { el, button, link, heading, panel, field, badge, confirmDialog, notice } from '../components/ui.js';
import { questions } from '../data.js';
let lastResult = null;
onSessionCleared(() => { lastResult = null; });
export function renderPractice() {
 const root = el('div', {}, heading('Luyện tập kiến thức', '5 câu hỏi. Tự kiểm tra mức hiểu bài và xem giải thích sau khi nộp.'));
 const difficulty = el('select', { className: 'select' }, ...['Dễ', 'Vừa', 'Khó'].map(s => el('option', {}, s)));
 const topic=el('select',{className:'select'},el('option',{},'Phương trình bậc hai'));
 const start = panel('Tạo bài luyện tập', el('p', {}, 'Chọn chủ đề và mức độ để bắt đầu.'),el('div',{className:'form-grid'},field('Chủ đề',topic), field('Mức độ', difficulty), button('Bắt đầu luyện tập', () => openQuiz(), 'primary')));
 root.append(start);
 function openQuiz() {
  const answers = Array(questions.length).fill(null); let index = 0;
  const questionArea = el('div', {}); const navigation = el('div', { className: 'question-nav', 'aria-label': 'Chuyển câu hỏi' }); const count = el('p', { className: 'helper', role: 'status' });
  const submit = button('Nộp bài', async () => { const missing = answers.filter(a => a === null).length; if (!(await confirmDialog('Nộp bài luyện tập?', missing ? `Còn ${missing} câu chưa trả lời. Những câu này được tính là chưa đúng.` : 'Sau khi nộp, bạn có thể xem đáp án và giải thích.', 'Nộp bài'))) return; lastResult = { answers: [...answers], difficulty: difficulty.value }; location.hash = 'results'; }, 'primary');
  function draw() {
   const q = questions[index];
   questionArea.replaceChildren(el('div', { className: 'panel-header' }, badge(`Câu ${index + 1} / 5`), badge(`Mức độ ${difficulty.value}`)), el('fieldset', {}, el('legend', {}, q.text), el('div', { className: 'answer-list' }, ...q.options.map((text, i) => { const radio = el('input', { type: 'radio', name: 'answer', value: i, checked: answers[index] === i }); radio.addEventListener('change', () => { answers[index] = i; drawNav(); }); return el('label', { className: 'answer-option' }, radio, `${'ABCD'[i]}. ${text}`); }))), el('div', { className: 'page-actions section-gap' }, button('Câu trước', () => { index = Math.max(0, index - 1); draw(); }, 'ghost'), button('Câu tiếp', () => { index = Math.min(4, index + 1); draw(); }, 'secondary')));
   drawNav();
  }
  function drawNav() { navigation.replaceChildren(...questions.map((_, i) => { const b = button(String(i + 1), () => { index = i; draw(); }, `question-dot ${index === i ? 'selected' : ''} ${answers[i] !== null ? 'answered' : ''}`); b.setAttribute('aria-label', `Câu ${i + 1}, ${answers[i] === null ? 'chưa trả lời' : 'đã trả lời'}`); if (i === index) b.setAttribute('aria-current', 'step'); return b; })); count.textContent = `Đã trả lời ${answers.filter(a => a !== null).length}/5 câu`; }
  const layout = el('div', { className: 'quiz-layout' }, el('section', { className: 'question-card' }, questionArea), panel('Tiến độ bài', navigation, count, submit)); start.replaceWith(layout); draw();
 }
 return root;
}
export function renderResults() {
 if (!lastResult) return el('div', {}, heading('Kết quả luyện tập', 'Hoàn thành bài luyện tập để xem kết quả.'), el('div', { className: 'empty-state' }, 'Chưa có bài đã nộp.', el('div', { className: 'section-gap' }, link('Mở bài luyện tập', '#practice', 'button primary'))));
 const correct = lastResult.answers.filter((a, i) => a === questions[i].correct).length;
 return el('div', {}, heading('Kết quả luyện tập', 'Đối chiếu cách làm và ôn lại những điểm chưa rõ.'), el('div', { className: 'grid-2' }, panel('', el('div', { className: 'result-score' }, el('strong', {}, `${correct * 20}`), el('span', {}, `${correct}/5 câu đúng · điểm`))), panel('Bước tiếp theo', el('p', {}, 'Ôn lại những câu chưa đúng hoặc tiếp tục hỏi gia sư để hiểu rõ hơn.'), el('div', { className: 'page-actions' }, link('Luyện tập lại', '#practice', 'button primary'), link('Hỏi gia sư', '#chat', 'button ghost')))), el('h2', { className: 'section-title' }, 'Đáp án và giải thích'), el('div', { className: 'result-list' }, ...questions.map((q, i) => el('article', { className: `result-item ${lastResult.answers[i] === q.correct ? 'correct' : 'wrong'}` }, badge(lastResult.answers[i] === q.correct ? 'Đúng' : 'Cần ôn lại', lastResult.answers[i] === q.correct ? 'success' : 'warning'), el('h3', {}, `Câu ${i + 1}. ${q.text}`), el('p', {}, `Bạn chọn: ${lastResult.answers[i] === null ? 'Chưa trả lời' : 'ABCD'[lastResult.answers[i]]} · Đáp án: ${'ABCD'[q.correct]}`), el('p', {}, q.explanation)))));
}
