// Voice helpers: browser Speech Synthesis (output) and MediaRecorder -> server Whisper (input).
import { api } from './core.js';

const BCP = { en: 'en-IN', ta: 'ta-IN', te: 'te-IN', hi: 'hi-IN' };
let muted = localStorage.getItem('tts-muted') === '1';
let current = null; // {onend}

export const isMuted = () => muted;
export function setMuted(v) { muted = v; localStorage.setItem('tts-muted', v ? '1' : '0'); if (v) stopSpeaking(); }

export const ttsSupported = () => 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;

function loadVoices() {
  return new Promise((resolve) => {
    const v = speechSynthesis.getVoices();
    if (v.length) return resolve(v);
    const t = setTimeout(() => resolve(speechSynthesis.getVoices()), 1500);
    speechSynthesis.addEventListener('voiceschanged', () => { clearTimeout(t); resolve(speechSynthesis.getVoices()); }, { once: true });
  });
}

export async function pickVoice(lang) {
  if (!ttsSupported()) return null;
  const voices = await loadVoices();
  const want = BCP[lang] || lang;
  return voices.find((v) => v.lang.replace('_', '-').toLowerCase() === want.toLowerCase())
    || voices.find((v) => v.lang.toLowerCase().startsWith(lang)) || null;
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
export async function speak(text, lang, rate = 1, { onstart, onend } = {}) {
  if (!ttsSupported()) return { ok: false, reason: 'unsupported' };
  if (muted) return { ok: false, reason: 'muted' };
  const voice = await pickVoice(lang);
  if (!voice) return { ok: false, reason: 'no-voice' };
  stopSpeaking();
  const parts = chunks(text);
  let i = 0;
  const token = {};
  current = token;
  const next = () => {
    if (current !== token) return;
    if (i >= parts.length) { current = null; onend && onend(); return; }
    const u = new SpeechSynthesisUtterance(parts[i++]);
    u.voice = voice; u.lang = voice.lang; u.rate = rate;
    u.onend = next; u.onerror = () => { if (current === token) { current = null; onend && onend(); } };
    speechSynthesis.speak(u);
  };
  onstart && onstart();
  next();
  return { ok: true };
}
export function pauseSpeaking() { if (ttsSupported()) speechSynthesis.pause(); }
export function resumeSpeaking() { if (ttsSupported()) speechSynthesis.resume(); }
export function stopSpeaking() { current = null; if (ttsSupported()) speechSynthesis.cancel(); }
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
