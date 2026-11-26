import { api, apiFile, ApiError } from '../api.js';
import { getSession, getAccessToken } from '../session.js';
import { el, heading, link, button, notice, badge } from '../components/ui.js';
import { skeletonState, thinkingStatus } from '../components/motion.js';

let activeController;
const PAGE_SIZE = 20;
const MAX_OFFSET = 100000;
function positiveId(value) {
  const text = String(value ?? ''), number = Number(text);
  return /^[1-9]\d*$/.test(text) && Number.isSafeInteger(number) && number <= 2147483647 ? number : null;
}
function metadata(value) {
  if (!value || !['id', 'topicId', 'subjectId'].every(key => typeof value[key] === 'number' && positiveId(value[key]))
    || !['title', 'subjectName', 'topicName', 'chapterName', 'fileName'].every(key => typeof value[key] === 'string')
    || !['pdf', 'txt', 'unknown'].includes(value.fileType)) {
    throw new ApiError('Thông tin tài liệu từ máy chủ chưa hợp lệ. Vui lòng thử lại.');
  }
  return value;
}

export function renderLearningDocuments() {
  activeController?.abort();
  if (getSession().reason === 'preview') return el('div', {}, heading('Tài liệu học tập', 'Tài liệu đã phát hành theo môn học và chủ đề.'),
    notice('Chế độ xem thử không tải tài liệu tài khoản. Vui lòng thoát xem thử và đăng nhập thật để đọc tài liệu.', 'warning'), link('Về trang học', '#home'));
  const controller = new AbortController(); activeController = controller;
  const owner = getSession().user?.id, token = getAccessToken();
  const params = new URLSearchParams(location.hash.split('?')[1]);
  const ids = Object.fromEntries(['subject', 'topic', 'document'].map(key => [key, params.has(key) ? positiveId(params.get(key)) : null]));
  const offsetText = params.get('offset') ?? '0';
  const offset = /^(0|[1-9]\d*)$/.test(offsetText) ? Number(offsetText) : NaN;
  const invalid = ['subject', 'topic', 'document'].some(key => params.has(key) && (!ids[key] || params.getAll(key).length !== 1))
    || !Number.isSafeInteger(offset) || offset > MAX_OFFSET || params.getAll('offset').length > 1;
  const filters = new URLSearchParams();
  if (ids.subject) filters.set('subject', ids.subject);
  if (ids.topic) filters.set('topic', ids.topic);
  const href = (id, pageOffset = offset) => {
    const query = new URLSearchParams(filters);
    if (id) query.set('document', id);
    if (pageOffset) query.set('offset', pageOffset);
    return `#documents${query.size ? `?${query}` : ''}`;
  };
  const listStatus = el('div', { role: 'status' });
  const list = el('ul', { className: 'learning-document-list' });
  const pagination = el('nav', { className: 'learning-document-pagination', 'aria-label': 'Phân trang tài liệu', hidden: true });
  const readerHeader = el('div');
  const readerStatus = el('div', { role: 'status', 'aria-live': 'polite' });
  const content = el('div', { className: 'learning-document-content' });
  const reader = el('section', { className: 'panel learning-document-reader', 'aria-label': 'Đọc tài liệu' }, readerHeader, readerStatus, content);
  const root = el('div', { className: 'learning-documents-page' },
    heading('Tài liệu học tập', 'Chọn tài liệu đã phát hành để đọc và hỏi gia sư theo chủ đề.'),
    el('div', { className: 'page-actions' }, link('Về danh mục môn học', '#home', 'button ghost small'), ids.document ? link('Về danh sách tài liệu', href(), 'button ghost small') : null),
    el('div', { className: 'learning-documents-layout' },
      el('section', { className: 'panel panel-cool learning-document-catalog', 'aria-label': 'Danh sách tài liệu' }, el('h2', {}, 'Danh sách tài liệu'), listStatus, list, pagination), reader));
  let listPending = false, readerPending = false, blobUrl = null, signature = null, timer, revoked = false;
  const current = () => root.isConnected && !controller.signal.aborted && getSession().status === 'authenticated'
    && getSession().user?.id === owner && getSession().reason !== 'preview' && getAccessToken() === token;
  const matches = item => (!ids.topic || item.topicId === ids.topic) && (!ids.subject || item.subjectId === ids.subject);
  function clearContent() {
    content.replaceChildren(); signature = null;
    if (blobUrl) { URL.revokeObjectURL(blobUrl); blobUrl = null; }
  }
  function cleanup() {
    clearTimeout(timer); clearContent(); readerHeader.replaceChildren();
    document.removeEventListener('visibilitychange', visibilityChanged);
    window.removeEventListener('focus', focusReturned);
  }
  controller.signal.addEventListener('abort', cleanup, { once: true });
  function schedule() {
    clearTimeout(timer);
    if (current() && ids.document && !document.hidden && !revoked) timer = setTimeout(() => loadDocument(true), 60000);
  }
  function visibilityChanged() {
    clearTimeout(timer);
    if (!document.hidden && current() && ids.document && !revoked) loadDocument(true);
  }
  function focusReturned() { if (!document.hidden && current() && ids.document && !revoked) loadDocument(true); }
  async function loadList() {
    if (listPending || !current()) return;
    listPending = true; list.replaceChildren();
    pagination.hidden = true; pagination.replaceChildren();
    list.setAttribute('aria-busy', 'true'); listStatus.replaceChildren(skeletonState('Đang tải danh sách tài liệu…', 'list'));
    const query = new URLSearchParams();
    if (ids.subject) query.set('subjectId', ids.subject);
    if (ids.topic) query.set('topicId', ids.topic);
    query.set('limit', PAGE_SIZE);
    query.set('offset', offset);
    try {
      const result = await api(`/documents${query.size ? `?${query}` : ''}`, { signal: controller.signal });
      if (!current()) return;
      if (!Array.isArray(result?.documents) || result.limit !== PAGE_SIZE || result.offset !== offset
        || typeof result.hasMore !== 'boolean' || result.documents.length > PAGE_SIZE) {
        throw new ApiError('Danh sách tài liệu từ máy chủ chưa hợp lệ.');
      }
      const documents = result.documents.map(metadata);
      if (documents.some(item => !matches(item)) || new Set(documents.map(item => item.id)).size !== documents.length) throw new ApiError('Danh sách tài liệu không khớp môn hoặc chủ đề đã chọn.');
      listStatus.replaceChildren(...(documents.length ? [] : [notice(offset
        ? 'Trang này không còn tài liệu. Hãy quay về trang trước.'
        : 'Chưa có tài liệu được phát hành cho lựa chọn này.')]));
      list.replaceChildren(...documents.map(item => el('li', {},
        el('a', { href: href(item.id), className: 'learning-document-link', 'aria-current': item.id === ids.document ? 'page' : null },
          el('strong', {}, item.title), el('span', { className: 'helper' }, `${item.subjectName} · ${item.chapterName} · ${item.topicName}`),
          badge(item.fileType === 'unknown' ? 'Chưa hỗ trợ' : item.fileType.toUpperCase(), item.fileType === 'unknown' ? 'neutral' : 'primary')))));
      pagination.replaceChildren(
        offset > 0 ? link('Trang trước', href(null, Math.max(0, offset - PAGE_SIZE)), 'button secondary small') : null,
        documents.length ? el('span', { className: 'helper' }, `Tài liệu ${offset + 1}–${offset + documents.length}`) : null,
        result.hasMore && offset + PAGE_SIZE <= MAX_OFFSET ? link('Trang sau', href(null, offset + PAGE_SIZE), 'button secondary small') : null);
      pagination.hidden = offset === 0 && !result.hasMore;
    } catch (error) {
      if (error.name !== 'AbortError' && current()) listStatus.replaceChildren(notice(error.message, 'error'), button('Thử lại danh sách', loadList, 'secondary small'));
    } finally { listPending = false; if (current()) list.removeAttribute('aria-busy'); }
  }
  function showHeader(item) {
    const key = JSON.stringify([item.title, item.subjectName, item.chapterName, item.topicName, item.topicId, item.fileType]);
    if (readerHeader.childElementCount && readerHeader.dataset.metadata === key) return;
    readerHeader.dataset.metadata = key;
    readerHeader.replaceChildren(el('h2', {}, item.title),
      el('p', { className: 'helper' }, `${item.subjectName} · ${item.chapterName} · ${item.topicName}`),
      el('div', { className: 'page-actions' }, badge(item.fileType.toUpperCase(), 'primary'),
        link('Hỏi gia sư về chủ đề này', `#chat?topic=${item.topicId}`, 'button secondary small', { trailingIcon: 'arrowRight' })));
  }
  async function loadDocument(verifyOnly = false) {
    if (readerPending || !current() || !ids.document) return;
    readerPending = true; clearTimeout(timer);
    if (!verifyOnly) { revoked = false; clearContent(); readerHeader.replaceChildren(); }
    reader.setAttribute('aria-busy', 'true');
    readerStatus.replaceChildren(thinkingStatus(verifyOnly ? 'Đang kiểm tra lại quyền xem tài liệu…' : 'Đang tải tài liệu…'));
    let loadedItem = null;
    try {
      const result = await api(`/documents/${ids.document}`, { signal: controller.signal });
      if (!current()) return;
      const item = metadata(result?.document);
      loadedItem = item;
      if (item.id !== ids.document || !matches(item)) throw new ApiError('Tài liệu không khớp môn hoặc chủ đề trên đường dẫn.', 404, 'DOCUMENT_FILTER_MISMATCH');
      if (item.fileType === 'unknown') throw new ApiError('Định dạng tài liệu này chưa được hỗ trợ. Vui lòng chọn PDF hoặc TXT.');
      const nextSignature = JSON.stringify([item.fileName, item.fileType, item.processedAt, item.sizeBytes]);
      if (signature !== nextSignature) {
        clearContent(); readerHeader.replaceChildren();
        const file = await apiFile(`/documents/${ids.document}/file`, { signal: controller.signal });
        if (!current()) return;
        if (file.contentType !== (item.fileType === 'pdf' ? 'application/pdf' : 'text/plain')) throw new ApiError('Máy chủ trả về sai định dạng tệp tài liệu. Vui lòng thử lại.');
        if (item.fileType === 'txt') {
          let text;
          try { text = new TextDecoder('utf-8', { fatal: true }).decode(await file.blob.arrayBuffer()); }
          catch { throw new ApiError('Tệp TXT không có nội dung UTF-8 hợp lệ. Vui lòng liên hệ người quản trị.'); }
          if (!current()) return;
          content.replaceChildren(el('pre', { className: 'learning-document-text', tabindex: '0', 'aria-label': 'Nội dung tài liệu TXT' }, text || 'Tài liệu không có nội dung văn bản.'));
        } else {
          if (await file.blob.slice(0, 5).text() !== '%PDF-') throw new ApiError('Tệp PDF chưa hợp lệ. Vui lòng thử lại hoặc liên hệ người quản trị.');
          if (!current()) return;
          blobUrl = URL.createObjectURL(file.blob);
          content.replaceChildren(el('iframe', { className: 'learning-document-pdf', title: `Đọc PDF: ${item.title}`, src: blobUrl, referrerpolicy: 'no-referrer' }),
            el('p', { className: 'helper' }, 'Nếu trình duyệt không hiển thị nội dung nhúng, hãy ',
              link('mở PDF ở tab riêng', blobUrl, 'learning-document-open')));
          const open = content.querySelector('a'); open.target = '_blank'; open.rel = 'noopener noreferrer';
        }
        signature = nextSignature;
      }
      showHeader(item); readerStatus.replaceChildren();
    } catch (error) {
      if (error.name === 'AbortError' || !current()) return;
      clearContent(); readerHeader.replaceChildren();
      const extracted = error.code === 'DOCUMENT_FILE_NOT_FOUND'
        && loadedItem && typeof loadedItem.content === 'string' && loadedItem.content.trim()
        && Array.isArray(loadedItem.chunks) && loadedItem.chunks.length > 0;
      if (extracted) {
        showHeader(loadedItem);
        readerStatus.replaceChildren(
          notice('Tệp gốc không còn trên máy chủ; đang hiển thị nội dung văn bản đã trích xuất.', 'warning'),
          button('Thử lại tài liệu', () => loadDocument(), 'secondary small'),
        );
        content.replaceChildren(el('pre', { className: 'learning-document-text', tabindex: '0', 'aria-label': 'Nội dung tài liệu đã trích xuất' }, loadedItem.content));
        return;
      }
      revoked = error.status === 404 || error.status === 403;
      const message = error.status === 403 ? 'Bạn không còn quyền truy cập tài liệu này.'
        : error.code === 'DOCUMENT_FILE_NOT_FOUND' ? 'Tệp gốc của tài liệu không còn truy cập được.'
          : error.status === 404 ? 'Tài liệu không còn truy cập được hoặc không thuộc môn/chủ đề đã chọn.'
            : verifyOnly ? `Chưa xác minh lại được tài liệu. ${error.message}` : error.message;
      readerStatus.replaceChildren(notice(message, 'error'), button('Thử lại tài liệu', () => loadDocument(), 'secondary small'));
      if (revoked) loadList();
    } finally { readerPending = false; if (current()) { reader.removeAttribute('aria-busy'); schedule(); } }
  }
  queueMicrotask(() => {
    if (!current()) return;
    if (invalid) { listStatus.replaceChildren(notice('Đường dẫn tài liệu không hợp lệ. Vui lòng chọn lại môn hoặc chủ đề.', 'error')); reader.hidden = true; return; }
    const observer = new MutationObserver(() => { if (!root.isConnected) { controller.abort(); observer.disconnect(); } });
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener('visibilitychange', visibilityChanged);
    window.addEventListener('focus', focusReturned);
    loadList();
    if (ids.document) loadDocument();
    else readerHeader.replaceChildren(el('h2', {}, 'Chọn tài liệu để đọc'), el('p', { className: 'helper' }, 'Chọn PDF hoặc TXT từ danh sách. Nội dung sẽ hiển thị tại đây.'));
  });
  return root;
}
