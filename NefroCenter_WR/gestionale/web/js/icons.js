// Icone a tratto (24×24), disegnate per NefroCenter WR. Create come SVG via DOM: nessun HTML in linea.
const NS = 'http://www.w3.org/2000/svg';
const PATHS = {
  home: 'M3 11.5 12 4l9 7.5M5.5 9.5V20h5v-6h3v6h5V9.5',
  check: 'M4 12.5l5 5L20 6.5',
  checks: 'M3 13l4 4 8-9M10 16l1 1 9-10',
  calendar: 'M4 6.5h16v13.5H4zM4 10.5h16M8.5 3.5v5M15.5 3.5v5',
  shield: 'M12 3.5l7.5 3v5.5c0 4.3-3.2 7.6-7.5 8.5-4.3-.9-7.5-4.2-7.5-8.5V6.5zM8.5 12l2.5 2.5 4.5-4.5',
  stamp: 'M8 20h8M6 16.5h12v-3a2 2 0 0 0-2-2h-1.5V9a2.5 2.5 0 1 0-5 0v2.5H8a2 2 0 0 0-2 2z',
  layers: 'M12 3.5 21 8l-9 4.5L3 8zM3 12.5l9 4.5 9-4.5M3 16.5l9 4.5 9-4.5',
  users: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2.5 20c.6-3.4 3.2-5.5 6.5-5.5s5.9 2.1 6.5 5.5M16 4.3a3.5 3.5 0 0 1 0 6.4M18 14.8c1.9.7 3.2 2.4 3.5 5.2',
  file: 'M6 3.5h8l4 4V20.5H6zM14 3.5V8h4M9 12.5h6M9 16h6',
  link: 'M10 14a4 4 0 0 0 5.7 0l3-3A4 4 0 0 0 13 5.3l-1.2 1.2M14 10a4 4 0 0 0-5.7 0l-3 3A4 4 0 0 0 11 18.7l1.2-1.2',
  door: 'M5 20.5V4.5l9-1.5v18zM14 5h5v15.5h-5M10.5 12.5v.5M3 20.5h18',
  building: 'M4 20.5V5.5l8-2v17M12 8.5h8v12M7 8h2M7 11.5h2M7 15h2M15 12h2M15 15.5h2M2.5 20.5h19',
  calculator: 'M6 3.5h12v17H6zM8.5 6.5h7v3h-7zM9 13h.01M12 13h.01M15 13h.01M9 16.5h.01M12 16.5h.01M15 16.5h.01',
  wallet: 'M4 6.5h14.5a1.5 1.5 0 0 1 1.5 1.5v11a1.5 1.5 0 0 1-1.5 1.5H4zM4 6.5 15 3.5v3M15.5 13.5h2',
  mail: 'M3.5 6h17v12.5h-17zM3.5 6.5l8.5 6.5 8.5-6.5',
  bell: 'M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15zM10 20.5h4',
  chart: 'M4 20h16M7 17v-6M11.5 17V7M16 17v-9M20 17v-3',
  download: 'M12 3.5v12M7 11l5 5 5-5M4.5 20h15',
  upload: 'M12 16V4M7 8.5l5-5 5 5M4.5 20h15',
  sliders: 'M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1M15 4v4M9 10v4M17 16v4',
  key: 'M14.5 10a4.5 4.5 0 1 0-3.2 4.3L13 16h2v2h2v2.5h3.5V17l-6-6',
  database: 'M5 6c0-1.4 3.1-2.5 7-2.5s7 1.1 7 2.5-3.1 2.5-7 2.5S5 7.4 5 6zM5 6v12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V6M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5',
  help: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9.5 9.5a2.6 2.6 0 0 1 5 .9c0 1.7-2.5 2.2-2.5 3.6M12 17h.01',
  lock: 'M6 10.5h12v10H6zM8.5 10.5V7.5a3.5 3.5 0 0 1 7 0v3',
  logout: 'M14 4.5h5v15h-5M10 16l4-4-4-4M14 12H4',
  menu: 'M4 7h16M4 12h16M4 17h16',
  x: 'M6 6l12 12M18 6 6 18',
  plus: 'M12 5v14M5 12h14',
  edit: 'M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4',
  trash: 'M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13M10 11v6M14 11v6',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v6M12 7.5h.01',
  alert: 'M12 4 2.5 20h19zM12 10v4.5M12 17.5h.01',
  inbox: 'M3.5 13.5 6 5h12l2.5 8.5V19h-17zM3.5 13.5H9l1 2h4l1-2h5.5',
  search: 'M10.5 17.5a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM15.5 15.5 20.5 20.5',
  sun: 'M12 16.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9zM12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4',
  moon: 'M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z',
  chevronLeft: 'M14.5 6l-6 6 6 6',
  chevronRight: 'M9.5 6l6 6-6 6',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3.5 2',
  send: 'M20.5 3.5 10 14M20.5 3.5 14 20.5l-4-6.5-6.5-4z',
  eye: 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  undo: 'M9 14 4 9l5-5M4.5 9H14a6 6 0 0 1 0 12h-3',
  refresh: 'M20 11a8 8 0 0 0-14.8-4.2L3.5 9M3.5 4v5h5M4 13a8 8 0 0 0 14.8 4.2l1.7-2.2M20.5 20v-5h-5',
  shieldUser: 'M12 3.5l7.5 3v5.5c0 4.3-3.2 7.6-7.5 8.5-4.3-.9-7.5-4.2-7.5-8.5V6.5zM12 12a2.2 2.2 0 1 0 0-4.4 2.2 2.2 0 0 0 0 4.4zM8.3 16c.8-1.6 2.1-2.4 3.7-2.4s2.9.8 3.7 2.4',
  sparkle: 'M12 3.5l1.8 5.2L19 10.5l-5.2 1.8L12 17.5l-1.8-5.2L5 10.5l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z',
  print: 'M7 9V3.5h10V9M7 17.5H4.5v-8h15v8H17M7 14.5h10v6H7z',
};

export function icon(name, cls = '') {
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.8');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  if (cls) svg.setAttribute('class', cls);
  const path = document.createElementNS(NS, 'path');
  path.setAttribute('d', PATHS[name] || PATHS.info);
  svg.append(path);
  return svg;
}
