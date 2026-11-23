import { $, api, h, fmtDate, relTime, toast, riskBadge } from './core.js';

function stars(name) {
  const wrap = h('div', { class: 'stars', role: 'radiogroup', 'aria-label': 'Helpfulness from 1 to 5' });
  for (let i = 5; i >= 1; i--) {
    wrap.append(h('input', { type: 'radio', name, id: `${name}-${i}`, value: i }), h('label', { for: `${name}-${i}`, title: `${i} of 5`, 'aria-label': `${i} of 5` }, '\u2605'));
  }
  return wrap;
}
const seg = (name, opts) => h('div', { class: 'segmented', role: 'radiogroup' }, opts.flatMap(([v, l], i) => [h('input', { type: 'radio', name, id: `${name}-${i}`, value: v }), h('label', { for: `${name}-${i}`, text: l })]));
const val = (form, name) => form.querySelector(`input[name="${name}"]:checked`)?.value || null;

function formFor(consultId, followupId) {
  const uid = `f${followupId || 'g'}${consultId || ''}`;
  const f = h('form', { class: 'stack', style: { '--gap': '16px' } });
  if (followupId) {
    f.append(h('div', {}, h('div', { class: 'label', text: 'How are your symptoms now?' }), seg(uid + '-o', [['improved', 'Improved'], ['partial', 'Partly improved'], ['no_change', 'No change'], ['worse', 'Worse']])),
      h('div', { class: 'check' }, h('input', { type: 'checkbox', id: uid + '-ns' }), h('label', { for: uid + '-ns', text: 'New symptoms have appeared' })));
  }
  f.append(h('div', {}, h('div', { class: 'label', text: 'Did you actually use the recommendation?' }), seg(uid + '-u', [['yes', 'Yes'], ['partly', 'Partly'], ['no', 'No']])),
    h('div', {}, h('div', { class: 'label', text: 'How helpful was the response?' }), stars(uid + '-r')),
    h('div', { class: 'field' }, h('label', { for: uid + '-c', text: 'Anything else? (optional, do not include personal details)' }), h('textarea', { id: uid + '-c', maxlength: 500 })),
    h('div', {}, h('button', { class: 'btn btn-primary', type: 'submit', text: 'Submit' })));
  const result = h('div');
  f.addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = { consultation_id: consultId, followup_id: followupId, outcome: val(f, uid + '-o'), new_symptoms: !!f.querySelector(`#${uid}-ns`)?.checked,
      used_recommendation: val(f, uid + '-u'), helpfulness: val(f, uid + '-r'), comment: f.querySelector(`#${uid}-c`).value };
    try {
      const r = await api('/api/feedback', { method: 'POST', body });
      toast('Thank you for the feedback');
      result.replaceChildren(r.advice ? h('div', { class: 'alert ' + (r.escalate ? 'alert-error' : 'alert-info'), role: 'alert', text: r.advice }) : '');
      f.querySelectorAll('input,textarea,button').forEach((x) => (x.disabled = true));
      if (followupId) setTimeout(load, 2500);
    } catch (x) { toast(x.message, 'error'); }
  });
  f.append(result);
  return f;
}

async function load() {
  const host = $('#due'); host.replaceChildren();
  const { items } = await api('/api/followups');
  if (!items.length) host.append(h('div', { class: 'card empty' }, 'No check-ins are scheduled right now.'));
  items.forEach((i) => host.append(h('section', { class: 'card' },
    h('div', { class: 'row', style: { justifyContent: 'space-between' } }, h('div', {}, h('h3', { text: i.title }), h('div', { class: 'small muted', text: i.due ? `Check-in due (${relTime(i.due_at)})` : `Check-in ${relTime(i.due_at)}` })), riskBadge(i.risk)),
    h('div', { style: { marginTop: '16px' } }, formFor(i.consultation_id, i.id)))));
  const { items: cons } = await api('/api/consultations');
  const g = $('#general-form'); g.replaceChildren();
  if (!cons.length) { g.append(h('p', { class: 'muted', text: 'Start a consultation first, then you can rate the answers here.' })); return; }
  const sel = h('select', { id: 'pick' }, cons.slice(0, 20).map((c) => h('option', { value: c.id, text: `${c.title} - ${fmtDate(c.updated)}` })));
  const holder = h('div');
  const draw = () => holder.replaceChildren(formFor(Number(sel.value), null));
  sel.addEventListener('change', draw);
  g.append(h('div', { class: 'field' }, h('label', { for: 'pick', text: 'Consultation' }), sel), holder); draw();
}
load();
