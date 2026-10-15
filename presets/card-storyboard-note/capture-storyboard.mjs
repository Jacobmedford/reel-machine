// card-storyboard-note: capture a real storyboard page as the creator sees it on a monitor: desktop layout, dark
// scheme, published state (the page shows its "Comment on this beat" buttons when it runs as a Claude artifact with
// comments; locally its script hides them, so they are un-hidden exactly as that branch does).
// It reads CAPTURE from the PRESET CONSTANTS block of this folder's index.html: page ("" = the project given as the
// argument, its storyboard/index.html; a name = another project folder beside it; or a path to a storyboard
// index.html) and three beat ids, the focus beat in the middle.
// Writes, next to this file in img/:
//   strip.png      the three beats, page x 0..STRIP_W CSS px, 4 device px per CSS px
//   btn.png, btn-hover.png   the focus beat's own button, normal and hover, 6 CSS px of sheet around it
//   strip.json     every box the card lays itself out from, in CSS px relative to the strip's top-left
//   strip.js       the same, as window.STRIP, for the card (a composition can't fetch JSON from disk)
// Run: node capture-storyboard.mjs <project>        (a headless browser: run it under the heavy lock)
//   PPTR / HEADLESS_BROWSER override where puppeteer-core and the headless shell are found (else the newest in the
//   npx cache and ~/.cache/puppeteer, which the hyperframes toolchain installs).
import { createRequire } from 'module';
import fs from 'fs';
import os from 'os';
import path from 'path';

const require = createRequire(import.meta.url);
const HERE = path.dirname(new URL(import.meta.url).pathname);
if (fs.existsSync(path.join(HERE, 'preset.json'))) {
  console.error(HERE + ' is the preset library: make an instance (pipeline/preset.py add) and run its copy');
  process.exit(1);
}
function newest(paths) {
  return paths.filter((p) => fs.existsSync(p)).map((p) => [p, fs.statSync(p).mtimeMs]).sort((a, b) => b[1] - a[1]).map((x) => x[0])[0];
}
function under(dir, tail) {
  try { return fs.readdirSync(dir).map((d) => path.join(dir, d, tail)); } catch (e) { return []; }
}
const HOME = os.homedir();
const PPTR = process.env.PPTR || newest(under(path.join(HOME, '.npm', '_npx'), 'node_modules/puppeteer-core'));
const CHROME = process.env.HEADLESS_BROWSER || newest(under(path.join(HOME, '.cache', 'puppeteer', 'chrome-headless-shell'),
  'chrome-headless-shell-mac-arm64/chrome-headless-shell').concat(under(path.join(HOME, '.cache', 'puppeteer', 'chrome-headless-shell'),
  'chrome-headless-shell-linux64/chrome-headless-shell')));
if (!PPTR || !CHROME) { console.error('no puppeteer-core / headless shell found: run `npx -y hyperframes@0.8.139 doctor` once, or set PPTR and HEADLESS_BROWSER'); process.exit(1); }
const puppeteer = require(PPTR);

// the card's own constants: CAPTURE = {"page": ..., "beats": [..., focus, ...]}
const html = fs.readFileSync(path.join(HERE, 'index.html'), 'utf8');
const block = html.slice(html.indexOf('// PRESET CONSTANTS START'), html.indexOf('// PRESET CONSTANTS END'));
const CAPTURE = JSON.parse(/var CAPTURE = (\{.*?\});/.exec(block)[1]);
const PROJECT = process.argv[2] ? path.resolve(process.argv[2]) : '';
if (!CAPTURE.page && !PROJECT) { console.error('CAPTURE.page is "" (this project): run node capture-storyboard.mjs <project>'); process.exit(1); }
// the creator's home folder: the kit's rule (pipeline/common.py), copied because this runs from a project's copy of
// the card, away from the kit (tests/test_home.py holds this copy to that one)
function resolveHome(env = process.env, exists = fs.existsSync) {
  const expand = (p) => p.replace(/^~(?=$|\/)/, HOME);
  for (const k of ['REEL_MACHINE_HOME', 'REEL_KIT_HOME']) if (env[k]) return expand(env[k]);
  const neu = path.join(HOME, 'reel-machine'), old = path.join(HOME, 'reel-kit');
  if (exists(neu)) return neu;
  if (exists(path.join(old, 'style', 'style.json'))) return old;
  return neu;
}
const PROJECTS = PROJECT ? path.dirname(PROJECT) : path.join(resolveHome(), 'projects');
const PAGE_FILE = /[\/.]/.test(CAPTURE.page) && CAPTURE.page.endsWith('.html') ? path.resolve(CAPTURE.page)
  : CAPTURE.page ? path.join(PROJECTS, CAPTURE.page, 'storyboard', 'index.html')
  : path.join(PROJECT, 'storyboard', 'index.html');
if (!fs.existsSync(PAGE_FILE)) { console.error('no storyboard at ' + PAGE_FILE); process.exit(1); }
const PAGE = 'file://' + PAGE_FILE;
const BEATS = CAPTURE.beats;                  // the focus beat is the middle one
const WIDTH = 1112;                           // CSS px viewport: the page's full desktop width (its wrap maxes at 1080)
const STRIP_W = 560;                          // CSS px of the page kept, from its left edge
const PAD = 40;                               // CSS px of page kept above the first beat and below the last
const DSF = 4;                                // device px per CSS px: crisp when the card shows it ~2x
const OUT = path.join(HERE, 'img');
fs.mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'shell',
  args: ['--allow-file-access-from-files', '--hide-scrollbars', '--font-render-hinting=none'] });
const page = await browser.newPage();
await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'dark' }]);
await page.setViewport({ width: WIDTH, height: 1400, deviceScaleFactor: DSF });
await page.goto(PAGE, { waitUntil: 'load' });
await page.evaluate(async (ids) => {
  document.querySelectorAll('[data-note]').forEach((b) => { b.hidden = false; });   // the published branch
  document.querySelectorAll('img').forEach((i) => { i.loading = 'eager'; });
  await document.fonts.ready;
  const imgs = ids.flatMap((id) => [...document.querySelectorAll('#' + id + ' img')]);
  await Promise.all(imgs.map((i) => (i.complete && i.naturalWidth ? null : new Promise((r) => { i.onload = r; i.onerror = r; }))));
  await Promise.all(imgs.map((i) => i.decode().catch(() => null)));
  document.getElementById(ids[1]).scrollIntoView({ block: 'center' });
}, BEATS);
await new Promise((r) => setTimeout(r, 400));

// geometry in document CSS px, then relative to the strip's origin
const geo = await page.evaluate((ids, PAD) => {
  const doc = (el) => { const r = el.getBoundingClientRect();
    return { x: r.left + window.scrollX, y: r.top + window.scrollY, w: r.width, h: r.height }; };
  const first = doc(document.getElementById(ids[0])), last = doc(document.getElementById(ids[2]));
  const origin = { x: 0, y: Math.floor(first.y - PAD) };
  const rel = (el) => { if (!el) return null; const d = doc(el);
    return { x: +(d.x - origin.x).toFixed(2), y: +(d.y - origin.y).toFixed(2), w: +d.w.toFixed(2), h: +d.h.toFixed(2) }; };
  const beats = {};
  ids.forEach((id) => { const b = document.getElementById(id);
    beats[id] = { box: rel(b), meta: rel(b.querySelector('.meta')), line: rel(b.querySelector('.line')), note: rel(b.querySelector('.note')),
      frames: [...b.querySelectorAll('.frame img')].map(rel), labels: [...b.querySelectorAll('.frame span')].map(rel),
      kind: rel(b.querySelector('.meta .kind')),
      text: { meta: b.querySelector('.meta').innerText.replace(/\n/g, ' · '), line: b.querySelector('.line').innerText,
              frames: [...b.querySelectorAll('.frame img')].map((i) => i.getAttribute('src')) } }; });
  return { origin, height: Math.ceil(last.y + last.h + PAD - origin.y), beats,
           eyebrow: document.querySelector('.eyebrow').innerText, h1: document.querySelector('h1').innerText };
}, BEATS, PAD);

async function shot(file, clip) {
  await page.screenshot({ path: path.join(OUT, file), captureBeyondViewport: true, clip });
}
await shot('strip.png', { x: 0, y: geo.origin.y, width: STRIP_W, height: geo.height });

// the focus beat's own button: normal, then hovered (the page's hover turns its border to ink)
const nb = geo.beats[BEATS[1]].note, bclip = { x: nb.x - 6, y: geo.origin.y + nb.y - 6, width: nb.w + 12, height: nb.h + 12 };
await page.mouse.move(2, 2);
await shot('btn.png', bclip);
await page.hover('#' + BEATS[1] + ' .note');
await new Promise((r) => setTimeout(r, 200));
await shot('btn-hover.png', bclip);

const data = { page: PAGE, viewport: WIDTH, dsf: DSF, stripW: STRIP_W, btnClip: bclip, ...geo };
fs.writeFileSync(path.join(OUT, 'strip.json'), JSON.stringify(data, null, 1));
fs.writeFileSync(path.join(OUT, 'strip.js'), '/* generated by capture-storyboard.mjs */\nwindow.STRIP = ' + JSON.stringify(data) + ';\n');
console.log('captured ' + BEATS.join(', ') + ' of ' + PAGE_FILE + ': strip ' + STRIP_W + ' x ' + geo.height + ' CSS px, focus ' + BEATS[1]);
await browser.close();
