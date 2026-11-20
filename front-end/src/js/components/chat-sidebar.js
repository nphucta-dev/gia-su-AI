import { el, button } from './ui.js';

let serial = 0;

// Keep the same sidebar nodes (and draft) when changing screen size.
export function chatSidebar(label, ...children) {
 const media = matchMedia('(max-width: 767px)');
 const body = el('div', { className: 'chat-sidebar-body', id: `chat-sidebar-${++serial}` }, ...children);
 let mobileOpen = false;
 const toggle = button('Mở lịch sử phiên', () => { mobileOpen = !mobileOpen; sync(); }, 'ghost small chat-sidebar-toggle');
 toggle.setAttribute('aria-controls', body.id);
 const sidebar = el('aside', { className: 'chat-sidebar', 'aria-label': label }, toggle, body);
 function sync() {
  const expanded = !media.matches || mobileOpen;
  if (!expanded && body.contains(document.activeElement)) toggle.focus();
  body.hidden = !expanded;
  toggle.setAttribute('aria-expanded', String(expanded));
  toggle.textContent = expanded ? 'Thu gọn lịch sử phiên' : 'Mở lịch sử phiên';
  toggle.setAttribute('aria-label', toggle.textContent);
 }
 sync();
 queueMicrotask(() => {
  if (!sidebar.isConnected) return;
  media.addEventListener('change', sync);
  const observer = new MutationObserver(() => {
   if (!sidebar.isConnected) { media.removeEventListener('change', sync); observer.disconnect(); }
  });
  observer.observe(document.body, { childList: true, subtree: true });
 });
 return sidebar;
}
