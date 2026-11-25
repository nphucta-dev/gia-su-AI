import { icon } from './icons.js';
import { prefersReducedMotion, setButtonState, skeletonState, syncSlidingTabs } from './motion.js';

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
  children.flat(Infinity).forEach(child => {
    if (child != null) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  });
  return node;
}

/* 1. Button (primary / secondary / ghost / icon) */
export function button(label, onClick, variant = 'secondary', opts = {}) {
  const {
    type = 'button',
    leadingIcon = null,
    trailingIcon = null,
    pulse = false,
    ariaLabel = null,
    attrs = {},
  } = opts;
  const classes = ['button', variant, pulse ? 'btn-hero-pulse' : ''].filter(Boolean).join(' ');
  const lead = typeof leadingIcon === 'string' ? icon(leadingIcon, { size: 16 }) : leadingIcon;
  const trail = typeof trailingIcon === 'string'
    ? icon(trailingIcon, { size: 16, className: 'ui-icon--trail btn-arrow' })
    : trailingIcon;
  return el('button', {
    type,
    className: classes,
    onclick: onClick,
    'aria-label': ariaLabel || attrs['aria-label'] || null,
    ...attrs,
  }, lead, label, trail);
}

export function iconButton(iconNameOrNode, ariaLabel, onClick, variant = 'icon') {
  const ic = typeof iconNameOrNode === 'string' ? icon(iconNameOrNode, { size: 18 }) : iconNameOrNode;
  return el('button', {
    type: 'button',
    className: `button ${variant}`,
    'aria-label': ariaLabel,
    title: ariaLabel,
    onclick: onClick,
  }, ic);
}

export function link(label, href, className = 'button secondary', opts = {}) {
  const { leadingIcon = null, trailingIcon = null, pulse = false, attrs = {} } = opts;
  const classes = [className, pulse ? 'btn-hero-pulse' : ''].filter(Boolean).join(' ');
  const lead = typeof leadingIcon === 'string' ? icon(leadingIcon, { size: 16 }) : leadingIcon;
  const trail = typeof trailingIcon === 'string'
    ? icon(trailingIcon, { size: 16, className: 'ui-icon--trail btn-arrow' })
    : trailingIcon;
  return el('a', { href, className: classes, ...attrs }, lead, label, trail);
}

/* 2. Heading & Eyebrow */
export const heading = (title, description) => el(
  'div',
  { className: 'page-heading' },
  el('div', {}, el('h1', {}, title), el('p', {}, description)),
);

export const eyebrow = (text, tone = 'main', iconNode = null) => el(
  'div',
  { className: `eyebrow-pill ${tone}`.trim() },
  iconNode,
  text,
);

/* 3. Card / Panel */
export const panel = (title, ...children) => el(
  'section',
  { className: 'panel' },
  title ? el('h2', {}, title) : null,
  ...children,
);

export function card({ title = '', interactive = false, muted = false, className = '', tag = 'section', attrs = {} } = {}, ...children) {
  const classes = [
    'panel',
    interactive ? 'card-interactive' : '',
    muted ? 'panel-cool' : '',
    className,
  ].filter(Boolean).join(' ');
  return el(tag, { className: classes, ...attrs }, title ? el('h2', {}, title) : null, ...children);
}

/* 4. Badge & Notice */
export const badge = (text, kind = 'neutral') => el('span', { className: `badge ${kind}`.trim() }, text);
export const notice = (text, kind = '') => el('div', { className: `notice ${kind}`.trim() }, text);

/* 5. Input & Field */
export function field(label, input, hintText = '') {
  input.id ||= `field-${++serial}`;
  return el(
    'div',
    { className: 'field' },
    el('label', { for: input.id }, label),
    input,
    hintText ? el('p', { className: 'helper' }, hintText) : null,
  );
}

export function inputControl({ kind = 'input', className = '', ...attrs } = {}) {
  const baseClass = kind === 'select' ? 'select' : kind === 'textarea' ? 'textarea' : 'input';
  return el(kind, { className: `${baseClass} ${className}`.trim(), ...attrs });
}

/* 6. Toast (Fade + Scale + Slide Enter & Exit) */
export function toast(text) {
  const region = document.querySelector('#toast-region');
  if (!region) return;
  const node = el('div', { className: 'toast toast-enter' }, text);
  region.append(node);
  setTimeout(() => {
    if (!node.isConnected) return;
    if (prefersReducedMotion()) {
      node.remove();
      return;
    }
    node.classList.remove('toast-enter');
    node.classList.add('toast-exit');
    node.addEventListener('animationend', () => node.remove(), { once: true });
    setTimeout(() => node.remove(), 260);
  }, 4200);
}

/* 7. Modal */
export function confirmDialog(title, text, confirmLabel = 'Xác nhận') {
  return new Promise(resolve => {
    const dialog = document.querySelector('#app-modal');
    const body = dialog.querySelector('.modal-body');
    const finish = value => { dialog.close(); resolve(value); };
    body.replaceChildren(
      el('h2', { id: 'dialog-title' }, title),
      el('p', {}, text),
      el('div', { className: 'modal-actions' },
        button('Quay lại', () => finish(false), 'ghost'),
        button(confirmLabel, () => finish(true), 'primary')),
    );
    dialog.setAttribute('aria-labelledby', 'dialog-title');
    dialog.querySelector('.modal-close').onclick = () => finish(false);
    dialog.addEventListener('cancel', () => resolve(false), { once: true });
    dialog.showModal();
  });
}

/* 8. Tabs (with Smooth Sliding Glider) */
export function tabs(items, activeId, { variant = 'line', ariaLabel = 'Chuyển mục', onSelect = null } = {}) {
  const nav = el(
    onSelect ? 'div' : 'nav',
    {
      className: variant === 'pill' ? 'auth-tabs ui-tabs ui-tabs--pill' : 'tabs ui-tabs ui-tabs--line',
      role: onSelect ? 'tablist' : null,
      'aria-label': ariaLabel,
    },
    ...items.map(item => {
      const isSelected = item.id === activeId;
      if (item.href && !onSelect) {
        return el('a', {
          href: item.href,
          className: `${variant === 'pill' ? 'auth-tab' : 'tab'} ${isSelected ? (variant === 'pill' ? 'is-active' : 'active') : ''}`.trim(),
          'aria-current': isSelected ? 'page' : null,
        }, item.label);
      }
      return el('button', {
        type: 'button',
        role: 'tab',
        'aria-selected': String(isSelected),
        className: `tab ui-tab ${isSelected ? 'active' : ''}`.trim(),
        onclick: e => {
          nav.querySelectorAll('.tab, .ui-tab').forEach(btn => {
            btn.classList.remove('active');
            btn.setAttribute('aria-selected', 'false');
          });
          e.currentTarget.classList.add('active');
          e.currentTarget.setAttribute('aria-selected', 'true');
          syncSlidingTabs(nav);
          onSelect?.(item.id);
        },
      }, item.label);
    }),
  );
  syncSlidingTabs(nav);
  return nav;
}

/* 9. Dropdown */
export function dropdown(label, items = [], { ariaLabel = label } = {}) {
  const menu = el('nav', { className: 'ui-dropdown-menu', 'aria-label': ariaLabel }, ...items);
  const root = el('details', { className: 'ui-dropdown' }, el('summary', {}, label, icon('chevronDown', { size: 15 })), menu);
  root.addEventListener('click', e => {
    if (e.target.closest('a, button')) root.open = false;
  });
  return root;
}

/* 10. Skeleton */
export const skeleton = skeletonState;

/* 11. Avatar */
export function avatar(name = 'U', { size = 'lg', solid = false } = {}) {
  const parts = String(name || 'U').trim().split(/\s+/).filter(Boolean);
  const initials = parts.slice(-2).map(part => part[0]).join('').toUpperCase() || 'U';
  const cls = [
    'avatar',
    size === 'sm' ? 'avatar--sm' : size === 'md' ? 'avatar--md' : '',
    solid ? 'avatar--solid' : '',
  ].filter(Boolean).join(' ');
  return el('div', { className: cls, 'aria-hidden': 'true' }, initials);
}

/* 12. Progress */
export function progress(value = 0, max = 100, { label = '', valueText = '', className = '' } = {}) {
  const safeMax = max > 0 ? max : 100;
  const ratio = Math.max(0, Math.min(1, Number(value) / safeMax));
  const fill = el('div', {
    className: 'ui-progress-fill',
    'data-target-ratio': ratio.toFixed(4),
  });
  fill.style.setProperty('--progress-ratio', prefersReducedMotion() ? ratio.toFixed(4) : '0');

  const track = el('div', {
    className: 'ui-progress-track',
    role: 'progressbar',
    'aria-valuemin': '0',
    'aria-valuemax': String(safeMax),
    'aria-valuenow': String(Math.round(Number(value) || 0)),
    'aria-label': label || 'Tiến độ',
  }, fill);

  if (!label && !valueText) return track;
  return el(
    'div',
    { className: `ui-progress ${className}`.trim() },
    el('div', { className: 'ui-progress-head' }, el('span', {}, label), el('span', {}, valueText || `${Math.round(ratio * 100)}%`)),
    track,
  );
}

export { setButtonState };
