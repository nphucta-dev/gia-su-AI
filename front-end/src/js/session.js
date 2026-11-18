// No server logout/revocation contract exists. Tokens are kept only for this tab.
const tokenKey = 'gia-su-ai.access-token';
const expiryKey = 'gia-su-ai.token-expires-at';
const apiBase = (document.querySelector('meta[name="api-base"]')?.content.trim() || '/api').replace(/\/$/, '');
let state = Object.freeze({ status: 'checking', user: null, message: '' });
let generation = 0;
let memoryToken = '';
let pendingLogin = null;
let expiresAt = 0;
let expiryTimer;
let loginHint = null;
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
try { expiresAt = Number(sessionStorage.getItem(expiryKey)) || 0; } catch { /* Memory-only session. */ }
function scheduleExpiry() {
  clearTimeout(expiryTimer);
  if (readToken() && expiresAt) expiryTimer = setTimeout(() => clearSession('expired'), Math.max(0, expiresAt - Date.now()));
}
function saveToken(token, expiry = 0) {
  memoryToken = token;
  expiresAt = expiry;
  try {
    if (token) {
      sessionStorage.setItem(tokenKey, token);
      if (expiry) sessionStorage.setItem(expiryKey, String(expiry));
      else sessionStorage.removeItem(expiryKey);
    } else {
      sessionStorage.removeItem(tokenKey);
      sessionStorage.removeItem(expiryKey);
    }
  } catch { /* Memory-only session if storage is unavailable. */ }
  scheduleExpiry();
}
function publish(status, user = null, message = '', reason = '') {
  state = Object.freeze({status, reason, user: user ? Object.freeze({...user}) : null, message});
  listeners.forEach(fn => fn(state));
}
function clearPrivateState() { resetters.forEach(fn => fn()); }
export const getSession = () => state;
export const getCurrentUser = () => state.status === 'authenticated' ? state.user : null;
export function getAccessToken() {
  if (readToken() && expiresAt && Date.now() >= expiresAt) clearSession('expired');
  return readToken();
}
export function setCurrentUser(user, { notifyChange = true } = {}) {
  if (notifyChange) publish('authenticated', user);
  else state = Object.freeze({...state, status:'authenticated', user:Object.freeze({...user})});
}
export function setLoginHint(hint) { loginHint = hint; }
export function takeLoginHint() { const hint = loginHint; loginHint = null; return hint; }
export function loginDestination() {
  const fallback = isAdmin() ? 'admin?tab=subjects' : 'home';
  const next = new URLSearchParams(location.hash.split('?')[1]).get('next') || fallback;
  return /^(home|chat|practice|results|dashboard|profile|history|admin)(\?[^#]*)?$/.test(next) ? next : fallback;
}
export const subscribeSession = fn => { listeners.add(fn); return () => listeners.delete(fn); };
export const onSessionCleared = fn => { resetters.add(fn); return () => resetters.delete(fn); };
export const isAdmin = () => state.status === 'authenticated' && state.user?.role === 'ADMIN';
// Navigation away from a pending login must not resurrect a session later.
export function cancelPendingLogin() { if(pendingLogin !== null) { ++generation; pendingLogin = null; } }
export function clearSession(reason = 'logout') {
  ++generation;
  pendingLogin = null;
  saveToken('');
  savePreview('');
  clearPrivateState();
  const message = reason === 'expired' ? 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
    : reason === 'inactive' ? 'Tài khoản đã bị vô hiệu hóa.'
    : 'Đã đăng xuất trên tab này. Bạn có thể đăng nhập lại.';
  setLoginHint({message, kind: reason === 'inactive' ? 'error' : 'warning'});
  publish('anonymous', null, message, reason);
}
export const logout = () => clearSession('logout');
async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(apiBase + path, {...options, cache: 'no-store', signal: controller.signal});
    let body;
    try { body = await response.json(); } catch { body = null; }
    if (!response.ok) {
      const error = new Error(body?.error?.message || 'Không thể xác thực phiên. Vui lòng thử lại.');
      error.status = response.status;
      error.fields = body?.error?.fields;
      throw error;
    }
    return body;
  } catch (error) {
    if (error.status) throw error;
    throw new Error(error.name === 'AbortError' ? 'Máy chủ phản hồi quá lâu. Vui lòng thử lại.' : 'Không thể kết nối với máy chủ. Vui lòng thử lại.');
  } finally { clearTimeout(timeout); }
}
function validateUser(body) {
  const user = body?.user;
  if (!user || !['string', 'number'].includes(typeof user.id) || typeof user.name !== 'string' || typeof user.email !== 'string' || !['LEARNER', 'ADMIN'].includes(user.role)) {
    throw new Error('Thông tin tài khoản hoặc vai trò không hợp lệ. Vui lòng liên hệ quản trị viên.');
  }
  return {id: user.id, name: user.name, email: user.email, role: user.role, createdAt: user.createdAt};
}
export async function restoreSession({ background = false } = {}) {
  const previousState = state;
  const previousUser = state.user;
  const token = getAccessToken();
  const attempt = ++generation;
  // Quay lại từ hộp chọn file/tab khác: giữ form của phiên đã xác minh.
  const preserveView = background && previousState.status === 'authenticated' && state === previousState;
  const demo = readPreview();
  if(!token && ['LEARNER','ADMIN'].includes(demo)) {
    if (!preserveView) publish('authenticated', previewUser(demo), '', 'preview');
    return;
  }
  if (!token) { publish('anonymous', null, state.message, state.reason); return; }
  if (!preserveView) publish('checking');
  try {
    const user = validateUser(await request('/auth/me', {headers: {Authorization: 'Bearer ' + token}}));
    if (attempt === generation && getAccessToken() === token) {
      const accessChanged = previousUser && (previousUser.id !== user.id || previousUser.role !== user.role);
      if (accessChanged) clearPrivateState();
      if (preserveView && !accessChanged) {
        // Không ghi đè hồ sơ vừa lưu trong lúc request kiểm tra phiên còn chạy.
        if (state.user === previousUser) setCurrentUser(user, {notifyChange:false});
      } else publish('authenticated', user);
    }
  } catch (error) {
    if (attempt !== generation || getAccessToken() !== token) return;
    if (error.status === 401 || error.status === 403) {
      clearSession(error.status === 403 ? 'inactive' : 'expired');
    } else if (!preserveView) {
      clearPrivateState();
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
  const body = await request('/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email: email.trim().toLowerCase(), password})});
  if (attempt !== generation) return false;
  if (typeof body?.access_token !== 'string' || !body.access_token || body.token_type?.toLowerCase() !== 'bearer' || !Number.isFinite(body.expires_in) || body.expires_in <= 0) throw new Error('Phản hồi đăng nhập không hợp lệ. Vui lòng thử lại.');
  // Never grant access from the login payload alone; verify the current user server-side.
  const user = validateUser(await request('/auth/me', {headers: {Authorization: 'Bearer ' + body.access_token}}));
  if (attempt !== generation) return false;
  saveToken(body.access_token, Date.now() + body.expires_in * 1000);
  publish('authenticated', user);
  return true;
  } finally { if(pendingLogin === attempt) pendingLogin = null; }
}
scheduleExpiry();
