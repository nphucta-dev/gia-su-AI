import { getSession, isAdmin, logout } from '../session.js';
import { el, button, link, heading, panel, field, badge, toast } from '../components/ui.js';
import { setupValidation, validateFields } from '../components/validation.js';
import { renderAccountScreen } from './auth-screen.js';
export function renderAuth(register = false) { return renderAccountScreen(register); }
export function renderProfile() {
 const user = getSession().user;
 if (!user) return el('div', {}, heading('Vui lòng đăng nhập', 'Đăng nhập để xem hồ sơ.'));
 if(isAdmin()) return el('div', {className:'admin-profile'},
  heading('Hồ sơ quản trị', 'Thông tin tài khoản quản trị nội dung.'),
  panel('Thông tin tài khoản',
   el('dl', {className:'profile-details'},
    el('div', {}, el('dt', {}, 'Họ tên'), el('dd', {}, user.name)),
    el('div', {}, el('dt', {}, 'Email'), el('dd', {}, user.email)),
    el('div', {}, el('dt', {}, 'Vai trò'), el('dd', {}, badge('Quản trị viên', 'success')))),
   el('p', {className:'helper'}, 'Chức năng cập nhật hồ sơ chưa được kết nối. Thông tin đang hiển thị từ phiên hiện tại.'),
   el('div', {className:'page-actions'}, link('Về quản trị nội dung', '#admin?tab=subjects', 'button secondary'), button('Đăng xuất', logout, 'ghost'))));
 const form = el('form', { className: 'form-grid' });
 const name = el('input', { className: 'input', value: user.name, maxlength: 120 });
 const year = el('input', { className: 'input', type: 'number', min: 1900, max: new Date().getFullYear(), placeholder: 'Ví dụ: 2005' });
 form.append(field('Họ tên', name), field('Năm sinh', year), el('button', { type: 'submit', className: 'button primary' }, 'Lưu thông tin'));
 setupValidation(form,[name,year]);
 form.addEventListener('submit', e => { e.preventDefault(); if(!validateFields([[name,!name.value.trim()?'Vui lòng nhập họ tên.':''],[year,year.value&&(!/^\d{4}$/.test(year.value)||+year.value<1900||+year.value>new Date().getFullYear())?'Năm sinh chưa hợp lệ. Vui lòng nhập 4 chữ số, từ 1900 đến năm hiện tại.':'']]))return;toast('Đã kiểm tra thông tin hồ sơ.'); });
 return el('div', {}, heading('Hồ sơ của tôi', 'Thông tin tài khoản và các hoạt động học tập.'), el('div', { className: 'grid-2' }, panel('', el('div', { className: 'profile-summary' }, el('div', { className: 'avatar', 'aria-hidden': 'true' }, 'NH'), el('div', {}, el('h2', {}, user.name), badge(user.role === 'ADMIN' ? 'Quản trị viên' : 'Sinh viên', 'success'))), el('hr'), el('p', { className: 'helper' }, user.email), el('div', { className: 'page-actions' }, button('Đăng xuất', logout, 'ghost'), isAdmin() ? link('Khu vực quản trị', '#admin', 'button secondary') : null)), panel('Chỉnh sửa thông tin', form)), el('div', { className: 'section-gap' }, panel('Lịch sử học tập', el('div', { className: 'activity-row' }, el('span', {}, 'Phương trình bậc hai'), link('Xem hội thoại', '#chat', 'button ghost small')), el('div', { className: 'activity-row' }, el('span', {}, 'Bài luyện tập trắc nghiệm'), link('Luyện tập', '#practice', 'button ghost small')))));
}
