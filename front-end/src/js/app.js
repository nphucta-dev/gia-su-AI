import { getSession, subscribeSession, restoreSession, logout, isAdmin, cancelPendingLogin } from './session.js';
import { renderHome, renderDashboard } from './pages/learning.js';
import { renderAuth, renderProfile } from './pages/account.js';
import { renderChat } from './pages/chat.js';
import { renderPractice, renderResults } from './pages/practice.js';
import { renderAdmin } from './pages/admin.js';
import { renderHistory, renderIntro } from './pages/history.js';
import { el, heading, link, button } from './components/ui.js';
const routes = { intro: renderIntro, history: renderHistory, home: renderHome, chat: renderChat, practice: renderPractice, results: renderResults, dashboard: renderDashboard, profile: renderProfile, admin: renderAdmin, login: () => renderAuth(false), register: () => renderAuth(true) };
const titles = { intro:'Giới thiệu',history:'Lịch sử học tập',home: 'Trang học', chat: 'Hỏi gia sư', practice: 'Luyện tập', results: 'Kết quả', dashboard: 'Tiến độ', profile: 'Hồ sơ', admin: 'Quản trị', login: 'Đăng nhập', register: 'Đăng ký' };
const menu = document.querySelector('.mobile-menu-button');
const accountMenu = document.querySelector('.account-menu');
accountMenu.addEventListener('click', e => { if(e.target.closest('a, button')) accountMenu.open = false; });
document.addEventListener('click', e => { if(!accountMenu.contains(e.target)) accountMenu.open = false; });
const sidebarToggle = document.querySelector('.admin-sidebar-toggle');
function setSidebarCollapsed(collapsed) {
 document.body.classList.toggle('admin-sidebar-collapsed', collapsed);
 sidebarToggle.setAttribute('aria-expanded', String(!collapsed));
 const label = collapsed ? 'Mở rộng thanh điều hướng' : 'Thu gọn thanh điều hướng';
 sidebarToggle.setAttribute('aria-label', label);
 sidebarToggle.title = label;
 sidebarToggle.firstElementChild.textContent = collapsed ? '»' : '«';
}
sidebarToggle.addEventListener('click', () => setSidebarCollapsed(!document.body.classList.contains('admin-sidebar-collapsed')));
const navBackdrop = document.querySelector('.admin-nav-backdrop');
function setNavigationOpen(open, restoreFocus = false) {
 menu.setAttribute('aria-expanded', String(open));
 document.querySelector('.nav').classList.toggle('open', open);
 const adminDrawer = document.body.dataset.role === 'admin' && matchMedia('(max-width:1099px)').matches;
 navBackdrop.hidden = !(open && adminDrawer);
 document.body.classList.toggle('admin-drawer-open', open && adminDrawer);
 document.querySelector('#app').inert = open && adminDrawer;
 document.querySelector('#preview-banner').inert = open && adminDrawer;
 accountMenu.inert = open && adminDrawer;
 menu.setAttribute('aria-label', open ? 'Đóng menu' : 'Mở menu');
 if(open && adminDrawer) document.querySelector('.nav a')?.focus();
 if(restoreFocus) menu.focus();
}
menu.addEventListener('click', () => setNavigationOpen(menu.getAttribute('aria-expanded') !== 'true'));
navBackdrop.addEventListener('click', () => setNavigationOpen(false, true));
window.addEventListener('resize', () => { if(matchMedia('(min-width:1100px)').matches) setNavigationOpen(false); });
const protectedRoutes = new Set(['dashboard', 'profile', 'history', 'chat', 'practice', 'results', 'admin']);
function updateAccountMenu() {
 const session = getSession();
 const banner = document.querySelector('#preview-banner');
 banner.hidden = session.reason !== 'preview';
 banner.textContent = session.reason === 'preview' ? 'Đang xem thử giao diện ' + (session.user.role === 'ADMIN' ? 'quản trị viên' : 'sinh viên') + ' · Dữ liệu minh họa · Không phải đăng nhập thật' : '';
 const nav = accountMenu.querySelector('nav');
 const items = [];
 if (session.status === 'checking') items.push(el('p', {className:'helper', role:'status'}, 'Đang kiểm tra phiên…'));
 else if (session.status === 'authenticated') {
  if (isAdmin()) items.push(link('Hồ sơ quản trị', '#profile', ''));
  else items.push(link('Hồ sơ của tôi', '#profile', ''), link('Lịch sử học tập', '#history', ''));
  items.push(button('Đăng xuất', () => logout(), 'account-logout'));
 } else {
  items.push(link('Đăng nhập', '#login', ''), link('Đăng ký', '#register', ''));
  if (session.status === 'error') items.push(button('Thử lại kết nối', restoreSession, 'account-retry'));
 }
 if(!isAdmin()) items.push(link('Giới thiệu', '#intro', ''));
 nav.replaceChildren(...items);
 const authenticated = session.status === 'authenticated';
 const brand = document.querySelector('.brand');
 brand.href = authenticated ? (isAdmin() ? '#admin?tab=subjects' : '#home') : '#intro';
 brand.setAttribute('aria-label', isAdmin() ? 'Gia Sư AI, quản trị nội dung' : 'Gia Sư AI, trang giới thiệu');
 const navigation = document.querySelector('.nav');
 const navigationRole = !authenticated ? 'guest' : isAdmin() ? 'admin' : 'learner';
 document.body.dataset.role = navigationRole;
 sidebarToggle.hidden = navigationRole !== 'admin';
 if(session.status !== 'checking' && navigationRole !== 'admin') setSidebarCollapsed(false);
 document.querySelector('.admin-context').hidden = navigationRole !== 'admin';
 if(navigation.dataset.role !== navigationRole) {
  const entries = navigationRole === 'admin'
   ? [['Môn học','#admin?tab=subjects'],['Chủ đề','#admin?tab=topics'],['Tài liệu nguồn','#admin?tab=documents']]
   : [['Trang học','#home'],['Hỏi gia sư','#chat'],['Luyện tập','#practice'],['Tiến độ','#dashboard']];
  navigation.replaceChildren(...entries.map(([label, href], index) => {
   const item = link(label, href, 'nav-link');
   if(navigationRole === 'admin') {
    item.dataset.icon = ['▥','◇','▤'][index];
    item.setAttribute('aria-label', label);
    item.title = label;
   }
   return item;
  }));
  navigation.dataset.role = navigationRole;
 }
 const currentRoute = location.hash.slice(1).split('?')[0];
 const currentTab = new URLSearchParams(location.hash.split('?')[1]).get('tab') || 'subjects';
 navigation.querySelectorAll('.nav-link').forEach(item => {
  const selected = navigationRole === 'admin'
   ? currentRoute === 'admin' && item.hash === '#admin?tab=' + currentTab
   : item.hash === '#' + currentRoute;
  item.classList.toggle('active', selected);
  if(selected) item.setAttribute('aria-current','page'); else item.removeAttribute('aria-current');
 });
 navigation.hidden = !authenticated;
 menu.hidden = !authenticated;
 if (!authenticated) {
  setNavigationOpen(false);
 }
}
function replaceRoute(route) {
 history.replaceState(null, '', '#' + route);
 render();
}
document.addEventListener('keydown', event => {
 if(event.key === 'Tab' && document.body.classList.contains('admin-drawer-open')) {
  const links = [...document.querySelectorAll('.nav a')];
  const first = links[0];
  const last = links.at(-1);
  if(!event.shiftKey && document.activeElement === last) { event.preventDefault(); menu.focus(); }
  else if(!event.shiftKey && document.activeElement === menu) { event.preventDefault(); first?.focus(); }
  else if(event.shiftKey && document.activeElement === first) { event.preventDefault(); menu.focus(); }
  else if(event.shiftKey && document.activeElement === menu) { event.preventDefault(); last?.focus(); }
 }
 if(event.key === 'Escape') {
  if(accountMenu.open) { accountMenu.open = false; accountMenu.querySelector('summary').focus(); }
  setNavigationOpen(false, menu.getAttribute('aria-expanded') === 'true');
 }
});
function render() {
 const session = getSession();
 const requestedRoute = location.hash.slice(1).split('?')[0];
 const route = requestedRoute || (session.status === 'authenticated' ? (isAdmin() ? 'admin' : 'home') : 'intro');
 if (!requestedRoute && session.status !== 'checking') history.replaceState(null, '', '#' + route);
 const main = document.querySelector('#app');
 if(route === 'admin' && isAdmin()) {
  const tab = new URLSearchParams(location.hash.split('?')[1]).get('tab');
  if(!['subjects','topics','documents'].includes(tab)) { replaceRoute('admin?tab=subjects'); return; }
 }
 updateAccountMenu();
 if (protectedRoutes.has(route)) {
  if (session.status === 'checking' || session.status === 'error') {
   const retry = session.status === 'error' ? button('Thử lại', restoreSession, 'primary') : null;
   main.replaceChildren(el('div', {}, heading(session.status === 'checking' ? 'Đang kiểm tra phiên…' : 'Chưa xác minh được phiên', session.message), retry));
   return;
  }
  if(session.status !== 'authenticated') { replaceRoute('login'); return; }
  if(route === 'admin' && !isAdmin()) {
   main.replaceChildren(el('div', {}, heading('Không có quyền truy cập', 'Khu vực quản trị chỉ dành cho quản trị viên.'), link('Về tiến độ học tập', '#dashboard')));
   document.title = 'Không có quyền truy cập · Gia Sư AI';
   accountMenu.open = false;
   main.focus({preventScroll:true});
   return;
  }
 }
 if(isAdmin() && ['intro','home','chat','practice','results','dashboard','history'].includes(route)) { replaceRoute('admin?tab=subjects'); return; }
 if(session.status === 'authenticated' && ['login','register'].includes(route)) { replaceRoute(isAdmin() ? 'admin' : 'dashboard'); return; }
 document.querySelector('#toast-region').replaceChildren();
 accountMenu.open = false;
 main.replaceChildren(routes[route] ? routes[route]() : el('div', {}, heading('Không tìm thấy trang', 'Đường dẫn này chưa có trong bản giao diện.'), link('Về trang học', '#home')));
 document.title = `${titles[route] || 'Không tìm thấy'} · Gia Sư AI`;

 setNavigationOpen(false);
 window.scrollTo(0, 0); main.focus({ preventScroll: true });
}
subscribeSession(session => {
 setNavigationOpen(false);
 const dialog = document.querySelector('#app-modal');
 if(dialog.open) dialog.close();
 dialog.querySelector('.modal-body').replaceChildren();
 accountMenu.open = false;
 if(session.status === 'anonymous') {
  const route = location.hash.slice(1).split('?')[0];
  if(protectedRoutes.has(route) || session.reason === 'logout') history.replaceState(null, '', '#login');
 }
 render();
});
window.addEventListener('hashchange', () => {
 if(getSession().status === 'authenticated') restoreSession(); else { cancelPendingLogin(); render(); }
});
window.addEventListener('pageshow', event => { if(event.persisted) restoreSession(); });
document.addEventListener('visibilitychange', () => {
 if(document.visibilityState === 'visible' && getSession().status === 'authenticated') restoreSession();
});
render(); restoreSession();
