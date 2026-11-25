import { $, api, h, icon, riskBadge, toast, LANG_LABEL, ApiError } from './core.js';
import { Recorder, BrowserRecognizer, transcribe, speak, stopSpeaking, pauseSpeaking, resumeSpeaking, isMuted, setMuted, ttsSupported } from './voice.js';

// Small UI string table for the chat chrome (safety-critical text itself comes from the server).
const UI = {
  emergency_title: { en: 'Seek medical help now', ta: 'உடனடியாக மருத்துவ உதவி பெறுங்கள்', te: 'వెంటనే వైద్య సహాయం పొందండి', hi: 'अभी चिकित्सा सहायता लें' },
  crisis_title: { en: 'You are not alone - reach out now', ta: 'நீங்கள் தனியாக இல்லை - இப்போதே உதவி பெறுங்கள்', te: 'మీరు ఒంటరి కాదు - ఇప్పుడే సహాయం పొందండి', hi: 'आप अकेले नहीं हैं - अभी मदद लें' },
  source: { en: 'Source', ta: 'ஆதாரம்', te: 'మూలం', hi: 'स्रोत' },
  record: { en: 'Record', ta: 'பதிவு', te: 'రికార్డు', hi: 'रिकॉर्ड' },
  matched: { en: 'Matches your', ta: 'உங்கள் அறிகுறியுடன் பொருத்தம்', te: 'మీ లక్షణానికి సరిపోలిక', hi: 'आपके लक्षण से मेल' },
  original_en: { en: 'Original text (English)', ta: 'மூல உரை (ஆங்கிலம்)', te: 'అసలు పాఠ్యం (ఇంగ్లీష్)', hi: 'मूल पाठ (अंग्रेज़ी)' },
  original_ta: { en: 'Original text (Tamil)', ta: 'மூல உரை (தமிழ்)', te: 'అసలు పాఠ్యం (తమిళం)', hi: 'मूल पाठ (तमिल)' },
  dataset_label: { en: 'Dataset label (not clinically validated)', ta: 'தரவுத்தொகுப்பு குறிப்பு (மருத்துவ சரிபார்ப்பு இல்லை)', te: 'డేటాసెట్ లేబుల్ (వైద్యపరంగా ధృవీకరించబడలేదు)', hi: 'डेटासेट लेबल (नैदानिक रूप से सत्यापित नहीं)' },
  precaution: { en: 'This record mentions a precaution. Read the full text carefully.', ta: 'இந்தப் பதிவில் ஒரு முன்னெச்சரிக்கை உள்ளது. முழு உரையையும் கவனமாகப் படியுங்கள்.', te: 'ఈ రికార్డులో ఒక జాగ్రత్త ఉంది. పూర్తి పాఠ్యాన్ని జాగ్రత్తగా చదవండి.', hi: 'इस रिकॉर्ड में एक सावधानी दी गई है। पूरा पाठ ध्यान से पढ़ें।' },
  listen: { en: 'Listen', ta: 'கேளுங்கள்', te: 'వినండి', hi: 'सुनें' },
  pause: { en: 'Pause', ta: 'இடைநிறுத்து', te: 'పాజ్', hi: 'रोकें' },
  stop: { en: 'Stop', ta: 'நிறுத்து', te: 'ఆపు', hi: 'बंद' },
  no_voice: { en: 'This device has no voice for this language. The answer is shown as text.', ta: 'இந்த சாதனத்தில் இந்த மொழிக்கான குரல் இல்லை. பதில் உரையாகக் காட்டப்படுகிறது.', te: 'ఈ పరికరంలో ఈ భాషకు వాయిస్ లేదు. సమాధానం టెక్స్ట్‌గా చూపబడుతోంది.', hi: 'इस डिवाइस पर इस भाषा की आवाज़ नहीं है। उत्तर टेक्स्ट में दिखाया गया है।' },
  voice_loading: { en: 'Preparing voice…', ta: 'குரலைத் தயாரிக்கிறது… முதல் முறையில் குரல் மாதிரி பதிவிறக்கப்படலாம்.', te: 'వాయిస్ సిద్ధం చేస్తోంది… మొదటిసారి వాయిస్ మోడల్ డౌన్‌లోడ్ కావచ్చు.', hi: 'आवाज़ तैयार हो रही है… पहली बार वॉइस मॉडल डाउनलोड हो सकता है।' },
  voice_error: { en: 'Could not prepare the on-device voice. Please retry.', ta: 'சாதனத்தில் குரலைத் தயாரிக்க முடியவில்லை. மீண்டும் முயற்சிக்கவும்.', te: 'ఈ పరికరంలో వాయిస్ సిద్ధం కాలేదు. మళ్లీ ప్రయత్నించండి.', hi: 'इस डिवाइस पर आवाज़ तैयार नहीं हो सकी। फिर कोशिश करें।' },
  call: { en: 'Call', ta: 'அழை', te: 'కాల్', hi: 'कॉल' },
  translation: { en: 'AI translation', ta: 'AI மொழிபெயர்ப்பு', te: 'AI అనువాదం', hi: 'AI अनुवाद' },
};
const u = (k, lang) => (UI[k][lang] || UI[k].en);

const log = $('#log'), input = $('#input'), sendBtn = $('#send'), micBtn = $('#mic'), langSel = $('#lang-sel');
let cid = $('#chat').dataset.cid ? Number($('#chat').dataset.cid) : null;
let busy = false, lastLang = 'en', autoSpeak = localStorage.getItem('tts-auto') === '1', autoSend = false;
let voiceAvail = false;

// -------------------------------------------------------------- rendering
function remedyText(r, lang) {
  if (lang === 'ta') return { text: r.remedy_ta || r.remedy_en, note: null };
  if (lang === 'en') return { text: r.remedy_en, note: null };
  if (r.translation) return { text: r.translation, note: `${u('translation', lang)}: ${r.translation_note || ''}` };
  return { text: r.remedy_en, note: null };
}

function remedyCard(r, lang) {
  const { text, note } = remedyText(r, lang);
  const main = h('div', { class: 'remedy-main' },
    h('div', { class: 'ref', text: r.ref }),
    h('div', { class: 'name', text: lang === 'ta' && r.problem_ta ? r.problem_ta : r.problem_en }),
    h('div', { class: 'text', lang: lang === 'te' || lang === 'hi' ? (r.translation ? lang : 'en') : lang, text }),
    note ? h('div', { class: 'small muted', text: note }) : null,
    r.matched_labels?.length ? h('div', { class: 'tags' }, h('span', { class: 'small muted', text: u('matched', lang) + ':' }), r.matched_labels.map((m) => h('span', { class: 'tag', text: m }))) : null,
    r.precautions_in_text?.length ? h('div', { class: 'alert alert-warn small', style: { marginTop: '8px' }, text: u('precaution', lang) }) : null,
    h('details', { class: 'orig' }, h('summary', { text: u('original_en', lang) }), h('p', { lang: 'en', text: r.remedy_en })),
    r.remedy_ta ? h('details', { class: 'orig' }, h('summary', { text: u('original_ta', lang) }), h('p', { lang: 'ta', text: r.remedy_ta })) : null,
    h('div', { class: 'tags' }, h('span', { class: 'tag', text: `${u('dataset_label', lang)}: ${r.dataset_risk ?? '-'}` })));
  const cite = h('div', { class: 'cite' }, icon('book', 18),
    h('div', {}, h('strong', { text: u('source', lang) + ': ' }), r.author, ' - ', h('em', { text: r.book }), h('br'), h('span', { text: `${u('record', lang)} #${r.record_id}` })));
  return h('div', { class: 'remedy' }, main, cite);
}

function externalBlock(ex, lang) {
  return h('div', { class: 'external' }, h('div', { class: 'ext-label', text: ex.label }),
    ex.summary ? h('p', { text: ex.summary }) : null,
    h('ul', { class: 'list' }, ex.results.map((r) => h('li', {}, h('div', {},
      h('a', { href: r.url, target: '_blank', rel: 'noopener noreferrer', text: r.title }), h('div', { class: 'small muted', text: `${r.source}${r.date ? ' - ' + r.date : ''}` }), h('div', { class: 'small', text: r.snippet }))))));
}

function speechText(p, text, lang) {
  if (!p) return text;
  if (p.type === 'emergency') return [p.text, p.extra].filter(Boolean).join(' ');
  if (p.type === 'assessment') {
    const parts = [p.notice, p.narrative];
    (p.remedies || []).forEach((r) => {
      const { text: t } = remedyText(r, lang);
      if (lang === 'en' || lang === 'ta' || r.translation) parts.push(`${lang === 'ta' && r.problem_ta ? r.problem_ta : r.problem_en}. ${t}. ${u('source', lang)}: ${r.author}, ${r.book}.`);
    });
    parts.push(p.care_note, p.no_match_text, p.gap_text, p.followup_text);
    return parts.filter(Boolean).join(' ');
  }
  return p.text || text;
}

function audioRow(getText, lang) {
  if (!ttsSupported()) return null;
  const play = h('button', { class: 'icon-btn', type: 'button', 'aria-label': u('listen', lang), title: u('listen', lang) }, icon('speaker', 16));
  const pause = h('button', { class: 'icon-btn hidden', type: 'button', 'aria-label': u('pause', lang), title: u('pause', lang) }, icon('pause', 16));
  const stop = h('button', { class: 'icon-btn hidden', type: 'button', 'aria-label': u('stop', lang), title: u('stop', lang) }, icon('stop', 16));
  const note = h('span', { class: 'small muted' });
  let paused = false;
  const reset = () => { play.classList.remove('hidden'); pause.classList.add('hidden'); stop.classList.add('hidden'); paused = false; };
  const start = async () => {
    if (isMuted()) { toast('Spoken replies are muted. Unmute to listen.'); return; }
    note.textContent = lang === 'en' ? '' : u('voice_loading', lang);
    try {
      const r = await speak(getText(), lang, Number($('#rate').value), {
        onstart: () => { note.textContent = ''; play.classList.add('hidden'); pause.classList.remove('hidden'); stop.classList.remove('hidden'); },
        onend: reset,
        onerror: () => { reset(); note.textContent = u('voice_error', lang); },
      });
      if (!r.ok) { reset(); if (r.reason === 'no-voice') note.textContent = u('no_voice', lang); }
    } catch {
      reset();
      note.textContent = u('voice_error', lang);
    }
  };
  play.onclick = start;
  pause.onclick = () => { paused ? resumeSpeaking() : pauseSpeaking(); paused = !paused; pause.setAttribute('aria-label', paused ? u('listen', lang) : u('pause', lang)); };
  stop.onclick = () => { stopSpeaking(); reset(); };
  const row = h('div', { class: 'audio-row' }, play, pause, stop, note);
  row._start = start;
  return row;
}

function renderUser(m) {
  const body = h('div', { class: 'msg-body' }, m.text, m.mode === 'voice' ? h('div', { class: 'meta', text: 'voice message' }) : null);
  return h('div', { class: 'msg user' }, body);
}

function renderBot(m, lang, { interactive = true } = {}) {
  const p = m.payload, body = h('div', { class: 'msg-body', lang });
  if (p?.type === 'emergency') {
    const crisis = p.category === 'crisis';
    const box = h('div', { class: 'alert-emergency', role: 'alert' },
      h('strong', {}, icon('warn', 20), crisis ? u('crisis_title', lang) : u('emergency_title', lang)),
      h('p', { text: p.text }), p.extra ? h('p', { text: p.extra }) : null,
      h('div', {}, crisis ? h('a', { class: 'btn btn-danger call', href: 'tel:14416', text: `${u('call', lang)} Tele-MANAS 14416` }) : null,
        h('a', { class: 'btn btn-danger call', href: 'tel:112', text: `${u('call', lang)} 112` }),
        h('a', { class: 'btn btn-ghost call', href: 'tel:108', text: `${u('call', lang)} 108` })));
    body.append(riskBadge('high'), box);
  } else if (p?.type === 'assessment') {
    body.append(h('div', { style: { marginBottom: '10px' } }, riskBadge(p.risk.level)), h('p', { text: p.notice }));
    if (p.narrative) body.append(h('p', { text: p.narrative }));
    if (p.care_note) body.append(h('p', { class: 'muted', text: p.care_note }));
    if (p.risk.level === 'medium' && p.risk.reasons?.length) body.append(h('ul', { class: 'reasons' }, p.risk.reasons.map((r) => h('li', { text: r }))));
    (p.remedies || []).forEach((r) => body.append(remedyCard(r, lang)));
    if (p.external) body.append(externalBlock(p.external, lang));
    if (p.no_match_text) body.append(h('div', { class: 'alert alert-info', text: p.no_match_text }));
    if (p.gap_text) body.append(h('p', { class: 'small muted', style: { marginTop: '10px' }, text: p.gap_text }));
    if (p.retrieval_note) body.append(h('p', { class: 'small muted', text: p.retrieval_note }));
    if (p.followup_text) body.append(h('p', { class: 'small', text: p.followup_text }));
    body.append(h('p', { class: 'small muted', style: { marginTop: '10px' }, text: p.disclaimer }));
  } else if (p?.type === 'followup') {
    body.append(h('p', { text: p.text }));
    if (p.quick_replies?.length) {
      const q = h('div', { class: 'quick', role: 'group', 'aria-label': 'Quick replies' });
      p.quick_replies.forEach((r) => q.append(h('button', { class: 'chip', type: 'button', disabled: !interactive, text: r.label,
        onclick: () => { $$q(q).forEach((b) => (b.disabled = true)); send(r.value, r.label); } })));
      body.append(q);
    }
  } else {
    body.append(h('p', { text: m.text }));
  }
  const row = audioRow(() => speechText(p, m.text, lang), lang);
  if (row) body.append(row);
  const el = h('div', { class: 'msg bot' }, h('div', { class: 'avatar' }, icon('leaf', 20)), body);
  el._audio = row;
  return el;
}
const $$q = (q) => [...q.querySelectorAll('button')];

function add(el) { log.append(el); log.scrollTop = log.scrollHeight; return el; }
function typing() { return add(h('div', { class: 'msg bot', id: 'typing' }, h('div', { class: 'avatar' }, icon('leaf', 20)), h('div', { class: 'msg-body' }, h('span', { class: 'typing', 'aria-label': 'Assistant is typing' }, h('i'), h('i'), h('i'))))); }

function updateLangIndicator(lang, manual) {
  lastLang = lang;
  $('#lang-ind span').textContent = manual && manual !== 'auto' ? `Language: ${LANG_LABEL[lang]}` : `Language: ${LANG_LABEL[lang]} (auto-detected)`;
  document.documentElement.lang = lang;
}

// ----------------------------------------------------------------- sending
async function ensureConsult() {
  if (cid) return cid;
  const r = await api('/api/chat/start', { method: 'POST' });
  cid = r.id; history.replaceState(null, '', `/chat/${cid}`);
  return cid;
}

async function send(text, display, mode = 'text') {
  text = (text || '').trim();
  if (!text || busy) return;
  busy = true; sendBtn.disabled = true;
  stopSpeaking();
  add(renderUser({ text: display || text, mode }));
  input.value = ''; autosize();
  const t = typing();
  try {
    await ensureConsult();
    const r = await api(`/api/chat/${cid}/message`, { method: 'POST', body: { text, lang: langSel.value, input_mode: mode } });
    t.remove();
    updateLangIndicator(r.language, langSel.value);
    r.replies.forEach((rep) => {
      const el = add(renderBot(rep, r.language));
      if (autoSpeak && !isMuted() && el._audio) el._audio._start();
    });
  } catch (x) {
    t.remove();
    add(h('div', { class: 'msg bot' }, h('div', { class: 'avatar' }, icon('warn', 20)), h('div', { class: 'msg-body' }, h('p', { text: x.message || 'Something went wrong.' }))));
  } finally { busy = false; sendBtn.disabled = false; input.focus(); }
}

function autosize() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 140) + 'px'; }
input.addEventListener('input', autosize);
input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input.value); } });
sendBtn.addEventListener('click', () => send(input.value));

// ------------------------------------------------------------------- voice
const vmsg = $('#voice-msg');
const say = (t) => { vmsg.textContent = t; vmsg.classList.toggle('hidden', !t); };
const rec = new Recorder();
const browserRec = new BrowserRecognizer();
let recording = false;
let sttBackend = 'server'; // 'server' | 'browser'

/** Codes returned by the server that mean "fall back to browser STT". */
const STT_FALLBACK_CODES = new Set(['stt_unavailable', 'stt_engine_error', 'stt_error']);

async function toggleMic() {
  if (busy) return;

  if (recording) {
    // User wants to STOP recording
    recording = false;
    micBtn.classList.remove('rec');
    micBtn.setAttribute('aria-label', 'Start voice recording');
    micBtn.firstElementChild.replaceWith(icon('mic', 20));

    if (sttBackend === 'browser') {
      browserRec.stop();
      return;
    }

    const blob = await rec.stop();
    if (!blob || blob.size < 800) {
      say('The recording was too short. Please try again.');
      return;
    }
    say('Transcribing…');
    micBtn.disabled = true;
    try {
      const r = await transcribe(blob, langSel.value);
      say(`Heard (${LANG_LABEL[r.language] || r.language}). ${autoSend ? '' : 'Check the text, edit if needed, then send.'}`);
      if (autoSend) {
        await send(r.text, null, 'voice');
      } else {
        input.value = r.text;
        autosize();
        input.focus();
      }
    } catch (x) {
      const code = x?.data?.code || x?.code || '';
      if (STT_FALLBACK_CODES.has(code) && BrowserRecognizer.supported()) {
        sttBackend = 'browser';
        micBtn.title = 'Voice input (Browser speech recognition)';
        say('Server voice engine error — switched to browser voice recognition. Tap mic to speak.');
      } else {
        say(x.message || 'Could not transcribe. Please try again or type your message.');
      }
    } finally {
      micBtn.disabled = false;
    }
    return;
  }

  // User wants to START recording
  if (sttBackend === 'browser') {
    recording = true;
    micBtn.classList.add('rec');
    micBtn.setAttribute('aria-label', 'Stop recording');
    micBtn.firstElementChild.replaceWith(icon('stop', 20));
    say('Listening… speak now. Tap the button or stop speaking when done.');
    stopSpeaking();
    try {
      const r = await browserRec.start(langSel.value === 'auto' ? 'en' : langSel.value);
      say(`Heard. ${autoSend ? '' : 'Check the text, edit if needed, then send.'}`);
      if (autoSend) {
        await send(r.text, null, 'voice');
      } else {
        input.value = r.text;
        autosize();
        input.focus();
      }
    } catch (e) {
      say(e.message || 'Could not recognise speech. Please try again or type.');
    } finally {
      recording = false;
      micBtn.classList.remove('rec');
      micBtn.setAttribute('aria-label', 'Start voice recording');
      micBtn.firstElementChild.replaceWith(icon('mic', 20));
    }
    return;
  }

  // Server STT via MediaRecorder
  try {
    await rec.start(60, () => { if (recording) toggleMic(); });
    recording = true;
    micBtn.classList.add('rec');
    micBtn.setAttribute('aria-label', 'Stop recording');
    micBtn.firstElementChild.replaceWith(icon('stop', 20));
    say('Listening… tap the button again to stop.');
    stopSpeaking();
  } catch (e) {
    if (BrowserRecognizer.supported()) {
      sttBackend = 'browser';
      say('Microphone recording error — switched to browser speech recognition. Tap mic to try again.');
    } else {
      say(Recorder.friendlyError(e));
    }
  }
}

micBtn.addEventListener('click', toggleMic);

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && recording) {
    if (sttBackend === 'browser') {
      browserRec.abort();
    } else {
      rec.cancel();
    }
    recording = false;
    micBtn.classList.remove('rec');
    micBtn.firstElementChild.replaceWith(icon('mic', 20));
    say('Recording cancelled.');
  }
});

async function initVoice() {
  const mediaSupported = Recorder.supported();
  const browserSupported = BrowserRecognizer.supported();

  if (!mediaSupported && !browserSupported) {
    micBtn.disabled = true;
    micBtn.title = 'Voice recording is not supported in this browser';
    say('Voice input is not supported in this browser. You can type instead.');
    return;
  }

  try {
    voiceAvail = (await api('/api/voice/status')).available;
  } catch {
    voiceAvail = false;
  }

  if (voiceAvail && mediaSupported) {
    sttBackend = 'server';
    micBtn.disabled = false;
    micBtn.title = 'Voice input (Whisper AI)';
  } else if (browserSupported) {
    sttBackend = 'browser';
    voiceAvail = true;
    micBtn.disabled = false;
    micBtn.title = 'Voice input (Browser speech recognition)';
  } else {
    micBtn.disabled = true;
    micBtn.title = 'Voice input is not enabled on this server';
    say('Voice input is not enabled on this server. You can type instead.');
  }
}

// ---------------------------------------------------------------- controls
const muteBtn = $('#mute'), autoBtn = $('#autospeak');
function paintControls() {
  muteBtn.setAttribute('aria-pressed', String(isMuted()));
  muteBtn.replaceChildren(icon(isMuted() ? 'mute' : 'speaker', 20));
  muteBtn.setAttribute('aria-label', isMuted() ? 'Unmute spoken replies' : 'Mute spoken replies');
  autoBtn.setAttribute('aria-pressed', String(autoSpeak));
  autoBtn.textContent = `Read replies aloud: ${autoSpeak ? 'on' : 'off'}`;
  if (!ttsSupported()) { muteBtn.classList.add('hidden'); autoBtn.classList.add('hidden'); }
}
muteBtn.addEventListener('click', () => { setMuted(!isMuted()); paintControls(); });
autoBtn.addEventListener('click', () => { autoSpeak = !autoSpeak; localStorage.setItem('tts-auto', autoSpeak ? '1' : '0'); paintControls(); });
langSel.addEventListener('change', () => { if (langSel.value !== 'auto') updateLangIndicator(langSel.value, langSel.value); else $('#lang-ind span').textContent = 'Language: automatic'; });

// -------------------------------------------------------------------- init
async function init() {
  paintControls(); initVoice();
  if (cid) {
    try {
      const r = await api(`/api/chat/${cid}`);
      updateLangIndicator(r.consultation.language || 'en', 'auto');
      r.messages.forEach((m) => add(m.role === 'user' ? renderUser(m) : renderBot(m, r.consultation.language || 'en', { interactive: false })));
      if (!r.messages.length) add(renderBot({ text: r.greeting }, 'en'));
    } catch { location.href = '/chat'; }
  } else {
    add(renderBot({ text: 'Hello! Tell me what you are experiencing in your own words - for example, how long it has been going on and how it feels. You can write or speak in English, Tamil, Telugu or Hindi. I share traditional Ayurvedic book information, not a diagnosis.' }, 'en'));
  }
  input.focus();
}
init();
