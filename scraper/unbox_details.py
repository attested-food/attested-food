"""Pack nutrition and back-of-pack photo links from Unbox Health.

Unbox lists each product's label claims as text ("Claims per 100g: 7.9g Protein, 21.2g Sugar, 316mg Sodium")
and keeps several photos per product, the later ones usually the back of the pack. This fills
products.label_nutrition from the claims (only when empty, only per-100 g claims) and stores the extra photo
links in products.pack_images for scraper/pack_reader.py.

One request for the whole catalogue. Dry run by default; pass --apply to write.
"""
import logging
import re
import sys

import orjson
from psycopg.types.json import Jsonb

from scraper.common import client, connect, norm, number, request
from scraper.unbox import API, CLAIM_RE, HEADERS

# Claim name (normalised) -> our label_nutrition key
KEYS = {
    "protein": "protein_g", "totalprotein": "protein_g",
    "sugar": "sugars_g", "sugars": "sugars_g", "totalsugar": "sugars_g", "totalsugars": "sugars_g",
    "addedsugar": "added_sugars_g", "addedsugars": "added_sugars_g",
    "fat": "fat_g", "totalfat": "fat_g",
    "saturatedfat": "saturated_fat_g", "saturatedfats": "saturated_fat_g", "satfat": "saturated_fat_g",
    "sodium": "sodium_mg",
    "fibre": "fiber_g", "fiber": "fiber_g", "dietaryfibre": "fiber_g", "dietaryfiber": "fiber_g",
    "energy": "energy_kcal", "calories": "energy_kcal", "calorie": "energy_kcal",
}
PER_100 = re.compile(r"Claims\s*(?:per\s*100\s*(?:g|gm|grams?|ml))?\s*:([^|]+)", re.I)
PER_UNIT = re.compile(r"per\s*(capsule|tablet|serv|scoop|sachet|bar\b|piece|cup|gumm|softgel|tbsp|tsp)", re.I)
PER_AMOUNT = re.compile(r"per\s*(\d+(?:\.\d+)?)\s*(?:g|gm|grams?|ml)\b", re.I)


def per_100(text: str) -> bool:
    """False when the claims are per serving / capsule / some amount other than 100 g."""
    if PER_UNIT.search(text):
        return False
    return all(float(m.group(1)) == 100 for m in PER_AMOUNT.finditer(text))


def claims_nutrition(highlight: str | None) -> dict:
    """Per-100 g label nutrition from an Unbox highlight, or {} if the claims aren't per 100 g or look wrong."""
    if not highlight:
        return {}
    m = PER_100.search(highlight)
    if not m or not per_100(highlight):
        return {}
    out: dict[str, float] = {}
    for c in CLAIM_RE.finditer(m.group(1)):
        value, unit, name = number(c.group(1)), (c.group(2) or "").lower(), norm(c.group(3))
        key = KEYS.get(name)
        if key is None or value is None or key in out:
            continue
        if key == "sodium_mg":
            value = value * 1000 if unit == "g" else value
        elif key == "energy_kcal":
            if unit == "kj":
                value = round(value / 4.184, 1)
            elif unit not in ("kcal", "cal", ""):
                continue
        elif unit not in ("g", "gm", ""):
            continue
        out[key] = value
    return out if plausible(out) else {}


def plausible(n: dict) -> bool:
    if not n:
        return False
    if n.get("energy_kcal", 0) > 900 or n.get("sodium_mg", 0) > 40000:
        return False
    if any(n.get(k, 0) > 100 for k in ("protein_g", "sugars_g", "added_sugars_g", "fat_g", "saturated_fat_g", "fiber_g")):
        return False
    if n.get("added_sugars_g", 0) > n.get("sugars_g", 100) or n.get("saturated_fat_g", 0) > n.get("fat_g", 100):
        return False
    return True


UNBOX_PRODUCTS = """
SELECT DISTINCT r.product_id, regexp_replace(r.source_url, '^.*/', '') AS unbox_id
FROM reports r JOIN sources s ON s.id = r.publisher_id
WHERE s.name = 'Unbox Health' AND r.source_url IS NOT NULL
"""

UPDATE = """
UPDATE products SET
    label_nutrition_source = CASE WHEN label_nutrition IS NULL AND %(nutrition)s::jsonb IS NOT NULL THEN 'unbox_claims'
                                  ELSE label_nutrition_source END,
    label_nutrition = coalesce(label_nutrition, %(nutrition)s),
    pack_images = coalesce(pack_images, %(images)s)
WHERE id = %(id)s
"""


def main(apply: bool) -> None:
    conn = connect()
    ours = {row[1]: row[0] for row in conn.execute(UNBOX_PRODUCTS).fetchall()}
    with client() as http:
        r = request(http, "POST", f"{API}/get_products_list", headers=HEADERS, content=orjson.dumps({"query": "", "page": 1, "size": 1000}))
        items = orjson.loads(r.content)["product"]["items"]
    stats = {"unbox": len(items), "matched": 0, "nutrition": 0, "images": 0}
    for item in items:
        pid = ours.get(str(item.get("product_id")))
        if not pid:
            continue
        stats["matched"] += 1
        nutrition = claims_nutrition(item.get("product_highlight"))
        images = [u for u in (item.get("all_images") or [])[1:] if isinstance(u, str) and u.startswith("https://")]
        stats["nutrition"] += bool(nutrition)
        stats["images"] += bool(images)
        if apply:
            conn.execute(UPDATE, {"id": pid, "nutrition": Jsonb(nutrition) if nutrition else None, "images": Jsonb(images) if images else None})
    logging.info("Unbox details: %s", stats)
    print(stats)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    main("--apply" in sys.argv)
