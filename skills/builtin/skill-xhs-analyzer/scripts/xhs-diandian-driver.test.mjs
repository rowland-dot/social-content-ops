// Tests for xhs-diandian-driver.mjs: node --test xhs-diandian-driver.test.mjs
// The browser is a stand-in: a small server that speaks the DevTools protocol over a WebSocket and keeps a fake
// page (a note page and the 点点 chat) in memory, so nothing here reaches Xiaohongshu. The driver's waits are
// shortened with XHS_DIANDIAN_TIME_SCALE; their order and the exactly-once rules are what is under test.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import crypto from 'node:crypto';
import vm from 'node:vm';
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const DRIVER = fileURLToPath(new URL('./xhs-diandian-driver.mjs', import.meta.url));
const CONTRACT = JSON.parse(readFileSync(fileURLToPath(new URL('./diandian-contract.json', import.meta.url)), 'utf8'));
const NOTE = 'https://www.xiaohongshu.com/explore/6aabad9400000000110328e1?xsec_token=tok-secret&xsec_source=pc_search';
const COPIED = 'https://www.xiaohongshu.com/discovery/item/6aabad9400000000110328e1?source=webshare&xsec_token=tok-copied';
const FULL = '这篇笔记讲了三件事：\n- 先做A\n- 再做B';

// --- the WebSocket side, by hand (the browser's side of the handshake and of framing) ---
const frameOut = (text) => {
  const p = Buffer.from(text);
  const h = p.length < 126 ? Buffer.from([0x81, p.length]) : Buffer.concat([Buffer.from([0x81, 126]), Buffer.from([p.length >> 8, p.length & 255])]);
  return Buffer.concat([h, p]);
};
const frameIn = (b) => {
  if (b.length < 2) return null;
  let len = b[1] & 0x7f; let off = 2;
  if (len === 126) { if (b.length < 4) return null; len = b.readUInt16BE(2); off = 4; }
  const need = off + 4 + len;
  if (b.length < need) return null;
  const mask = b.subarray(off, off + 4);
  const payload = Buffer.from(b.subarray(off + 4, need).map((x, i) => x ^ mask[i % 4]));
  return { opcode: b[0] & 0x0f, text: payload.toString('utf8'), used: need };
};

// --- the fake browser ---
function fakeBrowser(opts = {}) {
  const page = {
    url: 'about:blank', title: '', menuOpen: false, copied: false, messages: [{ text: '旧回复', finished: true }],
    cards: 0, value: '', inserts: [], enters: 0, navigations: [], closed: false, requests: 0,
    pasteMode: opts.pasteMode ?? 'card', clipboard: opts.clipboard ?? 'allowed',
  };
  const chat = () => page.url.startsWith(CONTRACT.ai_chat_url);
  const textarea = {
    placeholder: CONTRACT.selectors.input_placeholders[0], offsetParent: {}, focus() {}, setSelectionRange() {},
    get value() { return page.value; },
    dispatchEvent(e) {
      page.pastes = (page.pastes ?? 0) + 1;
      if (page.pasteMode === 'card') page.cards += 1;
      else if (page.pasteMode === 'direct') page.value = e.clipboardData.d;
      else if (page.pasteMode === 'transition') {   // a card appears while the link text lingers for a moment
        page.cards += 1; page.value = e.clipboardData.d;
        setTimeout(() => { page.value = ''; }, 120);
      }
    },
  };
  const msgEl = (m) => ({ classList: { contains: (c) => c === CONTRACT.selectors.finished_message_class && m.finished }, innerText: m.text });
  const share = { click() { page.menuOpen = true; } };
  const menuItem = { textContent: ` ${CONTRACT.selectors.copy_action_text} `, click() { page.copied = true; } };
  const ctx = {
    document: {
      get title() { return page.title; },
      querySelector: (sel) => {
        if (sel === CONTRACT.selectors.unlabeled_share_controls[0]) return chat() ? null : share;
        if (sel.includes('captcha')) return page.url.includes('captcha') ? {} : null;
        return null;
      },
      querySelectorAll: (sel) => {
        if (sel === CONTRACT.selectors.share_menu_items.join(',')) return page.menuOpen ? [menuItem] : [];
        if (sel === CONTRACT.selectors.input_controls.join(',')) return chat() ? [textarea] : [];
        if (sel === CONTRACT.selectors.selected_note_card) return Array.from({ length: page.cards });
        if (sel === CONTRACT.selectors.assistant_message) return chat() ? page.messages.map(msgEl) : [];
        return [];
      },
    },
    location: { get href() { return page.url; } },
    navigator: { clipboard: { readText: () => (page.clipboard === 'allowed' && page.copied ? Promise.resolve(COPIED) : Promise.reject(new Error('denied'))) } },
    DataTransfer: class { setData(_t, v) { this.d = v; } },
    ClipboardEvent: class { constructor(type, init) { this.type = type; this.clipboardData = init.clipboardData; } },
  };
  vm.createContext(ctx);

  const answer = (method, params) => {
    if (method === 'Page.navigate') {
      page.url = params.url; page.navigations.push(params.url);
      if (opts.captchaOnChat && chat()) page.url = 'https://www.xiaohongshu.com/website-login/captcha?redirect=x';
    }
    if (method === 'Input.insertText') { page.inserts.push(params.text); page.value += params.text; }
    if (method === 'Input.dispatchKeyEvent' && params.type === 'keyDown' && params.key === 'Enter') {
      page.enters += 1;
      const m = { text: '', finished: false }; page.messages.push(m);
      page.value = ''; page.cards = 0;
      setTimeout(() => { m.text = '正在整理…'; }, 150);
      setTimeout(() => { m.text = '草稿'; m.finished = true; }, 700);   // finished, but still being rewritten ...
      setTimeout(() => { m.text = FULL; }, 850);                       // ... faster than the stability window
    }
    if (method === 'Runtime.evaluate') {
      try {
        const out = vm.runInContext(params.expression, ctx);
        return Promise.resolve(out).then((value) => ({ result: { value: value === undefined ? undefined : JSON.parse(JSON.stringify(value)) } }));
      } catch (e) {
        return { exceptionDetails: { text: 'threw', exception: { description: String(e) } } };
      }
    }
    return {};
  };

  const server = http.createServer((req, res) => {
    page.requests += 1;
    if (req.url.startsWith('/json/new') && req.method === 'PUT') {
      res.end(JSON.stringify({ id: 'tab1', webSocketDebuggerUrl: `ws://127.0.0.1:${server.address().port}/devtools/page/tab1` }));
    } else if (req.url.startsWith('/json/close/')) { page.closed = true; res.end('{}'); } else { res.statusCode = 404; res.end(); }
  });
  server.on('upgrade', (req, socket) => {
    const accept = crypto.createHash('sha1').update(`${req.headers['sec-websocket-key']}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`).digest('base64');
    socket.write(`HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`);
    let buf = Buffer.alloc(0);
    socket.on('data', (d) => {
      buf = Buffer.concat([buf, d]);
      for (let f = frameIn(buf); f; f = frameIn(buf)) {
        buf = buf.subarray(f.used);
        if (f.opcode === 8) { socket.end(); return; }
        if (f.opcode !== 1) continue;
        const m = JSON.parse(f.text);
        Promise.resolve(answer(m.method, m.params ?? {})).then((r) => socket.write(frameOut(JSON.stringify({ id: m.id, result: r }))));
      }
    });
    socket.on('error', () => {});
  });
  return { page, server, listen: () => new Promise((r) => server.listen(0, '127.0.0.1', () => r(server.address().port))) };
}

async function drive(browser, args = [NOTE]) {
  const port = await browser.listen();
  const dir = mkdtempSync(join(tmpdir(), 'diandian-'));
  writeFileSync(join(dir, 'port.txt'), String(port));
  const child = spawn(process.execPath, [DRIVER, ...args], {
    env: { ...process.env, XHS_CDP_PORT_FILE: join(dir, 'port.txt'), XHS_DIANDIAN_TIME_SCALE: '0.1' },
  });
  let out = ''; let err = '';
  child.stdout.on('data', (d) => { out += d; }); child.stderr.on('data', (d) => { err += d; });
  const code = await new Promise((r) => child.on('close', r));
  browser.server.close();
  return { code, out, err };
}

test('a note in selected-card mode: one paste, the exact prompt once, the final reply of the NEW message', async () => {
  const b = fakeBrowser({ pasteMode: 'card' });
  const r = await drive(b);
  assert.equal(r.code, 0, r.err);
  assert.equal(r.out, `${FULL}\n`);
  assert.equal(b.page.pastes, 1);
  assert.deepEqual(b.page.inserts, [CONTRACT.prompt]);
  assert.equal(b.page.enters, 1);
  assert.equal(b.page.copied, true, 'the note page 复制链接 action was used');
  assert.deepEqual(b.page.navigations, [NOTE, CONTRACT.ai_chat_url]);
  assert.equal(b.page.closed, true, 'the tab it opened is closed again');
  assert.ok(!r.out.includes('旧回复'), 'the older reply is never returned');
});

test('direct-link mode: the prompt is appended to the retained link, never the whole link rewritten', async () => {
  const b = fakeBrowser({ pasteMode: 'direct', clipboard: 'allowed' });
  const r = await drive(b);
  assert.equal(r.code, 0, r.err);
  assert.deepEqual(b.page.inserts, [` ${CONTRACT.prompt}`]);
  assert.equal(b.page.pastes, 1);
});

test('a card plus link text that lingers for a moment is a transition, not a failure', async () => {
  const b = fakeBrowser({ pasteMode: 'transition' });
  const r = await drive(b);
  assert.equal(r.code, 0, r.err);
  assert.deepEqual(b.page.inserts, [CONTRACT.prompt]);
  assert.equal(b.page.pastes, 1);
});

test('when the browser keeps the clipboard to itself, the note page address stands in; the link is never printed', async () => {
  const b = fakeBrowser({ pasteMode: 'direct', clipboard: 'denied' });
  const r = await drive(b);
  assert.equal(r.code, 0, r.err);
  assert.ok(!r.err.includes('tok-') && !r.out.includes('tok-'), 'no access code on either stream');
});

test('a page that ignores the paste stops the run with a reason, and sends nothing', async () => {
  const b = fakeBrowser({ pasteMode: 'ignore' });
  const r = await drive(b);
  assert.equal(r.code, 1);
  assert.match(r.err, /timed out waiting for the page to take the pasted link/);
  assert.equal(b.page.pastes, 1, 'no second paste attempt');
  assert.deepEqual(b.page.inserts, []);
  assert.equal(b.page.enters, 0);
  assert.equal(b.page.closed, true);
});

test('a captcha page: exit 2, the guard-recognised line, nothing typed or sent', async () => {
  const b = fakeBrowser({ captchaOnChat: true });
  const r = await drive(b);
  assert.equal(r.code, 2);
  assert.match(r.err, /^safety-signal: captcha/);
  assert.deepEqual(b.page.inserts, []);
  assert.equal(b.page.enters, 0);
  assert.equal(b.page.closed, true);
});

test('an argument that is not a note address stops before any request to the browser', async () => {
  const b = fakeBrowser();
  const r = await drive(b, ['http://xhslink.com/o/AbCdEf123']);
  assert.equal(r.code, 1);
  assert.match(r.err, /not a note address/);
  assert.equal(b.page.requests, 0);
});
