// Paghe: anteprima controllata del tracciato, modello versionato, specifiche del consulente. Nessun invio automatico.
import { download, get, post, put } from '../api.js';
import {
  alertBox, badge, button, card, checkbox, clear, empty, errorMessage, field, fmt, h, input, kpi, select, showErrors, table, tabs, textarea, toast,
} from '../ui.js';

const DELIMITERS = [[';', 'Punto e virgola (;)'], [',', 'Virgola (,)'], ['\t', 'Tabulazione']];

export async function render(ctx) {
  const { app } = ctx;
  const data = await get(`payroll/${app.cid}`);
  const cfg = structuredClone(data.config);
  let tab = ctx.query.tab || 'anteprima';
  const bar = h('div');
  const body = h('div');
  const draw = () => {
    clear(bar, tabs([{ id: 'anteprima', label: 'Anteprima e scarico' }, { id: 'modello', label: 'Modello del tracciato' },
      { id: 'specifiche', label: 'Specifiche del consulente' }, { id: 'versioni', label: 'Versioni', count: data.history.length }], tab, id => { tab = id; draw(); }));
    const views = { anteprima: () => previewTab(ctx, data), modello: () => templateTab(ctx, data, cfg),
      specifiche: () => specTab(ctx, data, cfg, () => { tab = 'modello'; draw(); }), versioni: () => versionsTab(data) };
    clear(body, views[tab]());
  };
  draw();
  const confirmed = data.config.status === 'confirmed';
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', null, h('div', { class: 'eyebrow', text: 'Paghe' }),
      h('h1', { text: `Tracciato paghe · ${data.center.name}` }),
      h('div', { class: 'row' }, data.version ? badge(`Modello v${data.version}`, 'brand') : badge('Modello non ancora salvato', 'warn'),
        confirmed ? badge('Verificato con il consulente', 'ok', true) : badge('Bozza da concordare', 'warn', true)))),
    confirmed ? null : alertBox('Il tracciato non è ancora stato concordato con il consulente del lavoro: si può controllare l’anteprima, ma lo scarico resta bloccato finché il modello non viene confermato con il riferimento alla verifica.', 'warn'),
    bar, body);
}

function previewTab(ctx, data) {
  const from = input('from', ctx.app.month, { type: 'month' });
  const to = input('to', ctx.app.month, { type: 'month' });
  const out = h('div');
  const load = async () => {
    clear(out, h('div', { class: 'skeleton' }));
    try {
      const res = await get(`payroll/${ctx.app.cid}/preview?from=${from.value}&to=${to.value}`);
      clear(out, previewResult(ctx, res));
    } catch (err) { clear(out, alertBox(errorMessage(err), 'bad')); }
  };
  const form = h('form', { class: 'form-grid', novalidate: true }, field('Dal mese', from), field('Al mese', to),
    h('div', { class: 'field end' }, button('Aggiorna l’anteprima', { kind: 'primary', type: 'submit', ic: 'refresh' })));
  form.addEventListener('submit', e => { e.preventDefault(); load(); });
  load();
  return h('div', { class: 'stack' }, card('Periodo', { subtitle: 'Una riga per ogni fascia a consuntivo; i turni pianificati sono esclusi.' }, form), out);
}

function previewResult(ctx, res) {
  const s = res.summary;
  const grouped = {};
  for (const i of res.issues) (grouped[`${i.severity}|${i.message.replace(/^[^:]*: /, '')}`] ||= { ...i, count: 0 }).count += 1;
  const issues = Object.values(grouped).sort((a, b) => (a.severity === 'error' ? 0 : 1) - (b.severity === 'error' ? 0 : 1));
  const dl = fmtName => button(`Scarica ${fmtName.toUpperCase()}`, { kind: fmtName === 'xlsx' ? 'primary' : '', ic: 'download', disabled: !res.can_download, onClick: async () => {
    try {
      await download(`payroll/${ctx.app.cid}/export?from=${res.first}&to=${res.last}&format=${fmtName}&fingerprint=${res.fingerprint}`, `paghe.${fmtName}`);
      toast('File scaricato: lo scarico è registrato nello storico.', 'ok');
    } catch (err) { toast(errorMessage(err), 'bad'); }
  } });
  return h('div', { class: 'stack' },
    h('div', { class: 'kpis' },
      kpi('Righe', fmt.number(s.rows), `${fmt.number(s.people)} persone`),
      kpi('Turni lavorati', fmt.number(s.work_shifts), s.known_minutes === null ? 'ore non disponibili' : `${fmt.hours(s.known_minutes)} con orari`),
      kpi('Assenze', fmt.number(s.absence_slots), `${fmt.number(s.absence_days)} giornate per causale`),
      kpi('Controlli bloccanti', fmt.number(s.blocking_issues), `${fmt.number(s.warnings)} avvisi`, s.blocking_issues ? 'bad' : 'ok')),
    card('Controlli', { subtitle: res.can_download ? 'Nessun controllo bloccante: il file corrisponde a questa anteprima.' : 'Risolvi i controlli bloccanti per poter scaricare.',
      actions: [dl('csv'), dl('xlsx')], flush: true },
    issues.length ? h('ul', { class: 'list' }, issues.map(i => h('li', null,
      h('span', { class: `icon-dot ${i.severity === 'error' ? 'urgent' : ''}`, text: i.severity === 'error' ? '!' : 'i' }),
      h('div', { class: 'grow' }, h('div', { class: 'title', text: i.message }), i.count > 1 ? h('div', { class: 'detail', text: `${i.count} casi` }) : null),
      badge(i.severity === 'error' ? 'Bloccante' : 'Avviso', i.severity === 'error' ? 'bad' : 'warn'))))
      : h('div', { class: 'card-body' }, alertBox('Nessun problema trovato.', 'ok'))),
    card('Anteprima delle righe', { subtitle: `Prime ${res.shown_rows} righe su ${s.rows} · modello «${res.template_name}» v${res.version}`, flush: true },
      res.rows.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'table compact' },
        h('thead', null, h('tr', null, res.columns.map(c => h('th', { text: c.label })))),
        h('tbody', null, res.rows.map(r => h('tr', null, r.map(v => h('td', { text: v === null || v === undefined ? '' : String(v) })))))))
        : empty('Nessuna riga', 'Nel periodo non ci sono registrazioni a consuntivo.')));
}

function templateTab(ctx, data, cfg) {
  const consultant = () => cfg.connector.mode === 'consultant';
  const name = input('name', cfg.name, { max: 120 });
  name.addEventListener('input', () => { cfg.name = name.value; });
  const status = select('status', [['draft', 'Bozza da concordare'], ['confirmed', 'Verificato con il consulente']], cfg.status);
  const note = textarea('confirmation_note', cfg.confirmation_note, { max: 1000, rows: 2 });
  const confirmBox = checkbox('confirm_connector', false, 'Confermo di aver verificato questa versione del tracciato con il consulente');
  const syncStatus = () => { cfg.status = status.value; confirmBox.classList.toggle('hidden', !(consultant() && cfg.status === 'confirmed')); };
  status.addEventListener('change', syncStatus);
  note.addEventListener('input', () => { cfg.confirmation_note = note.value; });
  const delimiter = select('delimiter', DELIMITERS, cfg.delimiter);
  delimiter.addEventListener('change', () => { cfg.delimiter = delimiter.value; });
  const decimal = select('decimal_separator', [[',', 'Virgola'], ['.', 'Punto']], cfg.decimal_separator);
  decimal.addEventListener('change', () => { cfg.decimal_separator = decimal.value; });
  const mode = select('mode', [['generic', 'Tracciato generico (CSV o Excel da concordare)'], ['consultant', 'Specifiche ricevute dal consulente']], cfg.connector.mode);
  const connectorBox = h('div');
  const columnsBox = h('div');
  const fieldOptions = [['', '— Nessun dato —'], ...data.fields.map(f => [f.id, f.label + (f.required ? ' *' : '')])];

  const drawConnector = () => {
    const c = cfg.connector;
    if (!consultant()) { clear(connectorBox); return; }
    const bind = (key, el) => { el.addEventListener('input', () => { c[key] = el.value; }); el.addEventListener('change', () => { c[key] = el.value; }); return el; };
    clear(connectorBox, h('div', { class: 'form-grid' },
      field('Gestionale del consulente', bind('provider', input('provider', c.provider, { max: 120 })), { name: 'connector', hint: 'Indicare il nome esatto comunicato dal consulente.' }),
      field('Nome del tracciato', bind('format_name', input('format_name', c.format_name, { max: 120 }))),
      field('Versione delle specifiche', bind('format_version', input('format_version', c.format_version, { max: 80 }))),
      field('Riferimento alle specifiche ricevute', bind('specification_reference', input('specification_reference', c.specification_reference, { max: 500 }))),
      field('Formato delle date', bind('date_format', select('date_format', [['YYYY-MM-DD', 'AAAA-MM-GG'], ['DD/MM/YYYY', 'GG/MM/AAAA']], c.date_format))),
      field('Codifica del file', bind('encoding', select('encoding', [['utf-8-sig', 'UTF-8 con BOM'], ['utf-8', 'UTF-8'], ['cp1252', 'Windows-1252']], c.encoding)))),
    c.expected_columns.length ? h('p', { class: 'small muted mt', text: `Intestazioni attese dal consulente: ${c.expected_columns.map(x => x.header).join(' · ')}` })
      : alertBox('Nessuna intestazione del consulente: caricale dalla scheda «Specifiche del consulente».', 'info'));
  };
  const drawColumns = () => {
    clear(columnsBox, h('div', { class: 'table-wrap' }, h('table', { class: 'table editor' },
      h('thead', null, h('tr', null, ['#', 'Intestazione nel file', 'Dato del registro', ''].map(t => h('th', { text: t })))),
      h('tbody', null, cfg.columns.map((col, i) => {
        const label = input('label', col.label, { max: 120 });
        label.addEventListener('input', () => { col.label = label.value; });
        const fieldSel = select('field', fieldOptions, col.field);
        fieldSel.addEventListener('change', () => { col.field = fieldSel.value; });
        const move = d => () => { const j = i + d; if (j < 0 || j >= cfg.columns.length) return; [cfg.columns[i], cfg.columns[j]] = [cfg.columns[j], cfg.columns[i]]; drawColumns(); };
        return h('tr', null, h('td', { class: 'faint', text: String(i + 1) }), h('td', null, label), h('td', null, fieldSel),
          h('td', null, h('div', { class: 'row tight' }, button('', { kind: 'ghost icon', ic: 'chevronLeft', aria: 'Sposta su', onClick: move(-1) }),
            button('', { kind: 'ghost icon', ic: 'chevronRight', aria: 'Sposta giù', onClick: move(1) }),
            button('', { kind: 'ghost icon', ic: 'trash', aria: 'Rimuovi', onClick: () => { cfg.columns.splice(i, 1); drawColumns(); } }))));
      })))),
    h('div', { class: 'row mt' }, button('Aggiungi colonna', { small: true, ic: 'plus', onClick: () => { cfg.columns.push({ field: '', label: 'Nuova colonna' }); drawColumns(); } })));
  };
  mode.addEventListener('change', () => { cfg.connector.mode = mode.value; drawConnector(); syncStatus(); });
  drawConnector();
  drawColumns();
  syncStatus();

  const causes = h('div', { class: 'form-grid' }, data.causes.map(c => {
    const el = input(`cause-${c.id}`, cfg.causes[c.id] || '', { max: 100, placeholder: 'Codice paghe' });
    el.addEventListener('input', () => { cfg.causes[c.id] = el.value.trim(); });
    return field(`${c.id} · ${c.label}`, el);
  }));
  const registrations = h('div', { class: 'form-grid' }, data.people.map(p => {
    const el = input(`reg-${p.id}`, cfg.registrations[p.id] || '', { max: 100, placeholder: p.registration || 'matricola' });
    el.addEventListener('input', () => { if (el.value.trim()) cfg.registrations[p.id] = el.value.trim(); else delete cfg.registrations[p.id]; });
    return field(p.name, el, { hint: p.registration ? `Matricola del registro: ${p.registration}` : 'Nessuna matricola nel registro' });
  }));
  const form = h('form', { class: 'stack', novalidate: true },
    card('Modello', {}, h('div', { class: 'form-grid' }, field('Nome del modello', name, { name: 'name' }), field('Stato', status, { name: 'status' }),
      field('Separatore delle colonne', delimiter, { name: 'delimiter' }), field('Separatore decimale', decimal, { name: 'decimal_separator' }),
      field('Riferimento alla verifica con il consulente', note, { name: 'confirmation_note', wide: true, hint: 'Per esempio: data e persona con cui è stato verificato il tracciato. Obbligatorio per confermare.' })),
    confirmBox),
    card('Collegamento al consulente', { subtitle: 'Nessun gestionale è presunto: va indicato quello reale del consulente.' }, field('Tipo di tracciato', mode), connectorBox),
    card('Colonne del file', { subtitle: 'Ordine e intestazioni delle colonne. I dati con * sono obbligatori nel tracciato generico.' }, columnsBox),
    card('Codici paghe delle causali', { subtitle: 'Senza codice, le righe con quella causale bloccano lo scarico.' }, causes),
    card('Matricole paghe', { subtitle: 'Solo se diverse dalla matricola del registro.' }, registrations),
    h('div', { class: 'form-actions' }, button('Salva una nuova versione', { kind: 'primary', type: 'submit', ic: 'check' })));
  form.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const res = await put(`payroll/${ctx.app.cid}`, { config: cfg, version: data.version, confirm_connector: confirmBox.querySelector('input').checked });
      toast(`Modello salvato: versione ${res.version}${res.status === 'confirmed' ? ' (confermata)' : ' (bozza)'}.`, 'ok');
      ctx.refresh();
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); }
  });
  return form;
}

function specTab(ctx, data, cfg, goTemplate) {
  const kind = select('kind', [['csv_header', 'Riga di intestazione CSV'], ['json', 'Specifica JSON (nefrocenter.payroll-spec.v1)']], 'csv_header');
  const delimiter = select('delimiter', DELIMITERS, ';');
  const text = textarea('text', '', { rows: 6, max: 32768 });
  const out = h('div');
  const form = h('form', { class: 'stack', novalidate: true },
    alertBox('Incolla soltanto la riga delle intestazioni o le regole del tracciato: mai dati dei dipendenti. Niente viene salvato finché non salvi il modello.', 'info'),
    h('div', { class: 'form-grid' }, field('Tipo', kind), field('Separatore (per il CSV)', delimiter)),
    field('Testo delle specifiche', text, { name: 'text' }),
    h('div', { class: 'form-actions' }, button('Leggi le specifiche', { kind: 'primary', type: 'submit' })));
  form.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const res = await post(`payroll/${ctx.app.cid}/spec-preview`, { kind: kind.value, text: text.value, delimiter: delimiter.value });
      clear(out, card('Specifiche lette', { subtitle: res.notice }, table([
        { label: 'Intestazione', key: 'label' }, { label: 'Dato del registro', render: c => c.field ? (data.fields.find(f => f.id === c.field)?.label || c.field) : badge('Da associare', 'warn') },
      ], res.columns), h('div', { class: 'form-actions' }, button('Usa nel modello (da salvare)', { kind: 'primary', onClick: () => {
        Object.assign(cfg, { columns: res.columns, delimiter: res.delimiter, decimal_separator: res.decimal_separator, status: 'draft' });
        cfg.connector = res.connector;
        toast('Specifiche copiate nel modello: completa i dati mancanti e salva.', 'ok');
        goTemplate();
      } }))));
    } catch (err) { if (!showErrors(form, err)) toast(errorMessage(err), 'bad'); }
  });
  const exportSpec = button('Scarica le specifiche attuali (JSON)', { ic: 'download', onClick: async () => {
    try {
      const spec = await get(`payroll/${ctx.app.cid}/specification`);
      const url = URL.createObjectURL(new Blob([JSON.stringify(spec, null, 2)], { type: 'application/json' }));
      const a = h('a', { href: url, download: `specifiche-paghe-${data.center.code}.json` });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 3000);
    } catch (err) { toast(errorMessage(err), 'bad'); }
  } });
  return h('div', { class: 'stack' }, card('Importa le specifiche del consulente', { actions: exportSpec }, form), out);
}

function versionsTab(data) {
  return card('Versioni del modello', { flush: true }, table([
    { label: 'Versione', render: r => r.version === data.version ? badge(`v${r.version} · in uso`, 'ok') : `v${r.version}` },
    { label: 'Nome', key: 'name' }, { label: 'Stato', render: r => r.status === 'confirmed' ? badge('Verificato', 'ok') : badge('Bozza', 'warn') },
    { label: 'Quando', render: r => fmt.stamp(r.created_at) }, { label: 'Da', key: 'created_by' },
  ], data.history, { empty: 'Nessuna versione salvata: il modello generico non è ancora stato salvato.' }));
}
