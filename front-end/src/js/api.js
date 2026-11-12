import { getAccessToken, clearSession } from './session.js';

const configuredBase = document.querySelector('meta[name="api-base"]')?.content.trim();
const API_BASE = (configuredBase || '/api').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(message, status = 0, code = 'NETWORK_ERROR', fields = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

export async function api(path, { method = 'GET', body, auth = true, signal } = {}) {
  const token = auth ? getAccessToken() : '';
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method, headers, signal, cache: 'no-store',
      body: body === undefined ? undefined : JSON.stringify(body),
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
