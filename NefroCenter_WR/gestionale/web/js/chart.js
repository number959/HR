// Grafico a colonne di una sola serie (SVG creato via DOM): asse unico, griglia sottile, etichette selettive, tooltip al passaggio e al fuoco.
// Si ridisegna alla larghezza reale del riquadro, così i testi restano sempre della stessa dimensione.
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
  return [1, 2, 2.5, 5, 10].find(s => s * power >= value) * power;
}

// items: [{ label: 'ott 26', title: 'ottobre 2026', value: 64 }]; format: numero → testo
export function columnChart(items, { format = String, unit = '', height = 240 } = {}) {
  const wrap = document.createElement('div');
  wrap.className = 'chart-wrap';
  const tip = document.createElement('div');
  tip.className = 'chart-tip';
  tip.setAttribute('aria-hidden', 'true');
  let drawn = 0;

  const draw = width => {
    drawn = width;
    const left = 48;
    const right = 8;
    const top = 24;
    const bottom = 30;
    const band = (width - left - right) / Math.max(items.length, 1);
    const plot = height - top - bottom;
    const max = niceMax(Math.max(0, ...items.map(i => i.value || 0)));
    const y = v => top + plot - (v / max) * plot;
    const base = top + plot;
    const root = svg('svg', { viewBox: `0 0 ${width} ${height}`, width, height, class: 'chart', role: 'img',
      'aria-label': items.map(i => `${i.title}: ${format(i.value || 0)}${unit}`).join('; ') });
    for (const t of [0, max / 2, max]) {
      root.append(svg('line', { x1: left, x2: width - right, y1: y(t), y2: y(t), class: t ? 'chart-grid' : 'chart-axis' }));
      root.append(svg('text', { x: left - 8, y: y(t) + 4, class: 'chart-tick', 'text-anchor': 'end' }, format(t)));
    }
    const maxIndex = items.reduce((best, item, i) => ((item.value || 0) > (items[best]?.value || 0) ? i : best), 0);
    const every = Math.ceil(items.length / Math.max(1, Math.floor((width - left) / 54)));
    items.forEach((item, i) => {
      const cx = left + i * band + band / 2;
      const thick = Math.max(4, Math.min(24, band - 8));
      const value = item.value || 0;
      const h = (value / max) * plot;
      const x0 = cx - thick / 2;
      const r = Math.min(4, h);
      const col = h > 0 ? svg('path', { class: 'chart-col', d: `M${x0},${base} V${base - h + r} Q${x0},${base - h} ${x0 + r},${base - h} `
        + `H${x0 + thick - r} Q${x0 + thick},${base - h} ${x0 + thick},${base - h + r} V${base} Z` }) : null;
      if (col) root.append(col);
      if (i % every === 0 || i === items.length - 1) {
        root.append(svg('text', { x: cx, y: height - 10, class: 'chart-tick', 'text-anchor': 'middle' }, item.label));
      }
      if (value && (i === items.length - 1 || i === maxIndex)) {
        root.append(svg('text', { x: cx, y: base - h - 7, class: 'chart-value', 'text-anchor': 'middle' }, format(value)));
      }
      const hit = svg('rect', { x: left + i * band, y: top, width: band, height: plot, class: 'chart-hit', tabindex: '0',
        'aria-label': `${item.title}: ${format(value)}${unit}` });
      const show = () => {
        col?.classList.add('active');
        const strong = document.createElement('strong');
        strong.textContent = `${format(value)}${unit}`;
        const span = document.createElement('span');
        span.textContent = item.title;
        tip.replaceChildren(strong, span);
        tip.style.setProperty('--x', `${cx}px`);
        tip.style.setProperty('--y', `${base - h}px`);
        tip.classList.add('visible');
      };
      const hide = () => { col?.classList.remove('active'); tip.classList.remove('visible'); };
      hit.addEventListener('pointerenter', show);
      hit.addEventListener('pointerleave', hide);
      hit.addEventListener('focus', show);
      hit.addEventListener('blur', hide);
      root.append(hit);
    });
    wrap.replaceChildren(root, tip);
  };

  const observer = new ResizeObserver(entries => {
    const width = Math.floor(entries[0].contentRect.width);
    if (width > 0 && Math.abs(width - drawn) > 4) draw(width);
  });
  observer.observe(wrap);
  return wrap;
}
