import { api, ApiError } from './api.js';
import { onSessionCleared } from './session.js';

const MAX_QUOTA_LIMIT = 1_000_000;
const ISO_WITH_ZONE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,6})?)?(Z|([+-])(\d{2}):(\d{2}))$/;
let cachedQuota = null;

onSessionCleared(() => { cachedQuota = null; });

function validResetTime(value) {
  if (typeof value !== 'string') return false;
  const match = ISO_WITH_ZONE.exec(value);
  const timestamp = Date.parse(value);
  if (!match || Number.isNaN(timestamp)) return false;
  const [, year, month, day, hour, minute, second = '0', zone, sign, offsetHour = '0', offsetMinute = '0'] = match;
  if (Number(offsetHour) > 23 || Number(offsetMinute) > 59) return false;
  const offset = zone === 'Z' ? 0 : (sign === '+' ? 1 : -1) * (Number(offsetHour) * 60 + Number(offsetMinute));
  const local = new Date(timestamp + offset * 60_000);
  return local.getUTCFullYear() === Number(year)
    && local.getUTCMonth() + 1 === Number(month)
    && local.getUTCDate() === Number(day)
    && local.getUTCHours() === Number(hour)
    && local.getUTCMinutes() === Number(minute)
    && local.getUTCSeconds() === Number(second);
}

export function validateChatQuota(value) {
  const limit = value?.limit;
  const remaining = value?.remaining;
  const nextResetAt = value?.nextResetAt;
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > MAX_QUOTA_LIMIT) {
    throw new ApiError('Giới hạn lượt hỏi AI từ máy chủ chưa hợp lệ.', 0, 'INVALID_QUOTA_RESPONSE');
  }
  if (!Number.isSafeInteger(remaining) || remaining < 0 || remaining > limit) {
    throw new ApiError('Số lượt hỏi AI còn lại từ máy chủ chưa hợp lệ.', 0, 'INVALID_QUOTA_RESPONSE');
  }
  if (!validResetTime(nextResetAt)) {
    throw new ApiError('Thời điểm làm mới hạn mức từ máy chủ chưa hợp lệ.', 0, 'INVALID_QUOTA_RESPONSE');
  }
  return Object.freeze({ limit, remaining, nextResetAt });
}

export function formatQuotaReset(nextResetAt) {
  const date = new Date(nextResetAt);
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
  }).format(date);
}

// Provisional TK-076 frontend contract. The backend quota route belongs to TK-077.
export async function loadChatQuota({ force = false, signal } = {}) {
  if (!force && cachedQuota) return cachedQuota;
  const result = await api('/chat/quota', { signal });
  cachedQuota = validateChatQuota(result);
  return cachedQuota;
}
