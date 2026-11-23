import { $, api, h, showError, clearError } from './core.js';
import { STEPS, renderGroup, readFields, consentBlock } from './profileform.js';

const form = $('#setup-form'), stepper = $('#stepper'), err = $('#err');
let step = 0, profile = {}, consents = {}, draft = {};

async function load() {
  const r = await api('/api/profile');
  profile = r.profile; consents = r.consents;
  if (profile.completed && consents.health) location.replace('/dashboard');
  render();
}

function renderStepper() {
  stepper.replaceChildren(...STEPS.map((s, i) => h('li', { class: i === step ? 'on' : i < step ? 'done' : '', 'aria-current': i === step ? 'step' : null, text: `${i + 1}. ${s.title}` })));
}

function render() {
  clearError(err); renderStepper(); form.replaceChildren();
  const id = STEPS[step].id;
  $('#back').classList.toggle('hidden', step === 0);
  $('#next').textContent = id === 'review' ? 'Finish and start' : 'Continue';
  if (id === 'consent') {
    form.append(h('h2', { text: 'Your consent' }), h('p', { class: 'muted', text: 'This app handles health information, so we ask first. You can change these choices at any time under Profile.' }),
      consentBlock(consents, (k, v) => { consents[k] = v; }));
  } else if (id === 'review') {
    form.append(h('h2', { text: 'All set' }), h('p', { class: 'muted', text: 'Your profile is saved. You can edit or delete it at any time from Profile. Remember: this app gives information only and is not a substitute for a doctor.' }),
      h('div', { class: 'alert alert-warn', text: 'In an emergency call 112 (ambulance 108) or go to the nearest hospital.' }));
  } else {
    form.append(h('h2', { text: STEPS[step].title === 'Basics' ? 'About you' : STEPS[step].title === 'Health' ? 'Health background' : 'Daily life' }),
      h('p', { class: 'muted', text: 'Every field is optional. Skip anything you prefer not to share.' }));
    renderGroup(form, id, { ...profile, ...draft }, 'p');
  }
}

async function next() {
  clearError(err);
  const id = STEPS[step].id;
  try {
    if (id === 'consent') {
      if (!consents.health) return showError(err, 'Please give consent to process health information to continue, or leave the app.');
      await api('/api/profile/consents', { method: 'POST', body: { health: !!consents.health, ai_context: !!consents.ai_context, research: !!consents.research } });
    } else if (id !== 'review') {
      const vals = readFields(form);
      Object.assign(draft, vals);
      const r = await api('/api/profile', { method: 'PUT', body: vals });
      profile = r.profile;
    } else {
      await api('/api/profile', { method: 'PUT', body: { completed: true } });
      location.href = '/dashboard'; return;
    }
    step++; render();
  } catch (x) { showError(err, x.message); }
}
$('#next').addEventListener('click', next);
$('#back').addEventListener('click', () => { if (step > 0) { step--; render(); } });
load();
