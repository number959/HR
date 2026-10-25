// Grafico a colonne di una sola serie (SVG creato via DOM): asse unico, griglia sottile, etichette selettive, tooltip al passaggio e al fuoco.
const NS = 'http://www.w3.org/2000/svg';

function svg(tag, attrs = {}, text) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (text !== undefined) el.textContent = text;
  return el;
}

function niceMax(value) {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find(s => s * power >= value) * power;
  return step;
}

// items: [{ label: 'ott', title: 'ottobre 2026', value: 64 }], format: numero → testo
export function columnChart(items, { format = String, unit = '', height = 220 } = {}) {
  const wrap = document.createElement('div');
  wrap.className = 'chart-wrap';
  const tip = document.createElement('div');
  tip.className = 'chart-tip';
  tip.setAttribute('role', 'status');
  const band = 56;
  const left = 44;
  const top = 22;
  const bottom = 28;
  const width = left + Math.max(items.length, 4) * band + 8;
  const plot = height - top - bottom;
  const max = niceMax(Math.max(0, ...items.map(i => i.value || 0)));
  const y = v => top + plot - (v / max) * plot;
  const root = svg('svg', { viewBox: `0 0 ${width} ${height}`, class: 'chart', role: 'img', 'aria-label': items.map(i => `${i.title}: ${format(i.value)}${unit}`).join('; ') });
  for (const t of [0, max / 2, max]) {
    root.append(svg('line', { x1: left, x2: width - 4, y1: y(t), y2: y(t), class: 'chart-grid' }));
    root.append(svg('text', { x: left - 8, y: y(t) + 4, class: 'chart-tick', 'text-anchor': 'end' }, format(t)));
  }
  const maxIndex = items.reduce((best, item, i) => (item.value > (items[best]?.value ?? -1) ? i : best), 0);
  items.forEach((item, i) => {
    const cx = left + i * band + band / 2;
    const thick = Math.min(24, band - 12);
    const value = item.value || 0;
    const h = Math.max(0, (value / max) * plot);
    const x0 = cx - thick / 2;
    const base = top + plot;
    const r = Math.min(4, h);
    const d = h > 0
      ? `M${x0},${base} V${base - h + r} Q${x0},${base - h} ${x0 + r},${base - h} H${x0 + thick - r} Q${x0 + thick},${base - h} ${x0 + thick},${base - h + r} V${base} Z`
      : '';
    const col = svg('path', { d, class: 'chart-col' });
    const hit = svg('rect', { x: left + i * band, y: top, width: band, height: plot + bottom, class: 'chart-hit', tabindex: '0',
      'aria-label': `${item.title}: ${format(value)}${unit}` });
    const show = () => {
      col.classList.add('active');
      tip.replaceChildren(Object.assign(document.createElement('strong'), { textContent: `${format(value)}${unit}` }),
        Object.assign(document.createElement('span'), { textContent: item.title }));
      tip.style.setProperty('--x', `${((cx) / width) * 100}%`);
      tip.style.setProperty('--y', `${((base - h) / height) * 100}%`);
      tip.classList.add('visible');
    };
    const hide = () => { col.classList.remove('active'); tip.classList.remove('visible'); };
    hit.addEventListener('pointerenter', show);
    hit.addEventListener('pointerleave', hide);
    hit.addEventListener('focus', show);
    hit.addEventListener('blur', hide);
    root.append(col);
    root.append(svg('text', { x: cx, y: height - 8, class: 'chart-tick', 'text-anchor': 'middle' }, item.label));
    if (value && (i === items.length - 1 || i === maxIndex)) {
      root.append(svg('text', { x: cx, y: base - h - 6, class: 'chart-value', 'text-anchor': 'middle' }, format(value)));
    }
    root.append(hit);
  });
  root.append(svg('line', { x1: left, x2: width - 4, y1: top + plot, y2: top + plot, class: 'chart-axis' }));
  wrap.append(root, tip);
  return wrap;
}
