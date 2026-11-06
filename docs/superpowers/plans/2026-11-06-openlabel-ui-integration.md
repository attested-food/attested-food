# OpenLabel UI + backend integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder SvelteKit UI with the OpenLabel design (drifting label wall, peelable cards, marketplace, tests pages) on live data, and add ingredients + automatic label-vs-lab notes to the backend.

**Architecture:** Backend gains two product columns (ingredients, label nutrition), a pure rule-based `annotate` module that turns ingredients + results into marked segments and findings, and a `/api/wall` endpoint for the home page. Frontend keeps SvelteKit (Svelte 5 runes, static SPA) and the existing `$lib/api.ts` client; pages are rebuilt with shared components. Funding/campaigns stay frontend placeholders.

**Tech Stack:** FastAPI + psycopg (Postgres on Render), SvelteKit 2 / Svelte 5 / adapter-static, plain CSS, pytest.

**Spec:** Design mockups on the OpenLabel canvas (Home, Marketplace, Tests boards; local copies in the session scratchpad `design/project/*.dc.html`), plus these decisions from the design conversation:
- States: Requested, Funding, Funded, Tested. Funding/Funded are placeholders (no backend).
- Grades: fallback reports show the source's own grade (`reports.grade` / `verdict`) credited to the source; our own (`kind = 'user'`) reports show "Grade pending" until grading logic exists.
- Card front: photo, category, state tag, brand, name, plain ingredient list, label nutrition table. No grade, findings or marks on the front.
- Card back (after peel): grade, counted pass / fail / not tested, ingredients with marks + notes inferred automatically from label vs test deviation, findings rows, actions.
- No written verdict sentences. Notes state numbers only.
- No upload-a-report feature. Home nav: Marketplace, How it works, Sign in only.
- Palette: deep green `#1D4A37`, gold `#C6A26B` (gold text on green for buttons and logo, no gold borders), paper `#FBF9F4`, near-black `#141414`. Fonts: Geist (UI), Geist Mono (small labels), Barlow Condensed (label text).

## Global Constraints

- Database changes are additive only (`ADD COLUMN IF NOT EXISTS`, `UPDATE` of new columns). No deletes, no rewrites of existing columns.
- Never run tests or scripts that `POST` to the production API or insert into `test_requests`.
- Deviation threshold: a tested value counts as off its label when it differs by more than 10% (same rule as the existing product page).
- Notes and findings contain numbers and facts only, never judgement sentences.
- Product photos credited "Open Food Facts contributors, CC BY-SA" where they come from OFF.
- Branch `feat/openlabel-ui`, PR to `main`. Do not push to `main`.

## Review Focus

- Product with no image: card still renders (neutral pack placeholder, no broken image icon).
- Product with no ingredients and no results: back shows "Not tested yet" counts and no empty ingredient block.
- Ingredient text with nested brackets and percentages (`Malt (66.7%) [Barley (32%), ...]`): splitting must not break inside brackets.
- Result with `value` null and `value_raw` like `<1.0` or `Not detected`: no deviation, no crash.
- Drag vs click on the wall: dragging must not peel a card; clicking a label must.

---

### Task 1: Ingredients + label nutrition columns, OFF backfill script

**Files:**
- Modify: `db/schema.sql` (append ALTERs)
- Create: `scraper/off_details.py`
- Test: `scraper/test_parsers.py` (add OFF mapping test)

**Interfaces:**
- Produces: `products.ingredients text`, `products.ingredients_source text`, `products.label_nutrition jsonb` shaped `{"energy_kcal": n, "protein_g": n, "sugars_g": n, "added_sugars_g": n, "fiber_g": n, "fat_g": n, "saturated_fat_g": n, "sodium_mg": n}` (keys present only when known, per 100 g).
- Produces: `off_nutrition(nutriments: dict) -> dict` in `scraper/off_details.py`.

- [ ] Append to `db/schema.sql`: `ALTER TABLE products ADD COLUMN IF NOT EXISTS ingredients text; ... ingredients_source text; ... label_nutrition jsonb;`
- [ ] Test `test_off_nutrition_maps_and_converts`: `off_nutrition({"energy-kcal_100g": 375, "proteins_100g": 7.8, "sugars_100g": 20.8, "added-sugars_100g": 13.7, "fiber_100g": 7, "sodium_100g": 0.236})` → `{"energy_kcal": 375, "protein_g": 7.8, "sugars_g": 20.8, "added_sugars_g": 13.7, "fiber_g": 7, "sodium_mg": 236}`; missing keys omitted; non-numeric values dropped.
- [ ] Implement `off_nutrition` and `main(apply: bool)`: for products missing `ingredients`, look up OFF by `barcode` (`/api/v2/product/{code}`) else search (same brand/name-overlap matching as `scraper/off_images.find_image`); take `ingredients_text_en or ingredients_text`; skip implausible nutrition (energy_kcal > 900, sugars > 100). `--apply` writes `ingredients`, `ingredients_source = 'open_food_facts'`, `label_nutrition`, and `image_url` only if null.
- [ ] Run `uv run pytest scraper/test_parsers.py -q` → pass. Commit.

### Task 2: `backend/annotate.py` (pure)

**Files:**
- Create: `backend/annotate.py`
- Test: `tests/test_annotate.py`

**Interfaces:**
- Produces:
  - `split_ingredients(text: str) -> list[str]` top-level comma split, brackets respected.
  - `findings(results: list[dict], label_nutrition: dict | None) -> list[dict]` each `{"parameter", "kind": "good"|"bad"|"info"|"unk", "label": float|None, "tested": float|None, "unit": str|None, "deviation_pct": float|None, "text": str}`.
  - `segments(ingredients: str | None, name: str, fnds: list[dict]) -> list[dict]` each `{"t": str, "mark": None|"under"|"circle"|"hl"|"good", "note": str|None}`.
  - `summarize(product: dict) -> dict` → `{"segments": [...], "findings": [...], "counts": {"pass": n, "fail": n, "untested": n}}`.
- Rules (decisions):
  - Label value comes from `result.label_claim`, else `label_nutrition` mapped by parameter keyword (energy, protein, total sugar → sugars_g, added sugar, fibre/fiber, total fat, saturated, sodium; unit-aware: sodium mg).
  - Deviation > 10%: higher-is-worse params (sugar, sodium, fat, saturated, energy) → `bad` when tested above label, `good` when ≥10% below; higher-is-better (protein, fibre) the reverse. Within 10% → `info`.
  - `status == 'fail'` or value above `limit` → `bad`; `status == 'pass'` → `good`. No label and no limit → `info`.
  - Text format: `"283 mg, +20% vs label"`, `"8.0 g / 100 g"` for info. Numbers rounded to 1 decimal.
  - Segment marks: sugar words (sugar, jaggery, honey, glucose, syrup, maltodextrin, dextrose, fructose) → `hl`, note on the first only from the sugar finding; salt/sodium words → `circle` when sodium finding is `bad`; fibre words (bran, fibre, fiber) → `good` when fibre finding `good`/`info`; millet aliases (ragi, jowar, bajra, millet, foxtail, kodo, barnyard, proso) when product name contains "millet" → `circle` with note `"millets ~N%"` from summed percentages when total < 50%, else `good` with the same note.
- [ ] Tests (Kellogg's fixture: ingredients from the canvas mockup, results sodium 282.83 vs label 236, added sugars 14.87 vs 13.7, fibre 8.01 vs 7.0, protein 8.31 vs 7.8):
  - `test_split_respects_brackets`: `"Malt (66.7%) [Barley (32%), Wheat], sugar"` → `["Malt (66.7%) [Barley (32%), Wheat]", "sugar"]`
  - `test_findings_sodium_over_label`: sodium finding `kind == "bad"`, `deviation_pct == 19.8`, text `"282.8 mg, +20% vs label"`
  - `test_findings_fibre_good`: fibre `kind == "good"`
  - `test_findings_raw_value_no_crash`: result `{"value": None, "value_raw": "<1.0"}` → `kind == "info"`, deviation None
  - `test_segments_millet_share`: ragi/jowar segments `mark == "circle"`, one note `"millets ~11%"`
  - `test_segments_sugar_highlight`: sugar segment `mark == "hl"`
  - `test_summary_counts`: counts pass=1 (fibre), fail=2 (sodium, added sugar)
  - `test_no_ingredients`: `segments(None, "x", [])` → `[]`
- [ ] Run `uv run pytest tests/test_annotate.py -q` → pass. Commit.

### Task 3: API: expose fields, `/api/wall`

**Files:**
- Modify: `backend/main.py` (DETAIL_SQL select list, product detail handler, new route)
- Modify: `docs/api.md`
- Test: `tests/test_api.py` (read-only tests only)

**Interfaces:**
- Consumes: `annotate.summarize`.
- Produces:
  - `GET /api/products/{id}` adds `ingredients`, `label_nutrition`, `annotations` (`summarize` output for the primary report = first in order).
  - `GET /api/wall?limit=16` → `{"items": [WallItem]}`, `WallItem = {"kind": "product"|"request", "id", "brand", "name", "variant", "category", "image_url", "ingredients", "label_nutrition", "state": "tested"|"requested", "grade": str|null, "grade_source": str|null, "lab": str|null, "tested_on": str|null, "annotations": {...}}`. Products first ordered: has user report, has image, has results; then newest requests. `limit` 1–48.
- [ ] Tests: `test_wall_shape` (keys == WallItem keys, `limit` respected), `test_detail_has_annotations` (Kellogg's `annotations.counts` has keys pass/fail/untested).
- [ ] Run read-only API tests: `uv run pytest tests/test_api.py -q -k "not request and not prefill"` → pass. Commit.

### Task 4: Design system, layout, shared components

**Files:**
- Modify: `frontend/src/app.html` (font links), `frontend/src/app.css` (replace)
- Modify: `frontend/src/routes/+layout.svelte`
- Create: `frontend/src/lib/components/SiteHeader.svelte`, `StateTag.svelte`, `GradeBox.svelte`, `Segments.svelte`, `LabelCard.svelte`
- Create: `frontend/src/lib/placeholders.ts`
- Modify: `frontend/src/lib/api.ts` (types `WallItem`, `Annotations`, `Finding`, `Segment`; Product gets `ingredients`, `label_nutrition`, `annotations`)
- Delete: `frontend/src/routes/upload/`

**Interfaces:**
- `SiteHeader` props `{ overlay?: boolean }` (overlay = Home: gradient over content, links Marketplace + How it works + Sign in).
- `LabelCard` props `{ item: WallItem, theme: 'light' | 'dark', peeled: boolean, onpeel: () => void, onunpeel: () => void }`; 600×380; front/back as in the canvas Home board (Task spec: front no spoilers; back hidden until peeled; curl 96px traced path).
- `placeholders.ts` exports `FUNDING: { productHint: string; pct: number; raised: string; goal: string; backers: string; daysLeft: string; state: 'funding' | 'funded' }[]` clearly marked placeholder.
- [ ] `npm run check` → 0 errors. Commit.

### Task 5: Home wall

**Files:** Modify `frontend/src/routes/+page.svelte`.
- Consumes `GET /api/wall`, `LabelCard`, `SiteHeader overlay`.
- Behaviour: 4×4 wrapped grid, card 600×380, gap 32; drift speed 0.3 px/frame with direction changes every 5–9 s; cursor steering 1.1; drag; wheel; peeled cards slow drift to 20%; click-vs-drag threshold 6 px; reduced motion = still; bottom floating CTAs (Find better food, Request a test, Fund a test) on gradient.
- [ ] Verify in browser (local backend against DB, read-only): wall renders 16 cards with live data, clicking a label peels it, drag does not. Commit.

### Task 6: Marketplace `/products` and product page `/products/[id]`

- Rebuild both in the canvas Marketplace design; product page shows label vs lab table (label from `label_claim` or `label_nutrition`), annotated ingredients, source attribution notice for fallback, tests coverage, reports list.
- [ ] `npm run check`, browser check of `/products?q=muesli` and the Kellogg's page. Commit.

### Task 7: Tests `/tests`, `/request`, `/requests/[id]`, `/sources`, `/about`

- `/tests`: tabs Requested (live `GET /api/test-requests`), Funding, Funded (placeholders), Tested (products with user reports via `/api/products`).
- `/request`: same logic as the existing page, restyled.
- [ ] `npm run check`, `npm run build`, browser check without submitting. Commit, push branch, open PR.
