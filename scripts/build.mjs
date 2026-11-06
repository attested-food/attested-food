// data/<id>.json -> out/typst/<id>.pdf (Typst) -> out/raw/<id>.pdf (normalized, goes to S3)
//                -> out/redacted/<id>.pdf + .manifest.json (what the holder would publish), checked.
//
// usage: node scripts/build.mjs [<id> ...]   (default: every data/*.json)

import { execFileSync } from "node:child_process";
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { normalize } from "./normalize.mjs";

const ids = process.argv.slice(2).length
  ? process.argv.slice(2)
  : readdirSync("data").filter((f) => f.endsWith(".json") && f !== "opt-keys.json").map((f) => f.slice(0, -5));
for (const d of ["typst", "raw", "redacted"]) mkdirSync(`out/${d}`, { recursive: true });

for (const id of ids) {
  const data = JSON.parse(readFileSync(`data/${id}.json`, "utf8"));
  // Fixed timestamp from the issue date so a rebuild gives the same bytes.
  const ts = String(Math.floor(Date.parse(data.report.issue_date + " 12:00:00 GMT+0530") / 1000));
  execFileSync("typst", [
    "compile", "--root", ".", "--no-pdf-tags", "--ignore-system-fonts", "--creation-timestamp", ts,
    "--input", `data=/data/${id}.json`, "template/eurekha-report.typ", `out/typst/${id}.pdf`,
  ], { stdio: "inherit" });
  writeFileSync(`out/raw/${id}.pdf`, normalize(readFileSync(`out/typst/${id}.pdf`)));
  execFileSync("node", ["scripts/redact.mjs", `out/raw/${id}.pdf`, `out/redacted/${id}.pdf`, "--expect", `data/${id}.json`], { stdio: "inherit" });
  execFileSync("node", ["scripts/check.mjs", `out/raw/${id}.pdf`, `out/redacted/${id}.pdf`, `out/redacted/${id}.manifest.json`], { stdio: "inherit" });
  const manifest = `out/redacted/${id}.manifest.json`;
  const m = JSON.parse(readFileSync(manifest, "utf8"));
  m.original.s3 = { bucket: data.s3.bucket, key: data.s3.key };
  writeFileSync(manifest, JSON.stringify(m, null, 2) + "\n");
}
