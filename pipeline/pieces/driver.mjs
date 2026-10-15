// pieces/driver.mjs: render frame ranges of one HyperFrames composition through the producer's distributed
// protocol (plan, renderChunk), so a reel can be rendered in pieces and only the dirty ones re-rendered.
//
//   node driver.mjs plan    <srcDir> <planDir> [--format png-sequence|mp4]  freeze the composition once
//   node driver.mjs slices  <planDir> <slices.json>                        set the frame ranges, re-seal the plan
//   node driver.mjs chunk   <planDir> <index> <out>                        render one range (png dir or mp4)
//   node driver.mjs info                                                    the producer module and versions
//
// Every command prints one JSON line on stdout (logs go to stderr). Chunks are seek windows over the frozen
// composition: composition times are never rebased. The plan's uniform chunk list is replaced by our own ranges
// (beat aligned), and plan.json's planHash is recomputed with the producer's own recipe (computePlanHash below is
// a line-for-line port of producer/src/services/render/stages/planHash.ts in hyperframes 0.8.139), so renderChunk's
// integrity check still guards every byte of the plan. A producer upgrade that changes the recipe fails loudly
// (PLAN_HASH_MISMATCH), never silently.
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const HF_VERSION = process.env.PIECES_HF_VERSION || "0.8.139";

function out(obj) {
  process.stdout.write(`${JSON.stringify(obj)}\n`);
}

function die(msg) {
  process.stderr.write(`[pieces] ${msg}\n`);
  process.exit(2);
}

// ---- locate the producer bundled inside the pinned CLI (the npx cache), never a different version
function findProducer() {
  if (process.env.PIECES_PRODUCER) return process.env.PIECES_PRODUCER;
  const roots = [join(process.env.npm_config_cache || join(homedir(), ".npm"), "_npx")];
  for (const root of roots) {
    if (!existsSync(root)) continue;
    for (const d of readdirSync(root)) {
      const pkgDir = join(root, d, "node_modules", "hyperframes");
      const pj = join(pkgDir, "package.json");
      if (!existsSync(pj)) continue;
      if (JSON.parse(readFileSync(pj, "utf-8")).version !== HF_VERSION) continue;
      const dist = join(pkgDir, "dist");
      // the producer entry is the small src-*.js that re-exports plan + renderChunk
      const hits = readdirSync(dist)
        .filter((f) => /^src-.*\.js$/.test(f))
        .map((f) => join(dist, f))
        .filter((f) => {
          const t = readFileSync(f, "utf-8");
          return /\brenderChunk\b/.test(t) && /\bplanV2\b/.test(t) && /\bcreateProducerApp\b/.test(t);
        });
      if (hits.length) return hits.sort((a, b) => statSync(a).size - statSync(b).size)[0];
    }
  }
  die(`hyperframes@${HF_VERSION} producer not found in the npx cache: run \`npx -y hyperframes@${HF_VERSION} --version\` once`);
}

async function producer() {
  const path = findProducer();
  return { path, mod: await import(pathToFileURL(path).href) };
}

// the producer's messages on stderr with elapsed milliseconds, so a slow stage shows where the time went
const T0 = Date.now();
const stamp = (level) => (msg, meta) =>
  process.stderr.write(`[${String(Date.now() - T0).padStart(6)}ms ${level}] ${msg}${meta ? ` ${JSON.stringify(meta)}` : ""}\n`);
const logger = { debug: () => {}, info: stamp("info"), warn: stamp("warn"), error: stamp("error"),
  isLevelEnabled: (level) => level !== "debug" };

// ---- producer planHash recipe (port; see header)
const PLAN_HASH_SCHEMA_PREFIX = "hyperframes-plan-hash-v1\0";
const DELIM = Buffer.from([0]);
const COMPILED_INDEX = "compiled/index.html";
const HASH_EXCLUDED = new Set(["plan.json", "meta/encoder.json", COMPILED_INDEX]);

function listPlanFiles(planDir) {
  const root = resolve(planDir);
  const files = [];
  const walk = (dir) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, e.name);
      if (e.isDirectory()) walk(full);
      else if (e.isFile()) files.push({ rel: relative(root, full).split(/[\\/]+/).join("/"), full });
    }
  };
  walk(root);
  files.sort((a, b) => (a.rel < b.rel ? -1 : 1));
  return files;
}

function sha256Hex(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function computePlanHash(planDir) {
  const plan = JSON.parse(readFileSync(join(planDir, "plan.json"), "utf-8"));
  const encoderJson = readFileSync(join(planDir, "meta", "encoder.json"), "utf-8");
  let html = null;
  const assets = [];
  for (const f of listPlanFiles(planDir)) {
    if (f.rel === COMPILED_INDEX) {
      html = readFileSync(f.full);
      continue;
    }
    if (HASH_EXCLUDED.has(f.rel)) continue;
    assets.push({ path: f.rel, sha256: sha256Hex(readFileSync(f.full)) });
  }
  if (html === null) die(`no ${COMPILED_INDEX} in ${planDir}`);
  const h = createHash("sha256");
  h.update(PLAN_HASH_SCHEMA_PREFIX, "utf8");
  h.update(html);
  h.update(DELIM);
  assets.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  for (const a of assets) {
    h.update(a.path, "utf8");
    h.update(DELIM);
    h.update(a.sha256, "utf8");
    h.update(DELIM);
  }
  h.update(plan.fontSnapshotSha, "utf8");
  h.update(DELIM);
  h.update(encoderJson, "utf8");
  h.update(DELIM);
  h.update(plan.producerVersion, "utf8");
  h.update(DELIM);
  h.update(plan.ffmpegVersion, "utf8");
  h.update(DELIM);
  const d = plan.dimensions;
  h.update(`${d.fpsNum}/${d.fpsDen}x${d.width}x${d.height}x${d.format}`, "utf8");
  return h.digest("hex");
}

// ---- commands
async function cmdPlan(srcDir, planDir, format) {
  const { mod, path } = await producer();
  const t0 = Date.now();
  const res = await mod.plan(
    resolve(srcDir),
    {
      fps: 30,
      format,
      quality: "high",
      // one placeholder chunk: `slices` replaces the list with the beat-aligned pieces
      chunkSize: 1000000,
      maxParallelChunks: 1,
      // the dense v1 layout copies every extracted frame in; the default 2 GB Lambda cap does not apply here
      planDirSizeLimitBytes: 20 * 1024 ** 3,
      rejectOnSystemFonts: process.env.PIECES_ALLOW_SYSTEM_FONTS ? false : undefined,
      logger,
    },
    resolve(planDir),
  );
  // the producer's own hash must equal our port, or the re-seal in `slices` would be wrong
  const ours = computePlanHash(planDir);
  if (ours !== res.planHash) die(`planHash port mismatch: producer ${res.planHash}, port ${ours}`);
  out({ ok: true, cmd: "plan", ms: Date.now() - t0, producer: path, ...res });
}

function cmdSlices(planDir, slicesPath) {
  const t0 = Date.now();
  const slices = JSON.parse(readFileSync(slicesPath, "utf-8"));
  const planPath = join(planDir, "plan.json");
  const plan = JSON.parse(readFileSync(planPath, "utf-8"));
  slices.forEach((s, i) => {
    if (s.index !== i || !(s.startFrame >= 0) || !(s.endFrame > s.startFrame) || s.endFrame > plan.totalFrames)
      die(`bad slice ${JSON.stringify(s)} (totalFrames ${plan.totalFrames})`);
  });
  writeFileSync(join(planDir, "meta", "chunks.json"), `${JSON.stringify(slices, null, 2)}\n`, "utf-8");
  plan.chunkCount = slices.length;
  writeFileSync(planPath, `${JSON.stringify(plan, null, 2)}\n`, "utf-8");
  plan.planHash = computePlanHash(planDir);
  writeFileSync(planPath, `${JSON.stringify(plan, null, 2)}\n`, "utf-8");
  out({ ok: true, cmd: "slices", ms: Date.now() - t0, planHash: plan.planHash, chunkCount: slices.length });
}

async function cmdChunk(planDir, index, outPath) {
  const { mod } = await producer();
  const t0 = Date.now();
  const r = await mod.renderChunk(resolve(planDir), Number(index), resolve(outPath));
  out({ ok: true, cmd: "chunk", ms: Date.now() - t0, ...r });
}

async function cmdInfo() {
  const { mod, path } = await producer();
  out({ ok: true, cmd: "info", producer: path, hfVersion: HF_VERSION, exports: ["plan", "renderChunk"].filter((k) => typeof mod[k] === "function") });
}

const [cmd, ...args] = process.argv.slice(2);
const flag = (name, dflt) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : dflt;
};
try {
  if (cmd === "plan") await cmdPlan(args[0], args[1], flag("--format", "png-sequence"));
  else if (cmd === "slices") cmdSlices(args[0], args[1]);
  else if (cmd === "chunk") await cmdChunk(args[0], args[1], args[2]);
  else if (cmd === "info") await cmdInfo();
  else die("usage: driver.mjs plan <src> <planDir> [--format f] | slices <planDir> <slices.json> | chunk <planDir> <i> <out> | info");
  process.exit(0);
} catch (err) {
  process.stderr.write(`${err && err.stack ? err.stack : String(err)}\n`);
  out({ ok: false, cmd, error: err && err.message ? err.message : String(err), code: err && err.code });
  process.exit(1);
}
