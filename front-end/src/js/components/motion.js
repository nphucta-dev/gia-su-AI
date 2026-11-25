const THEME_KEY = 'gia-su-ai.theme';
const SVG_NS = 'http://www.w3.org/2000/svg';

export function prefersReducedMotion() {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function createThemeStage() {
  const stage = document.createElement('span');
  stage.className = 'theme-toggle-stage';
  stage.setAttribute('aria-hidden', 'true');

  const makeSvg = cls => {
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', '18');
    svg.setAttribute('height', '18');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('class', `theme-icon ${cls}`);
    return svg;
  };

  const moon = makeSvg('theme-icon--moon');
  const moonPath = document.createElementNS(SVG_NS, 'path');
  moonPath.setAttribute('d', 'M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z');
  moon.append(moonPath);

  const sun = makeSvg('theme-icon--sun');
  const circle = document.createElementNS(SVG_NS, 'circle');
  circle.setAttribute('cx', '12');
  circle.setAttribute('cy', '12');
  circle.setAttribute('r', '4');
  sun.append(circle);
  for (const d of [
    'M12 2v2', 'M12 20v2', 'm4.93 4.93 1.41 1.41', 'm17.66 17.66 1.41 1.41',
    'M2 12h2', 'M20 12h2', 'm6.34 17.66-1.41 1.41', 'm19.07 4.93-1.41 1.41',
  ]) {
    const ray = document.createElementNS(SVG_NS, 'path');
    ray.setAttribute('d', d);
    sun.append(ray);
  }

  stage.append(moon, sun);
  return stage;
}

export function applyTheme(theme) {
  const resolved = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.theme = resolved;
  return resolved;
}

let rippleBound = false;

export function initButtonRipples() {
  if (rippleBound || typeof document === 'undefined') return;
  rippleBound = true;

  document.addEventListener('pointerdown', event => {
    if (prefersReducedMotion() || event.button > 0) return;
    const target = event.target?.closest?.('.button, .primary-button, .theme-toggle');
    if (!target || target.disabled || target.getAttribute('aria-disabled') === 'true') return;

    const rect = target.getBoundingClientRect();
    if (!rect.width || !rect.height) return;

    const x = event.clientX ? event.clientX - rect.left : rect.width / 2;
    const y = event.clientY ? event.clientY - rect.top : rect.height / 2;
    const size = Math.round(Math.max(rect.width, rect.height) * 1.15);

    const ripple = document.createElement('span');
    ripple.className = 'btn-ripple';
    ripple.setAttribute('aria-hidden', 'true');
    ripple.style.setProperty('--rx', `${Math.round(x)}px`);
    ripple.style.setProperty('--ry', `${Math.round(y)}px`);
    ripple.style.setProperty('--rsize', `${size}px`);
    target.append(ripple);

    const cleanup = () => ripple.remove();
    ripple.addEventListener('animationend', cleanup, { once: true });
    setTimeout(cleanup, 600);
  }, { passive: true });
}

export function initThemeToggle(buttonEl) {
  initButtonRipples();

  let saved = null;
  try {
    saved = localStorage.getItem(THEME_KEY);
  } catch { /* Storage disabled */ }

  const systemDark = typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-color-scheme: dark)').matches;
  let current = applyTheme(saved === 'dark' || saved === 'light' ? saved : (systemDark ? 'dark' : 'light'));

  if (buttonEl && !buttonEl.querySelector('.theme-toggle-stage')) {
    buttonEl.replaceChildren(createThemeStage());
  }

  function syncButton() {
    if (!buttonEl) return;
    const isDark = current === 'dark';
    buttonEl.setAttribute('aria-pressed', String(isDark));
    buttonEl.setAttribute('aria-label', isDark ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối');
    buttonEl.title = isDark ? 'Chế độ sáng' : 'Chế độ tối';
  }

  syncButton();

  if (buttonEl) {
    buttonEl.addEventListener('click', () => {
      current = applyTheme(current === 'dark' ? 'light' : 'dark');
      try {
        localStorage.setItem(THEME_KEY, current);
      } catch { /* Storage disabled */ }
      syncButton();
    });
  }
}

export function setButtonState(buttonEl, state = 'idle', { label = '', replaceText = false } = {}) {
  if (!buttonEl) return;
  if (!buttonEl.dataset.originalWidth && buttonEl.offsetWidth > 0) {
    buttonEl.dataset.originalWidth = `${buttonEl.offsetWidth}px`;
  }
  buttonEl.querySelector('.btn-state-overlay')?.remove();
  buttonEl.classList.remove('is-loading', 'is-loading-replace', 'is-success');
  buttonEl.removeAttribute('aria-busy');

  if (state === 'loading') {
    if (buttonEl.dataset.originalWidth) buttonEl.style.minWidth = buttonEl.dataset.originalWidth;
    buttonEl.disabled = true;
    buttonEl.setAttribute('aria-busy', 'true');
    buttonEl.classList.add('is-loading');

    const spinner = document.createElement('span');
    spinner.className = 'btn-spinner';
    spinner.setAttribute('aria-hidden', 'true');

    if (replaceText || !label) {
      buttonEl.classList.add('is-loading-replace');
      const overlay = document.createElement('span');
      overlay.className = 'btn-state-overlay';
      overlay.setAttribute('aria-hidden', 'true');
      overlay.append(spinner);
      buttonEl.append(overlay);
    } else {
      buttonEl.textContent = label;
      buttonEl.prepend(spinner);
    }
    return;
  }

  if (state === 'success') {
    if (buttonEl.dataset.originalWidth) buttonEl.style.minWidth = buttonEl.dataset.originalWidth;
    buttonEl.disabled = false;
    buttonEl.classList.add('is-success');

    const checkWrap = document.createElement('span');
    checkWrap.className = 'btn-check-badge';
    checkWrap.setAttribute('aria-hidden', 'true');
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', '18');
    svg.setAttribute('height', '18');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2.5');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    const path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', 'M5 12.5 9.5 17 19 7.5');
    svg.append(path);
    checkWrap.append(svg);

    if (replaceText || !label) {
      buttonEl.classList.add('is-loading-replace');
      const overlay = document.createElement('span');
      overlay.className = 'btn-state-overlay';
      overlay.setAttribute('aria-hidden', 'true');
      overlay.append(checkWrap);
      buttonEl.append(overlay);
    } else {
      buttonEl.textContent = label;
      buttonEl.prepend(checkWrap);
    }
    return;
  }

  buttonEl.disabled = false;
  buttonEl.style.minWidth = '';
  delete buttonEl.dataset.originalWidth;
  if (label) buttonEl.textContent = label;
}

export function syncSlidingTabs(tabBar) {
  if (!tabBar) return;
  const items = [...tabBar.querySelectorAll(':scope > .tab, :scope > .auth-tab, :scope > .ui-tab')];
  if (!items.length) return;
  const active = items.find(item => item.classList.contains('active') || item.classList.contains('is-active') || item.getAttribute('aria-selected') === 'true') || items[0];

  let glider = tabBar.querySelector(':scope > .tabs-glider');
  if (!glider) {
    glider = document.createElement('span');
    glider.className = 'tabs-glider';
    glider.setAttribute('aria-hidden', 'true');
    tabBar.prepend(glider);
    tabBar.classList.add('has-glider');
  }

  const update = () => {
    const barRect = tabBar.getBoundingClientRect();
    const itemRect = active.getBoundingClientRect();
    if (!barRect.width || !itemRect.width) return;
    glider.style.width = `${Math.round(itemRect.width)}px`;
    glider.style.transform = `translateX(${Math.round(itemRect.left - barRect.left)}px)`;
  };

  requestAnimationFrame(update);
}

let socraticTimer = null;

function enhanceSocraticCard(container) {
  clearInterval(socraticTimer);
  socraticTimer = null;
  const card = container?.querySelector?.('.atelier-dialogue-card');
  if (!card || prefersReducedMotion()) return;

  const stepTag = card.querySelector('.atelier-dialogue-step');
  const rows = [...card.querySelectorAll('.atelier-dialogue-item')];
  if (!stepTag || rows.length !== 3) return;

  let stepIndex = 0;
  const applyStep = idx => {
    const num = String(idx + 1).padStart(2, '0');
    stepTag.textContent = `${num} / 03`;
    stepTag.classList.remove('step-swap');
    void stepTag.offsetWidth;
    stepTag.classList.add('step-swap');
    rows.forEach((row, i) => {
      row.classList.toggle('is-active-step', i === idx);
    });
  };

  socraticTimer = setInterval(() => {
    if (!card.isConnected) {
      clearInterval(socraticTimer);
      socraticTimer = null;
      return;
    }
    stepIndex = (stepIndex + 1) % 3;
    applyStep(stepIndex);
  }, 2800);
}

function animateIntroMetrics(container) {
  if (prefersReducedMotion()) return;
  const metrics = [...(container?.querySelectorAll?.('.intro-metric strong') || [])];
  for (const node of metrics) {
    if (node.dataset.counted === '1') continue;
    const finalText = node.textContent || '';
    const match = finalText.match(/^(\d+)(.*)$/);
    if (!match) continue;
    node.dataset.counted = '1';
    const target = Number(match[1]);
    const padLen = match[1].length;
    const suffix = match[2];
    const start = performance.now();
    const duration = 440;

    const tick = now => {
      if (!node.isConnected) return;
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = Math.round(target * eased);
      const formatted = padLen > 1 && target < 100 ? String(current).padStart(padLen, '0') : String(current);
      node.textContent = `${formatted}${suffix}`;
      if (progress < 1) requestAnimationFrame(tick);
      else node.textContent = finalText;
    };
    requestAnimationFrame(tick);
  }
}

function animateProgressBars(container) {
  const fills = [...(container?.querySelectorAll?.('.ui-progress-fill[data-target-ratio]') || [])];
  for (const fill of fills) {
    const ratio = fill.dataset.targetRatio || '0';
    if (prefersReducedMotion()) {
      fill.style.setProperty('--progress-ratio', ratio);
    } else {
      fill.style.setProperty('--progress-ratio', '0');
      requestAnimationFrame(() => {
        requestAnimationFrame(() => fill.style.setProperty('--progress-ratio', ratio));
      });
    }
  }
}

let activeObserver = null;

export function observeScrollReveal(root = document) {
  activeObserver?.disconnect();
  const targets = [...root.querySelectorAll('.reveal')];
  if (!targets.length) return;

  if (prefersReducedMotion() || typeof IntersectionObserver !== 'function') {
    targets.forEach(node => node.classList.add('is-visible'));
    return;
  }

  activeObserver = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        activeObserver?.unobserve(entry.target);
      }
    }
  }, { threshold: 0.08, rootMargin: '0px 0px -24px 0px' });

  for (const target of targets) {
    const rect = target.getBoundingClientRect();
    if (rect.top < window.innerHeight * 0.94) {
      target.classList.add('is-visible');
    } else {
      activeObserver.observe(target);
    }
  }
}

export function enhancePageMotion(container) {
  document.querySelectorAll('.celebration-layer').forEach(node => node.remove());
  const first = container?.firstElementChild;
  if (first) {
    first.classList.remove('page-enter');
    void first.offsetWidth;
    first.classList.add('page-enter');
  }

  const items = container?.querySelectorAll('.topic-row, .stat, .result-item, .intro-pillar, .learning-document-link') || [];
  items.forEach((node, index) => {
    node.classList.add('stagger-item');
    node.style.setProperty('--stagger-i', String(Math.min(index, 6)));
    if (node.classList.contains('result-item') && node.classList.contains('wrong')) {
      node.classList.add('shake-enter');
    }
  });

  container?.querySelectorAll('.tabs, .auth-tabs, .ui-tabs').forEach(syncSlidingTabs);
  enhanceSocraticCard(container);
  animateIntroMetrics(container);
  animateProgressBars(container);
  observeScrollReveal(container);
}

export function thinkingStatus(text) {
  const wrap = document.createElement('div');
  wrap.className = 'thinking-inline';
  wrap.setAttribute('role', 'status');

  const dots = document.createElement('span');
  dots.className = 'thinking-dots';
  dots.setAttribute('aria-hidden', 'true');
  dots.append(document.createElement('span'), document.createElement('span'), document.createElement('span'));

  const label = document.createElement('span');
  label.textContent = text;
  wrap.append(dots, label);
  return wrap;
}

export function skeletonState(labelText, variant = 'list') {
  const wrap = document.createElement('div');
  wrap.className = 'skeleton-wrap';
  wrap.setAttribute('role', 'status');

  const caption = document.createElement('p');
  caption.className = 'loading-caption';
  caption.textContent = labelText;

  const grid = document.createElement('div');
  grid.className = `skeleton-grid skeleton-grid--${variant === 'kpi' ? 'kpi' : variant === 'cards' ? 'cards' : 'list'}`;
  grid.setAttribute('aria-hidden', 'true');

  if (variant === 'kpi') {
    for (let i = 0; i < 3; i++) {
      const box = document.createElement('div');
      box.className = 'skeleton-box';
      grid.append(box);
    }
  } else if (variant === 'cards') {
    for (let i = 0; i < 4; i++) {
      const box = document.createElement('div');
      box.className = 'skeleton-box';
      grid.append(box);
    }
  } else {
    for (const cls of ['skeleton-line', 'skeleton-line short', 'skeleton-box']) {
      const item = document.createElement('div');
      item.className = cls;
      grid.append(item);
    }
  }

  wrap.append(caption, grid);
  return wrap;
}

export function launchCelebration() {
  if (prefersReducedMotion()) return;
  const layer = document.createElement('div');
  layer.className = 'celebration-layer';
  layer.setAttribute('aria-hidden', 'true');

  const styles = getComputedStyle(document.documentElement);
  const palette = [
    styles.getPropertyValue('--c-confetti-1').trim(),
    styles.getPropertyValue('--c-confetti-2').trim(),
    styles.getPropertyValue('--c-confetti-3').trim(),
    styles.getPropertyValue('--c-confetti-4').trim(),
    styles.getPropertyValue('--c-confetti-5').trim(),
  ].filter(Boolean);

  const count = 18;
  for (let i = 0; i < count; i++) {
    const bit = document.createElement('span');
    bit.className = 'confetti-bit';
    const angle = (Math.PI * 2 * i) / count + (i % 2 === 0 ? 0.12 : -0.12);
    const dist = 110 + (i % 4) * 38;
    const dx = Math.round(Math.cos(angle) * dist);
    const dy = Math.round(Math.sin(angle) * dist - 40);
    const rot = (i % 2 === 0 ? 1 : -1) * (160 + i * 24);
    bit.style.setProperty('--dx', `${dx}px`);
    bit.style.setProperty('--dy', `${dy}px`);
    bit.style.setProperty('--rot', `${rot}deg`);
    if (palette.length) bit.style.setProperty('--bit-color', palette[i % palette.length]);
    bit.style.setProperty('--bit-delay', `${(i % 5) * 35}ms`);
    layer.append(bit);
  }

  document.body.append(layer);
  setTimeout(() => layer.remove(), 1450);
}
