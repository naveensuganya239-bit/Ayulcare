// Shared health-profile form (used by the setup wizard and the settings page).
import { h } from './core.js';

export const STEPS = [
  { id: 'consent', title: 'Consent' },
  { id: 'basics', title: 'Basics' },
  { id: 'health', title: 'Health' },
  { id: 'lifestyle', title: 'Lifestyle' },
  { id: 'review', title: 'Review' },
];

const YNP = [['yes', 'Yes'], ['no', 'No'], ['prefer_not', 'Prefer not to say']];
export const FIELDS = {
  basics: [
    { name: 'name', label: 'Name', type: 'text', why: 'Used only to greet you. It is never sent to AI or search services.', autocomplete: 'name' },
    { name: 'date_of_birth', label: 'Date of birth', type: 'date', why: 'Age changes which warning signs matter (for example infants and older adults).' },
    { name: 'gender', label: 'Gender', type: 'choice', options: [['female', 'Female'], ['male', 'Male'], ['other', 'Other'], ['prefer_not', 'Prefer not to say']], why: 'Optional. Used only for general lifestyle information.' },
    { name: 'height_cm', label: 'Height (cm)', type: 'number', min: 40, max: 260, step: '0.1', why: 'Used to compute BMI for general lifestyle information.' },
    { name: 'weight_kg', label: 'Weight (kg)', type: 'number', min: 1, max: 500, step: '0.1', why: 'Used to compute BMI for general lifestyle information.' },
    { name: 'city', label: 'City', type: 'text', why: 'Optional. Helps future regional features. Never sent to AI or search services.' },
    { name: 'area', label: 'Area (optional)', type: 'text', why: 'Optional and never sent to AI or search services.' },
  ],
  health: [
    { name: 'chronic_conditions', label: 'Existing long-term conditions', type: 'textarea', placeholder: 'For example: diabetes, high blood pressure, asthma', why: 'Safety rules treat fever or infection symptoms more cautiously with some long-term conditions. Optional.' },
    { name: 'acute_problems', label: 'Current short-term health problems', type: 'textarea', why: 'Optional context for you; it does not change any safety rule.' },
    { name: 'pregnant', label: 'Are you currently pregnant? (if applicable)', type: 'choice3', why: 'Pregnancy changes when symptoms need a doctor. Optional.' },
    { name: 'menstrual_info', label: 'Menstrual cycle information (optional)', type: 'textarea', why: 'Optional. Stored encrypted. Not used for any automatic decision.' },
  ],
  lifestyle: [
    { name: 'sleep_hours', label: 'Average sleeping hours', type: 'number', min: 0, max: 24, step: '0.5', why: 'Used for general sleep information.' },
    { name: 'food_preference', label: 'Food preference', type: 'choice', options: [['vegetarian', 'Vegetarian'], ['non_vegetarian', 'Non-vegetarian'], ['eggetarian', 'Eggetarian'], ['vegan', 'Vegan'], ['other', 'Other']], why: 'Used for general eating information. It never creates a diet plan.' },
    { name: 'smoking', label: 'Do you smoke?', type: 'choice', options: YNP, why: 'Used for general lifestyle information.' },
    { name: 'alcohol', label: 'Do you drink alcohol?', type: 'choice', options: YNP, why: 'Used for general lifestyle information.' },
    { name: 'preferred_language', label: 'Preferred language', type: 'choice', options: [['auto', 'Detect automatically'], ['en', 'English'], ['ta', 'தமிழ்'], ['te', 'తెలుగు'], ['hi', 'हिन्दी']], why: 'Automatic detection is the default. This is only a fallback when detection is unsure.' },
    { name: 'contact_number', label: 'Contact number (only if you want to give one)', type: 'tel', why: 'Not needed to use the app. Stored encrypted and never sent to AI or search services.', consentFor: true },
  ],
};

export function fieldEl(f, value, uid) {
  const id = `${uid}-${f.name}`;
  const wrap = h('div', { class: 'field' });
  if (f.type === 'choice' || f.type === 'choice3') {
    const opts = f.type === 'choice3' ? [['true', 'Yes'], ['false', 'No'], ['', 'Not applicable / prefer not to say']] : f.options;
    const cur = f.type === 'choice3' ? (value === true ? 'true' : value === false ? 'false' : '') : (value ?? '');
    const grp = h('div', { class: 'segmented', role: 'radiogroup', 'aria-labelledby': id + '-l' });
    opts.forEach(([v, l], i) => {
      const rid = `${id}-${i}`;
      const inp = h('input', { type: 'radio', name: id, id: rid, value: v, 'data-field': f.name });
      if (String(cur) === String(v)) inp.checked = true;
      grp.append(inp, h('label', { for: rid, text: l }));
    });
    wrap.append(h('div', { class: 'label', id: id + '-l', text: f.label }), grp);
  } else {
    const common = { id, 'data-field': f.name, autocomplete: f.autocomplete || 'off' };
    const inp = f.type === 'textarea'
      ? h('textarea', { ...common, rows: 3, placeholder: f.placeholder || '', maxlength: 600 })
      : h('input', { ...common, type: f.type, min: f.min, max: f.max, step: f.step });
    if (value != null) inp.value = value;
    wrap.append(h('label', { for: id, text: f.label }), inp);
  }
  wrap.append(h('div', { class: 'why', text: f.why }));
  if (f.consentFor) {
    wrap.append(h('div', { class: 'check', style: { marginTop: '8px' } },
      h('input', { type: 'checkbox', id: id + '-consent', 'data-field': 'contact_consent' }),
      h('label', { for: id + '-consent', text: 'I consent to this contact number being stored.' })));
  }
  return wrap;
}

export function readFields(root) {
  const out = {};
  root.querySelectorAll('[data-field]').forEach((el) => {
    const k = el.dataset.field;
    if (el.type === 'radio') { if (el.checked) out[k] = el.value; return; }
    if (el.type === 'checkbox') { out[k] = el.checked; return; }
    out[k] = el.value;
  });
  if ('pregnant' in out) out.pregnant = out.pregnant === 'true' ? true : out.pregnant === 'false' ? false : null;
  for (const k of ['height_cm', 'weight_kg', 'sleep_hours']) if (k in out && out[k] === '') out[k] = null;
  return out;
}

export function renderGroup(root, group, profile, uid) {
  FIELDS[group].forEach((f) => root.append(fieldEl(f, profile?.[f.name], uid)));
  const cc = root.querySelector('[data-field=contact_consent]');
  if (cc) cc.checked = !!profile?.contact_consent;
}

export function consentBlock(consents, onChange) {
  const mk = (key, title, text, required) => {
    const id = 'c-' + key;
    const inp = h('input', { type: 'checkbox', id, 'data-consent': key });
    inp.checked = !!consents[key];
    inp.addEventListener('change', () => onChange(key, inp.checked));
    return h('div', { class: 'check' }, inp, h('label', { for: id }, h('strong', { text: title + (required ? ' (required to use the consultation)' : ' (optional)') }), h('br'), text));
  };
  return h('div', { class: 'stack', style: { '--gap': '12px' } },
    mk('health', 'Process my health information', 'I agree that the health details I enter and the symptoms I describe are processed to provide information in this app.', true),
    mk('ai_context', 'Personalise with my health profile', 'Share a de-identified summary (age band, long-term conditions, food preference) with the AI provider so explanations fit me. Never your name, contact, city or date of birth.', false),
    mk('research', 'Include my feedback in research statistics', 'My ratings and reported outcomes may be counted in anonymous research statistics. No raw messages are shared.', false));
}
