# Read API

All endpoints are `GET`, JSON, read-only. Tables: [db/schema.sql](../db/schema.sql).

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
  ]
}
```

`lab` / `publisher` are `{id, name, url, accreditation}` or `null`. Numbers are JSON numbers, dates are `YYYY-MM-DD`.

## `GET /api/sources`

```json
[{"id": "uuid", "type": "website", "name": "Trustified", "url": "https://www.trustified.in",
  "accreditation": null, "description": "...", "report_count": 12}]
```

## `GET /api/categories`

```json
[{"category": "breakfast_cereal", "product_count": 1}]
```

## `GET /api/health`

`{"ok": true}`
