"""Fill missing product images from Open Food Facts (brand and name overlap must match)."""
import logging
import sys

import httpx

from scraper.common import USER_AGENT, connect, norm

SEARCH = "https://search.openfoodfacts.org/search"
MISSING = """
SELECT id, brand, name, variant FROM products WHERE image_url IS NULL AND EXISTS (
  SELECT 1 FROM reports r JOIN sources s ON s.id = r.publisher_id WHERE r.product_id = products.id AND s.name = 'Consumer Voice')
"""


def tokens(text: str) -> set[str]:
    return {t for t in norm(text).split() if len(t) > 2}


def find_image(http: httpx.Client, brand: str, name: str, variant: str | None) -> tuple[str, str] | None:
    resp = http.get(SEARCH, params={"q": f"{brand} {name} {variant or ''}", "page_size": 20, "fields": "product_name,brands,image_front_url,countries_tags"})
    resp.raise_for_status()
    want_brand, want_name = norm(brand), tokens(f"{name} {variant or ''}")
    best = None
    for hit in resp.json()["hits"]:
        brands = hit.get("brands") or []
        label = norm(" ".join([brands] if isinstance(brands, str) else brands) + (hit.get("product_name") or ""))
        if not hit.get("image_front_url") or want_brand not in label:
            continue
        overlap = len(want_name & tokens(hit.get("product_name") or ""))
        india = "en:india" in (hit.get("countries_tags") or [])
        if not overlap:
            continue
        score = (overlap, india)
        if best is None or score > best[0]:
            best = (score, hit["image_front_url"], hit.get("product_name"))
    return best and best[1:]


def main(apply: bool) -> None:
    conn, found = connect(), 0
    rows = conn.execute(MISSING).fetchall()
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30) as http:
        for pid, brand, name, variant in rows:
            try:
                match = find_image(http, brand, name, variant)
            except httpx.HTTPError:
                logging.exception("OFF lookup failed for %s %s", brand, name)
                continue
            if match:
                found += 1
                print(f"{brand} | {name} -> {match[1]} {match[0]}")
                if apply:
                    conn.execute("UPDATE products SET image_url = %s WHERE id = %s", (match[0], pid))
    print(f"{found}/{len(rows)} matched")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main("--apply" in sys.argv)
