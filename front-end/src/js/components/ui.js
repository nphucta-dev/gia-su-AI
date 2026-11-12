let serial = 0;
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === false || value == null) continue;
    if (key === 'className') node.className = value;
    else if (key === 'textContent') node.textContent = value;
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2).toLowerCase(), value);
    else node.setAttribute(key, value === true ? '' : String(value));
  }
  children.flat(Infinity).forEach(child => { if (child != null) node.append(child instanceof Node ? child : document.createTextNode(String(child))); });
  return node;
}
export const button = (label, onClick, variant = 'secondary') => el('button', { type: 'button', className: `button ${variant}`, onclick: onClick }, label);
export const link = (label, href, className = 'button secondary') => el('a', { href, className }, label);
export const heading = (title, description) => el('div', { className: 'page-heading' }, el('div', {}, el('h1', {}, title), el('p', {}, description)));
export const panel = (title, ...children) => el('section', { className: 'panel' }, title ? el('h2', {}, title) : null, ...children);
export const notice = (text, kind = '') => el('div', { className: `notice ${kind}` }, text);
export const badge = (text, kind = 'neutral') => el('span', { className: `badge ${kind}` }, text);
export function field(label, input) { input.id ||= `field-${++serial}`; return el('div', { className: 'field' }, el('label', { for: input.id }, label), input); }
export function toast(text) {
  const node = el('div', { className: 'toast' }, text); document.querySelector('#toast-region').append(node); setTimeout(() => node.remove(), 4500);
}
export function confirmDialog(title, text, confirmLabel = 'Xác nhận') {
  return new Promise(resolve => {
    const dialog = document.querySelector('#app-modal');
    const body = dialog.querySelector('.modal-body');
    const finish = value => { dialog.close(); resolve(value); };
    body.replaceChildren(el('h2', { id: 'dialog-title' }, title), el('p', {}, text), el('div', { className: 'modal-actions' }, button('Quay lại', () => finish(false), 'ghost'), button(confirmLabel, () => finish(true), 'primary')));
    dialog.setAttribute('aria-labelledby', 'dialog-title');
    dialog.querySelector('.modal-close').onclick = () => finish(false);
    dialog.addEventListener('cancel', () => resolve(false), { once: true });
    dialog.showModal();
  });
}
