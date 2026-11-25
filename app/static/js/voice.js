// Voice helpers: local browser/server speech output and MediaRecorder -> server Whisper (input).
import { api } from './core.js';

const BCP = { en: 'en-IN', ta: 'ta-IN', te: 'te-IN', hi: 'hi-IN' };
let muted = localStorage.getItem('tts-muted') === '1';
let current = null; // {onend}

export const isMuted = () => muted;
export function setMuted(v) { muted = v; localStorage.setItem('tts-muted', v ? '1' : '0'); if (v) stopSpeaking(); }

const browserTtsSupported = () => 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
export const ttsSupported = () => typeof Audio !== 'undefined';

function loadVoices() {
  return new Promise((resolve) => {
    const v = speechSynthesis.getVoices();
    if (v.length) return resolve(v);
    const t = setTimeout(() => resolve(speechSynthesis.getVoices()), 1500);
    speechSynthesis.addEventListener('voiceschanged', () => { clearTimeout(t); resolve(speechSynthesis.getVoices()); }, { once: true });
  });
}

export async function pickVoice(lang) {
  if (!browserTtsSupported()) return null;
  const voices = await loadVoices();
  const want = BCP[lang] || lang;
  const matches = voices.filter((v) => {
    const voiceLang = v.lang.replace('_', '-').toLowerCase();
    return voiceLang === want.toLowerCase() || voiceLang.startsWith(lang);
  });

  const femaleName = /(female|woman|zira|samantha|victoria|karen|moira|tessa|veena|heera|sunhi|susan|linda|hazel|salli|joanna|kimberly|ivy|kendra|amy|emma|alice|natasha|nina|aria)/i;
  const maleName = /(\bmale\b|david|mark|ravi|guy|james|daniel|alex|george|thomas|prabhat|hemant)/i;

  return matches.find((v) => femaleName.test(v.name))
    || matches.find((v) => !maleName.test(v.name))
    || matches[0]
    || null;
}

function chunks(text, max = 180) {
  const parts = text.replace(/\s+/g, ' ').split(/(?<=[.!?।॥])\s+/);
  const out = [];
  let cur = '';
  for (const p of parts) {
    if ((cur + ' ' + p).length > max && cur) { out.push(cur.trim()); cur = p; } else cur += ' ' + p;
  }
  if (cur.trim()) out.push(cur.trim());
  return out.flatMap((c) => c.length > max * 1.6 ? c.match(new RegExp(`.{1,${max}}(\\s|$)`, 'g')) : [c]);
}

/** Speak text. Returns {ok, reason}. reason: 'unsupported' | 'muted' | 'no-voice'. */
export async function speak(text, lang, rate = 1, { onstart, onend, onerror } = {}) {
  if (muted) return { ok: false, reason: 'muted' };
  stopSpeaking();
  if (lang !== 'en') {
    const token = { audio: null, url: null };
    current = token;
    try {
      const blob = await api('/api/voice/synthesize', {
        method: 'POST',
        body: { text, language: lang },
        responseType: 'blob',
      });
      if (current !== token) return { ok: false, reason: 'cancelled' };

      token.url = URL.createObjectURL(blob);
      token.audio = new Audio(token.url);
      token.audio.playbackRate = rate;
      const finish = (error = false) => {
        if (current !== token) return;
        current = null;
        URL.revokeObjectURL(token.url);
        if (error) { onerror && onerror(); return; }
        onend && onend();
      };
      token.audio.onended = () => finish();
      token.audio.onerror = () => finish(true);
      await token.audio.play();
      if (current !== token) return { ok: false, reason: 'cancelled' };
      onstart && onstart();
      return { ok: true };
    } catch (error) {
      if (current === token) {
        current = null;
        if (token.url) URL.revokeObjectURL(token.url);
      }
      throw error;
    }
  }
  if (!browserTtsSupported()) return { ok: false, reason: 'unsupported' };
  const voice = await pickVoice(lang);
  if (!voice) return { ok: false, reason: 'no-voice' };
  const parts = chunks(text);
  let i = 0;
  const token = {};
  current = token;
  const next = () => {
    if (current !== token) return;
    if (i >= parts.length) { current = null; onend && onend(); return; }
    const u = new SpeechSynthesisUtterance(parts[i++]);
    u.voice = voice; u.lang = voice.lang; u.rate = rate; u.pitch = 1.08;
    u.onend = next; u.onerror = () => { if (current === token) { current = null; onend && onend(); } };
    speechSynthesis.speak(u);
  };
  onstart && onstart();
  next();
  return { ok: true };
}
export function pauseSpeaking() {
  if (current?.audio) current.audio.pause();
  else if (browserTtsSupported()) speechSynthesis.pause();
}
export function resumeSpeaking() {
  if (current?.audio) {
    current.audio.play().catch((error) => console.error('Could not resume spoken reply.', error));
  } else if (browserTtsSupported()) speechSynthesis.resume();
}
export function stopSpeaking() {
  const token = current;
  current = null;
  if (token?.audio) { token.audio.pause(); token.audio.currentTime = 0; }
  if (token?.url) URL.revokeObjectURL(token.url);
  if (browserTtsSupported()) speechSynthesis.cancel();
}
window.addEventListener('beforeunload', stopSpeaking);

// ------------------------------------------------------------------ recording
export class Recorder {
  constructor() { this.rec = null; this.chunks = []; this.stream = null; this.timer = null; }
  static supported() { return !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder); }

  static friendlyError(e) {
    switch (e?.name) {
      case 'NotAllowedError': case 'SecurityError': return 'Microphone permission was denied. Allow microphone access in your browser settings, or type your message instead.';
      case 'NotFoundError': return 'No microphone was found on this device. Please type your message.';
      case 'NotReadableError': return 'The microphone is busy or unavailable. Close other apps using it, or type your message.';
      default: return 'Voice recording is not available here. Please type your message.';
    }
  }

  async start(maxSeconds = 60, onAutoStop) {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'].find((t) => MediaRecorder.isTypeSupported(t)) || '';
    this.rec = new MediaRecorder(this.stream, type ? { mimeType: type } : undefined);
    this.chunks = [];
    this.rec.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
    this.rec.start();
    this.timer = setTimeout(() => { onAutoStop && onAutoStop(); }, maxSeconds * 1000);
  }

  stop() {
    return new Promise((resolve) => {
      clearTimeout(this.timer);
      if (!this.rec || this.rec.state === 'inactive') { this._release(); return resolve(null); }
      this.rec.onstop = () => { const blob = new Blob(this.chunks, { type: this.rec.mimeType || 'audio/webm' }); this._release(); resolve(blob); };
      this.rec.stop();
    });
  }
  cancel() { clearTimeout(this.timer); try { this.rec?.stop(); } catch { /* */ } this._release(); }
  _release() { this.stream?.getTracks().forEach((t) => t.stop()); this.stream = null; }
}

export async function transcribe(blob, lang) {
  const fd = new FormData();
  const ext = blob.type.includes('mp4') ? 'm4a' : blob.type.includes('ogg') ? 'ogg' : 'webm';
  fd.append('audio', blob, `speech.${ext}`);
  fd.append('lang', lang || 'auto');
  return api('/api/voice/transcribe', { method: 'POST', form: fd });
}

// ------------------------------------------------------------------ Browser STT (Web Speech API fallback)
// Used when server-side Whisper is unavailable or returns an engine error.
const BCP_LANG = { en: 'en-IN', ta: 'ta-IN', te: 'te-IN', hi: 'hi-IN' };

export const browserSttSupported = () =>
  !!(window.SpeechRecognition || window.webkitSpeechRecognition);

export class BrowserRecognizer {
  constructor() {
    this.r = null;
    this.gotResult = false;
    this.resolve = null;
    this.reject = null;
    this.timer = null;
  }

  static supported() {
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  }

  start(lang) {
    return new Promise((resolve, reject) => {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) return reject(new Error('Browser speech recognition is not supported.'));

      this.resolve = resolve;
      this.reject = reject;
      this.gotResult = false;

      const r = new SR();
      this.r = r;
      r.lang = BCP_LANG[lang] || BCP_LANG.en;
      r.interimResults = false;
      r.maxAlternatives = 1;
      r.continuous = false;

      r.onresult = (e) => {
        this.gotResult = true;
        const text = e.results[0]?.[0]?.transcript?.trim() || '';
        if (text) {
          this.resolve && this.resolve({ text, language: lang || 'en', source: 'browser' });
        } else {
          this.reject && this.reject(new Error('No speech detected. Please speak clearly.'));
        }
        this.resolve = null;
        this.reject = null;
      };

      r.onerror = (e) => {
        if (e.error === 'no-speech') {
          this.reject && this.reject(new Error('No speech was detected. Please try again.'));
        } else if (e.error === 'not-allowed') {
          this.reject && this.reject(new Error('Microphone permission denied. Allow microphone access in your browser settings.'));
        } else if (e.error === 'aborted') {
          this.reject && this.reject(new Error('Recording cancelled.'));
        } else {
          this.reject && this.reject(new Error(`Speech recognition error: ${e.error}`));
        }
        this.resolve = null;
        this.reject = null;
      };

      r.onend = () => {
        clearTimeout(this.timer);
        if (!this.gotResult && this.reject) {
          this.reject(new Error('No speech recognised. Please speak clearly and try again.'));
          this.resolve = null;
          this.reject = null;
        }
        this.r = null;
      };

      try {
        r.start();
        this.timer = setTimeout(() => { this.stop(); }, 30000);
      } catch (err) {
        this.reject && this.reject(err);
        this.resolve = null;
        this.reject = null;
      }
    });
  }

  stop() {
    clearTimeout(this.timer);
    try { this.r?.stop(); } catch { /* */ }
  }

  abort() {
    clearTimeout(this.timer);
    try { this.r?.abort(); } catch { /* */ }
  }
}
