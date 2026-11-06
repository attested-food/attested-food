"""Fill missing ingredient lists and label nutrition (per 100 g) from Open Food Facts.

Looks a product up by barcode first, then by search (brand must appear, name words must overlap).
Dry run by default; pass --apply to write. Only fills empty columns, never overwrites.
"""
import logging
import re
import sys
import time

import httpx
from psycopg.types.json import Jsonb

from scraper.common import USER_AGENT, connect

PRODUCT = "https://world.openfoodfacts.org/api/v2/product/{code}.json"
SEARCH = "https://search.openfoodfacts.org/search"
FIELDS = "code,product_name,brands,image_front_url,countries_tags,ingredients_text_en,ingredients_text,nutriments"

MISSING = """
SELECT id, brand, name, variant, barcode, image_url FROM products
WHERE ingredients IS NULL OR label_nutrition IS NULL
ORDER BY (EXISTS (SELECT 1 FROM reports r WHERE r.product_id = products.id AND r.kind = 'user')) DESC, brand, name
"""

UPDATE = """
UPDATE products SET
    ingredients = coalesce(ingredients, %(ingredients)s),
    ingredients_source = coalesce(ingredients_source, CASE WHEN %(ingredients)s::text IS NULL THEN NULL ELSE 'open_food_facts' END),
    label_nutrition = coalesce(label_nutrition, %(nutrition)s),
    image_url = coalesce(image_url, %(image)s)
WHERE id = %(id)s
"""

# Pack barcodes we have checked by hand, keyed by (brand, name, variant). Used for lookup only; the
# products.barcode column is left alone.
KNOWN_CODES = {
    ("Kellogg's", "Millet Muesli", "Choco"): "8901499027610",
}

# OFF nutriment key -> (our key, multiplier)
NUTRIENTS = {
    "energy-kcal_100g": ("energy_kcal", 1),
    "proteins_100g": ("protein_g", 1),
    "sugars_100g": ("sugars_g", 1),
    "added-sugars_100g": ("added_sugars_g", 1),
    "fiber_100g": ("fiber_g", 1),
    "fat_100g": ("fat_g", 1),
    "saturated-fat_100g": ("saturated_fat_g", 1),
    "sodium_100g": ("sodium_mg", 1000),
}


def off_nutrition(nutriments: dict) -> dict:
    """Map OFF nutriments to our per-100 g keys. Returns {} when the values can't be right."""
    out = {}
    for key, (ours, mult) in NUTRIENTS.items():
        value = nutriments.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            out[ours] = round(value * mult, 3) if mult != 1 else value
    if out.get("energy_kcal", 0) > 900:
        return {}
    if "added_sugars_g" in out and out["added_sugars_g"] > out.get("sugars_g", 100):
        return {}
    if any(out.get(k, 0) > 100 for k in ("protein_g", "sugars_g", "fiber_g", "fat_g")):
        return {}
    return out


def words(text: str | None) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2}


def sold_in_india(hit: dict) -> bool:
    return "en:india" in (hit.get("countries_tags") or []) or str(hit.get("code") or "").startswith("890")


def clean_ingredients(text: str | None) -> str | None:
    """OFF marks allergens as _wheat_; drop the markers and tidy spaces."""
    if not text:
        return None
    text = re.sub(r"_+", "", text)
    return re.sub(r"\s+", " ", text).strip() or None


def pick(hits: list[dict], brand: str, name: str, variant: str | None) -> dict | None:
    """Best search hit: sold in India, brand overlaps, and most of our name words appear."""
    want_brand, want_name = words(brand), words(f"{name} {variant or ''}")
    best = None
    for hit in hits:
        if not sold_in_india(hit):
            continue
        brands = hit.get("brands") or []
        brand_text = " ".join(brands) if isinstance(brands, list) else str(brands)
        if not want_brand & words(f"{brand_text} {hit.get('product_name')}"):
            continue
        overlap = len(want_name & words(hit.get("product_name")))
        if not want_name or overlap / len(want_name) < 0.75:
            continue
        score = (overlap / len(want_name), -len(words(hit.get("product_name"))))
        if best is None or score > best[0]:
            best = (score, hit)
    return best[1] if best else None


def lookup(http: httpx.Client, brand: str, name: str, variant: str | None, barcode: str | None) -> dict | None:
    if barcode:
        r = http.get(PRODUCT.format(code=barcode), params={"fields": FIELDS})
        if r.status_code == 200 and r.json().get("status") == 1:
            return r.json()["product"]
    r = http.get(SEARCH, params={"q": f"{brand} {name} {variant or ''}", "page_size": 20, "fields": FIELDS})
    r.raise_for_status()
    hit = pick(r.json().get("hits", []), brand, name, variant)
    if not hit or not hit.get("code"):
        return hit
    full = http.get(PRODUCT.format(code=hit["code"]), params={"fields": FIELDS})
    if full.status_code == 200 and full.json().get("status") == 1:
        return {**hit, **full.json()["product"]}
    return hit


def main(apply: bool, limit: int | None = None, delay: float = 3.0, known_only: bool = False) -> None:
    conn = connect()
    rows = conn.execute(MISSING).fetchall()
    if known_only:
        rows = [row for row in rows if (row[1], row[2], row[3]) in KNOWN_CODES]
    rows = rows[:limit]
    found = 0
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30) as http:
        for pid, brand, name, variant, barcode, image in rows:
            time.sleep(delay)
            try:
                hit = lookup(http, brand, name, variant, barcode or KNOWN_CODES.get((brand, name, variant)))
            except httpx.HTTPError:
                logging.exception("OFF lookup failed for %s %s", brand, name)
                continue
            if not hit:
                continue
            ingredients = clean_ingredients(hit.get("ingredients_text_en") or hit.get("ingredients_text"))
            nutrition = off_nutrition(hit.get("nutriments") or {}) or None
            if not ingredients and not nutrition:
                continue
            found += 1
            print(f"{brand} | {name} -> {hit.get('product_name')} | ingredients={bool(ingredients)} nutrition={bool(nutrition)}")
            if apply:
                conn.execute(UPDATE, {"id": pid, "ingredients": ingredients,
                                      "nutrition": Jsonb(nutrition) if nutrition else None,
                                      "image": None if image else hit.get("image_front_url")})
    print(f"{found}/{len(rows)} matched")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    lim = next((int(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--limit=")), None)
    main("--apply" in sys.argv, lim, known_only="--known" in sys.argv)
