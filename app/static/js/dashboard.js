import { $, api, h, riskBadge, fmtDate } from './core.js';

(async () => {
  const d = await api('/api/dashboard');
  $('#hello').textContent = d.name ? `Welcome, ${d.name}` : 'Welcome';
  $('#s-total').textContent = d.total; $('#s-due').textContent = d.due_followups; $('#s-up').textContent = d.upcoming_followups;
  if (!d.consent_health || !d.profile_completed) {
    $('#nudge').append(h('div', { class: 'alert alert-info', style: { marginBottom: '18px' } }, 'Finish your health profile and consent to start consultations. ', h('a', { href: '/setup', text: 'Continue setup' })));
  } else if (d.due_followups) {
    $('#nudge').append(h('div', { class: 'alert alert-warn', style: { marginBottom: '18px' } }, `You have ${d.due_followups} check-in${d.due_followups > 1 ? 's' : ''} waiting. `, h('a', { href: '/feedback', text: 'Tell us how you are doing' })));
  }
  const ul = $('#recent');
  if (!d.recent.length) ul.append(h('li', { class: 'empty' }, 'No consultations yet. Start one whenever you need.'));
  d.recent.forEach((c) => ul.append(h('li', {}, h('div', {}, h('a', { href: `/chat/${c.id}`, text: c.title }), h('div', { class: 'small muted', text: fmtDate(c.updated) })), riskBadge(c.risk))));
})();
