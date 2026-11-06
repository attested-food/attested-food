import logging
import re
import sys

import orjson

from scraper.common import Blocked, client, connect, norm, number, product_id, request, save_report, source_id

API = "https://api.unboxhealth.in"
PAGE = "https://www.unboxhealth.in/explore/product/{slug}/{id}"
HEADERS = {"Content-Type": "application/json", "Referer": "https://www.unboxhealth.in/"}

CATEGORY_OVERRIDES = {
    "Cookies & Biscuits": "biscuits", "Chips & Puffs": "chips", "Idli & Dosa Batters": "idli_dosa_batter",
    "Prebiotics & Fiber": "fibre_supplement", "Fish Oil Capsules": "omega_3_supplement",
    "Veg Omega-3 Supplements": "omega_3_supplement", "Omega-3 Supplements": "omega_3_supplement",
    "Multivitamins": "multivitamin", "Dark Chocolates": "dark_chocolate", "Ice Cream": "ice_cream",
}
METALS = ("lead", "arsenic", "cadmium", "mercury", "chromium", "nickel", "tin", "aluminium", "aluminum")
CLAIMS_RE = re.compile(r"Claims[^:|]*:([^|]+)")
CLAIM_RE = re.compile(r"([\d.]+)\s*([a-zA-Zµμ%]*)\s+([^,.]+(?:\.\d[^,]*)?)")
GRADE_RE = re.compile(r"rated ([A-F][+-]?)|^\s*([A-F][+-]?)\s*$")


def category(names: list[str]) -> str:
    name = next((n for n in names if "Product Hunt" not in n), names[0] if names else "other")
    if name in CATEGORY_OVERRIDES:
        return CATEGORY_OVERRIDES[name]
    words = re.sub(r"[^a-z0-9]+", " ", name.lower().replace("&", "and")).split()
    if words and words[-1].endswith("s") and not words[-1].endswith("ss"):
        words[-1] = words[-1][:-1]
    return "_".join(words) or "other"


def claim_key(label: str) -> str:
    """Match 'Total Protein' to 'Protein', 'Vit-D' to 'Vitamin D', 'PUFA+MUFA' to 'MUFA+PUFA'."""
    k = norm(label).replace("vitamin", "vit").replace("pufamufa", "mufapufa").replace("carbohydrates", "carbs")
    return k.removeprefix("total")


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def safety_group(label: str) -> str:
    l = label.lower()
    if any(re.search(rf"\b{m}\b", l) for m in METALS):
        return "heavy_metal"
    if "pesticide" in l:
        return "pesticide"
    return "toxin"


def parse(d: dict) -> dict:
    brand = d["brand_name"].strip()
    if brand.isupper() and len(brand) > 4:
        brand = brand.title()
    parts = [p.strip() for p in d["title"].split("|")]
    if len(parts) > 1 and norm(parts[0]) == norm(brand):
        parts = parts[1:]
    claims_text = " ".join(CLAIMS_RE.findall(d.get("product_highlight") or ""))
    claims = {claim_key(m.group(3)): number(m.group(1)) for m in CLAIM_RE.finditer(claims_text)}

    results = []
    for p in d.get("lab_test_label_accuracy_parameters") or []:
        label, raw = p["label"].strip(), p["value"].strip()
        results.append({
            "parameter": label, "group": "nutrition", "unit": p["unit"].strip() or None, "value": number(raw),
            "value_raw": raw, "label_claim": claims.get(claim_key(label)),
        })
    for p in d.get("lab_test_safety_parameters") or []:
        label, raw = p["label"].strip(), p["value"].strip()
        results.append({
            "parameter": label, "group": safety_group(label), "unit": p["unit"].strip() or None, "value": number(raw),
            "value_raw": raw,
        })
    for s in d.get("rating_details") or []:
        raw = s["rating"].strip()
        results.append({"parameter": s["rating_name"].strip(), "group": "other", "unit": "/10", "value": number(raw), "value_raw": raw})

    grade = GRADE_RE.search(d.get("rating_explanation") or "")
    size = d.get("size") or 0
    return {
        "brand": brand,
        "name": parts[0],
        "variant": " | ".join(parts[1:]) or None,
        "category": category(d.get("category_name") or []),
        "image_url": (d.get("all_images") or [d.get("thumbnail_url")])[0],
        "net_quantity": f"{size:g} {d['unit'].strip()}" if size and (d.get("unit") or "").strip() else None,
        "labs": [l.strip() for l in (d.get("labs_used") or "").split(",") if l.strip()],
        "batch_no": d.get("batch_number") or None,
        "issued_on": d.get("rating_live_date"),
        "grade": (grade.group(1) or grade.group(2)) if grade else None,
        "results": results,
        "url": PAGE.format(slug=slug(d["title"]), id=d["product_id"]),
    }


def main(limit: int | None) -> None:
    conn = connect()
    with client() as http:
        publisher = source_id(conn, "Unbox Health", "website")
        r = request(http, "POST", f"{API}/get_products_list", headers=HEADERS, content=orjson.dumps({"query": "", "page": 1, "size": 1000}))
        items = orjson.loads(r.content)["product"]["items"][:limit]
        logging.info("Unbox Health: %d products listed", len(items))
        stats = {"reports": 0, "results": 0, "skipped": 0}
        for item in items:
            try:
                if item.get("auth_required"):
                    stats["skipped"] += 1
                    logging.warning("Login required for %s, skipping", item["title"])
                    continue
                r = request(http, "POST", f"{API}/get_product_detail", headers=HEADERS, content=orjson.dumps([item["product_id"]]))
                body = orjson.loads(r.content) if r else None
                if not body:
                    stats["skipped"] += 1
                    logging.warning("No detail for %s", item["title"])
                    continue
                data = parse(body[0])
                with conn.transaction():
                    pid = product_id(
                        conn, data["brand"], data["name"], data["variant"], data["category"],
                        image_url=data["image_url"], net_quantity=data["net_quantity"],
                    )
                    save_report(
                        conn, pid, publisher, data["url"], data["results"],
                        lab_id=source_id(conn, data["labs"][0]) if data["labs"] else None,
                        verdict="grade" if data["grade"] else None,
                        **{k: data[k] for k in ("batch_no", "issued_on", "grade")},
                    )
                stats["reports"] += 1
                stats["results"] += len(data["results"])
                logging.info("%s %s: %s, %d results", data["brand"], data["name"], data["grade"], len(data["results"]))
            except Blocked:
                raise
            except Exception:
                logging.exception("Failed on %s", item.get("title"))
                if conn.broken:
                    logging.warning("Database connection lost, reconnecting")
                    conn = connect()
        logging.info("Unbox Health done: %s", stats)
    conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
