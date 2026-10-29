#!/usr/bin/env node
// Prints the Xiaohongshu login cookie header ("a1=...; web_session=...; ...") on stdout.
// Nothing else is ever printed to stdout, and nothing is written to disk.
//
// Runs on Windows (node.exe, reached from WSL through interop) because the account's login lives
// in the SOP project's scanning Chrome, whose debug port is on Windows loopback. Called by
// redbook-guard.sh for every read, so the cookie is fresh and exists only in memory.
//
// Exit codes (stderr carries one line saying why, never a cookie value):
//   0 cookie printed   3 someone else is using the account right now (favsense run, SOP scan)
//   4 scanning browser not running, or the port belongs to some other browser
//   5 browser is up but not logged in to Xiaohongshu   1 anything else
import { readFileSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';
import { homedir } from 'node:os';

const SOP = process.env.XHS_SOP_ROOT ?? join(homedir(), 'Codex', 'SOP - 小红书');
const PORT_FILE = process.env.XHS_CDP_PORT_FILE ?? join(SOP, '.secrets', 'cdp-port.txt');
const PROFILE = process.env.XHS_SCAN_PROFILE_DIR ?? join(SOP, '.secrets', 'browser-profiles', 'cdp-chrome');
const LOCKS = process.env.XHS_SOP_LOCK_DIR ?? join(SOP, '.secrets', 'locks');
const FAVSENSE_SYNC =
  process.env.XHS_FAVSENSE_SYNC_STATE ?? join(homedir(), 'Codex', '小红书收藏整理', '.xhs-favorites', 'manual-sync.json');

const stop = (code, msg) => { console.error(`xhs-cdp-cookies: ${msg}`); process.exit(code); };
const norm = (s) => s.toLowerCase().replaceAll('/', '\\').replaceAll('\\scripts\\..\\', '\\').replaceAll('"', '');

const port = Number.parseInt(existsSync(PORT_FILE) ? readFileSync(PORT_FILE, 'utf8').trim() : '', 10);
if (!(port >= 1 && port <= 65535)) stop(4, `no usable port in ${PORT_FILE}; the scanning browser has never been started.`);

const get = async (path) => {
  const r = await fetch(`http://127.0.0.1:${port}${path}`, { signal: AbortSignal.timeout(3000) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
};

let version;
try { version = await get('/json/version'); }
catch { stop(4, `scanning browser is not running on port ${port} (it is started by SOP's scripts\\启动扫描浏览器.bat).`); }

// The port number alone proves nothing: 9222 is also the port other browsers use. Only read
// cookies from the process that was started with the scanning profile.
let cmdline = '';
try {
  cmdline = execFileSync('powershell.exe', ['-NoProfile', '-Command',
    '[Console]::OutputEncoding=[Text.UTF8Encoding]::new();' +
    `$c=Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue|Select-Object -First 1;` +
    'if($c){(Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)").CommandLine}'],
    { encoding: 'utf8', timeout: 20000 });
} catch { stop(1, 'could not look up which program owns the debug port.'); }
if (!norm(cmdline).includes(norm(PROFILE))) stop(4, `port ${port} belongs to a different browser, not the scanning profile; reading nothing.`);

// the owner's condition: only while favsense is idle. favsense records an organisation run as
// "starting"/"running" in manual-sync.json; SOP's own scans hold a lock directory per port.
try {
  const state = JSON.parse(readFileSync(FAVSENSE_SYNC, 'utf8')).state;
  if (state === 'starting' || state === 'running') stop(3, `favsense has a run in progress (${state}); wait until it is idle.`);
} catch (e) { if (e?.code !== 'ENOENT') stop(3, 'could not tell whether favsense is idle; not reading.'); }
if (existsSync(join(LOCKS, `cdp-${port}.lock`))) stop(3, 'an SOP scan holds the scanning browser right now; wait.');

const cookies = await new Promise((resolve, reject) => {
  const ws = new WebSocket(version.webSocketDebuggerUrl);
  const timer = setTimeout(() => { ws.close(); reject(new Error('timed out')); }, 10000);
  ws.addEventListener('open', () => ws.send(JSON.stringify({ id: 1, method: 'Storage.getCookies' })));
  ws.addEventListener('error', () => { clearTimeout(timer); reject(new Error('websocket failed')); });
  ws.addEventListener('message', (ev) => {
    const m = JSON.parse(String(ev.data));
    if (m.id !== 1) return;
    clearTimeout(timer); ws.close();
    m.error ? reject(new Error(m.error.message)) : resolve(m.result?.cookies ?? []);
  });
}).catch((e) => stop(1, `reading cookies failed: ${e.message}`));

const jar = new Map();
for (const c of cookies) if (c.domain.replace(/^\./, '').endsWith('xiaohongshu.com')) jar.set(c.name, c.value);
if (!jar.has('a1') || !jar.has('web_session')) stop(5, 'scanning browser is not logged in to Xiaohongshu (a1/web_session missing).');
process.stdout.write([...jar].map(([k, v]) => `${k}=${v}`).join('; ') + '\n');
