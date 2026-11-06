# Read API

All endpoints are JSON. Everything is read-only except `POST /api/test-requests`. Tables: [db/schema.sql](../db/schema.sql).

## `GET /api/products`

Query: `q` (search brand/name/variant), `brand`, `category`, `page` (1-based, default 1), `page_size` (default 24, max 100).

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

`tests` is the test set for the product's category ([backend/category_tests.py](../backend/category_tests.py)), each marked tested if any report has a matching result.

`lab` / `publisher` are `{id, name, url, accreditation}` or `null`. Numbers are JSON numbers, dates are `YYYY-MM-DD`.

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
- `422` validation error

## `GET /api/health`

`{"ok": true}`
