import { api, ApiError } from './api.js';
import { loadCatalog, flattenTopics } from './catalog.js';

const PAGE_SIZE = 100;
const MAX_OFFSET = 100000;

function validCount(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

function validateProgressItems(items, label) {
  if (!Array.isArray(items)) throw new ApiError(`Dữ liệu ${label} từ máy chủ chưa hợp lệ.`);
  return items.map(item => {
    if (!item || !Number.isSafeInteger(item.id) || item.id <= 0
      || !Number.isSafeInteger(item.topicId) || item.topicId <= 0
      || !validCount(item.totalQuizzes) || !validCount(item.correctCount)
      || !validCount(item.totalCount) || item.correctCount > item.totalCount
      || !Number.isFinite(item.masteryPercent) || item.masteryPercent < 0 || item.masteryPercent > 100) {
      throw new ApiError(`Dữ liệu ${label} từ máy chủ chưa hợp lệ.`);
    }
    return item;
  });
}

async function loadAllPages(path, collectionKey, signal) {
  const collected = [];
  let offset = 0;

  while (true) {
    const response = await api(`${path}?limit=${PAGE_SIZE}&offset=${offset}`, { signal });
    const items = response?.[collectionKey];
    if (!Array.isArray(items) || typeof response.hasMore !== 'boolean') {
      throw new ApiError(`Phản hồi ${path} từ máy chủ chưa hợp lệ.`);
    }
    collected.push(...items);

    if (!response.hasMore) return collected;
    if (!items.length || offset + items.length > MAX_OFFSET) {
      throw new ApiError(`Không thể đọc hết dữ liệu ${path}. Vui lòng tải lại.`);
    }
    offset += items.length;
  }
}

function validateSessions(items) {
  if (!Array.isArray(items)) throw new ApiError('Danh sách phiên chat từ máy chủ chưa hợp lệ.');
  for (const session of items) {
    if (!session || !Number.isSafeInteger(session.id) || session.id <= 0
      || !Number.isSafeInteger(session.topicId) || session.topicId <= 0
      || typeof session.updatedAt !== 'string') {
      throw new ApiError('Danh sách phiên chat từ máy chủ chưa hợp lệ.');
    }
  }
  return items;
}

/** Dashboard is composed only from existing owner-scoped backend endpoints. */
export async function loadDashboardData({ signal } = {}) {
  const [progressResponse, reviewResponse, sessionsResponse, catalogResult] = await Promise.all([
    loadAllPages('/progress', 'progress', signal),
    loadAllPages('/progress/review-topics', 'topics', signal),
    loadAllPages('/chat/sessions', 'sessions', signal),
    loadCatalog().then(subjects => ({ subjects })).catch(error => ({ error, subjects: [] })),
  ]);

  const progress = validateProgressItems(progressResponse, 'tiến độ');
  const reviews = validateProgressItems(reviewResponse, 'chủ đề cần ôn');
  const sessions = validateSessions(sessionsResponse);
  const topics = flattenTopics(catalogResult.subjects);
  const topicById = new Map(topics.map(topic => [Number(topic.id), topic]));

  const totalQuizzes = progress.reduce((sum, item) => sum + item.totalQuizzes, 0);
  const correctCount = progress.reduce((sum, item) => sum + item.correctCount, 0);
  const totalCount = progress.reduce((sum, item) => sum + item.totalCount, 0);
  const averageScore = totalCount > 0 ? (correctCount / totalCount) * 100 : null;

  const mapTopic = item => {
    const catalogTopic = topicById.get(Number(item.topicId));
    return {
      ...item,
      name: catalogTopic?.name || `Chủ đề #${item.topicId}`,
      subjectName: catalogTopic?.subjectName || '',
      chapterName: catalogTopic?.chapterName || '',
    };
  };

  return {
    stats: {
      totalQuizzes,
      averageScore,
      chatSessions: sessions.length,
      studiedTopics: progress.length,
    },
    progress: progress.map(mapTopic).sort((a, b) => a.name.localeCompare(b.name, 'vi')),
    reviewTopics: reviews.map(mapTopic),
    recentSessions: sessions.slice(0, 5),
    catalogUnavailable: Boolean(catalogResult.error),
  };
}