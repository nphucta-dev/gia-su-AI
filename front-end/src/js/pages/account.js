import { getSession, isAdmin, logout } from '../session.js';
import { el, button, link, heading, panel, field, badge } from '../components/ui.js';
import { setupValidation, validateFields, showError, clearError } from '../components/validation.js';
import { renderAccountScreen } from './auth-screen.js';
export function renderAuth(register = false) { return renderAccountScreen(register); }

// TK-010 has no update contract yet. This form checks a local draft only.
// Never send guessed requests or persist this draft as a saved profile.
export function renderProfile() {
 const session = getSession();
 const user = session.user;
 if (!user) return el('div', {}, heading('Vui lòng đăng nhập', 'Đăng nhập để xem hồ sơ.'));
 const admin = isAdmin();
 const name = el('input', {className:'input', name:'name', value:user.name, maxlength:120, required:true, autocomplete:'name'});
 const year = el('input', {className:'input', name:'birth_year', type:'text', inputmode:'numeric', 'aria-describedby':'profile-year-help'});
 const status = el('p', {className:'helper', role:'status', 'aria-live':'polite'});
 const form = el('form', {className:'form-grid', 'aria-label':'Kiểm tra thông tin hồ sơ', 'aria-describedby':'profile-availability'});
 const nameError = () => !name.value.trim() ? 'Vui lòng nhập họ tên.' : Array.from(name.value.trim()).length > 120 ? 'Họ tên không được quá 120 ký tự.' : '';
 // Only integer syntax is checked until backend confirms the birth-year range.
 const yearError = () => year.value.trim() && !/^[0-9]+$/.test(year.value.trim()) ? 'Nhập năm sinh bằng số nguyên hoặc để trống.' : '';
 form.append(
  el('p', {id:'profile-availability', className:'notice'}, 'Chưa thể lưu thay đổi hồ sơ. Bạn có thể kiểm tra thông tin nhập bên dưới; nội dung sẽ mất khi rời trang hoặc tải lại.'),
  field('Họ tên', name), field('Năm sinh (không bắt buộc)', year),
  el('p', {id:'profile-year-help', className:'helper'}, 'Năm sinh hiện chưa được cung cấp. Ô trống không có nghĩa tài khoản chưa có năm sinh. Giới hạn năm sinh chưa được xác nhận.'),
  el('div', {className:'page-actions'}, el('button', {type:'submit', className:'button secondary'}, 'Kiểm tra thông tin')),
  status
 );
 setupValidation(form, [name,year]);
 for (const [input, error] of [[name,nameError],[year,yearError]]) {
  input.addEventListener('input', () => { status.textContent = ''; });
  input.addEventListener('blur', () => { const message = error(); if(message) showError(input,message); else clearError(input); });
 }
 form.addEventListener('submit', event => {
  event.preventDefault();
  status.textContent = '';
  name.value = name.value.trim();
  year.value = year.value.trim();
  if (!validateFields([[name,nameError()],[year,yearError()]])) {
   status.textContent = 'Vui lòng sửa thông tin được đánh dấu. Chưa có thay đổi nào được lưu.';
   return;
  }
  status.textContent = 'Đã kiểm tra định dạng nhập. Thông tin chưa được lưu; năm sinh cần được xác nhận khi chức năng cập nhật khả dụng.';
 });
 const detail = (label,value) => el('div', {}, el('dt', {}, label), el('dd', {}, value));
 return el('div', {className:'profile-page'},
  heading(admin ? 'Hồ sơ quản trị' : 'Hồ sơ của tôi', 'Xem thông tin tài khoản và kiểm tra thông tin cá nhân.'),
  session.reason === 'preview' ? el('p', {className:'notice'}, 'Bạn đang xem thử giao diện. Đây không phải dữ liệu tài khoản thật.') : null,
  el('div', {className:'grid-2'},
   panel('Thông tin tài khoản', el('dl', {className:'profile-details'},
    detail('Họ tên',user.name), detail('Email',user.email), detail('Năm sinh','Chưa có dữ liệu để hiển thị'),
    detail('Vai trò',badge(admin ? 'Quản trị viên' : 'Người học','success'))),
    el('div', {className:'page-actions'}, admin ? link('Về quản trị nội dung','#admin?tab=subjects') : link('Về trang học','#home'), button('Đăng xuất',logout,'ghost'))),
   panel('Chỉnh sửa thông tin',form)),
  !admin ? panel('Lịch sử học tập',el('p', {className:'helper'}, 'Lịch sử học tập hiện chưa khả dụng. Hoạt động của bạn sẽ hiển thị tại đây khi chức năng được kết nối.')) : null
 );
}
