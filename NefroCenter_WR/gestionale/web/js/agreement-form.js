// Modulo dell'accordo economico (accordi del mese e condizioni con decorrenza del personale di gruppo).
import { checkbox, field, h, input, select } from './ui.js';

export const MODELS = [['turns', 'A turni'], ['hours', 'A ore'], ['fixed', 'Quota fissa']];
export const BASES = [['surplus', 'Solo oltre il teorico'], ['all', 'Tutti i turni o le ore']];
const NUMBER_FIELDS = [
  ['weekday_rate', 'Tariffa feriale (€ per unità)'], ['holiday_rate', 'Tariffa festiva (€ per unità)'],
  ['fixed_amount', 'Quota fissa (€)'], ['fixed_deduction', 'Detrazione fissa (€)'], ['adjustment', 'Conguaglio (€, anche negativo)'],
  ['ccnl_count', 'Festivi già riconosciuti dal CCNL (numero)'], ['ccnl_rate', 'Valore di un festivo CCNL (€)'],
];

// Restituisce { node, value() }; disabled rende il modulo di sola lettura.
export function agreementForm(agreement, absenceCodes, { disabled = false } = {}) {
  const a = structuredClone(agreement);
  const model = select('model', MODELS, a.model, { disabled });
  const basis = select('basis', BASES, a.basis, { disabled });
  const mode = select('theoretical_mode', [['calendar', 'Dal calendario della struttura'], ['manual', 'Indicato a mano']], a.theoretical_mode, { disabled });
  const units = input('theoretical_units', a.theoretical_units, { type: 'number', min: '0', step: 'any', disabled });
  const hours = input('hours_per_day', a.hours_per_day, { type: 'number', min: '0', step: 'any', disabled });
  const numbers = Object.fromEntries(NUMBER_FIELDS.map(([key]) => [key, input(key, a[key], { type: 'number', step: 'any', disabled })]));
  const external = checkbox('include_external', a.include_external, 'Conteggia anche i turni fuori sede');
  const confirmed = checkbox('confirmed', a.confirmed, 'Accordo e calendario confermati con la persona');
  for (const box of [external, confirmed]) box.querySelector('input').disabled = disabled;
  const absences = h('div', { class: 'row tight' }, absenceCodes.map(c => {
    const box = checkbox('absence', a.counted_absences.includes(c.id), `${c.id} · ${c.label}`);
    const el = box.querySelector('input');
    el.value = c.id;
    el.disabled = disabled;
    return box;
  }));
  const unitsField = field('Teorico indicato a mano', units, { name: 'theoretical_units' });
  const hoursField = field('Ore teoriche al giorno', hours, { name: 'hours_per_day' });
  const sync = () => {
    unitsField.classList.toggle('hidden', mode.value !== 'manual');
    hoursField.classList.toggle('hidden', model.value !== 'hours');
  };
  model.addEventListener('change', sync);
  mode.addEventListener('change', sync);
  sync();
  const node = h('div', { class: 'stack' },
    h('div', { class: 'form-grid' }, field('Modello di calcolo', model, { name: 'model' }), field('Base di calcolo', basis, { name: 'basis' }),
      field('Teorico del mese', mode, { name: 'theoretical_mode' }), unitsField, hoursField),
    h('div', { class: 'form-grid' }, NUMBER_FIELDS.map(([key, label]) => field(label, numbers[key], { name: key }))),
    h('fieldset', { dataset: { field: 'counted_absences' } }, h('legend', { text: 'Assenze conteggiate come turni' }), absences),
    external, confirmed);
  const value = () => ({
    ...a, model: model.value, basis: basis.value, theoretical_mode: mode.value,
    theoretical_units: Number(units.value || 0), hours_per_day: Number(hours.value || 0),
    ...Object.fromEntries(NUMBER_FIELDS.map(([key]) => [key, Number(numbers[key].value || 0)])),
    counted_absences: [...absences.querySelectorAll('input:checked')].map(el => el.value),
    include_external: external.querySelector('input').checked, confirmed: confirmed.querySelector('input').checked,
  });
  return { node, value };
}

export function modelLabel(id) { return (MODELS.find(m => m[0] === id) || [id, id])[1]; }
