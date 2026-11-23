import { $, api, h } from './core.js';

const pct = (v) => (v == null ? 'n/a' : v + '%');
const kv = (rows) => h('table', { class: 'data' }, h('tbody', {}, rows.map(([k, v]) => h('tr', {}, h('th', { text: k }), h('td', { text: String(v ?? 'n/a') })))));

(async () => {
  const s = await api('/api/research/summary');
  $('#caveat').textContent = s.caveat;
  $('#sys').textContent = `Embedding: ${s.system.embedder || 'not loaded'} (${s.system.embedder_backend || '-'}) - records: ${s.system.records ?? '-'} - Gemini: ${s.system.gemini ? 'on' : 'off'} - web fallback: ${s.system.web_search ? 'on' : 'off'}`;
  [['Consultations', s.consultations], ['Feedback submissions', s.feedback_total], ['In research scope (opted in)', s.feedback_in_research_scope]].forEach(([l, v]) =>
    $('#top').append(h('section', { class: 'card' }, h('div', { class: 'muted small', text: l }), h('div', { class: 'stat', text: v }))));
  const o = s.outcomes;
  [['Improved', o.improved, o.improved_pct], ['Partially improved', o.partial, o.partial_pct], ['No change', o.no_change, o.no_change_pct], ['Worse', o.worse, o.worse_pct]].forEach(([l, n, p]) =>
    $('#outcomes').append(h('div', {}, h('div', { class: 'row', style: { justifyContent: 'space-between' } }, h('span', { text: l }), h('strong', { text: `${pct(p)} (${n})` })), h('div', { class: 'bar' }, h('i', { style: { width: (p || 0) + '%' } })))));
  $('#outcomes').append(h('p', { class: 'small muted', text: `Based on ${o.n} self-reported outcomes. These are user reports, not medical accuracy or proven effectiveness.` }));
  const sat = s.satisfaction;
  $('#sat').append(h('div', { class: 'stat', text: sat.mean ?? 'n/a' }), h('div', { class: 'small muted', text: `${sat.n} ratings` }),
    ...Object.entries(sat.distribution).reverse().map(([k, v]) => h('div', { class: 'row' }, h('span', { text: k + ' \u2605', style: { width: '40px' } }), h('div', { class: 'bar grow' }, h('i', { style: { width: (sat.n ? (100 * v / sat.n) : 0) + '%' } })), h('span', { text: v }))));
  const r = s.retrieval;
  $('#ret').append(kv([['Logged retrievals', r.logged_retrievals], ['Proposed-mode retrievals', r.proposed_mode], ['No-match rate', pct(r.no_match_pct)], ['Web fallback rate', pct(r.web_fallback_pct)], ['Mean top rank score', r.mean_top_rank_score], ['LLM explanations rejected by guard', r.explanations_rejected_by_guard],
    ['By language', JSON.stringify(r.by_language)], ['By risk', JSON.stringify(r.by_risk)]]));
  const e = await api('/api/research/eval-reports');
  const dq = e.data_quality;
  if (dq) $('#dq').append(kv([['Records', dq.n_records], ['Header columns', dq.n_header_columns], ['Risk fallback records', dq.risk_status_counts.fallback ?? 0], ['Risk conflicts', dq.risk_status_counts.conflict ?? 0], ['Unique problems', dq.unique_problems], ['Books', dq.unique_books]]));
  else $('#dq').append(h('p', { class: 'muted small', text: 'Run: flask --app wsgi data-report' }));
  const host = $('#reports');
  if (!e.reports.length) host.append(h('p', { class: 'muted', text: 'No evaluation report yet.' }));
  e.reports.forEach(({ file, report }) => {
    const ks = report.meta.ks;
    host.append(h('h4', { text: file }), report.meta.warning ? h('div', { class: 'alert alert-warn small', text: report.meta.warning }) : null,
      h('div', { class: 'scroll-x' }, h('table', { class: 'data' },
        h('thead', {}, h('tr', {}, ['System', 'MRR', ...ks.flatMap((k) => [`P@${k}`, `R@${k}`]), 'No-match'].map((t) => h('th', { text: t })))),
        h('tbody', {}, Object.values(report.results).map((x) => h('tr', {}, [x.label, x.summary.mrr, ...ks.flatMap((k) => [x.summary[`precision@${k}`], x.summary[`recall@${k}`]]), x.summary.no_match_rate].map((t) => h('td', { text: String(t) }))))))));
  });
})();
