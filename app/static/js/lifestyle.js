import { $, api, h, ApiError } from './core.js';

(async () => {
  try {
    const d = await api('/api/lifestyle');
    $('#disc').textContent = d.disclaimer;
    const host = $('#cards');
    d.cards.forEach((c) => host.append(h('article', { class: 'card' }, h('h3', { text: c.title }), h('p', { text: c.body }),
      c.note ? h('div', { class: 'alert alert-info small', text: c.note }) : null,
      h('p', { class: 'small muted', style: { marginTop: '12px' } }, 'Basis: ' + c.basis + (c.link ? ' - ' : ''), c.link ? h('a', { href: c.link, target: '_blank', rel: 'noopener noreferrer', text: 'read more' }) : null))));
    if (!d.cards.length) host.append(h('p', { class: 'muted', text: 'Add details to your profile to see lifestyle information.' }));
  } catch (x) {
    $('#disc').textContent = x.status === 403 ? 'Please give consent in Profile to see lifestyle information.' : x.message;
  }
})();
