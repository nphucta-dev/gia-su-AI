const SVG_NS = 'http://www.w3.org/2000/svg';

const PATHS = {
  sparkles: [
    ['path', { d: 'M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z' }],
    ['path', { d: 'M20 3v4' }],
    ['path', { d: 'M22 5h-4' }],
  ],
  arrowRight: [
    ['path', { d: 'M5 12h14' }],
    ['path', { d: 'm13 6 6 6-6 6' }],
  ],
  checkSimple: [
    ['path', { d: 'M5 12.5 9.5 17 19 7.5' }],
  ],
  chevronDown: [
    ['path', { d: 'm6 9 6 6 6-6' }],
  ],
  refresh: [
    ['path', { d: 'M3 12a9 9 0 0 1 15-6.7L21 8' }],
    ['path', { d: 'M21 3v5h-5' }],
    ['path', { d: 'M21 12a9 9 0 0 1-15 6.7L3 16' }],
    ['path', { d: 'M3 21v-5h5' }],
  ],
  plus: [
    ['path', { d: 'M12 5v14' }],
    ['path', { d: 'M5 12h14' }],
  ],
  upload: [
    ['path', { d: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4' }],
    ['polyline', { points: '17 8 12 3 7 8' }],
    ['line', { x1: '12', y1: '3', x2: '12', y2: '15' }],
  ],
  rocket: [
    ['path', { d: 'M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z' }],
    ['path', { d: 'm12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z' }],
    ['path', { d: 'M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0' }],
    ['path', { d: 'M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5' }],
  ],
  brain: [
    ['path', { d: 'M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z' }],
    ['path', { d: 'M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z' }],
    ['path', { d: 'M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4' }],
  ],
  target: [
    ['circle', { cx: '12', cy: '12', r: '10' }],
    ['circle', { cx: '12', cy: '12', r: '6' }],
    ['circle', { cx: '12', cy: '12', r: '2' }],
  ],
  trending: [
    ['polyline', { points: '22 7 13.5 15.5 8.5 10.5 2 17' }],
    ['polyline', { points: '16 7 22 7 22 13' }],
  ],
  book: [
    ['path', { d: 'M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z' }],
    ['path', { d: 'M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z' }],
  ],
  compass: [
    ['circle', { cx: '12', cy: '12', r: '10' }],
    ['polygon', { points: '16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76' }],
  ],
  message: [
    ['path', { d: 'M7.9 20A9 9 0 1 0 4 16.1L2 22Z' }],
  ],
  check: [
    ['circle', { cx: '12', cy: '12', r: '10' }],
    ['path', { d: 'm9 12 2 2 4-4' }],
  ],
  xCircle: [
    ['circle', { cx: '12', cy: '12', r: '10' }],
    ['path', { d: 'm15 9-6 6' }],
    ['path', { d: 'm9 9 6 6' }],
  ],
  trophy: [
    ['path', { d: 'M6 9H4.5a2.5 2.5 0 0 1 0-5H6' }],
    ['path', { d: 'M18 9h1.5a2.5 2.5 0 0 0 0-5H18' }],
    ['path', { d: 'M4 22h16' }],
    ['path', { d: 'M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22' }],
    ['path', { d: 'M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22' }],
    ['path', { d: 'M18 2H6v7a6 6 0 0 0 12 0V2Z' }],
  ],
  clock: [
    ['circle', { cx: '12', cy: '12', r: '10' }],
    ['polyline', { points: '12 6 12 12 16 14' }],
  ],
  file: [
    ['path', { d: 'M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z' }],
    ['path', { d: 'M14 2v4a2 2 0 0 0 2 2h4' }],
    ['path', { d: 'M10 9H8' }],
    ['path', { d: 'M16 13H8' }],
    ['path', { d: 'M16 17H8' }],
  ],
  inbox: [
    ['polyline', { points: '22 12 16 12 14 15 10 15 8 12 2 12' }],
    ['path', { d: 'M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z' }],
  ],
  alert: [
    ['path', { d: 'm21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z' }],
    ['path', { d: 'M12 9v4' }],
    ['path', { d: 'M12 17h.01' }],
  ],
};

function svgEl(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v != null) node.setAttribute(k, String(v));
  }
  children.forEach(child => { if (child) node.append(child); });
  return node;
}

export function icon(name, { size = 18, className = '' } = {}) {
  const shapes = PATHS[name] || PATHS.sparkles;
  return svgEl('svg', {
    viewBox: '0 0 24 24',
    width: size,
    height: size,
    fill: 'none',
    stroke: 'currentColor',
    'stroke-width': '2',
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'aria-hidden': 'true',
    focusable: 'false',
    class: className ? `ui-icon ${className}` : 'ui-icon',
  }, ...shapes.map(([tag, attrs]) => svgEl(tag, attrs)));
}

export function socraticPreviewCard() {
  const card = document.createElement('div');
  card.className = 'atelier-dialogue-card';
  card.setAttribute('aria-hidden', 'true');

  const head = document.createElement('div');
  head.className = 'atelier-dialogue-head';
  const label = document.createElement('span');
  label.textContent = 'MẠCH GỢI MỞ SOCRATIC';
  const tag = document.createElement('span');
  tag.className = 'atelier-dialogue-step';
  tag.textContent = '01 / 03';
  head.append(label, tag);

  const steps = [
    ['q', 'Bạn học', 'Làm sao tìm nghiệm phương trình x² − 5x + 6 = 0?'],
    ['h', 'Gợi ý 01', 'Hãy thử tính biệt thức Δ = b² − 4ac trước. Bạn xác định hệ số a, b, c là bao nhiêu?'],
    ['s', 'Tự giải', 'a = 1, b = −5, c = 6 nên Δ = 25 − 24 = 1 > 0 → hai nghiệm x = 2 hoặc x = 3.'],
  ];

  const list = document.createElement('div');
  list.className = 'atelier-dialogue-list';
  steps.forEach(([kind, who, text], index) => {
    const row = document.createElement('div');
    row.className = `atelier-dialogue-item atelier-dialogue-item--${kind} stagger-item`;
    row.style.setProperty('--stagger-i', String(index + 1));
    const badge = document.createElement('span');
    badge.className = 'atelier-dialogue-who';
    badge.textContent = who;
    const body = document.createElement('p');
    body.textContent = text;
    row.append(badge, body);
    list.append(row);
  });

  card.append(head, list);
  return card;
}

export function knowledgeGraphVisual() {
  return socraticPreviewCard();
}
