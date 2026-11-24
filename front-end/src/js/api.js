import { getAccessToken, clearSession } from './session.js';

const configuredBase = document.querySelector('meta[name="api-base"]')?.content.trim();
const base = (configuredBase || '/api').replace(/\/$/, '');
const API_BASE = /^https?:\/\/[^/]+$/.test(base) ? `${base}/api` : base;

export class ApiError extends Error {
  constructor(message, status = 0, code = 'NETWORK_ERROR', fields = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

// Authenticated binary download; keep the JSON API contract unchanged.
export async function apiFile(path, { signal } = {}) {
  const token = getAccessToken();
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { Accept: 'application/pdf, text/plain', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      signal, cache: 'no-store',
    });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new ApiError('Không thể tải tệp. Vui lòng kiểm tra kết nối và thử lại.');
  }
  if (token && response.status === 401 && getAccessToken() === token) clearSession('expired');
  if (!response.ok) {
    let result;
    try { result = await response.json(); } catch { /* A non-JSON error must not become a document. */ }
    throw new ApiError(result?.error?.message || 'Chưa thể tải tệp tài liệu. Vui lòng thử lại.', response.status, result?.error?.code || 'FILE_UNAVAILABLE');
  }
  try {
    return { blob: await response.blob(), contentType: response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() };
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new ApiError('Quá trình tải tệp bị gián đoạn. Vui lòng thử lại.');
  }
}

export async function api(path, { method = 'GET', body, auth = true, signal } = {}) {
  const token = auth ? getAccessToken() : '';
  const headers = { Accept: 'application/json' };
  const multipart = body instanceof FormData;
  if (body !== undefined && !multipart) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method, headers, signal, cache: 'no-store',
      body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
    });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new ApiError('Không thể kết nối với máy chủ. Vui lòng thử lại.');
  }
  if (auth && token && response.status === 401 && getAccessToken() === token) clearSession('expired');
  if (auth && token && path === '/auth/me' && response.status === 403 && getAccessToken() === token) clearSession('inactive');

  let result;
  try {
    const text = await response.text();
    result = text ? JSON.parse(text) : null;
  } catch {
    throw new ApiError('Phản hồi từ máy chủ chưa hợp lệ. Vui lòng thử lại.', response.status, 'INVALID_RESPONSE');
  }
  if (!response.ok) {
    const error = result?.error || {};
    throw new ApiError(error.message || 'Chưa thể xử lý yêu cầu. Vui lòng thử lại.', response.status, error.code || 'REQUEST_FAILED', error.fields || {});
  }
  return result;
}
