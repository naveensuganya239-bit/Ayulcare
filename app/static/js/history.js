import { $, api, h, riskBadge, fmtDate, modal, toast } from './core.js';

async function load() {
  const { items } = await api('/api/consultations');
  const ul = $('#items'); ul.replaceChildren();
  if (!items.length) { ul.append(h('li', { class: 'empty' }, 'Nothing here yet.')); return; }
  items.forEach((c) => ul.append(h('li', {},
    h('div', {}, h('a', { href: `/chat/${c.id}`, text: c.title }), h('div', { class: 'small muted', text: `${fmtDate(c.updated)} - ${c.messages} messages - ${c.language}` })),
    h('div', { class: 'row' }, riskBadge(c.risk), h('button', { class: 'btn btn-ghost btn-sm', type: 'button', 'aria-label': `Delete consultation ${c.title}`, text: 'Delete',
      onclick: async () => { if (await modal({ title: 'Delete this consultation?', body: 'The conversation and its follow-ups are removed permanently.', confirmText: 'Delete', danger: true })) { await api(`/api/consultations/${c.id}`, { method: 'DELETE' }); toast('Deleted'); load(); } } })))));
}
load();
