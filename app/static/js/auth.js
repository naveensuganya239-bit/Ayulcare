import { $, api, showError, clearError } from './core.js';

const err = $('#err');
const rf = $('#register-form'), lf = $('#login-form');

function strength(pw) {
  let s = 0;
  if (pw.length >= 10) s++; if (pw.length >= 14) s++;
  if (/[A-Za-z]/.test(pw) && /\d/.test(pw)) s++;
  if (/[^A-Za-z0-9]/.test(pw) && pw.length >= 10) s++;
  return s;
}
if (rf) {
  $('#pw').addEventListener('input', (e) => {
    const s = strength(e.target.value), bar = $('#pwbar');
    bar.style.width = (s * 25) + '%';
    bar.style.background = s < 2 ? 'var(--risk-high)' : s < 3 ? 'var(--gold-500)' : 'var(--risk-low)';
  });
  rf.addEventListener('submit', async (e) => {
    e.preventDefault(); clearError(err);
    try {
      await api('/api/auth/register', { method: 'POST', body: { email: $('#email').value, password: $('#pw').value, consent_terms: $('#terms').checked } });
      location.href = '/setup';
    } catch (x) { showError(err, x.message); }
  });
}
if (lf) {
  lf.addEventListener('submit', async (e) => {
    e.preventDefault(); clearError(err);
    try {
      const r = await api('/api/auth/login', { method: 'POST', body: { email: $('#email').value, password: $('#pw').value } });
      const next = new URLSearchParams(location.search).get('next');
      location.href = !r.user.consent_health || !r.user.profile_completed ? '/setup' : (next && next.startsWith('/') && !next.startsWith('//') ? next : '/dashboard');
    } catch (x) { showError(err, x.message); }
  });
}
