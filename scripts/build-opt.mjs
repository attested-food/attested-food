// Prover-friendly variants of every report, next to the originals (which stay untouched):
//   out/opt/template/  opt template (raster QR, no kerning, no bold) + normalize
//   out/opt/full/      template + optimize.mjs (one BT per page, flattened graphics, no XMP/ICC)
// each with raw/<id>.pdf, redacted/<id>.pdf + .manifest.json. Checks per variant: same text runs
// as out/raw/<id>.pdf (run sequence the guest extracts from), redact + check.mjs pass.
//
// S3 keys of the variants live in data/opt-keys.json ({ variant: { id: key } }); a missing key
// gets a fresh random one. Manifests carry the file's s3 location.
//
// usage: node scripts/build-opt.mjs [<id> ...]   (run scripts/build.mjs first)

import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { normalize } from "./normalize.mjs";
import { optimize } from "./optimize.mjs";
import { pageRuns } from "./redact.mjs";

const ids = process.argv.slice(2).length
  ? process.argv.slice(2)
  : readdirSync("data").filter((f) => f.endsWith(".json") && f !== "opt-keys.json").map((f) => f.slice(0, -5));
const VARIANTS = ["template", "full"];
mkdirSync("out/opt/typst", { recursive: true });
for (const v of VARIANTS) for (const d of ["raw", "redacted"]) mkdirSync(`out/opt/${v}/${d}`, { recursive: true });
const KEYS = "data/opt-keys.json";
let keys = {};
try {
  keys = JSON.parse(readFileSync(KEYS, "utf8"));
} catch {}

for (const id of ids) {
  const data = JSON.parse(readFileSync(`data/${id}.json`, "utf8"));
  const ts = String(Math.floor(Date.parse(data.report.issue_date + " 12:00:00 GMT+0530") / 1000));
  const url = `https://${data.s3.bucket}.s3.amazonaws.com/${data.s3.key}`;
  const typst = (...a) => execFileSync("typst", ["compile", "--ignore-system-fonts", "--creation-timestamp", ts, ...a], { stdio: "inherit" });
  typst("--format", "png", "--ppi", "216", "--input", `url=${url}`, "template/qr.typ", `out/opt/typst/${id}.qr.png`);
  typst("--root", ".", "--no-pdf-tags", "--input", `data=/data/${id}.json`, "--input", "opt=1",
    "--input", `qr=/out/opt/typst/${id}.qr.png`, "template/eurekha-report.typ", `out/opt/typst/${id}.pdf`);

  const template = normalize(readFileSync(`out/opt/typst/${id}.pdf`));
  const files = { template, full: optimize(template) };
  const runs = (b) => JSON.stringify(pageRuns(b).map((r) => r.trim())); // the guest trims runs
  const want = runs(readFileSync(`out/raw/${id}.pdf`));
  for (const v of VARIANTS) {
    const raw = `out/opt/${v}/raw/${id}.pdf`;
    writeFileSync(raw, files[v]);
    if (runs(files[v]) !== want) throw new Error(`${raw}: text runs differ from out/raw/${id}.pdf`);
    const red = `out/opt/${v}/redacted/${id}.pdf`;
    execFileSync("node", ["scripts/redact.mjs", raw, red, "--expect", `data/${id}.json`], { stdio: "inherit" });
    const manifest = red.replace(/\.pdf$/, ".manifest.json");
    execFileSync("node", ["scripts/check.mjs", raw, red, manifest], { stdio: "inherit" });
    keys[v] ??= {};
    keys[v][id] ??= `reports/2026/opt/${v}/${id}-${randomBytes(8).toString("hex")}.pdf`;
    const m = JSON.parse(readFileSync(manifest, "utf8"));
    m.original.s3 = { bucket: data.s3.bucket, key: keys[v][id] };
    writeFileSync(manifest, JSON.stringify(m, null, 2) + "\n");
  }
}

writeFileSync(KEYS, JSON.stringify(keys, null, 2) + "\n");
