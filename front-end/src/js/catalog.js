import { api } from './api.js';
import { onSessionCleared } from './session.js';

const cache = new Map();
const pending = new Map();
let version = 0;
// Đăng xuất / đổi tài khoản thì bỏ cache, kể cả request đang bay.
onSessionCleared(() => { cache.clear(); pending.clear(); version++; });

export function loadCatalog({ force = false, gradeLevel = '' } = {}) {
  const grade = typeof gradeLevel === 'string' ? gradeLevel.trim() : '';
  if (cache.has(grade) && !force) return Promise.resolve(cache.get(grade));
  if (!pending.has(grade)) {
    const current = version;
    const query = grade ? `?${new URLSearchParams({ gradeLevel: grade })}` : '';
    const request = api(`/catalog/subjects${query}`).then(result => {
      if (!Array.isArray(result?.subjects)) throw new Error('Danh mục môn học chưa hợp lệ. Vui lòng thử lại.');
      if (current === version) cache.set(grade, result.subjects);
      return result.subjects;
    }).finally(() => { if (pending.get(grade) === request) pending.delete(grade); });
    pending.set(grade, request);
  }
  return pending.get(grade);
}

export const flattenTopics = subjects => subjects.flatMap(subject =>
  subject.chapters.flatMap(chapter => chapter.topics.map(topic => ({
    ...topic, subjectId: subject.id, subjectName: subject.name, gradeLevel: subject.gradeLevel, chapterName: chapter.name
  }))));
