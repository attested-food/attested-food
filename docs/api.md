# Read API

All endpoints are JSON. Everything is read-only except `POST /api/test-requests`. Tables: [db/schema.sql](../db/schema.sql).

## `GET /api/products`

Query: `q` (search brand/name/variant), `brand`, `category`, `page` (1-based, default 1), `page_size` (default 24, max 100).

Filters, all optional:

- `dept`: a department key from `/api/departments` (e.g. `dairy`). `category` narrows further and wins over `dept`.
  Duplicate categories are folded (`instant_noodle` → `instant_noodles`), so either spelling matches.
- `brand`: one or more brands (repeat the parameter), case-insensitive.
- `grade`: one or more of `A`–`E`, matched against the latest third-party report. Scores map to letters by percentage
  (80+ A, 60+ B, 40+ C, 20+ D, else E); Pass = A, Fail = E; letter grades use their first letter (`B+` → B).

- `evidence`: `lab` (has an OpenLabel lab report) and/or `published` (only third-party published tests). Repeat it to
  allow both, e.g. `?evidence=lab&evidence=published`. Anything else is a 422.
- `no_added_sugar=true` (label says 0 g added sugar), `high_fibre=true` (6 g+ fibre), `high_protein=true` (20 g+
  protein), all per 100 g from `label_nutrition`. Products without that label value are left out.

Order: products with a lab report first, then those with a photo, then by brand and name.

```json
{
  "items": [
    {
      "id": "uuid",
      "brand": "Kellogg's",
      "name": "Millet Muesli",
      "variant": "Choco",
      "category": "breakfast_cereal",
      "image_url": null,
      "label_nutrition": {"sodium_mg": 236, "fiber_g": 7},
      "report_count": 1,
      "has_user_report": true,
      "latest": {
        "kind": "user",
        "verdict": null,
        "grade": null,
        "publisher": null,
        "lab": "Equinox Labs",
        "tested_on": "2026-11-03"
      }
    }
  ],
  "page": 1,
  "page_size": 24,
  "total": 1
}
```

`latest` is the report shown on cards: user reports win over fallback, then newest `tested_on` / `issued_on` / `created_at`.

## `GET /api/products/{id}`

Product plus every report (user reports first, then newest first), each with all results. 404 if unknown.

```json
{
  "id": "uuid",
  "brand": "Kellogg's",
  "name": "Millet Muesli",
  "variant": "Choco",
  "category": "breakfast_cereal",
  "manufacturer": null,
  "fssai_license": null,
  "barcode": null,
  "net_quantity": null,
  "image_url": null,
  "reports": [
    {
      "id": "uuid",
      "kind": "user",
      "lab": {"id": "uuid", "name": "Equinox Labs", "url": "https://www.equinoxlab.com", "accreditation": "NABL TC-6820"},
      "publisher": null,
      "source_url": null,
      "report_number": "EQNX:001:NL:26:10:09217",
      "ulr_number": "TC682026000108177F",
      "batch_no": "S6A280526",
      "mfg_date": "2026-05-28",
      "expiry_date": "2027-02-22",
      "tested_on": "2026-11-03",
      "issued_on": "2026-11-05",
      "verdict": null,
      "grade": null,
      "pdf_url": null,
      "pdf_sha256": null,
      "verification": "none",
      "verified": false,
      "chain_tx": null,
      "fetched_at": null,
      "results": [
        {"parameter": "Protein", "group": "nutrition", "unit": "g/100g", "value": 8.31, "value_raw": "8.31",
         "label_claim": null, "limit": null, "detection_limit": null, "method": "SOP-CHM-137-00", "status": null}
      ]
    }
  ],
  "tests": [{"name": "Nutrition vs label claims", "tested": true}]
}
```

Also returned: `ingredients` (text or null), `ingredients_source` (`open_food_facts` or null), `label_nutrition` (per 100 g: `energy_kcal`, `protein_g`, `sugars_g`,
`added_sugars_g`, `fiber_g`, `fat_g`, `saturated_fat_g`, `sodium_mg`, any subset, or null) and `annotations` for the
first report (see `/api/wall`).

`tests` is the test set for the product's category ([backend/category_tests.py](../backend/category_tests.py)), each marked tested if any report has a matching result.

`lab` / `publisher` are `{id, name, url, accreditation}` or `null`. Numbers are JSON numbers, dates are `YYYY-MM-DD`.

## OpenLabel grade

Product detail, list items and wall items carry `openlabel_grade` for products whose primary report is our own
(`kind: "user"`), else `null`:

```json
{"letter": "B", "score": 78, "provisional": false, "safety_failed": false,
 "parts": {"honesty": 88, "safety": null, "nutrition": 60}}
```

Label honesty 40%, safety 40%, nutrition 20%, over the parts that were tested; a failed safety test caps the
grade at D; `provisional` while any of the category's standard tests is untested. See
[backend/grading.py](../backend/grading.py).

## `GET /api/wall?limit=16`

Cards for the home page: products with their latest report (user reports first, then products with a photo,
ingredients and results), followed by up to `limit / 4` newest test requests. `limit` 1–48.

```json
{"items": [{
  "kind": "product", "id": "uuid", "brand": "Kellogg's", "name": "Millet Muesli", "variant": "Choco",
  "category": "breakfast_cereal", "image_url": "https://…", "ingredients": "MULTIGRAIN MIX (69.1%) …",
  "label_nutrition": {"sodium_mg": 236, "fiber_g": 7},
  "state": "tested", "grade": null, "grade_source": "Equinox Labs", "report_kind": "user",
  "lab": "Equinox Labs", "tested_on": "2026-11-03",
  "annotations": {
    "segments": [{"t": "IODIZED SALT", "mark": "circle", "note": "sodium 282.8 mg, +20% vs label"}],
    "findings": [{"parameter": "Sodium", "kind": "bad", "label": 236, "tested": 282.83, "unit": "mg",
                  "deviation_pct": 19.8, "text": "282.8 mg, +20% vs label"}],
    "counts": {"pass": 2, "fail": 1, "untested": 0}
  }
}]}
```

- `grade`: the source's own grade for fallback reports (`"86/100"`, `"A+"`, `"Pass"`); `null` for our own reports
  until grading exists. `state` is `tested` for products and `requested` for test requests.
- `annotations` come from [backend/annotate.py](../backend/annotate.py): a result is off its label when it differs from
  `label_claim` (or `label_nutrition`) by more than 10%; higher is worse for sugar, sodium, fat and energy, lower is
  worse for protein and fibre. `status` and `limit` decide the rest. `segments` join back to `ingredients`;
  `mark` is `under`, `circle`, `hl`, `good` or `null`. Notes hold numbers only.

## `GET /api/departments`

Shop departments in shelf order: `[{"key": "dairy", "name": "Dairy", "product_count": 98, "categories": [{"category": "milk", "product_count": 39}, …]}]`.
Every product falls in exactly one department (supplements and "other" catch the rest). Defined in
[backend/departments.py](../backend/departments.py).

## `GET /api/brands?dept=&category=&limit=30`

Brands with the most products, optionally within a department or category: `[{"brand": "Amul", "product_count": 12}]`.

## `GET /api/sources`

```json
[{"id": "uuid", "type": "website", "name": "Trustified", "url": "https://www.trustified.in",
  "accreditation": null, "description": "...", "report_count": 12}]
```

## `GET /api/categories`

```json
[{"category": "breakfast_cereal", "product_count": 1, "tests": ["Nutrition vs label claims"]}]
```

## `POST /api/test-requests`

Request a product to be tested. Required: `brand`, `name`, `category`, and exactly one of `image_url` (http/https)
or `image_data` (PNG/JPEG/WebP data URL, max 5 MB). Optional: `variant`, `net_quantity`, `manufacturer`,
`fssai_license` (14 digits), `barcode` (8-14 digits), `buy_url`.

- `201` `{"id": "uuid", "tests": ["..."]}`
- `409` `{"detail": {"message": "product already exists", "product_id": "uuid"}}` when brand + name + variant match an existing product (case-insensitive)
- `409` `{"detail": {"message": "already requested", "request": {...}}}` when the same Amazon ASIN (from `buy_url`) or brand + name + variant was already requested
- `422` validation error

## `GET /api/test-requests?q=&brand=&category=`

Newest 24 test requests matching the same filters as `/api/products`:
`[{"id", "brand", "name", "variant", "category", "requested_on", "image_url"}]`.

## `GET /api/duplicates?q=`

Products and test requests whose brand/name/variant contain at least 60% of the words in `q` (any order; a
brand found in `q` counts as two extra words), best match first, max 10: `[{"kind": "product" | "request", "id", "brand", "name", "variant", "category", "requested_on"}]`.

## `GET /api/test-requests/{id}`

One request plus `net_quantity`, `manufacturer`, `fssai_license`, `barcode`, `buy_url`, `image_url` and `tests`.
Uploaded images are served at `GET /api/test-requests/{id}/image`.

## `GET /api/prefill?url=`

Reads an amazon.in product link (short links like amzn.in are followed, only to Amazon hosts) and returns
`{asin, buy_url, brand, name, category, image_url, manufacturer, net_quantity, existing_request}`.
`existing_request` is set when that ASIN was already requested. `422` if not an Amazon product link, `502` if
Amazon didn't return the page (captcha/blocked).

## `GET /api/health`

`{"ok": true}`
