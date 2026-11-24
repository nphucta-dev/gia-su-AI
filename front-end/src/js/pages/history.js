import {el,heading,link,button,panel,notice} from '../components/ui.js';
import { getSession } from '../session.js';
import { accountView, activityRow, loadActivity } from '../account-data.js';
export function renderHistory() {
 const list=el('div',{className:'topic-list'});
 const search=el('input',{className:'input',type:'search',placeholder:'Tìm phiên học…','aria-label':'Tìm lịch sử học tập'});
 const type=el('select',{className:'select','aria-label':'Loại hoạt động'},el('option',{value:'all'},'Tất cả hoạt động'),el('option',{value:'chat'},'Hội thoại'),el('option',{value:'quiz'},'Luyện tập'));
 const root = el('div', {}, heading('Lịch sử học tập', 'Các cuộc hội thoại và bài luyện tập được lưu cho tài khoản của bạn.'), el('div', {className:'filter-bar'},search,type), list);
 const view = accountView(root);
 let records = [], pending = false, loaded = false;
 function draw() {
  if (!loaded) return;
  const query = search.value.trim().toLocaleLowerCase('vi');
  const items = records.filter(record => (type.value === 'all' || type.value === record.kind)
   && `${record.title} ${record.subjectName} ${record.topicName}`.toLocaleLowerCase('vi').includes(query));
  list.replaceChildren(...items.map(activityRow));
  if (!items.length) list.append(el('div', {className:'empty-state',role:'status'}, records.length ? 'Chưa có hoạt động phù hợp với bộ lọc.' : 'Bạn chưa có hoạt động học tập.'));
 }
 async function load() {
  if (pending || !view.current()) return;
  pending = true; loaded = false; root.setAttribute('aria-busy', 'true');
  list.replaceChildren(el('p', {role:'status'}, 'Đang tải lịch sử học tập…'));
  try {
   const data = await loadActivity({signal:view.signal});
   if (!view.current()) return;
   records = data.records; loaded = true; draw();
  } catch (error) {
   if (error.name !== 'AbortError' && view.current()) list.replaceChildren(notice(error.message || 'Chưa thể tải lịch sử học tập.', 'error'), button('Tải lại lịch sử', load));
  } finally { pending = false; if (view.current()) root.removeAttribute('aria-busy'); }
 }
 search.addEventListener('input',draw);type.addEventListener('change',draw);
 queueMicrotask(() => {
  if (!view.current()) return;
  if (getSession().reason === 'preview') list.replaceChildren(notice('Đăng nhập tài khoản thật để xem lịch sử học tập.', 'warning'), link('Đăng nhập', '#login'));
  else load();
 });
 return root;
}
export function renderIntro(){return el('div',{},el('div',{className:'auth-layout'},el('section',{className:'auth-intro'},el('h1',{},'Tự tin hiểu bài, từng bước một.'),el('p',{},'Đặt câu hỏi tiếng Việt, nhận gợi ý từng mức và luyện tập để củng cố kiến thức.'),el('div',{className:'page-actions'},link('Khám phá các chủ đề','#home','button primary'))),panel('Học cùng Gia Sư AI',el('div',{className:'stack'},el('section',{},el('h3',{},'Hỏi để hiểu'),el('p',{},'Khám phá lời giải qua câu hỏi gợi mở và ba mức gợi ý.')),el('section',{},el('h3',{},'Luyện tập theo chủ đề'),el('p',{},'Bài trắc nghiệm 5 câu với đáp án và giải thích sau khi nộp.')),el('section',{},el('h3',{},'Nhìn lại tiến bộ'),el('p',{},'Theo dõi điểm số, lịch sử và các chủ đề cần ôn.'))))));}
