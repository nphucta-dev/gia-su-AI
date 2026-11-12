import { onSessionCleared } from '../session.js';
import { el, button, heading, panel, field, badge, notice, toast } from '../components/ui.js';
import { setupValidation, validateFields } from '../components/validation.js';

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
  const root = el('div', { className: 'admin-page' }, el('div', {className:'admin-preview-note'}, notice('Bản xem trước: thay đổi chỉ nằm trong bộ nhớ, chưa lưu lên máy chủ. Tải lại trang hoặc đăng xuất sẽ đặt lại dữ liệu.', 'warning')));
  const content = el('div');
  const requestedTab = new URLSearchParams(location.hash.split('?')[1]).get('tab');
  const active = ['subjects','topics','documents'].includes(requestedTab) ? requestedTab : 'subjects';
  let editing = null;
  let uploadOpen = false;
  const {subjects, topics, documents} = catalog;
  const pageHeading = heading(active === 'subjects' ? 'Quản lý môn học' : active === 'topics' ? 'Quản lý chủ đề' : 'Tài liệu nguồn', active === 'subjects' ? 'Cập nhật danh mục người học có thể truy cập.' : active === 'topics' ? 'Sắp xếp nội dung theo môn học và chương.' : 'Kiểm soát nguồn kiến thức được dùng trong câu trả lời AI.');
  root.prepend(pageHeading);
  const tabs = el('nav', { className: 'tabs', 'aria-label': 'Nhóm quản trị' });

  function draw() {
    tabs.replaceChildren(...[['subjects', 'Môn học'], ['topics', 'Chủ đề'], ['documents', 'Tài liệu nguồn']].map(([id, label]) => {
      const tab = button(label, () => { if(id !== active) location.hash = 'admin?tab=' + id; }, `tab ${active === id ? 'active' : ''}`);
      if (id === active) tab.setAttribute('aria-current', 'page');
      return tab;
    }));
    if (active === 'documents') return uploadOpen ? drawUpload() : drawDocuments();
    drawCatalog();
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
      const [label, kind] = statusMeta[document.status];
      const toggle = el('button', { type: 'button', className: `source-switch ${document.active ? 'active' : ''}`, role: 'switch', 'aria-checked': String(document.active), 'aria-label': `${document.active ? 'Tắt' : 'Bật'} nguồn ${document.name}`, disabled: document.status !== 'ready' }, el('span', { 'aria-hidden': 'true' }));
      toggle.addEventListener('click', () => { document.active = !document.active; renderList(); toast(document.active ? 'Đã bật tài liệu trong bản xem trước.' : 'Đã tắt tài liệu trong bản xem trước.'); });
      const action = document.status === 'error' ? button('Thử lại', () => { document.status = 'pending'; document.error = ''; renderList(); toast('Đã đổi trạng thái minh họa sang chờ xử lý. Chưa gửi yêu cầu lên máy chủ.'); }, 'document-action') : document.status === 'pending' ? el('span', { className: 'document-waiting' }, 'Chờ xử lý') : button('Chi tiết', () => toast(`${document.name}: trạng thái sẵn sàng là dữ liệu minh họa.`), 'document-action');
      return el('article', { className: 'document-row' },
        el('div', { className: `document-icon ${kind}`, 'aria-hidden': 'true' }, document.status === 'error' ? '!' : '▤'),
        el('div', { className: 'document-name' }, el('h3', {}, document.name), el('p', {}, `${document.size} · ${document.date}`), document.error ? el('p', { className: 'document-error' }, document.error) : null),
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
      el('aside', { className: 'document-rule' }, el('span', {}, 'Quy tắc phát hành nguồn'), el('strong', {}, 'Chỉ tài liệu đã xử lý xong và được bật mới được Gia sư AI sử dụng.'), el('p', {}, 'Quy tắc dự kiến khi kết nối backend. Thao tác tại đây chỉ cập nhật bản xem trước.')),
      el('section', { className: 'panel documents-panel', 'aria-labelledby': 'document-list-title' }, el('div', { className: 'documents-toolbar' }, el('h2', { id: 'document-list-title' }, 'Danh sách tài liệu'), el('div', { className: 'document-filters' }, search, statusFilter, topicFilter)), el('div', { className: 'document-table-head', 'aria-hidden': 'true' }, ...['Tài liệu', 'Chủ đề', 'Xử lý', 'Sử dụng', 'Thao tác'].map(label => el('span', {}, label))), results, summary)
    ));
    renderList();
  }

  function drawUpload() {
    let selectedFile = null;
    const subject = el('select', { className: 'select', required: true }, el('option', { value: '' }, 'Chọn môn học'), ...subjects.filter(item => item.active).map(item => el('option', { value: item.name }, `${item.name} · ${item.level}`)));
    const topic = el('select', { className: 'select', required: true, disabled: true }, el('option', { value: '' }, 'Chọn môn học trước'));
    const title = el('input', { className: 'input', maxlength: 200, placeholder: 'Ví dụ: Chuyên đề hàm số bậc hai', required: true });
    const file = el('input', { type: 'file', accept: '.pdf,.txt,application/pdf,text/plain', className: 'sr-only', id: 'document-file', 'aria-describedby': 'file-rules file-feedback' });
    const feedback = el('div', { id: 'file-feedback', className: 'upload-feedback', role: 'status' });
    const dropTitle = el('strong', {}, 'Kéo thả tệp hoặc chọn từ máy');
    const dropMeta = el('span', {}, 'PDF/TXT · tối đa 10 MB');
    const dropZone = el('div', { className: 'upload-dropzone' }, el('span', { className: 'upload-icon', 'aria-hidden': 'true' }, '↑'), dropTitle, dropMeta, el('label', { className: 'button ghost small', for: file.id }, 'Chọn tệp'), file);
    subject.addEventListener('change', () => {
      const matches = topics.filter(item => item.subject === subject.value && item.active);
      topic.replaceChildren(el('option', { value: '' }, matches.length ? 'Chọn chủ đề' : 'Chưa có chủ đề phù hợp'), ...matches.map(item => el('option', { value: item.name }, item.name)));
      topic.disabled = !matches.length;
    });
    const validateFile = candidate => {
      selectedFile = null;
      dropZone.classList.remove('has-file', 'has-error');
      feedback.replaceChildren();
      if (!candidate) return false;
      if (!/\.(pdf|txt)$/i.test(candidate.name) || (candidate.type && !ALLOWED_TYPES.includes(candidate.type))) {
        dropZone.classList.add('has-error'); feedback.replaceChildren(notice('Định dạng không hợp lệ. Hãy chọn tệp PDF hoặc TXT.', 'error')); file.value = ''; return false;
      }
      if (candidate.size > MAX_FILE_SIZE) {
        dropZone.classList.add('has-error'); feedback.replaceChildren(notice(`Tệp “${candidate.name}” vượt quá giới hạn 10 MB.`, 'error')); file.value = ''; return false;
      }
      selectedFile = candidate;
      dropZone.classList.add('has-file'); dropTitle.textContent = candidate.name; dropMeta.textContent = `${formatSize(candidate.size)} · Sẵn sàng tải lên`;
      if (!title.value.trim()) title.value = candidate.name.replace(/\.(pdf|txt)$/i, '');
      feedback.replaceChildren(notice('Tệp hợp lệ để xem trước. Chưa gửi tệp lên máy chủ.', 'success'));
      return true;
    };
    file.addEventListener('change', () => validateFile(file.files[0]));
    ['dragenter', 'dragover'].forEach(type => dropZone.addEventListener(type, event => { event.preventDefault(); dropZone.classList.add('is-dragging'); }));
    ['dragleave', 'drop'].forEach(type => dropZone.addEventListener(type, event => { event.preventDefault(); dropZone.classList.remove('is-dragging'); }));
    dropZone.addEventListener('drop', event => { const candidate = event.dataTransfer.files[0]; if (validateFile(candidate)) { const transfer = new DataTransfer(); transfer.items.add(candidate); file.files = transfer.files; } });
    const form = el('form', { className: 'upload-form', novalidate: true }, el('h2', {}, 'Thông tin tài liệu'), el('div', { className: 'upload-fields' }, field('Môn học', subject), field('Chủ đề', topic)), field('Tiêu đề tài liệu', title), el('div', { className: 'field' }, el('span', { className: 'field-label' }, 'Tệp tài liệu'), dropZone, feedback), el('aside', { id: 'file-rules', className: 'upload-warning' }, el('span', { 'aria-hidden': 'true' }, '△'), el('div', {}, el('strong', {}, 'PDF phải có lớp văn bản có thể sao chép.'), el('p', {}, 'Tài liệu được tải lên ở trạng thái tắt cho đến khi xử lý xong.'))), el('div', { className: 'upload-actions' }, button('Hủy', () => { uploadOpen = false; draw(); }, 'ghost'), el('button', { type: 'submit', className: 'button primary' }, 'Tải lên')));
    setupValidation(form, [subject, topic, title, file]);
    form.addEventListener('submit', event => {
      event.preventDefault();
      const valid = validateFields([[subject, subjects.some(item => item.active && item.name === subject.value) ? '' : 'Vui lòng chọn môn học.'], [topic, topics.some(item => item.active && item.name === topic.value && item.subject === subject.value) ? '' : 'Vui lòng chọn chủ đề.'], [title, title.value.trim() ? '' : 'Vui lòng nhập tiêu đề tài liệu.'], [file, selectedFile ? '' : 'Vui lòng chọn tệp PDF hoặc TXT hợp lệ.']]);
      if (!valid || !selectedFile) return;
      const extension = selectedFile.name.match(/\.(pdf|txt)$/i)?.[0] || '';
      const cleanTitle = title.value.trim().replace(/\.(pdf|txt)$/i, '');
      documents.unshift({ name: `${cleanTitle}${extension}`, size: formatSize(selectedFile.size), date: new Intl.DateTimeFormat('vi-VN').format(new Date()), topic: topic.value, status: 'pending', active: false });
      uploadOpen = false; draw(); toast('Đã thêm tài liệu vào bản xem trước với trạng thái đang xử lý.');
    });
    content.replaceChildren(el('div', { className: 'admin-upload-view' }, el('div', { className: 'upload-page-heading' }, button('←  Tài liệu nguồn', () => { uploadOpen = false; draw(); }, 'upload-back'), el('h2', {}, 'Thêm tài liệu nguồn'), el('p', {}, 'PDF có văn bản hoặc TXT, gắn với đúng chủ đề.')), panel('', form), el('p', { className: 'upload-process-note' }, 'Bản xem trước chỉ thêm tên tệp và trạng thái chờ minh họa. Không upload hoặc xử lý nội dung tệp.')));
  }

  root.append(tabs, content);
  draw();
  return root;
}
