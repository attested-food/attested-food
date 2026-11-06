import logging
import re
import sys

from bs4 import BeautifulSoup

from scraper.common import (
    Blocked, category_for, client, connect, number, parse_date, product_id, request, save_report, source_id, strip_brand,
)

DELAY = 3.0
SITEMAP = "https://www.trustified.in/dynamic-passandfail_p_ad26dc62_0d97_4c38_8dd2_f4591f4befb1_0_5000-sitemap.xml"

FIELDS = r"Product\s*Name|Category|Batch No\. Tested|Mfg Date|Exp Date|Date Published|Date Certified|Date Tested|Tested By|Testing Status|Status"
FIELD_RE = re.compile(rf"\b({FIELDS})\b\s*[-–]?\s*")
IMAGE_SECTIONS = {"macro accuracy", "accuracy", "heavy metals", "microbiological", "pesticides"}
BODY_START = re.compile(r"^(Limit|Result|In tests|No |This |A total|RANGE)", re.I)
KNOWN_SECTIONS = re.compile(r"^(aflatoxin|pesticides|heavy metals|microbiolog|synthetic dyes|amino spiking|melamine spiking)", re.I)
RESULT_RE = re.compile(r"^Result\s*[:=\-]\s*(.+)$", re.I)
LIMIT_RE = re.compile(r"^Limit of detection\s*\(?\s*\w*\s*\)?\s*[:=\-]\s*(.+)$", re.I)
VALUE_RE = re.compile(r"^([<>≤≥]?\s*\d+(?:\.\d+)?)\s*(.*)$")
STOP_RE = re.compile(r"Further (tests|testing) (are|were|was) not (performed|conducted).*$", re.I)

BRANDS = [
    "Aashirvaad", "Abbott", "Alkem Laboratories", "Alpino", "Amul", "Amyleord", "AS-IT-IS", "Avvatar", "Becadexamine",
    "Bevzilla", "Bgreen", "Blackbeast", "Bluvit", "Britannia", "Brooke Bond", "Cadbury", "Centrum", "Country Delight",
    "Cutler Nutrition", "Daawat", "DiSano", "DMart", "Dr. Oetker FunFoods", "Dr. Vaidya's", "Epigamia", "ESN", "Everest",
    "Exalt", "Explosive Whey", "Farmley", "Foodstrong", "Fortune", "Fuelled", "Gentle Beast", "Get-A-Way", "Go Zero",
    "Gritzo", "Haldiram's", "Haleup", "HealthFarm", "Hershey's", "HK Vitals", "India Gate", "Baidyanath", "Jan Aushadhi",
    "Jivo", "Kellogg's", "Kissan", "Koshaveda", "Licious", "Lindt", "Maggi", "Man Matters", "Maxener Wellness", "MDH",
    "Mill'd", "Mille", "Minus 30", "Mother Dairy", "MuscleBlaze", "Muscle Club", "Muscle Dominator", "Muscle Gears",
    "Musclenectar", "Nakpro", "Naturaltein", "Nescafe", "Nestle", "Noto", "Nutrabay", "Nutrabox", "Nutrela", "Nutrijet",
    "Nutriquint", "Nutrova", "One Science Nutrition", "OSOAA", "Only What's Needed", "Patanjali", "Pintola", "Pure Serving",
    "RawRX", "Ripped Up Nutrition", "Ronnie Coleman", "Saffola", "Smash", "Sundrop", "Superyou", "Tata 1mg", "Tata",
    "The Butternut Co", "The Whole Truth", "Total Nutrition", "Trikut", "Truebasics", "Trunativ", "Unived", "VS Mani & Co",
    "XLR8", "YogaBar", "Zaveda", "Zeroharm",
]
ALIASES = {"abott": "Abbott", "asitis": "AS-IT-IS", "kelloggs": "Kellogg's", "biozyme": "MuscleBlaze", "dr.oetkar": "Dr. Oetker FunFoods"}

# Same product as listed on Unbox Health under a slightly different name.
MERGES = {
    ("Patanjali", "Cow's Ghee"): ("Patanjali", "Cow Ghee"),
    ("Country Delight", "Desi Danedar Ghee"): ("Country Delight", "Desi Danedar Cow Ghee"),
    ("Centrum", "Men Multivitamin"): ("Centrum", "Men Multivitamin Tablet"),
    ("Kellogg's", "Corn Flakes"): ("Kellogg's", "Corn Flakes Original"),
    ("Naturaltein", "Creamag Boost"): ("Naturaltein", "CreaMag Boost Creatine + Magnesium"),
    ("Amul", "Bitter Intense Dark Chocolate 90 %"): ("Amul", "Bitter 90% Chocolate"),
    ("Ritebite", "Max Protein Daily Choco Almond Bar"): ("RiteBite Max Protein", "Daily - Choco Almond Bar"),
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("’", "'"))


def brand_for(heading: str) -> str:
    h = norm(heading)
    for alias, brand in ALIASES.items():
        if h.startswith(norm(alias)):
            return brand
    match = max((b for b in BRANDS if h.startswith(norm(b))), key=len, default=None)
    return match or heading.replace("’", "'")


def group_for(name: str) -> str:
    n = name.lower()
    if "spiking" in n or "melamine" in n or "nitrogen" in n:
        return "spiking"
    if "aflatoxin" in n or "saffrole" in n:
        return "toxin"
    if "pesticide" in n:
        return "pesticide"
    if any(k in n for k in ("heavy metal", "lead", "arsenic", "mercury", "cadmium")):
        return "heavy_metal"
    if any(k in n for k in ("protein", "macro", "moisture", "ash", "fat", "sugar")):
        return "nutrition"
    return "other"


def status_for(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\bspiked\b|exceed|does not comply|\bfailed\b|\bdetected\b(?!.*not)", t) and not re.search(r"not detected|no \w+ spiking", t):
        return "fail"
    if re.search(r"not detected|no \w+ spiking found|below|negative|absent|\bblq\b", t):
        return "pass"
    return None


def parse_value(raw: str) -> tuple[str, str | None]:
    """'<0.5 μg/kg' -> ('<0.5', 'μg/kg')."""
    m = VALUE_RE.match(raw.strip())
    if not m:
        return raw.strip(), None
    return m.group(1).replace(" ", ""), m.group(2).strip() or None


def parse(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = soup.get_text("\n", strip=True).split("\n")
    lines = lines[lines.index("SHOP") + 1 : lines.index("Connect with us.")]
    if not lines:
        return None
    heading = lines[0]
    is_header = lambda i: (
        lines[i].lower() in IMAGE_SECTIONS
        or KNOWN_SECTIONS.match(lines[i])
        or (i + 1 < len(lines) and BODY_START.match(lines[i + 1]) and not BODY_START.match(lines[i]))
    )
    first = next((i for i in range(1, len(lines)) if is_header(i)), len(lines))
    head = " ".join(lines[1:first])
    parts = FIELD_RE.split(head)
    fields = {}
    for label, value in zip(parts[1::2], parts[2::2]):
        fields[re.sub(r"\s+", " ", label)] = value.strip(" -–#|").strip() or None
    if not fields.get("Product Name"):
        return None

    sections, cur = [], None
    for i in range(first, len(lines)):
        if is_header(i):
            cur = [lines[i], []]
            sections.append(cur)
        elif cur and lines[i] not in ("g",) and not lines[i].startswith("*"):
            cur[1].append(lines[i])

    results, image_only = [], 0
    for name, body in sections:
        text = STOP_RE.sub("", " ".join(body)).strip()
        if not re.search(r"[a-z]", text, re.I):
            if name.lower() in IMAGE_SECTIONS or not body:
                image_only += not body
            continue
        param = name.title() if name.isupper() else name
        limit_raw = next((m.group(1) for b in body if (m := LIMIT_RE.match(b))), None)
        result_raw = next((m.group(1) for b in body if (m := RESULT_RE.match(b))), None)
        if result_raw:
            raw, unit = parse_value(result_raw)
            limit = number(parse_value(limit_raw)[0]) if limit_raw else None
            narrative = " ".join(b for b in body if not RESULT_RE.match(b) and not LIMIT_RE.match(b))
            results.append({
                "parameter": param, "group": group_for(param), "unit": unit, "value": number(raw), "value_raw": raw,
                "detection_limit": limit, "status": status_for(narrative or result_raw),
            })
        else:
            results.append({"parameter": param, "group": group_for(param), "value_raw": text, "status": status_for(text)})

    status = (fields.get("Testing Status") or fields.get("Status") or "").lower()
    return {
        "brand": brand_for(heading),
        "name": fields["Product Name"],
        "category_raw": fields.get("Category"),
        "lab": fields.get("Tested By"),
        "batch_no": fields.get("Batch No. Tested"),
        "mfg_date": parse_date(fields.get("Mfg Date")),
        "expiry_date": parse_date(fields.get("Exp Date")),
        "issued_on": parse_date(fields.get("Date Published") or fields.get("Date Certified")),
        "tested_on": parse_date(fields.get("Date Tested")),
        "verdict": "pass" if status in ("passed", "active") else "fail" if status == "failed" else None,
        "results": results,
        "image_only": image_only,
        "images": len(soup.select("[data-hook=gallery-item-image-img]")),
        "image_url": og["content"] if (og := soup.find("meta", property="og:image")) and "logo" not in og["content"].lower() else None,
    }


def main(limit: int | None, resume: bool) -> None:
    conn = connect()
    with client() as http:
        publisher = source_id(conn, "Trustified", "website")
        urls = re.findall(r"<loc>([^<]+)</loc>", request(http, "GET", SITEMAP, DELAY).text)[:limit]
        if resume:
            done = {u for (u,) in conn.execute(
                "SELECT source_url FROM reports WHERE publisher_id = %s AND fetched_at > now() - interval '1 day'", (publisher,)
            )}
            urls = [u for u in urls if u not in done]
            logging.info("Resuming: %d pages left", len(urls))
        stats = {"reports": 0, "results": 0, "skipped": 0, "image_sections": 0, "images": 0}
        for url in urls:
            try:
                r = request(http, "GET", url, DELAY)
                data = parse(r.text) if r else None
                if not data:
                    stats["skipped"] += 1
                    logging.warning("No report data on %s", url)
                    continue
                brand, name = MERGES.get((data["brand"], strip_brand(data["brand"], data["name"])), (data["brand"], data["name"]))
                with conn.transaction():
                    pid = product_id(
                        conn, brand, name, None, category_for(f"{data['category_raw']} {data['name']}"), image_url=data["image_url"],
                    )
                    save_report(
                        conn, pid, publisher, url, data["results"],
                        lab_id=source_id(conn, data["lab"]) if data["lab"] else None,
                        **{k: data[k] for k in ("batch_no", "mfg_date", "expiry_date", "tested_on", "issued_on", "verdict")},
                    )
                stats["reports"] += 1
                stats["results"] += len(data["results"])
                stats["image_sections"] += data["image_only"]
                stats["images"] += data["images"]
                logging.info("%s %s: %s, %d results", data["brand"], data["name"], data["verdict"], len(data["results"]))
            except Blocked:
                logging.error("Stopped by the site; progress so far: %s (re-run with --resume)", stats)
                raise
            except Exception:
                logging.exception("Failed on %s", url)
                if conn.broken:
                    logging.warning("Database connection lost, reconnecting")
                    conn = connect()
        logging.info("Trustified done: %s", stats)
    conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = [a for a in sys.argv[1:] if a != "--resume"]
    main(int(args[0]) if args else None, "--resume" in sys.argv)
