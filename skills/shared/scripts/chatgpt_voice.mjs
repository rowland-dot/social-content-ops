#!/usr/bin/env node
// Browser half of chatgpt_voice.py: drives the owner's ChatGPT (dedicated Chrome profile, debug port on
// Windows loopback) to get a spoken version of a fixed script. Runs on Windows (node.exe, reached from
// WSL through interop), exactly like xhs-cdp-cookies.mjs.
//
//   ask                       script on stdin -> one JSON line {conversation_id, message_id, reply}
//                             (a new normal chat: send "repeat this word for word", read ChatGPT's reply)
//   speak --message-id M --conversation-id C --voice V    -> mp3 bytes on stdout (ChatGPT "Read aloud")
//   status                    prints {"signed_in":true}
//
// The login never leaves the dedicated profile: the access token is read inside the page and used by
// the page's own fetch; nothing is written to disk, nothing but the audio / the reply is printed.
//
// Exit codes (stderr carries one line saying why, never a token):
//   0 ok   4 the dedicated browser is not running, or the port belongs to some other browser
//   5 the dedicated browser is up but ChatGPT is not signed in   1 anything else
import { homedir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';

const argv = process.argv.slice(2);
const cmd = argv[0];
const flag = (name) => { const i = argv.indexOf(`--${name}`); return i >= 0 ? argv[i + 1] : undefined; };

const PORT = Number.parseInt(flag('port') ?? process.env.CHATGPT_CDP_PORT ?? '9230', 10);
const PROFILE = flag('profile-dir') ?? process.env.CHATGPT_PROFILE_DIR ?? join(homedir(), '.easel-browser', 'chatgpt');
const ORIGIN = 'https://chatgpt.com';

const stop = (code, msg) => { console.error(`chatgpt_voice: ${msg}`); process.exit(code); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const norm = (s) => s.toLowerCase().replaceAll('/', '\\').replaceAll('"', '').replace(/\\+$/, '');

// ── which browser answers on the port? only the dedicated profile counts ─────────────────────────
async function browserWebSocket() {
  let version;
  try {
    const r = await fetch(`http://127.0.0.1:${PORT}/json/version`, { signal: AbortSignal.timeout(3000) });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    version = await r.json();
  } catch { stop(4, `no browser is listening on port ${PORT}; the dedicated ChatGPT Chrome is not running.`); }
  // The port number proves nothing: another browser may hold it. Only trust the process that was
  // started with the dedicated profile folder.
  let cmdline = '';
  try {
    cmdline = execFileSync('powershell.exe', ['-NoProfile', '-Command',
      '[Console]::OutputEncoding=[Text.UTF8Encoding]::new();' +
      `$c=Get-NetTCPConnection -LocalPort ${PORT} -State Listen -ErrorAction SilentlyContinue|Select-Object -First 1;` +
      'if($c){(Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)").CommandLine}'],
      { encoding: 'utf8', timeout: 20000 });
  } catch { stop(1, 'could not look up which program owns the debug port.'); }
  if (!norm(cmdline).includes(norm(PROFILE))) stop(4, `port ${PORT} belongs to a different browser, not the dedicated ChatGPT profile; touching nothing.`);
  return version.webSocketDebuggerUrl;
}

// ── a minimal Chrome DevTools Protocol client ────────────────────────────────────────────────────
class Cdp {
  constructor(url) {
    this.n = 0; this.pending = new Map();
    this.ws = new WebSocket(url);
    this.ready = new Promise((res, rej) => {
      this.ws.addEventListener('open', res);
      this.ws.addEventListener('error', () => rej(new Error('websocket failed')));
    });
    this.ws.addEventListener('message', (ev) => {
      const m = JSON.parse(String(ev.data));
      const p = this.pending.get(m.id);
      if (!p) return;
      this.pending.delete(m.id);
      m.error ? p.rej(new Error(m.error.message)) : p.res(m.result);
    });
  }
  send(method, params = {}, sessionId) {
    const id = ++this.n;
    return new Promise((res, rej) => {
      this.pending.set(id, { res, rej });
      this.ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    });
  }
  close() { try { this.ws.close(); } catch { /* already closed */ } }
}

async function openPage(cdp) {
  const { targetInfos } = await cdp.send('Target.getTargets');
  let target = targetInfos.find((t) => t.type === 'page' && t.url.startsWith(ORIGIN));
  const targetId = target ? target.targetId : (await cdp.send('Target.createTarget', { url: `${ORIGIN}/` })).targetId;
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  const page = {
    sessionId,
    send: (m, p) => cdp.send(m, p, sessionId),
    async eval(expression) {
      const r = await cdp.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, sessionId);
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
      return r.result.value;
    },
  };
  await page.send('Page.enable');
  return page;
}

async function until(fn, timeoutMs, what, everyMs = 500) {
  const end = Date.now() + timeoutMs;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > end) throw new Error(`timed out waiting for ${what}`);
    await sleep(everyMs);
  }
}

// Same-origin fetch with the page's own login; the token is only ever read inside the page.
const IN_PAGE_TOKEN = `(async()=>{const r=await fetch('/api/auth/session',{credentials:'include'});
  const j=await r.json().catch(()=>({}));return j&&j.accessToken||''})()`;

async function ensureOnChatGPT(page) {
  const here = await page.eval('location.origin');
  if (here !== ORIGIN) await gotoNewChat(page);
}

async function gotoNewChat(page) {
  await page.send('Page.navigate', { url: `${ORIGIN}/` });
  await until(async () => (await page.eval('document.readyState')) === 'complete', 30000, 'the page to load');
}

async function requireSignedIn(page) {
  const token = await page.eval(IN_PAGE_TOKEN);
  if (!token) stop(5, 'the dedicated ChatGPT profile is not signed in; sign in once in that window.');
}

// ── commands ─────────────────────────────────────────────────────────────────────────────────────
const PROMPT = '请逐字重复下面这段文字。只输出这段文字本身，不要加引号、标题、解释或任何其他内容。\n\n';
// What the ChatGPT page looks like (checked 2026-10-12): the message box is a ProseMirror editor with
// no id, and the send button is the form's submit button. Nothing else on the page is relied on.
const BOX = '.ProseMirror[contenteditable="true"]';
const SEND = 'form button[type="submit"]:not([disabled])';

async function ask(script) {
  const cdp = new Cdp(await browserWebSocket());
  await cdp.ready;
  try {
    const page = await openPage(cdp);
    await ensureOnChatGPT(page);
    await requireSignedIn(page);
    await gotoNewChat(page); // a fresh normal chat for every request
    await until(() => page.eval(`!!document.querySelector(${JSON.stringify(BOX)})`), 30000, 'the message box');
    await page.eval(`document.querySelector(${JSON.stringify(BOX)}).focus()`);
    await page.send('Input.insertText', { text: PROMPT + script });
    await until(() => page.eval(`!!document.querySelector(${JSON.stringify(SEND)})`), 15000, 'the send button');
    await page.eval(`document.querySelector(${JSON.stringify(SEND)}).click()`);
    // A sent message turns the address into /c/<conversation id>. If it never does, the send did not go through.
    const conversationId = await until(() => page.eval(`(location.pathname.match(/\\/c\\/([0-9a-f-]+)/)||[])[1]||''`),
      45000, 'the message to be sent (a human check may be showing in the window)');
    // The reply is read from ChatGPT's own record of the conversation, not from the page layout:
    // the finished, final assistant text message is the one the chat currently ends on.
    const reply = await until(async () => {
      const r = await page.eval(`(async()=>{const t=await ${IN_PAGE_TOKEN};
        const r=await fetch('/backend-api/conversation/${conversationId}',{headers:{Authorization:'Bearer '+t}});
        if(!r.ok)return null;const j=await r.json();const n=j.mapping&&j.mapping[j.current_node];const m=n&&n.message;
        if(!m||!m.author||m.author.role!=='assistant'||!m.content||m.content.content_type!=='text')return null;
        if(m.status!=='finished_successfully'||m.end_turn!==true)return null;
        return {message_id:m.id,reply:(m.content.parts||[]).filter(p=>typeof p==='string').join('')}})()`);
      return r;
    }, 240000, 'the reply to finish', 1500);
    process.stdout.write(JSON.stringify({ conversation_id: conversationId, message_id: reply.message_id, reply: reply.reply }) + '\n');
  } finally { cdp.close(); }
}

async function speak(messageId, conversationId, voice) {
  const cdp = new Cdp(await browserWebSocket());
  await cdp.ready;
  try {
    const page = await openPage(cdp);
    await ensureOnChatGPT(page);
    await requireSignedIn(page);
    const q = new URLSearchParams({ message_id: messageId, conversation_id: conversationId, voice, format: 'mp3' });
    const b64 = await page.eval(`(async()=>{const t=await ${IN_PAGE_TOKEN};
      const r=await fetch('/backend-api/synthesize?${q}',{headers:{Authorization:'Bearer '+t}});
      if(!r.ok)throw new Error('synthesize HTTP '+r.status);
      const b=new Uint8Array(await r.arrayBuffer());let s='';
      for(let i=0;i<b.length;i+=0x8000)s+=String.fromCharCode.apply(null,b.subarray(i,i+0x8000));
      return btoa(s)})()`);
    process.stdout.write(Buffer.from(b64, 'base64'));
  } finally { cdp.close(); }
}

async function status() {
  const cdp = new Cdp(await browserWebSocket());
  await cdp.ready;
  try {
    const page = await openPage(cdp);
    await ensureOnChatGPT(page);
    await requireSignedIn(page);
    process.stdout.write(JSON.stringify({ signed_in: true }) + '\n');
  } finally { cdp.close(); }
}

const readStdin = async () => { const chunks = []; for await (const c of process.stdin) chunks.push(c); return Buffer.concat(chunks).toString('utf8'); };

try {
  if (cmd === 'ask') {
    const script = (await readStdin()).trim();
    if (!script) stop(1, 'no script text on stdin.');
    await ask(script);
  } else if (cmd === 'speak') {
    const messageId = flag('message-id'), conversationId = flag('conversation-id'), voice = flag('voice');
    if (!messageId || !conversationId || !voice) stop(1, 'speak needs --message-id, --conversation-id and --voice.');
    await speak(messageId, conversationId, voice);
  } else if (cmd === 'status') {
    await status();
  } else {
    stop(1, 'usage: chatgpt_voice.mjs ask | speak --message-id M --conversation-id C --voice V | status');
  }
} catch (e) { stop(1, e.message); }
// no process.exit() here: it can cut off a large audio write to a pipe; the socket is closed, so node ends by itself
