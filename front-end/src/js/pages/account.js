import { getAccessToken, getSession, isAdmin, logout, setCurrentUser } from '../session.js';
import { api } from '../api.js';
import { el, button, link, heading, panel, field, badge, notice, toast } from '../components/ui.js';
import { setupValidation, validateFields, showServerErrors } from '../components/validation.js';
import { renderAccountScreen } from './auth-screen.js';
export function renderAuth(register = false) { return renderAccountScreen(register); }
export function renderProfile() {
 const session = getSession();
 if (!session.user) return el('div', {}, heading('Vui lòng đăng nhập', 'Đăng nhập để xem hồ sơ.'));
 const admin = isAdmin();
 const preview = session.reason === 'preview';
 const token = getAccessToken();
 const root = el('div', {className: admin ? 'admin-profile' : ''});
 const content = el('div', {'aria-live':'polite'});
 root.append(heading(admin ? 'Hồ sơ quản trị' : 'Hồ sơ của tôi', 'Thông tin tài khoản và các hoạt động học tập.'), content);

 function currentPage() {
  return root.isConnected && getSession().user?.id === session.user.id && getAccessToken() === token;
 }

 function draw(user) {
  const form = el('form', {className:'form-grid profile-form'});
  const name = el('input', {className:'input', name:'name', value:user.name, maxlength:120, autocomplete:'name'});
  const year = el('input', {className:'input', name:'birthYear', type:'number', value:user.birthYear ?? '', min:1900, max:new Date().getUTCFullYear(), placeholder:'Ví dụ: 2005'});
  const submit = el('button', {type:'submit', className:'button primary'}, 'Lưu thông tin');
  const message = el('div', {role:'status', 'aria-live':'polite'});
  form.append(field('Họ tên', name), field('Năm sinh', year), submit, message);
  setupValidation(form, [name,year]);
  let pending = false;
  form.addEventListener('submit', async event => {
   event.preventDefault();
   if (pending) return;
   message.replaceChildren();
   if (!validateFields([
    [name, !name.value.trim() ? 'Vui lòng nhập họ tên.' : name.value.trim().length > 120 ? 'Họ tên tối đa 120 ký tự.' : /\p{Cc}/u.test(name.value) ? 'Họ tên không được chứa ký tự điều khiển.' : ''],
    [year, year.value && (!/^\d{4}$/.test(year.value) || +year.value < 1900 || +year.value > new Date().getUTCFullYear()) ? 'Năm sinh chưa hợp lệ. Vui lòng nhập 4 chữ số, từ 1900 đến năm hiện tại.' : ''],
   ])) return;
   if (preview) {
    message.replaceChildren(notice('Đã kiểm tra thông tin trong bản xem thử. Chưa lưu lên máy chủ.', 'warning'));
    return;
   }
   pending = true;
   submit.disabled = true;
   submit.textContent = 'Đang lưu…';
   form.setAttribute('aria-busy', 'true');
   try {
    const result = await api('/profile', {method:'PATCH', body:{name:name.value, birthYear:year.value ? Number(year.value) : null}});
    if (!currentPage() || !form.isConnected) return;
    if (!result?.user || result.user.id !== user.id) throw new Error('Phản hồi hồ sơ chưa hợp lệ. Vui lòng tải lại trang.');
    setCurrentUser(result.user);
    toast(result.message || 'Cập nhật hồ sơ thành công.');
   } catch (error) {
    if (!currentPage() || !form.isConnected) return;
    showServerErrors(error.fields, {name, birthYear:year});
    message.replaceChildren(notice(error.message || 'Chưa thể lưu hồ sơ. Vui lòng thử lại.', 'error'));
   } finally {
    pending = false;
    submit.disabled = false;
    submit.textContent = 'Lưu thông tin';
    form.removeAttribute('aria-busy');
   }
  });

  const initials = user.name.split(/\s+/).filter(Boolean).slice(-2).map(part => part[0]).join('').toUpperCase();
  const details = el('dl', {className:'profile-details'},
   el('div', {}, el('dt', {}, 'Họ tên'), el('dd', {}, user.name)),
   el('div', {}, el('dt', {}, 'Email'), el('dd', {}, user.email)),
   el('div', {}, el('dt', {}, 'Vai trò'), el('dd', {}, badge(admin ? 'Quản trị viên' : 'Sinh viên', 'success'))));
  if (admin) {
   content.replaceChildren(panel('Thông tin tài khoản', details,
    el('div', {className:'page-actions'}, link('Về quản trị nội dung', '#admin?tab=subjects', 'button secondary'), button('Đăng xuất', logout, 'ghost'))),
   panel('Chỉnh sửa thông tin', form));
  } else {
   content.replaceChildren(el('div', {className:'grid-2'},
    panel('', el('div', {className:'profile-summary'}, el('div', {className:'avatar', 'aria-hidden':'true'}, initials), el('div', {}, el('h2', {}, user.name), badge('Sinh viên', 'success'))),
     el('hr'), el('p', {className:'helper'}, user.email), el('div', {className:'page-actions'}, button('Đăng xuất', logout, 'ghost'))),
    panel('Chỉnh sửa thông tin', form)),
    el('div', {className:'section-gap'}, panel('Lịch sử học tập',
     el('div', {className:'activity-row'}, el('span', {}, 'Phương trình bậc hai'), link('Xem hội thoại', '#chat', 'button ghost small')),
     el('div', {className:'activity-row'}, el('span', {}, 'Bài luyện tập trắc nghiệm'), link('Luyện tập', '#practice', 'button ghost small')))));
  }
 }

 async function load() {
  content.replaceChildren(el('p', {role:'status'}, 'Đang tải hồ sơ…'));
  try {
   const result = await api('/profile');
   if (!currentPage()) return;
   if (!result?.user || result.user.id !== session.user.id) throw new Error('Phản hồi hồ sơ chưa hợp lệ. Vui lòng thử lại.');
   setCurrentUser(result.user, {notifyChange:false});
   draw(result.user);
  } catch (error) {
   if (!currentPage()) return;
   content.replaceChildren(notice(error.message || 'Chưa thể tải hồ sơ.', 'error'), button('Thử lại', load, 'primary'));
  }
 }
 if (preview) draw(session.user);
 else load();
 return root;
}
