# Database schema (MVP)

User lab reports and fallback data from trusted websites share the same tables, distinguished by `reports.kind`.

## Product identity (MVP)

`products.id` is our own UUID. During scraping, Claude Code decides by hand which product a scraped report belongs to (same brand + name + variant/flavour = same product; pack size ignored). No automated cross-source matching yet; revisit later (barcodes/GTINs, per-source IDs, a lookup table).

## Tables

```json
{
  "products": {
    "id": "uuid PK, ours",
    "brand": "text",
    "name": "text",
    "variant": "text | null",
    "category": "text",
    "image_url": "text | null"
  },

  "sources": {
    "id": "uuid PK",
    "type": "lab | website",
    "name": "text",
    "url": "text",
    "accreditation": "text | null"
  },

  "reports": {
    "id": "uuid PK",
    "product_id": "FK products",
    "kind": "user | fallback",
    "lab_id": "FK sources (type=lab) | null",
    "publisher_id": "FK sources (type=website) | null",
    "source_url": "text | null",
    "report_number": "text | null",
    "ulr_number": "text | null",
    "batch_no": "text | null",
    "mfg_date": "date | null",
    "expiry_date": "date | null",
    "tested_on": "date | null",
    "issued_on": "date | null",
    "verdict": "pass | fail | grade | null",
    "grade": "text | null",
    "pdf_url": "text | null",
    "pdf_sha256": "text | null",
    "verification": "zk_email | zk_tls | signature | none",
    "verified": "bool",
    "chain_tx": "text | null",
    "fetched_at": "timestamptz | null",
    "created_at": "timestamptz"
  },

  "results": {
    "id": "uuid PK",
    "report_id": "FK reports",
    "parameter": "text",
    "group": "nutrition | heavy_metal | toxin | pesticide | spiking | other",
    "unit": "text",
    "value": "numeric | null",
    "value_raw": "text, as printed e.g. <1.0, Not detected",
    "label_claim": "numeric | null",
    "limit": "numeric | null, regulatory or spec limit",
    "detection_limit": "numeric | null, lab LOQ/LOD (not a safety limit)",
    "method": "text | null",
    "status": "pass | fail | null"
  }
}
```

## Notes

- No personal data columns: customer name, address and contact are never stored.
- Fallback reports have both a `publisher_id` (e.g. Unbox Health) and a `lab_id` (e.g. Eurofins).
- Display per product: verified `user` reports first, else `fallback` reports with attribution, else a funding campaign.
- Campaigns and user accounts are out of scope for now (smart contract + `campaigns` table later).
