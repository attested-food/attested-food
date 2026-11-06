import logging
import os
import re
import time
from datetime import date, datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import psycopg
from dotenv import load_dotenv

USER_AGENT = "Mozilla/5.0 (compatible; attested-food-bot/0.1; +https://attested.food)"
DELAY = 1.0
MAX_CLIENT_ERRORS = 3

NUM_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*$")

_last_request = 0.0
_client_errors = 0
_robots: dict[str, RobotFileParser] = {}


class Blocked(Exception):
    pass


def client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=60)


def _wait(delay: float = DELAY) -> None:
    global _last_request
    pause = _last_request + delay - time.monotonic()
    if pause > 0:
        time.sleep(pause)
    _last_request = time.monotonic()


def _allowed(http: httpx.Client, url: str) -> bool:
    parts = urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    rp = _robots.get(base)
    if rp is None:
        rp = RobotFileParser()
        _wait()
        r = http.get(base + "/robots.txt")
        rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        _robots[base] = rp
    return rp.can_fetch(USER_AGENT, url)


def request(http: httpx.Client, method: str, url: str, delay: float = DELAY, **kw) -> httpx.Response | None:
    """Polite request: robots.txt, ~1 req/s, stop on 429 or repeated 4xx."""
    global _client_errors
    if not _allowed(http, url):
        logging.warning("robots.txt disallows %s", url)
        return None
    _wait(delay)
    r = http.request(method, url, **kw)
    if r.status_code == 429:
        raise Blocked(f"429 from {url}")
    if 400 <= r.status_code < 500:
        _client_errors += 1
        logging.warning("%s from %s", r.status_code, url)
        if _client_errors >= MAX_CLIENT_ERRORS:
            raise Blocked(f"{_client_errors} consecutive 4xx, last {url}")
        return None
    r.raise_for_status()
    _client_errors = 0
    return r


def connect() -> psycopg.Connection:
    load_dotenv()
    return psycopg.connect(
        os.environ["DATABASE_URL"], autocommit=True, connect_timeout=30,
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3,
        options="-c idle_in_transaction_session_timeout=60000",
    )


def number(raw: str | None) -> float | None:
    m = NUM_RE.match(raw or "")
    return float(m.group(1)) if m else None


DATE_FORMATS = (
    "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%d.%m.%Y", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d/%b/%Y",
    "%d %b, %Y", "%Y-%m-%d", "%d-%b-%Y", "%d/%b/%y", "%d/%B/%Y", "%d.%m.%y", "%d%b%Y", "%b.%Y", "%B.%Y", "%b %Y", "%B %Y",
    "%b-%y", "%B-%y", "%b-%Y", "%B-%Y", "%b/%y", "%B/%y", "%b/%Y", "%B/%Y", "%b %y", "%m/%Y", "%m/%y", "%m.%Y", "%m-%Y", "%b%y", "%b%Y",
)


def parse_date(raw: str | None) -> date | None:
    """Parse the many date spellings sites use ('5 Jan 2026', '20.05.2026', 'APR-26', '10/2025'); month-only -> 1st."""
    if not raw:
        return None
    text = re.sub(r"\bSept\b", "Sep", re.sub(r"\s*([/-])\s*", r"\1", re.sub(r"\s+", " ", raw))).strip(" -–.").title()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    logging.warning("Unparsed date %r", raw)
    return None


CATEGORIES = (
    ("peanut butter", "peanut_butter"), ("nut butter", "peanut_butter"), ("nuts butter", "peanut_butter"),
    ("glutathione", "supplement"), ("gainer", "mass_gainer"), ("creatine", "creatine_supplement"),
    ("pre-workout", "pre_workout"), ("preworkout", "pre_workout"), ("pre workout", "pre_workout"),
    ("protein bar", "protein_bar"), ("muesli", "breakfast_cereal"), ("corn flakes", "breakfast_cereal"),
    ("cornflakes", "breakfast_cereal"), ("oats", "breakfast_cereal"), ("cereal", "breakfast_cereal"),
    ("supermilk", "kids_nutrition_drink"), ("pediasure", "kids_nutrition_drink"), ("nutritional drink", "kids_nutrition_drink"),
    ("nanpro", "infant_formula"), ("protein", "protein_powder"), ("whey", "protein_powder"),
    ("omega", "omega_3_supplement"), ("fish oil", "omega_3_supplement"), ("multivitamin", "multivitamin"),
    ("vitamin", "vitamin_supplement"), ("d3", "vitamin_supplement"), ("magnesium", "magnesium_supplement"),
    ("melatonin", "melatonin_supplement"), ("ghee", "ghee"), ("butter", "butter"), ("paneer", "paneer"),
    ("cheese", "cheese"), ("dahi", "curd"), ("yoghurt", "curd"), ("yogurt", "curd"), ("milk", "milk"),
    ("ice cream", "ice_cream"), ("icecream", "ice_cream"), ("dark", "dark_chocolate"), ("chocolate", "chocolate"),
    ("cocoa", "cocoa_powder"), ("bar", "snack_bar"), ("atta", "flour"), ("flour", "flour"), ("rice", "rice"),
    ("bread", "bread"), ("masala", "spices"), ("kitchen king", "spices"), ("mirch", "spices"), ("chilli", "spices"),
    ("haldi", "spices"), ("turmeric", "spices"), ("oil", "cooking_oil"), ("tea", "tea"), ("coffee", "coffee_powder"),
    ("ketchup", "ketchup"), ("peanut", "nuts"), ("makhana", "snacks"), ("nuts", "nuts"), ("salt", "salt"),
    ("soya", "soya_chunks"), ("vinegar", "apple_cider_vinegar"), ("noodles", "instant_noodles"), ("honey", "honey"),
    ("biscuit", "biscuits"), ("isabgol", "fibre_supplement"), ("chicken", "meat"), ("shilajit", "shilajit_supplement"),
    ("gummies", "supplement"),
)


def category_for(text: str) -> str:
    t = text.lower()
    return next((c for k, c in CATEGORIES if k in t), "other")


def norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def strip_brand(brand: str, name: str) -> str:
    """'MuscleBlaze Biozyme Whey' or 'Muscle Blaze Biozyme Whey' under brand 'MuscleBlaze' -> 'Biozyme Whey'."""
    words = name.split()
    for k in range(1, len(words)):
        if norm(" ".join(words[:k])) == norm(brand):
            return " ".join(words[k:]).lstrip("-–: ").strip() or name.strip()
    return name.strip()


def source_id(conn: psycopg.Connection, name: str, type_: str = "lab", url: str | None = None) -> str:
    row = conn.execute("SELECT id FROM sources WHERE lower(name) = lower(%s)", (name,)).fetchone()
    if row:
        return row[0]
    logging.info("Adding %s source %s", type_, name)
    return conn.execute(
        "INSERT INTO sources (type, name, url) VALUES (%s, %s, %s) RETURNING id", (type_, name, url)
    ).fetchone()[0]


NORM = "regexp_replace(lower({}), '[^a-z0-9]', '', 'g')"
VARIANT = NORM.format("coalesce(variant, '')")
PRODUCT_FIELDS = ("manufacturer", "fssai_license", "barcode", "net_quantity", "image_url")


def product_id(conn: psycopg.Connection, brand: str, name: str, variant: str | None, category: str, **fields) -> str:
    """Reuse a product with the same normalised brand/name/variant, else insert; fills NULL fields."""
    name = strip_brand(brand, name)
    fields = {k: v for k, v in fields.items() if k in PRODUCT_FIELDS and v}
    row = conn.execute(
        f"SELECT id FROM products WHERE {NORM.format('brand')} = {NORM.format('%s')}"
        f" AND {NORM.format('name')} = {NORM.format('%s')}"
        f" AND {VARIANT} = {NORM.format('%s')}",
        (brand, name, variant or ""),
    ).fetchone()
    if row:
        if fields:
            sets = ", ".join(f"{k} = coalesce({k}, %({k})s)" for k in fields)
            conn.execute(f"UPDATE products SET {sets} WHERE id = %(id)s", {**fields, "id": row[0]})
        return row[0]
    cols = ["brand", "name", "variant", "category", *fields]
    return conn.execute(
        f"INSERT INTO products ({', '.join(cols)}) VALUES ({', '.join(f'%({c})s' for c in cols)}) RETURNING id",
        {"brand": brand, "name": name, "variant": variant or None, "category": category, **fields},
    ).fetchone()[0]


REPORT_FIELDS = (
    "lab_id", "report_number", "batch_no", "mfg_date", "expiry_date", "tested_on", "issued_on",
    "verdict", "grade", "pdf_url",
)
RESULT_FIELDS = ("parameter", "group", "unit", "value", "value_raw", "label_claim", "limit", "detection_limit", "method", "status")


def save_report(
    conn: psycopg.Connection, product: str, publisher: str, source_url: str, results: list[dict], **fields
) -> str:
    """Upsert a fallback report by source_url and replace its results."""
    fields = {k: fields.get(k) for k in REPORT_FIELDS}
    sets = ", ".join(f"{k} = excluded.{k}" for k in ("product_id", "publisher_id", *REPORT_FIELDS, "fetched_at"))
    rid = conn.execute(
        f"INSERT INTO reports (product_id, kind, publisher_id, source_url, fetched_at, {', '.join(REPORT_FIELDS)})"
        f" VALUES (%(product_id)s, 'fallback', %(publisher_id)s, %(source_url)s, now(),"
        f" {', '.join(f'%({k})s' for k in REPORT_FIELDS)})"
        f" ON CONFLICT (source_url) DO UPDATE SET {sets} RETURNING id",
        {"product_id": product, "publisher_id": publisher, "source_url": source_url, **fields},
    ).fetchone()[0]
    conn.execute("DELETE FROM results WHERE report_id = %s", (rid,))
    with conn.cursor() as cur:
        cur.executemany(
            'INSERT INTO results (report_id, parameter, "group", unit, value, value_raw, label_claim, "limit", detection_limit,'
            " method, status) VALUES (%(report_id)s, %(parameter)s, %(group)s, %(unit)s, %(value)s,"
            " %(value_raw)s, %(label_claim)s, %(limit)s, %(detection_limit)s, %(method)s, %(status)s)",
            [{**{k: r.get(k) for k in RESULT_FIELDS}, "report_id": rid} for r in results],
        )
    return rid
