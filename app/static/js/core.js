// Shared helpers: API client with CSRF, DOM builder, toasts, icons, modal.
export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];

let csrf = document.querySelector('meta[name=csrf]')?.content || '';

export class ApiError extends Error {
  constructor(message, status, data) { super(message); this.status = status; this.data = data; }
}

export async function api(path, { method = 'GET', body, form, responseType } = {}) {
  const headers = { 'X-CSRF-Token': csrf };
  const opts = { method, headers, credentials: 'same-origin' };
  if (form) opts.body = form;
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  let res;
  try { res = await fetch(path, opts); }
  catch { throw new ApiError('Network problem. Please check your connection and try again.', 0); }
  let data = null;
  if (responseType !== 'blob' || !res.ok) {
    try { data = await res.json(); } catch { /* non-JSON */ }
  }
  if (data && data.csrf) csrf = data.csrf;
  if (!res.ok) {
    if (res.status === 401 && !location.pathname.startsWith('/login') && !location.pathname.startsWith('/register')) {
      location.href = '/login?next=' + encodeURIComponent(location.pathname);
    }
    throw new ApiError((data && data.error) || 'Something went wrong.', res.status, data);
  }
  if (responseType === 'blob') return res.blob();
  return data;
}

export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'style' && typeof v === 'object') { for (const [sk, sv] of Object.entries(v)) { if (sk.startsWith('--')) el.style.setProperty(sk, sv); else el.style[sk] = sv; } }
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

export function icon(name, size = 18) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', size); svg.setAttribute('height', size); svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', '#i-' + name);
  svg.append(use);
  return svg;
}

export function toast(msg, type = 'info') {
  const host = $('#toasts');
  if (!host) return;
  const t = h('div', { class: 'toast ' + (type === 'error' ? 'error' : ''), text: msg });
  host.append(t);
  setTimeout(() => t.remove(), 4500);
}

export function showError(el, msg) {
  if (!el) return toast(msg, 'error');
  el.textContent = msg; el.classList.remove('hidden');
  el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}
export const clearError = (el) => el && el.classList.add('hidden');

export function utc(iso) { return new Date(iso.endsWith('Z') ? iso : iso + 'Z'); }
export function fmtDate(iso) {
  return utc(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' });
}
export function relTime(iso) {
  const ms = utc(iso) - Date.now(), abs = Math.abs(ms), mins = Math.round(abs / 60000);
  const txt = mins < 60 ? `${mins} min` : mins < 2880 ? `${Math.round(mins / 60)} h` : `${Math.round(mins / 1440)} days`;
  return ms < 0 ? `${txt} ago` : `in ${txt}`;
}

export function riskBadge(level) {
  const L = { low: 'Low risk', medium: 'Medium risk', high: 'High risk' }[level];
  if (!L) return null;
  const ic = level === 'low' ? 'check' : 'warn';
  return h('span', { class: `risk risk-${level}` }, icon(ic, 16), L);
}

export function modal({ title, body, confirmText = 'Confirm', danger = false, fields = [] }) {
  return new Promise((resolve) => {
    const inputs = {};
    const back = h('div', { class: 'modal-back', role: 'dialog', 'aria-modal': 'true', 'aria-label': title });
    const box = h('div', { class: 'modal' }, h('h3', { text: title }), body ? h('p', { class: 'muted', text: body }) : null);
    for (const f of fields) {
      const id = 'm-' + f.name;
      inputs[f.name] = h('input', { id, type: f.type || 'text', autocomplete: f.autocomplete || 'off' });
      box.append(h('div', { class: 'field' }, h('label', { for: id, text: f.label }), inputs[f.name]));
    }
    const done = (ok) => { back.remove(); document.removeEventListener('keydown', onKey); resolve(ok ? Object.fromEntries(Object.entries(inputs).map(([k, v]) => [k, v.value])) : null); };
    const onKey = (e) => { if (e.key === 'Escape') done(false); };
    box.append(h('div', { class: 'row', style: { justifyContent: 'flex-end', marginTop: '8px' } },
      h('button', { class: 'btn btn-ghost', type: 'button', onclick: () => done(false), text: 'Cancel' }),
      h('button', { class: 'btn ' + (danger ? 'btn-danger' : 'btn-primary'), type: 'button', onclick: () => done(true), text: confirmText })));
    back.append(box); document.body.append(back);
    document.addEventListener('keydown', onKey);
    (Object.values(inputs)[0] || box.querySelector('button')).focus();
  });
}

export async function logout() {
  try { await api('/api/auth/logout', { method: 'POST' }); } catch { /* ignore */ }
  location.href = '/';
}
document.getElementById('logout')?.addEventListener('click', (e) => { e.preventDefault(); logout(); });

export const LANG_LABEL = { auto: 'Automatic', en: 'English', ta: 'தமிழ்', te: 'తెలుగు', hi: 'हिन्दी' };
