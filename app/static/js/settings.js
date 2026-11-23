import { $, api, h, modal, showError, clearError, toast } from './core.js';
import { renderGroup, readFields, consentBlock } from './profileform.js';

const err = $('#err');
(async () => {
  const r = await api('/api/profile');
  const consents = { ...r.consents };
  $('#consents').append(consentBlock(consents, async (k, v) => {
    consents[k] = v;
    try { await api('/api/profile/consents', { method: 'POST', body: { [k]: v } }); toast('Consent updated'); } catch (x) { showError(err, x.message); }
  }));
  const form = $('#profile-form');
  ['basics', 'health', 'lifestyle'].forEach((g) => { form.append(h('h4', { text: { basics: 'About you', health: 'Health background', lifestyle: 'Daily life' }[g], style: { marginTop: '16px' } })); renderGroup(form, g, r.profile, 'p' + g); });
  $('#save').addEventListener('click', async () => {
    clearError(err);
    try { await api('/api/profile', { method: 'PUT', body: { ...readFields(form), completed: true } }); toast('Profile saved'); } catch (x) { showError(err, x.message); }
  });
  $('#chpw').addEventListener('click', async () => {
    const v = await modal({ title: 'Change password', confirmText: 'Change', fields: [{ name: 'current_password', label: 'Current password', type: 'password', autocomplete: 'current-password' }, { name: 'new_password', label: 'New password (10+ characters)', type: 'password', autocomplete: 'new-password' }] });
    if (!v) return;
    try { await api('/api/auth/change-password', { method: 'POST', body: v }); toast('Password changed'); } catch (x) { toast(x.message, 'error'); }
  });
  $('#delete').addEventListener('click', async () => {
    const v = await modal({ title: 'Delete account and all data?', body: 'This permanently deletes your profile, consultations, follow-ups and feedback. It cannot be undone.', confirmText: 'Delete everything', danger: true, fields: [{ name: 'password', label: 'Confirm your password', type: 'password', autocomplete: 'current-password' }] });
    if (!v) return;
    try { await api('/api/account', { method: 'DELETE', body: { password: v.password } }); location.href = '/'; } catch (x) { toast(x.message, 'error'); }
  });
})();
