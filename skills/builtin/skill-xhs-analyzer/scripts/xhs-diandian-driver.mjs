#!/usr/bin/env node
// Asks Xiaohongshu's own AI (点点) for a summary of ONE note and prints the finished reply on stdout.
// Run only by redbook-guard.sh's `diandian` step, on Windows (node.exe from WSL) like xhs-cdp-cookies.mjs,
// because the login lives in the SOP project's scanning Chrome. The guard has already taken the lock, checked
// the tripped marker and the daily cap, and asked the cookie helper whether favsense and SOP are idle.
// This script never reads a cookie: the browser already holds the login.
//
// The workflow is FavSense's (skills/xhs-diandian-summarize-note): open the note page, use its 复制链接
// action, give that one link to https://www.xiaohongshu.com/ai_chat, send exactly `总结` once, wait for a NEW
// finished assistant message whose text has stayed the same for 2 s. The prompt, selectors and waits come from
// diandian-contract.json (a copy of FavSense's runtime/browser-contract.json). This is a port: it is tested
// against a stand-in browser (xhs-diandian-driver.test.mjs) and has not been run against the live site; the
// first live run is the owner's call.
//
// Exit codes (stderr carries one line saying why, never a link or a cookie):
//   0 reply printed on stdout   2 the page showed a safety signal ("safety-signal: <what>")   1 anything else
// XHS_DIANDIAN_TIME_SCALE shortens every wait of the contract (tests only).
import { readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const C = JSON.parse(readFileSync(join(HERE, 'diandian-contract.json'), 'utf8'));
const SCALE = Number(process.env.XHS_DIANDIAN_TIME_SCALE ?? 1);
const T = Object.fromEntries(Object.entries(C.timings_ms).map(([k, v]) => [k, v * SCALE]));
const S = C.selectors;
const SOP = process.env.XHS_SOP_ROOT ?? join(homedir(), 'Codex', 'SOP - 小红书');
const PORT_FILE = process.env.XHS_CDP_PORT_FILE ?? join(SOP, '.secrets', 'cdp-port.txt');
const SAFETY = /NeedVerify|captcha|验证码|300012|300031|访问频繁/i;
const NOTE_RE = /^https?:\/\/(www\.)?xiaohongshu\.com\/(discovery\/item|explore)\/[A-Za-z0-9_-]+/;

class Stop extends Error { constructor(code, msg) { super(msg); this.code = code; } }
const stop = (msg) => new Stop(1, msg);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const noteUrl = process.argv[2] ?? '';
if (!NOTE_RE.test(noteUrl)) { console.error('xhs-diandian-driver: the argument is not a note address.'); process.exit(1); }

// --- a minimal DevTools-protocol client ---------------------------------------------------
const port = Number.parseInt(existsSync(PORT_FILE) ? readFileSync(PORT_FILE, 'utf8').trim() : '', 10);
if (!(port >= 1 && port <= 65535)) { console.error('xhs-diandian-driver: no usable port; the scanning browser has never been started.'); process.exit(1); }

const http = async (path, init) => {
  const r = await fetch(`http://127.0.0.1:${port}${path}`, { ...init, signal: AbortSignal.timeout(5000) });
  if (!r.ok) throw stop(`browser answered HTTP ${r.status} for ${path.split('?')[0]}`);
  return r.json();
};

function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  const pending = new Map();
  let next = 0;
  const opened = new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve);
    ws.addEventListener('error', () => reject(stop('could not open the browser tab.')));
  });
  ws.addEventListener('message', (ev) => {
    const m = JSON.parse(String(ev.data));
    const p = pending.get(m.id);
    if (!p) return;
    pending.delete(m.id);
    clearTimeout(p.timer);
    m.error ? p.reject(stop(`browser refused ${p.method}: ${m.error.message}`)) : p.resolve(m.result);
  });
  const send = async (method, params = {}) => {
    await opened;
    return new Promise((resolve, reject) => {
      const id = ++next;
      const timer = setTimeout(() => { if (pending.delete(id)) reject(stop(`${method} timed out`)); }, 30000);
      pending.set(id, { resolve, reject, method, timer });
      ws.send(JSON.stringify({ id, method, params }));
    });
  };
  return { send, close: () => ws.close() };
}

let tab; let cdp;
const ev = async (expression) => {
  const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture: true });
  if (r.exceptionDetails) throw stop(`page script failed: ${r.exceptionDetails.exception?.description ?? r.exceptionDetails.text}`.slice(0, 200));
  return r.result.value;
};

// A safety signal anywhere on the page stops everything: the guard trips on the line this prints.
const checkSafety = async () => {
  const seen = await ev(`(() => {
    const flagged = document.querySelector('[class*="captcha" i], [id*="captcha" i], [class*="verify-modal" i]');
    return [location.href, document.title, flagged ? 'captcha element' : ''].join(' | ');
  })()`);
  const hit = SAFETY.exec(seen) ?? (seen.endsWith('captcha element') ? ['captcha'] : null);
  if (hit) throw new Stop(2, `safety-signal: ${hit[0]}`);
};

const waitFor = async (what, ms, probe) => {
  const until = Date.now() + ms;
  for (;;) {
    await checkSafety();
    const v = await probe();
    if (v) return v;
    if (Date.now() > until) throw stop(`timed out waiting for ${what}`);
    await sleep(T.worker_probe_interval);
  }
};

// The value `probe` returns must stay equal (as JSON) for `stableMs` before it counts.
const settled = async (what, ms, stableMs, probe) => {
  let last = null; let since = Date.now();
  return waitFor(what, ms, async () => {
    const v = JSON.stringify(await probe());
    if (v !== last) { last = v; since = Date.now(); return null; }
    return Date.now() - since >= stableMs ? JSON.parse(v) : null;
  });
};

const q = JSON.stringify;
const run = async () => {
  // 1. the note page, and its 复制链接 action
  await cdp.send('Page.enable');
  await cdp.send('Page.navigate', { url: noteUrl });
  await sleep(T.page_dom_stable);
  const share = S.unlabeled_share_controls[0];
  await waitFor('the share control', T.share_control_wait, () => ev(`!!document.querySelector(${q(share)})`));
  await ev(`document.querySelector(${q(share)}).click()`);
  await waitFor('the 复制链接 menu item', T.share_menu_wait, () => ev(`(() => {
    const el = [...document.querySelectorAll(${q(S.share_menu_items.join(','))})].find((e) => e.textContent.trim() === ${q(S.copy_action_text)});
    if (!el) return false; el.click(); return true; })()`));
  await sleep(T.page_dom_stable);
  // The copied link stays inside this process: it is read from the page clipboard, or, when the browser keeps
  // the clipboard to itself, the note page's own address stands in. It is never printed.
  const copied = await ev(`navigator.clipboard.readText().catch(() => '')`);
  const link = NOTE_RE.test(copied) ? copied.trim() : await ev('location.href');

  // 2. the chat, with the counts taken before anything is given to it
  await cdp.send('Page.navigate', { url: C.ai_chat_url });
  await sleep(T.page_dom_stable);
  const input = `[...document.querySelectorAll(${q(S.input_controls.join(','))})].find((t) => t.offsetParent !== null && ${q(S.input_placeholders)}.includes(t.placeholder))`;
  await waitFor('the 点点 input', T.input_wait, () => ev(`!!(${input})`));
  const before = await ev(`({ cards: document.querySelectorAll(${q(S.selected_note_card)}).length, messages: document.querySelectorAll(${q(S.assistant_message)}).length })`);
  const state = () => ev(`(() => { const t = ${input}; return { cards: document.querySelectorAll(${q(S.selected_note_card)}).length, value: t ? t.value : null }; })()`);

  // 3. one paste of the link, then wait for the page to settle into one of the two accepted shapes
  await ev(`(() => { const t = ${input}; t.focus(); const dt = new DataTransfer(); dt.setData('text/plain', ${q(link)});
    t.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); })()`);
  await waitFor('the page to take the pasted link', T.paste_acceptance_wait, async () => {
    const s = await state(); return s.cards > before.cards || (s.value ?? '') !== '';
  });
  const shape = await settled('the pasted link to settle', T.context_wait, T.note_context_stable, state);
  const cardMode = shape.cards === before.cards + 1 && shape.value === '';
  const directMode = shape.cards === before.cards && shape.value === link;
  if (!cardMode && !directMode) throw stop('ai-paste-not-handled: the page did not settle into a selected note card or the plain link.');

  // 4. the exact prompt, once
  await ev(`(() => { const t = ${input}; t.focus(); t.setSelectionRange(t.value.length, t.value.length); })()`);
  await cdp.send('Input.insertText', { text: cardMode ? C.prompt : ` ${C.prompt}` });
  await sleep(T.prompt_stable);
  if ((await state()).value !== (cardMode ? C.prompt : `${link} ${C.prompt}`)) throw stop('the input does not hold exactly the note link and the prompt.');
  for (const type of ['keyDown', 'keyUp']) {
    await cdp.send('Input.dispatchKeyEvent', { type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, text: type === 'keyDown' ? '\r' : undefined });
  }
  await waitFor('the page to take the question', T.submit_acceptance_wait,
    () => ev(`document.querySelectorAll(${q(S.assistant_message)}).length > ${before.messages}`));

  // 5. a NEW finished message, unchanged for 2 s
  const reply = await settled('the finished reply', T.response_wait, T.reply_text_stable, () => ev(`(() => {
    const all = document.querySelectorAll(${q(S.assistant_message)}); const m = all[all.length - 1];
    return m && all.length > ${before.messages} && m.classList.contains(${q(S.finished_message_class)}) ? m.innerText : null; })()`));
  if (typeof reply !== 'string' || !reply.trim()) throw stop('the finished reply is empty.');
  await sleep(T.success_dwell);
  return reply;
};

let code = 0;
try {
  tab = await http('/json/new?about:blank', { method: 'PUT' });
  cdp = connect(tab.webSocketDebuggerUrl);
  process.stdout.write(`${await run()}\n`);
} catch (e) {
  code = e instanceof Stop ? e.code : 1;
  console.error(e instanceof Stop ? e.message : `xhs-diandian-driver: ${String(e?.message ?? e).slice(0, 200)}`);
} finally {
  cdp?.close();
  if (tab) await http(`/json/close/${tab.id}`).catch(() => {});
}
// Let the loop drain instead of process.exit(): on Windows, exiting with the socket still closing aborts node
// (exit 0xC0000409) and the guard would read that as a failure of a run that worked.
process.exitCode = code;
setTimeout(() => process.exit(code), 5000).unref();
