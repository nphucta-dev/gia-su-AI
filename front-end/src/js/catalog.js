import { api } from './api.js';
import { onSessionCleared } from './session.js';

let cache = null;
let pending = null;
let version = 0;
// Đăng xuất / đổi tài khoản thì bỏ cache, kể cả request đang bay.
onSessionCleared(() => { cache = null; pending = null; version++; });

export function loadCatalog({ force = false } = {}) {
  if (cache && !force) return Promise.resolve(cache);
  if (!pending) {
    const current = version;
    const request = api('/catalog/subjects').then(result => {
      if (!Array.isArray(result?.subjects)) throw new Error('Danh mục môn học chưa hợp lệ. Vui lòng thử lại.');
      if (current === version) cache = result.subjects;
      return result.subjects;
    }).finally(() => { if (pending === request) pending = null; });
    pending = request;
  }
  return pending;
}

export const flattenTopics = subjects => subjects.flatMap(subject =>
  subject.chapters.flatMap(chapter => chapter.topics.map(topic => ({
    ...topic, subjectId: subject.id, subjectName: subject.name, gradeLevel: subject.gradeLevel, chapterName: chapter.name
  }))));
