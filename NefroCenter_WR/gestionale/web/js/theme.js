// Applica il tema prima del disegno della pagina (evita il lampo bianco in modalità scura).
(function () {
  var theme = null;
  try { theme = localStorage.getItem('wr.theme'); } catch (e) { theme = null; }
  if (!theme) theme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', theme);
})();
