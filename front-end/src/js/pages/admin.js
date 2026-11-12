import { getAccessToken, getSession, onSessionCleared } from '../session.js';
import { api } from '../api.js';
import { invalidateCatalog } from '../catalog.js';
import { el, button, heading, panel, field, badge, notice, toast } from '../components/ui.js';
import { setupValidation, validateFields, showServerErrors } from '../components/validation.js';

const MAX_FILE_SIZE = 10 * 1024 * 1024;
const ALLOWED_TYPES = ['application/pdf', 'text/plain'];
const statusMeta = {
  ready: ['Sẵn sàng', 'success'],
  pending: ['Đang xử lý', 'warning'],
  error: ['Lỗi', 'error']
};
const formatSize = bytes => bytes < 1024 * 1024
  ? `${Math.max(1, Math.round(bytes / 1024))} KB`
  : `${(bytes / 1024 / 1024).toLocaleString('vi-VN', { maximumFractionDigits: 1 })} MB`;

function createCatalog() {
  const subjects = [{ name: 'Toán học', level: 'THPT', active: true }, { name: 'Tiếng Anh', level: 'THPT', active: true }, { name: 'Vật lý', level: 'THPT', active: true }];
  const topics = [
    { name: 'Phương trình bậc hai', subject: 'Toán học', chapter: 'Chương 1', active: true },
    { name: 'Hàm số bậc hai', subject: 'Toán học', chapter: 'Chương 1', active: true },
    { name: 'Đạo hàm', subject: 'Toán học', chapter: 'Chương 2', active: true },
    { name: 'Cơ học', subject: 'Vật lý', chapter: 'Chương 2', active: true }
  ];
  const documents = [
    { name: 'Chuyên đề hàm số.pdf', size: '2,4 MB', date: '08/11/2026', topic: 'Hàm số bậc hai', status: 'ready', active: true },
    { name: 'Bài tập parabol.txt', size: '86 KB', date: '10/11/2026', topic: 'Hàm số bậc hai', status: 'pending', active: false },
    { name: 'Công thức tổng hợp.pdf', size: '1,7 MB', date: '10/11/2026', topic: 'Đạo hàm', status: 'error', active: false, error: 'Không thể trích xuất văn bản.' },
    { name: 'Định luật Newton.pdf', size: '1,8 MB', date: '02/11/2026', topic: 'Cơ học', status: 'ready', active: false }
  ];
 return {subjects, topics, documents};
}
let catalog = createCatalog();
onSessionCleared(() => { catalog = createCatalog(); });

export function renderAdmin() {
  const preview = getSession().reason === 'preview';
  const token = getAccessToken();
  const userId = getSession().user?.id;
  const root = el('div', { className: 'admin-page' });
  const content = el('div');
  const requestedTab = new URLSearchParams(location.hash.split('?')[1]).get('tab');
  const active = ['subjects','topics','documents'].includes(requestedTab) ? requestedTab : 'subjects';
  let editing = null;
  let uploadOpen = false;
  const {subjects, topics} = catalog;
  const liveDocuments = active === 'documents' && !preview;
  if (preview) root.append(el('div', {className:'admin-preview-note'}, notice('Bản xem trước: thay đổi chỉ nằm trong bộ nhớ, chưa lưu lên máy chủ. Tải lại trang hoặc đăng xuất sẽ đặt lại dữ liệu.', 'warning')));
  let liveSubjects = [];
  let liveTopics = [];
  let liveDocumentCounts = null;
  let catalogReady = preview;
  let catalogPending = false;
  let catalogVersion = 0;
  let catalogSearch = '';
  let documents = catalog.documents;
  let uploadSubjects = subjects;
  let uploadTopics = topics;
  let documentsReady = !liveDocuments;
  let uploadPending = false;
  const pageHeading = heading(active === 'subjects' ? 'Quản lý môn học' : active === 'topics' ? 'Quản lý chủ đề' : 'Tài liệu nguồn', active === 'subjects' ? 'Cập nhật danh mục người học có thể truy cập.' : active === 'topics' ? 'Sắp xếp nội dung theo môn học và chương.' : 'Kiểm soát nguồn kiến thức được dùng trong câu trả lời AI.');
  root.prepend(pageHeading);
  const tabs = el('nav', { className: 'tabs', 'aria-label': 'Nhóm quản trị' });

  function draw() {
    tabs.replaceChildren(...[['subjects', 'Môn học'], ['topics', 'Chủ đề'], ['documents', 'Tài liệu nguồn']].map(([id, label]) => {
      const tab = button(label, () => { if(id !== active) location.hash = 'admin?tab=' + id; }, `tab ${active === id ? 'active' : ''}`);
      if (id === active) tab.setAttribute('aria-current', 'page');
      return tab;
    }));
    if (active === 'documents') {
      if (!documentsReady) {
        content.replaceChildren(el('p', {role:'status'}, 'Đang tải tài liệu và chủ đề…'));
        return;
      }
      return uploadOpen ? drawUpload() : drawDocuments();
    }
    if (preview) drawCatalog();
    else if (catalogReady) drawLiveCatalog();
    else content.replaceChildren(el('p', {role:'status'}, 'Đang tải môn học và chủ đề…'));
  }

  function currentPage() {
    return root.isConnected && getSession().user?.id === userId && getAccessToken() === token;
  }

  function serverDocument(item) {
    const created = new Date(item.createdAt);
    return {
      id:item.id, topicId:item.topicId, name:item.title, fileName:item.fileName, topic:item.topicName,
      size:Number.isFinite(item.sizeBytes) ? formatSize(item.sizeBytes) : 'Chưa có kích thước',
      date:Number.isNaN(created.getTime()) ? '' : created.toLocaleDateString('vi-VN'),
      status:item.status, active:item.isActive,
    };
  }

  async function loadDocuments() {
    documentsReady = false;
    draw();
    try {
      const [options, result] = await Promise.all([api('/admin/documents/options'), api('/admin/documents')]);
      if (!currentPage()) return;
      if (!Array.isArray(options?.subjects) || !Array.isArray(result?.documents)) throw new Error('Phản hồi tài liệu chưa hợp lệ. Vui lòng thử lại.');
      uploadSubjects = options.subjects.map(item => ({id:item.id, name:item.name, level:item.gradeLevel, active:true}));
      uploadTopics = options.subjects.flatMap(subject => (subject.topics || []).map(item => ({id:item.id, name:item.name, subjectId:subject.id, subject:subject.name, chapter:item.chapterName, active:true})));
      documents = result.documents.map(serverDocument);
      documentsReady = true;
      draw();
    } catch (error) {
      if (!currentPage()) return;
      content.replaceChildren(notice(error.message || 'Chưa thể tải danh sách tài liệu.', 'error'), button('Thử lại', loadDocuments, 'primary'));
    }
  }

  async function loadAdminCatalog() {
    const version = ++catalogVersion;
    catalogReady = false;
    draw();
    try {
      const [subjectRequest, topicRequest, documentRequest] = await Promise.allSettled([
        api('/admin/subjects'), api('/admin/topics'), active === 'topics' ? api('/admin/documents') : Promise.resolve(null)
      ]);
      if (!currentPage() || version !== catalogVersion) return;
      if (subjectRequest.status === 'rejected') throw subjectRequest.reason;
      if (topicRequest.status === 'rejected') throw topicRequest.reason;
      const subjectResult = subjectRequest.value;
      const topicResult = topicRequest.value;
      if (!Array.isArray(subjectResult?.subjects) || !Array.isArray(topicResult?.topics)) {
        throw new Error('Danh mục chưa hợp lệ. Vui lòng thử lại.');
      }
      liveSubjects = subjectResult.subjects;
      liveTopics = topicResult.topics;
      liveDocumentCounts = null;
      if (documentRequest.status === 'fulfilled' && Array.isArray(documentRequest.value?.documents)) {
        liveDocumentCounts = new Map();
        documentRequest.value.documents.forEach(item => liveDocumentCounts.set(item.topicId, (liveDocumentCounts.get(item.topicId) || 0) + 1));
      }
      catalogReady = true;
      draw();
    } catch (error) {
      if (!currentPage() || version !== catalogVersion) return;
      content.replaceChildren(notice(error.message || 'Chưa thể tải môn học và chủ đề.', 'error'), button('Thử lại', loadAdminCatalog, 'primary'));
    }
  }

  function drawLiveCatalog() {
    const isSubject = active === 'subjects';
    const collection = isSubject ? liveSubjects : liveTopics;
    if (editing && !collection.includes(editing)) editing = null;
    const clean = value => value.trim().replace(/\s+/g, ' ');
    const name = el('input', {className:'input', value:editing?.name || '', maxlength:isSubject ? 120 : 180, required:true, placeholder:isSubject ? 'Ví dụ: Toán học' : 'Ví dụ: Phương trình bậc hai'});
    const detail = el('input', {className:'input', value:(isSubject ? editing?.gradeLevel : editing?.chapterName) || '', maxlength:isSubject ? 50 : 150, required:true, placeholder:isSubject ? 'THPT' : 'Chương 1'});
    const subjectSelect = isSubject ? null : el('select', {className:'select', required:true}, el('option', {value:''}, 'Chọn môn học'), ...liveSubjects.map(item => el('option', {value:item.id, selected:editing?.subjectId === item.id}, `${item.name} · ${item.gradeLevel}${item.isActive ? '' : ' (đã tắt)'}`)));
    const description = isSubject ? null : el('textarea', {className:'textarea', maxlength:5000, rows:4, placeholder:'Nội dung người học sẽ tìm hiểu trong chủ đề này.'}, editing?.description || '');
    const submit = el('button', {type:'submit', className:'button primary'}, editing ? 'Lưu thay đổi' : 'Thêm nội dung');
    const cancel = button(editing ? 'Huỷ chỉnh sửa' : 'Hủy', () => { if (!catalogPending) { editing = null; draw(); } }, 'ghost');
    const message = el('div', {role:'status', 'aria-live':'polite'});
    const form = el('form', {className:'form-grid'}, field(isSubject ? 'Tên môn học' : 'Tên chủ đề', name), subjectSelect ? field('Môn học', subjectSelect) : null, field(isSubject ? 'Cấp học' : 'Chương', detail), description ? field('Mô tả', description) : null, submit, cancel, message);
    setupValidation(form, [name, detail, ...(subjectSelect ? [subjectSelect, description] : [])]);
    const search = el('input', {className:'input', type:'search', value:catalogSearch, placeholder:isSubject ? 'Tìm môn học hoặc cấp học…' : 'Tìm chủ đề, môn học hoặc chương…', 'aria-label':'Tìm trong danh mục'});
    const rows = el('div', {className:'topic-list'});
    const summary = el('p', {className:'catalog-summary', 'aria-live':'polite'});
    const feedback = el('div', {role:'status', 'aria-live':'polite'});
    const add = button(isSubject ? 'Thêm môn học' : 'Thêm chủ đề', () => {
      if (catalogPending) return;
      if (editing) { editing = null; draw(); pageHeading.querySelector('.button')?.click(); return; }
      editor.hidden = false;
      editor.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches ? 'instant' : 'smooth', block:'center'});
      name.focus({preventScroll:true});
    }, 'primary');

    function replaceItem(item) {
      const index = collection.findIndex(current => current.id === item.id);
      if (index === -1) collection.push(item);
      else collection[index] = item;
      if (isSubject) {
        liveTopics = liveTopics.map(topic => topic.subjectId === item.id ? {...topic, subjectName:item.name, gradeLevel:item.gradeLevel} : topic);
      }
    }

    function setPending(value) {
      catalogPending = value;
      add.disabled = value;
      for (const control of form.querySelectorAll('input,select,textarea,button')) control.disabled = value;
      if (value) form.setAttribute('aria-busy', 'true');
      else form.removeAttribute('aria-busy');
      renderRows();
    }

    async function toggleItem(item) {
      if (catalogPending) return;
      feedback.replaceChildren();
      setPending(true);
      try {
        const result = await api(`/admin/${active}/${item.id}`, {method:'PATCH', body:{isActive:!item.isActive}});
        if (!currentPage() || !rows.isConnected) return;
        const updated = isSubject ? result?.subject : result?.topic;
        if (updated?.id !== item.id) throw new Error('Chưa thể xác nhận thay đổi. Vui lòng tải lại trang.');
        replaceItem(updated);
        invalidateCatalog();
        toast(updated.isActive ? 'Đã kích hoạt nội dung.' : 'Đã vô hiệu hoá nội dung.');
      } catch (error) {
        if (currentPage() && rows.isConnected) feedback.replaceChildren(notice(error.message || 'Chưa thể cập nhật trạng thái. Vui lòng thử lại.', 'error'));
      } finally {
        if (currentPage() && rows.isConnected) setPending(false);
        else catalogPending = false;
      }
    }

    function renderRows() {
      const query = catalogSearch.toLocaleLowerCase('vi');
      const filtered = collection.filter(item => [item.name,item.gradeLevel,item.subjectName,item.chapterName].filter(Boolean).join(' ').toLocaleLowerCase('vi').includes(query));
      const sorted = [...filtered].sort((a,b) => (isSubject ? a.name + a.gradeLevel : a.subjectName + a.gradeLevel + a.chapterName + a.name).localeCompare(isSubject ? b.name + b.gradeLevel : b.subjectName + b.gradeLevel + b.chapterName + b.name, 'vi') || a.id - b.id);
      rows.replaceChildren();
      let previousGroup = '';
      for (const item of sorted) {
        const group = isSubject ? '' : `${item.subjectName} · ${item.gradeLevel} · ${item.chapterName}`;
        if (group && group !== previousGroup) rows.append(el('h3', {className:'catalog-group'}, group));
        previousGroup = group;
        const edit = button('Sửa', () => { if (!catalogPending) { editing = item; draw(); content.querySelector('input:not([type=search])')?.focus(); } }, 'secondary small');
        const toggle = button(item.isActive ? 'Vô hiệu hoá' : 'Kích hoạt', () => toggleItem(item), 'ghost small');
        edit.disabled = toggle.disabled = catalogPending;
        const subject = !isSubject && liveSubjects.find(subject => subject.id === item.subjectId);
        rows.append(el('article', {className:'topic-row', 'data-catalog-id':item.id},
          el('div', {className:'catalog-name'}, el('h3', {}, item.name), el('p', {}, isSubject ? item.gradeLevel : `${item.subjectName} · ${item.gradeLevel} · ${item.chapterName}`), !isSubject && item.description ? el('p', {}, item.description) : null, subject && !subject.isActive ? el('p', {}, 'Môn học đã tắt; chủ đề đang ẩn với người học.') : null),
          el('div', {className:'catalog-relation'}, isSubject ? `${liveTopics.filter(topic => topic.subjectId === item.id).length} chủ đề` : liveDocumentCounts ? `${liveDocumentCounts.get(item.id) || 0} tài liệu` : '—'),
          badge(item.isActive ? 'Đang bật' : 'Đã tắt', item.isActive ? 'success' : 'warning'),
          el('div', {className:'page-actions'}, edit, toggle)
        ));
      }
      if (!sorted.length) rows.append(el('div', {className:'empty-state'}, el('h3', {}, 'Không tìm thấy nội dung'), el('p', {}, 'Thử một từ khóa khác hoặc thêm nội dung mới.')));
      summary.textContent = `Hiển thị ${filtered.length} trong ${collection.length} ${isSubject ? 'môn học' : 'chủ đề'}`;
    }

    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (catalogPending) return;
      message.replaceChildren();
      const valid = validateFields([[name, clean(name.value) ? '' : 'Vui lòng nhập tên nội dung.'], [detail, clean(detail.value) ? '' : 'Vui lòng nhập thông tin phân loại.'], ...(subjectSelect ? [[subjectSelect, liveSubjects.some(item => String(item.id) === subjectSelect.value) ? '' : 'Vui lòng chọn môn học hợp lệ.']] : [])]);
      if (!valid) return;
      const itemId = editing?.id;
      const body = isSubject ? {name:clean(name.value), gradeLevel:clean(detail.value)} : {name:clean(name.value), subjectId:Number(subjectSelect.value), chapterName:clean(detail.value), description:description.value.trim() || null};
      setPending(true);
      submit.textContent = 'Đang lưu…';
      try {
        const result = await api(`/admin/${active}${itemId ? `/${itemId}` : ''}`, {method:itemId ? 'PATCH' : 'POST', body});
        if (!currentPage() || !form.isConnected) return;
        const updated = isSubject ? result?.subject : result?.topic;
        if (!updated?.id || (itemId && updated.id !== itemId)) throw new Error('Chưa thể xác nhận thay đổi. Vui lòng tải lại trang.');
        replaceItem(updated);
        invalidateCatalog();
        editing = null;
        catalogPending = false;
        draw();
        toast(itemId ? 'Đã lưu thay đổi.' : 'Đã thêm nội dung.');
      } catch (error) {
        if (!currentPage() || !form.isConnected) return;
        setPending(false);
        showServerErrors(error.fields, {name, gradeLevel:detail, grade_level:detail, chapterName:detail, chapter_name:detail, subjectId:subjectSelect, subject_id:subjectSelect, description});
        message.replaceChildren(notice(error.message || 'Chưa thể lưu nội dung. Vui lòng thử lại.', 'error'));
      } finally {
        if (currentPage() && form.isConnected) { setPending(false); submit.textContent = itemId ? 'Lưu thay đổi' : 'Thêm nội dung'; }
        else catalogPending = false;
      }
    });

    search.addEventListener('input', () => { catalogSearch = search.value.trim(); renderRows(); });
    const editor = el('section', {className:'panel catalog-editor', hidden:!editing}, el('h2', {}, editing ? 'Chỉnh sửa nội dung' : 'Thêm nội dung'), form);
    pageHeading.querySelector('.page-actions')?.remove();
    pageHeading.append(el('div', {className:'page-actions'}, add));
    const list = el('section', {className:'panel catalog-panel'}, el('div', {className:'catalog-toolbar'}, el('h2', {}, isSubject ? 'Danh sách môn học' : 'Cấu trúc nội dung'), search), el('div', {className:'catalog-table-head', 'aria-hidden':'true'}, el('span', {}, isSubject ? 'Môn học / Cấp học' : 'Chủ đề / Môn học'), el('span', {}, isSubject ? 'Chủ đề' : 'Tài liệu'), el('span', {}, 'Trạng thái'), el('span', {}, 'Thao tác')), feedback, rows, summary);
    content.replaceChildren(el('div', {className:'catalog-admin-layout'}, list, editor));
    renderRows();
  }

  function drawCatalog() {
    const collection = active === 'subjects' ? subjects : topics;
    if (editing && !collection.includes(editing)) editing = null;
    const name = el('input', { className: 'input', value: editing?.name || '', maxlength: 180, placeholder: active === 'subjects' ? 'Ví dụ: Toán học' : 'Ví dụ: Phương trình bậc hai' });
    const detail = el('input', { className: 'input', value: editing?.level || editing?.chapter || '', maxlength: 150, placeholder: active === 'subjects' ? 'THPT' : 'Toán học · Chương 1' });
    const subjectSelect = active === 'topics' ? el('select', {className:'select',required:true}, el('option',{value:''},'Chọn môn học'), ...subjects.map(item => el('option',{value:item.name, selected:editing?.subject === item.name},item.name))) : null;
    const form = el('form', { className: 'form-grid' }, field(active === 'subjects' ? 'Tên môn học' : 'Tên chủ đề', name), subjectSelect ? field('Môn học',subjectSelect) : null, field(active === 'subjects' ? 'Cấp học' : 'Chương', detail), el('button', { type: 'submit', className: 'button primary' }, editing ? 'Lưu thay đổi' : 'Thêm nội dung'));
    form.append(button(editing ? 'Huỷ chỉnh sửa' : 'Hủy', () => { editing = null; draw(); }, 'ghost'));
    setupValidation(form, [name, detail, ...(subjectSelect ? [subjectSelect] : [])]);
    form.addEventListener('submit', event => {
      event.preventDefault();
      const duplicate = collection.some(item => item !== editing && item.name.toLocaleLowerCase('vi') === name.value.trim().toLocaleLowerCase('vi'));
      if (!validateFields([[name, !name.value.trim() ? 'Vui lòng nhập tên nội dung.' : duplicate ? 'Tên này đã được sử dụng trong danh sách. Vui lòng chọn tên khác.' : ''], [detail, detail.value.trim() ? '' : 'Vui lòng nhập thông tin phân loại.'], ...(subjectSelect ? [[subjectSelect, subjects.some(item => item.name === subjectSelect.value) ? '' : 'Vui lòng chọn môn học hợp lệ.']] : [])])) return;
      if (editing) {
        const oldName = editing.name;
        if(active === 'subjects') {
          topics.filter(item => item.subject === oldName).forEach(item => { item.subject = name.value.trim(); });
          Object.assign(editing, {name:name.value.trim(),level:detail.value.trim()});
        } else {
          documents.filter(item => item.topic === oldName).forEach(item => { item.topic = name.value.trim(); });
          Object.assign(editing, {name:name.value.trim(),chapter:detail.value.trim(),subject:subjectSelect.value});
        }
      }
      else collection.push(active === 'subjects' ? { name: name.value.trim(), level: detail.value.trim(), active: true } : { name: name.value.trim(), subject: subjectSelect.value, chapter: detail.value.trim(), active: true });
      editing = null;
      draw();
      toast('Đã cập nhật danh mục trong bản xem trước; chưa lưu lên máy chủ.');
    });
    const search = el('input', {className:'input', type:'search', placeholder:active === 'subjects' ? 'Tìm môn học hoặc cấp học…' : 'Tìm chủ đề, môn học hoặc chương…', 'aria-label':'Tìm trong danh mục'});
    const rows = el('div', {className:'topic-list'});
    const summary = el('p', {className:'catalog-summary', 'aria-live':'polite'});
    function renderRows() {
      const query = search.value.trim().toLocaleLowerCase('vi');
      const filtered = collection.filter(item => [item.name,item.level,item.subject,item.chapter].filter(Boolean).join(' ').toLocaleLowerCase('vi').includes(query));
      const sorted = active === 'topics' ? [...filtered].sort((a,b) => (a.subject + a.chapter).localeCompare(b.subject + b.chapter, 'vi')) : filtered;
      rows.replaceChildren(...sorted.map(item => el('article', {className:'topic-row'},
        el('div', {className:'catalog-name'}, el('h3', {}, item.name), el('p', {}, item.level || item.subject + ' · ' + item.chapter)),
        el('div', {className:'catalog-relation'}, active === 'subjects' ? topics.filter(topic => topic.subject === item.name).length + ' chủ đề' : documents.filter(doc => doc.topic === item.name).length + ' tài liệu'),
        badge(item.active ? 'Đang bật' : 'Đã tắt', item.active ? 'success' : 'warning'),
        el('div', {className:'page-actions'}, button('Sửa', () => { editing=item; draw(); content.querySelector('input:not([type=search])')?.focus(); }, 'secondary small'), button(item.active ? 'Vô hiệu hoá' : 'Kích hoạt', () => {item.active=!item.active; renderRows();}, 'ghost small'))
      )));
      if(active === 'topics') {
        let previousGroup = '';
        [...rows.children].forEach((row,index) => {
          const group = sorted[index].subject + ' · ' + sorted[index].chapter;
          if(group !== previousGroup) row.before(el('h3',{className:'catalog-group'},group));
          previousGroup = group;
        });
      }
      if(!filtered.length) rows.append(el('div',{className:'empty-state'}, el('h3',{},'Không tìm thấy nội dung'), el('p',{},'Thử một từ khóa khác hoặc thêm nội dung mới.')));
      summary.textContent = 'Hiển thị ' + filtered.length + ' trong ' + collection.length + (active === 'subjects' ? ' môn học' : ' chủ đề');
    }
    search.addEventListener('input',renderRows);
    const editor = el('section', {className:'panel catalog-editor',hidden:!editing}, el('h2',{},editing ? 'Chỉnh sửa nội dung' : 'Thêm nội dung'), form);
    const add = button(active === 'subjects' ? 'Thêm môn học' : 'Thêm chủ đề', () => { if(editing) { editing=null; draw(); pageHeading.querySelector('.button').click(); return; } editor.hidden=false; editor.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches ? 'instant' : 'smooth',block:'center'}); name.focus({preventScroll:true});}, 'primary');
    pageHeading.querySelector('.page-actions')?.remove();
    pageHeading.append(el('div',{className:'page-actions'},add));
    const list = el('section',{className:'panel catalog-panel'},el('div',{className:'catalog-toolbar'},el('h2',{}, active === 'subjects' ? 'Danh sách môn học' : 'Cấu trúc nội dung'),search),el('div',{className:'catalog-table-head','aria-hidden':'true'},el('span',{},active === 'subjects' ? 'Môn học / Cấp học' : 'Chủ đề / Môn học'),el('span',{},active === 'subjects' ? 'Chủ đề' : 'Tài liệu'),el('span',{},'Trạng thái'),el('span',{},'Thao tác')),rows,summary);
    content.replaceChildren(el('div',{className:'catalog-admin-layout'},list,editor));
    renderRows();
  }

  function drawDocuments() {
    const search = el('input', { className: 'input', type: 'search', placeholder: 'Tìm tài liệu...', 'aria-label': 'Tìm tài liệu' });
    const statusFilter = el('select', { className: 'select', 'aria-label': 'Lọc theo trạng thái' }, el('option', { value: 'all' }, 'Tất cả trạng thái'), ...Object.entries(statusMeta).map(([value, meta]) => el('option', { value }, meta[0])));
    const topicFilter = el('select', { className: 'select', 'aria-label': 'Lọc theo chủ đề' }, el('option', { value: 'all' }, 'Tất cả chủ đề'), ...[...new Set(documents.map(item => item.topic))].map(topic => el('option', { value: topic }, topic)));
    const results = el('div', { className: 'document-results', 'aria-live': 'polite' });
    const summary = el('p', { className: 'document-summary' });

    const makeRow = document => {
      const [label, kind] = statusMeta[document.status] || statusMeta.pending;
      const toggle = el('button', { type: 'button', className: `source-switch ${document.active ? 'active' : ''}`, role: 'switch', 'aria-checked': String(document.active), 'aria-label': `${document.active ? 'Tắt' : 'Bật'} nguồn ${document.name}`, disabled: liveDocuments || document.status !== 'ready' }, el('span', { 'aria-hidden': 'true' }));
      if (!liveDocuments) toggle.addEventListener('click', () => { document.active = !document.active; renderList(); toast(document.active ? 'Đã bật tài liệu trong bản xem trước.' : 'Đã tắt tài liệu trong bản xem trước.'); });
      const action = liveDocuments
        ? el('span', {className:'document-waiting'}, document.status === 'pending' ? 'Chờ xử lý' : document.status === 'ready' ? 'Đã xử lý' : 'Xử lý lỗi')
        : document.status === 'error' ? button('Thử lại', () => { document.status = 'pending'; document.error = ''; renderList(); toast('Đã đổi trạng thái minh họa sang chờ xử lý. Chưa gửi yêu cầu lên máy chủ.'); }, 'document-action') : document.status === 'pending' ? el('span', { className: 'document-waiting' }, 'Chờ xử lý') : button('Chi tiết', () => toast(`${document.name}: trạng thái sẵn sàng là dữ liệu minh họa.`), 'document-action');
      return el('article', { className: 'document-row' },
        el('div', { className: `document-icon ${kind}`, 'aria-hidden': 'true' }, document.status === 'error' ? '!' : '▤'),
        el('div', { className: 'document-name' }, el('h3', {}, document.name), el('p', {}, `${document.fileName ? document.fileName + ' · ' : ''}${document.size} · ${document.date}`), document.error ? el('p', { className: 'document-error' }, document.error) : null),
        el('div', { className: 'document-topic', 'data-label': 'Chủ đề' }, document.topic),
        el('div', { className: 'document-status', 'data-label': 'Xử lý' }, badge(label, kind)),
        el('div', { className: 'document-usage', 'data-label': 'Sử dụng' }, toggle),
        el('div', { className: 'document-actions', 'data-label': 'Thao tác' }, action)
      );
    };
    function renderList() {
      const query = search.value.trim().toLocaleLowerCase('vi');
      const filtered = documents.filter(item => (!query || item.name.toLocaleLowerCase('vi').includes(query)) && (statusFilter.value === 'all' || item.status === statusFilter.value) && (topicFilter.value === 'all' || item.topic === topicFilter.value));
      results.replaceChildren(filtered.length ? el('div', { className: 'document-list' }, ...filtered.map(makeRow)) : el('div', { className: 'empty-state' }, el('h3', {}, 'Không tìm thấy tài liệu'), el('p', {}, 'Thử đổi từ khoá hoặc bộ lọc để xem kết quả khác.')));
      summary.textContent = `${documents.length} tài liệu · ${documents.filter(item => item.active).length} đang bật · ${documents.filter(item => item.status === 'error').length} lỗi cần xử lý`;
    }
    [search, statusFilter, topicFilter].forEach(control => control.addEventListener(control === search ? 'input' : 'change', renderList));
    content.replaceChildren(el('div', { className: 'admin-documents' },
      el('div', { className: 'documents-heading' }, button('↑  Tải tài liệu', () => { uploadOpen = true; draw(); }, 'primary upload-document-button')),
      el('aside', { className: 'document-rule' }, el('span', {}, 'Quy tắc phát hành nguồn'), el('strong', {}, 'Chỉ tài liệu đã xử lý xong và được bật mới được Gia sư AI sử dụng.'), el('p', {}, liveDocuments ? 'Tài liệu tải lên được lưu ở trạng thái chờ xử lý và chưa được bật làm nguồn.' : 'Quy tắc dự kiến khi kết nối backend. Thao tác tại đây chỉ cập nhật bản xem trước.')),
      el('section', { className: 'panel documents-panel', 'aria-labelledby': 'document-list-title' }, el('div', { className: 'documents-toolbar' }, el('h2', { id: 'document-list-title' }, 'Danh sách tài liệu'), el('div', { className: 'document-filters' }, search, statusFilter, topicFilter)), el('div', { className: 'document-table-head', 'aria-hidden': 'true' }, ...['Tài liệu', 'Chủ đề', 'Xử lý', 'Sử dụng', 'Thao tác'].map(label => el('span', {}, label))), results, summary)
    ));
    renderList();
  }

  function drawUpload() {
    let selectedFile = null;
    const closeUpload = () => { if (!uploadPending) { uploadOpen = false; draw(); } };
    const subjectValue = item => String(liveDocuments ? item.id : item.name);
    const topicValue = item => String(liveDocuments ? item.id : item.name);
    const topicMatchesSubject = item => liveDocuments ? String(item.subjectId) === subject.value : item.subject === subject.value;
    const subject = el('select', { className: 'select', required: true }, el('option', { value: '' }, 'Chọn môn học'), ...uploadSubjects.filter(item => item.active).map(item => el('option', { value: subjectValue(item) }, `${item.name} · ${item.level}`)));
    const topic = el('select', { className: 'select', required: true, disabled: true }, el('option', { value: '' }, 'Chọn môn học trước'));
    const title = el('input', { className: 'input', maxlength: 200, placeholder: 'Ví dụ: Chuyên đề hàm số bậc hai', required: true });
    const file = el('input', { type: 'file', accept: '.pdf,.txt,application/pdf,text/plain', className: 'sr-only', id: 'document-file', 'aria-describedby': 'file-rules file-feedback' });
    const feedback = el('div', { id: 'file-feedback', className: 'upload-feedback', role: 'status' });
    const dropTitle = el('strong', {}, 'Kéo thả tệp hoặc chọn từ máy');
    const dropMeta = el('span', {}, 'PDF/TXT · tối đa 10 MB');
    const dropZone = el('div', { className: 'upload-dropzone' }, el('span', { className: 'upload-icon', 'aria-hidden': 'true' }, '↑'), dropTitle, dropMeta, el('label', { className: 'button ghost small', for: file.id }, 'Chọn tệp'), file);
    subject.addEventListener('change', () => {
      const matches = uploadTopics.filter(item => topicMatchesSubject(item) && item.active);
      topic.replaceChildren(el('option', { value: '' }, matches.length ? 'Chọn chủ đề' : 'Chưa có chủ đề phù hợp'), ...matches.map(item => el('option', { value: topicValue(item) }, `${item.chapter ? item.chapter + ' · ' : ''}${item.name}`)));
      topic.disabled = !matches.length;
    });
    const validateFile = candidate => {
      selectedFile = null;
      dropZone.classList.remove('has-file', 'has-error');
      feedback.replaceChildren();
      dropTitle.textContent = 'Kéo thả tệp hoặc chọn từ máy';
      dropMeta.textContent = 'PDF/TXT · tối đa 10 MB';
      if (!candidate) {
        dropTitle.textContent = 'Kéo thả tệp hoặc chọn từ máy';
        dropMeta.textContent = 'PDF/TXT · tối đa 10 MB';
        return false;
      }
      if (!/\.(pdf|txt)$/i.test(candidate.name) || (candidate.type && !ALLOWED_TYPES.includes(candidate.type))) {
        dropZone.classList.add('has-error'); feedback.replaceChildren(notice('Định dạng không hợp lệ. Hãy chọn tệp PDF hoặc TXT.', 'error')); file.value = ''; return false;
      }
      if (candidate.size > MAX_FILE_SIZE) {
        dropZone.classList.add('has-error'); feedback.replaceChildren(notice(`Tệp “${candidate.name}” vượt quá giới hạn 10 MB.`, 'error')); file.value = ''; return false;
      }
      selectedFile = candidate;
      dropZone.classList.add('has-file'); dropTitle.textContent = candidate.name; dropMeta.textContent = `${formatSize(candidate.size)} · Sẵn sàng tải lên`;
      if (!title.value.trim()) title.value = candidate.name.replace(/\.(pdf|txt)$/i, '');
      feedback.replaceChildren(notice(liveDocuments ? 'Tệp hợp lệ. Nhấn Tải lên để lưu tài liệu.' : 'Tệp hợp lệ để xem trước. Chưa gửi tệp lên máy chủ.', 'success'));
      return true;
    };
    file.addEventListener('change', () => { if (!uploadPending) validateFile(file.files[0]); });
    ['dragenter', 'dragover'].forEach(type => dropZone.addEventListener(type, event => { event.preventDefault(); dropZone.classList.add('is-dragging'); }));
    ['dragleave', 'drop'].forEach(type => dropZone.addEventListener(type, event => { event.preventDefault(); dropZone.classList.remove('is-dragging'); }));
    dropZone.addEventListener('drop', event => { if (uploadPending) return; const candidate = event.dataTransfer.files[0]; if (validateFile(candidate)) { const transfer = new DataTransfer(); transfer.items.add(candidate); file.files = transfer.files; } });
    const submit = el('button', { type: 'submit', className: 'button primary' }, 'Tải lên');
    const cancel = button('Hủy', closeUpload, 'ghost');
    const message = el('div', {role:'status', 'aria-live':'polite'});
    const form = el('form', { className: 'upload-form', novalidate: true }, el('h2', {}, 'Thông tin tài liệu'), el('div', { className: 'upload-fields' }, field('Môn học', subject), field('Chủ đề', topic)), field('Tiêu đề tài liệu', title), el('div', { className: 'field' }, el('span', { className: 'field-label' }, 'Tệp tài liệu'), dropZone, feedback), el('aside', { id: 'file-rules', className: 'upload-warning' }, el('span', { 'aria-hidden': 'true' }, '△'), el('div', {}, el('strong', {}, 'PDF phải có lớp văn bản có thể sao chép.'), el('p', {}, 'Tài liệu được tải lên ở trạng thái tắt cho đến khi xử lý xong.'))), el('div', { className: 'upload-actions' }, cancel, submit), message);
    setupValidation(form, [subject, topic, title, file]);
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (uploadPending) return;
      message.replaceChildren();
      const valid = validateFields([[subject, uploadSubjects.some(item => item.active && subjectValue(item) === subject.value) ? '' : 'Vui lòng chọn môn học.'], [topic, uploadTopics.some(item => item.active && topicValue(item) === topic.value && topicMatchesSubject(item)) ? '' : 'Vui lòng chọn chủ đề.'], [title, title.value.trim() ? '' : 'Vui lòng nhập tiêu đề tài liệu.'], [file, selectedFile ? '' : 'Vui lòng chọn tệp PDF hoặc TXT hợp lệ.']]);
      if (!valid || !selectedFile) return;
      if (!liveDocuments) {
        const extension = selectedFile.name.match(/\.(pdf|txt)$/i)?.[0] || '';
        const cleanTitle = title.value.trim().replace(/\.(pdf|txt)$/i, '');
        documents.unshift({ name: `${cleanTitle}${extension}`, size: formatSize(selectedFile.size), date: new Intl.DateTimeFormat('vi-VN').format(new Date()), topic: topic.value, status: 'pending', active: false });
        uploadOpen = false; draw(); toast('Đã thêm tài liệu vào bản xem trước với trạng thái đang xử lý.');
        return;
      }
      const data = new FormData();
      data.append('file', selectedFile);
      data.append('topic_id', topic.value);
      data.append('title', title.value.trim());
      uploadPending = true;
      form.setAttribute('aria-busy', 'true');
      for (const control of [subject,topic,title,file,submit,cancel]) control.disabled = true;
      submit.textContent = 'Đang tải lên…';
      message.replaceChildren(el('p', {}, 'Đang lưu tài liệu…'));
      try {
        const result = await api('/admin/documents', {method:'POST', body:data});
        if (!currentPage() || !form.isConnected) return;
        if (!result?.document?.id) throw new Error('Phản hồi tài liệu chưa hợp lệ. Vui lòng tải lại danh sách.');
        documents.unshift(serverDocument(result.document));
        uploadOpen = false;
        draw();
        toast(result.message || 'Tải tài liệu thành công.');
      } catch (error) {
        if (!currentPage() || !form.isConnected) return;
        for (const control of [subject,topic,title,file,submit,cancel]) control.disabled = false;
        showServerErrors(error.fields, {topic_id:topic, title, file});
        message.replaceChildren(notice(error.message || 'Chưa thể tải tài liệu. Vui lòng thử lại.', 'error'));
      } finally {
        uploadPending = false;
        form.removeAttribute('aria-busy');
        for (const control of [subject,topic,title,file,submit,cancel]) control.disabled = false;
        submit.textContent = 'Tải lên';
      }
    });
    content.replaceChildren(el('div', { className: 'admin-upload-view' }, el('div', { className: 'upload-page-heading' }, button('←  Tài liệu nguồn', closeUpload, 'upload-back'), el('h2', {}, 'Thêm tài liệu nguồn'), el('p', {}, 'PDF có văn bản hoặc TXT, gắn với đúng chủ đề.')), panel('', form), !uploadSubjects.length ? notice('Chưa có môn học và chủ đề đang hoạt động để tải tài liệu.', 'warning') : null, el('p', { className: 'upload-process-note' }, liveDocuments ? 'Tài liệu được lưu trên máy chủ. Nội dung sẽ ở trạng thái chờ cho đến khi được xử lý.' : 'Bản xem trước chỉ thêm tên tệp và trạng thái chờ minh họa. Không upload hoặc xử lý nội dung tệp.')));
  }

  root.append(tabs, content);
  draw();
  if (liveDocuments) loadDocuments();
  else if (!preview) loadAdminCatalog();
  return root;
}
