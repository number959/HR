// Backup: copie giornaliere sul server, scarico, seconda copia su una cartella separata (NAS o disco), prova di ripristino.
import { download, get, post, put } from '../api.js';
import { alertBox, badge, button, card, checkbox, errorMessage, field, fmt, h, input, kpi, showErrors, table, toast } from '../ui.js';

export async function render(ctx) {
  const data = await get('backups');
  const p = data.policy;
  const destination = input('destination', p.destination, { max: 2048, placeholder: 'Percorso della cartella montata sul server' });
  const retention = input('retention_count', p.retention_count, { type: 'number', min: '0' });
  const probeDays = input('probe_interval_days', p.probe_interval_days, { type: 'number', min: '1' });
  const enabled = checkbox('enabled', p.enabled, 'Attiva la seconda copia giornaliera');
  const form = h('form', { class: 'stack', novalidate: true },
    alertBox('Indica solo una cartella reale, già montata sul server e verificata dal tecnico (per esempio il NAS aziendale). Finché non è attiva, i backup restano solo sul server.', 'info'),
    h('div', { class: 'form-grid' }, field('Cartella di destinazione', destination, { name: 'destination', wide: true }),
      field('Copie da conservare (0 = tutte)', retention, { name: 'retention_count' }),
      field('Prova di ripristino ogni (giorni)', probeDays, { name: 'probe_interval_days' })),
    enabled,
    h('div', { class: 'form-actions' }, button('Salva', { kind: 'primary', type: 'submit', ic: 'check' })));
  form.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await put('backups/policy', { destination: destination.value.trim(), retention_count: Number(retention.value),
        probe_interval_days: Number(probeDays.value), enabled: enabled.querySelector('input').checked });
      toast('Impostazioni della seconda copia salvate.', 'ok');
      ctx.refresh();
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); }
  });
  const runCopy = probe => async () => {
    try {
      await post('backups/policy/run', { probe });
      toast(probe ? 'Copia eseguita e prova di ripristino superata.' : 'Copia eseguita e verificata.', 'ok');
      ctx.refresh();
    } catch (err) { toast(errorMessage(err), 'bad'); ctx.refresh(); }
  };
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Sistema' }),
      h('h1', { text: 'Backup' }), h('p', { text: data.schedule })),
    h('div', { class: 'page-actions' }, button('Crea un backup ora', { kind: 'primary', ic: 'database', onClick: async () => {
      try { const res = await post('backups'); toast(`Backup creato: ${res.filename}`, 'ok'); ctx.refresh(); } catch (err) { toast(errorMessage(err), 'bad'); }
    } }))),
    p.last_error || p.retention_error ? alertBox(`Ultimo problema: ${p.last_error || p.retention_error}`, 'bad') : null,
    h('div', { class: 'kpis' },
      kpi('Backup sul server', fmt.number(data.count), fmt.bytes(data.bytes)),
      kpi('Seconda copia', p.enabled ? 'Attiva' : 'Non attiva', p.enabled ? `${fmt.number(p.copy_count)} copie nella destinazione` : 'da configurare', p.enabled ? 'ok' : 'warn'),
      kpi('Ultima copia riuscita', p.last_success ? fmt.stamp(p.last_success) : '—', p.last_copy?.folder || ''),
      kpi('Ultima prova di ripristino', p.last_probe?.at ? fmt.stamp(p.last_probe.at) : '—', p.last_probe?.ok === false ? 'non riuscita' : '', p.last_probe?.ok === false ? 'bad' : '')),
    h('div', { class: 'grid grid-main' },
      card('Backup sul server', { subtitle: `Ultimi ${data.shown} di ${data.count}`, flush: true }, table([
        { label: 'File', render: f => h('span', { class: 'mono', text: f.filename }) },
        { label: 'Creato', render: f => fmt.stamp(f.created_at) },
        { label: 'Dimensione', num: true, render: f => fmt.bytes(f.bytes) },
        { label: '', render: f => f.downloadable ? button('Scarica', { small: true, ic: 'download', onClick: async () => {
          try { await download(`backups/files/${encodeURIComponent(f.filename)}`, f.filename); } catch (err) { toast(errorMessage(err), 'bad'); }
        } }) : h('span', { class: 'small faint', text: 'copiare dal server' }) },
      ], data.files, { empty: 'Nessun backup ancora creato.' })),
      card('Seconda copia', { subtitle: p.note, actions: p.enabled ? [button('Copia ora', { small: true, onClick: runCopy(false) }),
        button('Prova di ripristino', { small: true, onClick: runCopy(true) })] : null },
      p.destination_error ? alertBox(p.destination_error, 'bad') : null,
      p.same_filesystem ? alertBox('La destinazione è sullo stesso disco dei dati: non protegge da un guasto del disco.', 'warn') : null,
      form)),
    card('Ripristino', {}, h('p', { text: 'Il ripristino si esegue sul server, a servizio fermo, seguendo il manuale tecnico. Dopo il ripristino va eseguito «python manage.py after-restore»: chiude tutte le sessioni, annulla i codici di recupero, disattiva posta e promemoria e sospende gli invii in corso.' }),
      h('p', { class: 'small muted' }, 'Nota: «after-restore» modifica l’archivio ripristinato. ', badge('Mai su un archivio in uso', 'warn'))));
}
