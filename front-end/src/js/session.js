// /login follows origin/feature/auth-and-database; /me exists on current main.
// No server logout/revocation contract exists. Tokens are kept only for this tab.
const tokenKey = 'gia-su-ai.access-token';
const apiBase = document.querySelector('meta[name="api-base"]')?.content || 'http://localhost:8000';
let state = Object.freeze({ status: 'checking', user: null, message: '' });
let generation = 0;
let memoryToken = '';
let pendingLogin = null;
const previewKey = 'gia-su-ai.preview-role';
export const previewAvailable = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
let previewRole = '';
function savePreview(role) { previewRole = role; try { if(role) sessionStorage.setItem(previewKey,role); else sessionStorage.removeItem(previewKey); } catch { /* Memory-only preview. */ } }
function readPreview() { if(!previewAvailable) return ''; try { return sessionStorage.getItem(previewKey) || previewRole; } catch { return previewRole; } }
function previewUser(role) { return {id:'preview-only',name:role === 'ADMIN' ? 'Quản trị viên xem thử' : 'Sinh viên xem thử',email:'xem-thu@example.invalid',role}; }
export function startPreview(role = 'LEARNER') {
 if(!previewAvailable || !['LEARNER','ADMIN'].includes(role)) return;
 ++generation;
 saveToken('');
 clearPrivateState();
 savePreview(role);
 publish('authenticated', previewUser(role), '', 'preview');
}
const listeners = new Set();
const resetters = new Set();
function readToken() { try { return sessionStorage.getItem(tokenKey) || memoryToken; } catch { return memoryToken; } }
function saveToken(token) { memoryToken = token; try { if (token) sessionStorage.setItem(tokenKey, token); else sessionStorage.removeItem(tokenKey); } catch { /* Memory-only session if storage is unavailable. */ } }
function publish(status, user = null, message = '', reason = '') {
  state = Object.freeze({status, reason, user: user ? Object.freeze({...user}) : null, message});
  listeners.forEach(fn => fn(state));
}
function clearPrivateState() { resetters.forEach(fn => fn()); }
export const getSession = () => state;
export const subscribeSession = fn => { listeners.add(fn); return () => listeners.delete(fn); };
export const onSessionCleared = fn => { resetters.add(fn); return () => resetters.delete(fn); };
export const isAdmin = () => state.status === 'authenticated' && state.user?.role === 'ADMIN';
// Navigation away from a pending login must not resurrect a session later.
export function cancelPendingLogin() { if(pendingLogin !== null) { ++generation; pendingLogin = null; } }
export function logout() {
  ++generation;
  saveToken('');
  savePreview('');
  clearPrivateState();
  publish('anonymous', null, 'Đã đăng xuất trên tab này. Bạn có thể đăng nhập lại.', 'logout');
}
async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(apiBase + path, {...options, cache: 'no-store', signal: controller.signal});
    let body;
    try { body = await response.json(); } catch { body = null; }
    if (!response.ok) {
      const error = new Error(response.status === 404 && path === '/api/auth/login'
        ? 'Backend đang chạy chưa có API đăng nhập. Cần tích hợp nhánh backend đăng nhập để tiếp tục.'
        : body?.error?.message || 'Không thể xác thực phiên. Vui lòng thử lại.');
      error.status = response.status;
      error.fields = body?.error?.fields;
      throw error;
    }
    return body;
  } catch (error) {
    if (error.status) throw error;
    throw new Error(error.name === 'AbortError' ? 'Máy chủ phản hồi quá lâu. Vui lòng thử lại.' : 'Không kết nối được dịch vụ đăng nhập. Vui lòng kiểm tra kết nối và thử lại.');
  } finally { clearTimeout(timeout); }
}
function validateUser(body) {
  const user = body?.user;
  if (!user || !['string', 'number'].includes(typeof user.id) || typeof user.name !== 'string' || typeof user.email !== 'string' || !['LEARNER', 'ADMIN'].includes(user.role)) {
    throw new Error('Thông tin tài khoản hoặc vai trò không hợp lệ. Vui lòng liên hệ quản trị viên.');
  }
  return {id: user.id, name: user.name, email: user.email, role: user.role};
}
export async function restoreSession() {
  const previousUser = state.user;
  const attempt = ++generation;
  const token = readToken();
  const demo = readPreview();
  if(!token && ['LEARNER','ADMIN'].includes(demo)) { publish('authenticated', previewUser(demo), '', 'preview'); return; }
  if (!token) { publish('anonymous'); return; }
  publish('checking');
  try {
    const user = validateUser(await request('/api/auth/me', {headers: {Authorization: 'Bearer ' + token}}));
    if (attempt === generation) {
      if(previousUser && (previousUser.id !== user.id || previousUser.role !== user.role)) clearPrivateState();
      publish('authenticated', user);
    }
  } catch (error) {
    if (attempt !== generation) return;
    clearPrivateState();
    if (error.status === 401 || error.status === 403) {
      saveToken('');
      publish('anonymous', null, 'Phiên đăng nhập không còn hợp lệ. Vui lòng đăng nhập lại.');
    } else {
      // Keep the credential for a retry, but never expose private views before verification.
      publish('error', null, error.message);
    }
  }
}
export async function login(email, password) {
  const attempt = ++generation;
  pendingLogin = attempt;
  savePreview('');
  try {
  saveToken('');
  clearPrivateState();
  const body = await request('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email: email.trim().toLowerCase(), password})});
  if (attempt !== generation) return false;
  if (typeof body?.access_token !== 'string' || !body.access_token || body.token_type?.toLowerCase() !== 'bearer') throw new Error('Phản hồi đăng nhập không hợp lệ. Vui lòng thử lại.');
  // Never grant access from the login payload alone; verify the current user server-side.
  const user = validateUser(await request('/api/auth/me', {headers: {Authorization: 'Bearer ' + body.access_token}}));
  if (attempt !== generation) return false;
  saveToken(body.access_token);
  publish('authenticated', user);
  return true;
  } finally { if(pendingLogin === attempt) pendingLogin = null; }
}
