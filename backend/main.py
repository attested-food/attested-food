import base64
import binascii
import logging
import os
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Literal

import httpx
import orjson
import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, ORJSONResponse, Response
from psycopg.rows import dict_row
from psycopg.types.json import set_json_loads
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend import amazon
from backend.annotate import findings, summarize, test_statuses
from backend import departments
from backend.grading import openlabel_grade
from backend.thumbs import thumbnail
from backend.category_tests import coverage, names_for, tests_for

load_dotenv()
set_json_loads(orjson.loads)

DATABASE_URL = os.environ["DATABASE_URL"]
BUILD_DIR = (Path(__file__).resolve().parent.parent / "frontend" / "build").resolve()

app = FastAPI(title="OpenLabel.fyi", default_response_class=ORJSONResponse)

SEARCH_TEXT = "p.brand || ' ' || p.name || ' ' || coalesce(p.variant, '')"
REPORT_ORDER = "r.kind = 'user' DESC, r.tested_on DESC NULLS LAST, r.issued_on DESC NULLS LAST, r.created_at DESC"
SOURCE_JSON = "CASE WHEN {a}.id IS NULL THEN NULL ELSE json_build_object('id', {a}.id, 'name', {a}.name, 'url', {a}.url, 'accreditation', {a}.accreditation) END"

# A product is listed only when we can show why it passed or failed: test results with values or statuses,
# its ingredient list and its pack nutrition. Products missing any of these stay reachable by direct link.
LISTABLE = """(p.ingredients IS NOT NULL AND p.label_nutrition IS NOT NULL
    AND EXISTS (SELECT 1 FROM reports r JOIN results x ON x.report_id = r.id
                WHERE r.product_id = p.id AND (x.value IS NOT NULL OR x.status IS NOT NULL)))"""

# Letter (A–E) for the latest third-party report's grade: "86/100", "B+", "A grade", Pass/Fail.
GRADE_LETTER = f"""(SELECT CASE
        WHEN x.pct IS NOT NULL THEN CASE WHEN x.pct >= 80 THEN 'A' WHEN x.pct >= 60 THEN 'B' WHEN x.pct >= 40 THEN 'C'
                                         WHEN x.pct >= 20 THEN 'D' ELSE 'E' END
        WHEN upper(x.g) = 'PASS' THEN 'A'
        WHEN upper(x.g) = 'FAIL' THEN 'E'
        WHEN upper(left(btrim(x.g), 1)) IN ('A', 'B', 'C', 'D', 'E') THEN upper(left(btrim(x.g), 1)) END
    FROM (SELECT coalesce(r.grade, CASE r.verdict WHEN 'pass' THEN 'Pass' WHEN 'fail' THEN 'Fail' END) AS g,
                 CASE WHEN coalesce(r.grade, '') ~ '^\\s*[0-9.]+\\s*/\\s*[0-9.]+\\s*$'
                      THEN 100 * split_part(r.grade, '/', 1)::numeric / nullif(split_part(r.grade, '/', 2)::numeric, 0) END AS pct
          FROM reports r WHERE r.product_id = p.id AND r.kind = 'fallback'
          ORDER BY {REPORT_ORDER} LIMIT 1) x)"""

LIST_SQL = f"""
WITH filtered AS (
    SELECT p.id, p.brand, p.name, p.variant, p.category, p.image_url, p.label_nutrition,
           (SELECT count(*) FROM reports r WHERE r.product_id = p.id) AS report_count,
           EXISTS (SELECT 1 FROM reports r WHERE r.product_id = p.id AND r.kind = 'user') AS has_user_report
    FROM products p
    WHERE {LISTABLE}
      AND (%(q)s::text IS NULL
           OR to_tsvector('simple', {SEARCH_TEXT}) @@ plainto_tsquery('simple', %(q)s::text)
           OR {SEARCH_TEXT} ILIKE %(like)s::text)
      AND (%(brands)s::text[] IS NULL OR lower(p.brand) = ANY(%(brands)s::text[]))
      AND (%(categories)s::text[] IS NULL OR p.category = ANY(%(categories)s::text[]))
      AND (%(grades)s::text[] IS NULL OR {GRADE_LETTER} = ANY(%(grades)s::text[]))
      AND (NOT %(any_evidence)s::bool
           OR (%(lab)s::bool AND EXISTS (SELECT 1 FROM reports r WHERE r.product_id = p.id AND r.kind = 'user'))
           OR (%(published)s::bool AND EXISTS (SELECT 1 FROM reports r WHERE r.product_id = p.id)
               AND NOT EXISTS (SELECT 1 FROM reports r WHERE r.product_id = p.id AND r.kind = 'user')))
      AND (NOT %(no_added_sugar)s::bool OR (p.label_nutrition->>'added_sugars_g')::numeric = 0)
      AND (NOT %(high_fibre)s::bool OR (p.label_nutrition->>'fiber_g')::numeric >= 6)
      AND (NOT %(high_protein)s::bool OR (p.label_nutrition->>'protein_g')::numeric >= 20)
),
page AS (
    SELECT f.*, (
        SELECT json_build_object('kind', r.kind, 'verdict', r.verdict, 'grade', r.grade,
                                 'publisher', pub.name, 'lab', lab.name, 'tested_on', r.tested_on)
        FROM reports r
        LEFT JOIN sources lab ON lab.id = r.lab_id
        LEFT JOIN sources pub ON pub.id = r.publisher_id
        WHERE r.product_id = f.id
        ORDER BY {REPORT_ORDER}
        LIMIT 1
    ) AS latest
    FROM filtered f
    ORDER BY f.has_user_report DESC, (f.image_url IS NOT NULL) DESC, f.brand, f.name, f.variant NULLS FIRST, f.id
    LIMIT %(limit)s OFFSET %(offset)s
)
SELECT (SELECT count(*) FROM filtered) AS total,
       (SELECT coalesce(json_agg(page), '[]'::json) FROM page) AS items
"""

DETAIL_SQL = f"""
SELECT p.id, p.brand, p.name, p.variant, p.category, p.manufacturer, p.fssai_license,
       p.barcode, p.net_quantity, p.image_url, p.ingredients, p.ingredients_source, p.label_nutrition,
       coalesce((
           SELECT json_agg(to_jsonb(rep) - 'ord' ORDER BY rep.ord)
           FROM (
               SELECT r.id, r.kind,
                      {SOURCE_JSON.format(a="lab")} AS lab,
                      {SOURCE_JSON.format(a="pub")} AS publisher,
                      r.source_url, r.report_number, r.ulr_number, r.batch_no, r.mfg_date, r.expiry_date,
                      r.tested_on, r.issued_on, r.verdict, r.grade, r.pdf_url, r.pdf_sha256,
                      r.verification, r.verified, r.chain_tx, r.fetched_at,
                      coalesce((
                          SELECT json_agg(json_build_object(
                              'parameter', x.parameter, 'group', x."group", 'unit', x.unit,
                              'value', x.value, 'value_raw', x.value_raw, 'label_claim', x.label_claim,
                              'limit', x."limit", 'detection_limit', x.detection_limit, 'method', x.method, 'status', x.status
                          ) ORDER BY x."group", x.parameter)
                          FROM results x WHERE x.report_id = r.id
                      ), '[]'::json) AS results,
                      row_number() OVER (ORDER BY {REPORT_ORDER}) AS ord
               FROM reports r
               LEFT JOIN sources lab ON lab.id = r.lab_id
               LEFT JOIN sources pub ON pub.id = r.publisher_id
               WHERE r.product_id = p.id
           ) rep
       ), '[]'::json) AS reports
FROM products p
WHERE p.id = %s
"""

SOURCES_SQL = """
SELECT s.id, s.type, s.name, s.url, s.accreditation, s.description,
       (SELECT count(*) FROM reports r WHERE r.lab_id = s.id OR r.publisher_id = s.id) AS report_count
FROM sources s
ORDER BY s.type DESC, s.name
"""

CATEGORIES_SQL = "SELECT category, count(*) AS product_count FROM products GROUP BY category ORDER BY category"

DUPLICATE_SQL = """
SELECT id FROM products
WHERE lower(brand) = lower(%(brand)s) AND lower(name) = lower(%(name)s)
  AND lower(coalesce(variant, '')) = lower(coalesce(%(variant)s::text, ''))
LIMIT 1
"""

REQUEST_FIELDS = "id::text AS id, brand, name, variant, category, created_at::date::text AS requested_on"

DUPLICATE_REQUEST_SQL = f"""
SELECT {REQUEST_FIELDS} FROM test_requests
WHERE asin = %(asin)s
   OR (lower(brand) = lower(%(brand)s) AND lower(name) = lower(%(name)s)
       AND lower(coalesce(variant, '')) = lower(coalesce(%(variant)s::text, '')))
ORDER BY created_at
LIMIT 1
"""

DUPLICATES_SQL = """
WITH words AS (
    SELECT DISTINCT w FROM unnest(regexp_split_to_array(lower(%(q)s), '[^[:alnum:]]+')) w WHERE length(w) >= 2
),
candidates AS (
    SELECT 'product' AS kind, id::text AS id, brand, name, variant, category, NULL AS requested_on FROM products
    UNION ALL
    SELECT 'request', id::text, brand, name, variant, category, created_at::date::text FROM test_requests
),
scored AS (
    SELECT c.*, (SELECT count(*) FROM words
                 WHERE lower(c.brand || ' ' || c.name || ' ' || coalesce(c.variant, '')) LIKE '%%' || w || '%%')
           + CASE WHEN position(lower(c.brand) IN lower(%(q)s)) > 0 THEN 2 ELSE 0 END AS score
    FROM candidates c
)
SELECT kind, id, brand, name, variant, category, requested_on FROM scored
WHERE score > 0 AND score >= ceil((SELECT count(*) FROM words) * 0.6)
ORDER BY score DESC, kind DESC, brand, name, variant NULLS FIRST
LIMIT 10
"""

REQUEST_SEARCH_TEXT = SEARCH_TEXT.replace("p.", "t.")

LIST_REQUESTS_SQL = f"""
SELECT t.id::text AS id, t.brand, t.name, t.variant, t.category, t.created_at::date::text AS requested_on,
       CASE WHEN t.image IS NOT NULL THEN '/api/test-requests/' || t.id || '/image' ELSE t.image_url END AS image_url
FROM test_requests t
WHERE (%(q)s::text IS NULL
       OR to_tsvector('simple', {REQUEST_SEARCH_TEXT}) @@ plainto_tsquery('simple', %(q)s::text)
       OR {REQUEST_SEARCH_TEXT} ILIKE %(like)s::text)
  AND (%(brand)s::text IS NULL OR lower(t.brand) = lower(%(brand)s::text))
  AND (%(category)s::text IS NULL OR t.category = %(category)s::text)
ORDER BY t.created_at DESC
LIMIT 24
"""

GET_REQUEST_SQL = f"""
SELECT {REQUEST_FIELDS}, net_quantity, manufacturer, fssai_license, barcode, buy_url, image_url,
       image IS NOT NULL AS has_image
FROM test_requests WHERE id = %s
"""

INSERT_REQUEST_SQL = """
INSERT INTO test_requests (brand, name, variant, category, net_quantity, manufacturer, fssai_license, barcode,
                           buy_url, asin, image_url, image, image_type)
VALUES (%(brand)s, %(name)s, %(variant)s, %(category)s, %(net_quantity)s, %(manufacturer)s, %(fssai_license)s,
        %(barcode)s, %(buy_url)s, %(asin)s, %(image_url)s, %(image)s, %(image_type)s)
RETURNING id
"""

MAX_IMAGE_BYTES = 5 * 1024 * 1024
DATA_URL_RE = re.compile(r"^data:(image/(?:png|jpeg|webp));base64,(.+)$", re.S)
HTTP_URL = r"^https?://\S+$"


class TestRequestBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    brand: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    variant: str | None = Field(None, max_length=100)
    category: str = Field(pattern=r"^[a-z0-9_]{1,64}$")
    net_quantity: str | None = Field(None, max_length=50)
    manufacturer: str | None = Field(None, max_length=200)
    fssai_license: str | None = Field(None, pattern=r"^\d{14}$")
    barcode: str | None = Field(None, pattern=r"^\d{8,14}$")
    buy_url: str | None = Field(None, max_length=2000, pattern=HTTP_URL)
    image_url: str | None = Field(None, max_length=2000, pattern=HTTP_URL)
    image_data: str | None = Field(None, max_length=MAX_IMAGE_BYTES * 4 // 3 + 100)

    @model_validator(mode="after")
    def one_image(self):
        if (self.image_url is None) == (self.image_data is None):
            raise ValueError("give exactly one of image_url or image_data")
        return self


_conn: psycopg.Connection | None = None


def fetch(sql: str, params: dict | tuple | None = None) -> list[dict]:
    # ponytail: one shared connection, queries serialise on it; add psycopg_pool if concurrency matters
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row)
    try:
        return _conn.execute(sql, params).fetchall()
    except psycopg.OperationalError:
        logging.exception("db query failed, reconnecting and retrying once")
        _conn.close()
        _conn = psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row)
        return _conn.execute(sql, params).fetchall()


@app.get("/api/health")
def health() -> dict:
    fetch("SELECT 1")
    return {"ok": True}


@app.get("/api/products")
def list_products(
    q: str | None = None,
    brand: list[str] = Query(default=[]),
    category: str | None = None,
    dept: str | None = None,
    grade: list[Literal["A", "B", "C", "D", "E"]] = Query(default=[]),
    evidence: list[Literal["lab", "published"]] = Query(default=[]),
    no_added_sugar: bool = False,
    high_fibre: bool = False,
    high_protein: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
) -> dict:
    """evidence: lab = has an OpenLabel lab report; published = only published third-party tests."""
    q = q.strip() if q and q.strip() else None
    row = fetch(LIST_SQL, {
        "q": q,
        "like": f"%{q}%" if q else None,
        "brands": [b.lower() for b in brand if b] or None,
        "categories": departments.with_aliases(category) if category else (departments.categories_in(dept, all_categories()) or ["-"]) if dept else None,
        "grades": list(grade) or None,
        "any_evidence": bool(evidence),
        "lab": "lab" in evidence,
        "published": "published" in evidence,
        "no_added_sugar": no_added_sugar,
        "high_fibre": high_fibre,
        "high_protein": high_protein,
        "limit": page_size,
        "offset": (page - 1) * page_size,
    })[0]
    items = row["items"]
    for item in items:  # few products have our own report; grade those from their full detail
        item["openlabel_grade"] = get_product(item["id"])["openlabel_grade"] if item["has_user_report"] else None
    return {"items": items, "page": page, "page_size": page_size, "total": row["total"]}


@app.get("/api/products/{product_id}")
def get_product(product_id: str) -> dict:
    try:
        pid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(404, "product not found") from None
    rows = fetch(DETAIL_SQL, (pid,))
    if not rows:
        raise HTTPException(404, "product not found")
    product = rows[0]
    every = [x for r in product["reports"] for x in r["results"]]
    product["tests"] = test_statuses(product["category"], every, findings(every, product["label_nutrition"], product["category"]),
                                     coverage(product["category"], every))
    primary = product["reports"][0]["results"] if product["reports"] else []
    product["annotations"] = summarize({**product, "results": primary})
    ours = bool(product["reports"]) and product["reports"][0]["kind"] == "user"
    product["openlabel_grade"] = (
        openlabel_grade(primary, product["label_nutrition"], product["annotations"]["findings"], product["tests"],
                        product["category"], product.get("ingredients"), product["name"]) if ours else None
    )
    return product


WALL_SQL = f"""
SELECT p.id::text AS id, p.brand, p.name, p.variant, p.category, p.image_url, p.ingredients, p.label_nutrition,
       rep.kind, rep.grade, rep.verdict, rep.lab, rep.publisher, rep.tested_on, rep.results
FROM products p
JOIN LATERAL (
    SELECT r.kind, r.grade, r.verdict, lab.name AS lab, pub.name AS publisher, r.tested_on::text AS tested_on,
           coalesce((
               SELECT json_agg(json_build_object(
                   'parameter', x.parameter, 'group', x."group", 'unit', x.unit, 'value', x.value,
                   'value_raw', x.value_raw, 'label_claim', x.label_claim, 'limit', x."limit",
                   'detection_limit', x.detection_limit, 'method', x.method, 'status', x.status
               ) ORDER BY x."group", x.parameter)
               FROM results x WHERE x.report_id = r.id
           ), '[]'::json) AS results
    FROM reports r
    LEFT JOIN sources lab ON lab.id = r.lab_id
    LEFT JOIN sources pub ON pub.id = r.publisher_id
    WHERE r.product_id = p.id
    ORDER BY {REPORT_ORDER}
    LIMIT 1
) rep ON true
WHERE {LISTABLE}
ORDER BY (rep.kind = 'user') DESC, (p.image_url IS NOT NULL) DESC, (p.ingredients IS NOT NULL) DESC,
         (json_array_length(rep.results) > 0) DESC, p.brand, p.name
LIMIT %(limit)s
"""


def source_grade(kind: str, grade: str | None, verdict: str | None) -> str | None:
    """Fallback reports keep the source's own grade; our own reports have no grade until grading exists."""
    if kind == "user":
        return None
    if grade:
        return grade
    return {"pass": "Pass", "fail": "Fail"}.get(verdict or "")


@app.get("/api/wall")
def wall(limit: int = Query(16, ge=1, le=48)) -> dict:
    """Products with their latest report, best-documented first, then the newest test requests."""
    items = []
    for row in fetch(WALL_SQL, {"limit": limit}):
        tests = coverage(row["category"], row["results"])
        notes = summarize({**row, "tests": tests})
        ours = openlabel_grade(row["results"], row["label_nutrition"], notes["findings"], tests,
                               row["category"], row.get("ingredients"), row["name"]) if row["kind"] == "user" else None
        items.append({
            "kind": "product", "id": row["id"], "brand": row["brand"], "name": row["name"], "variant": row["variant"],
            "category": row["category"], "image_url": row["image_url"], "ingredients": row["ingredients"],
            "label_nutrition": row["label_nutrition"], "state": "tested",
            "grade": ours["letter"] if ours else source_grade(row["kind"], row["grade"], row["verdict"]),
            "grade_source": "OpenLabel" if ours else row["publisher"] or row["lab"], "report_kind": row["kind"],
            "openlabel_grade": ours,
            "lab": row["lab"], "tested_on": row["tested_on"],
            "annotations": notes,
        })
    requests = fetch(LIST_REQUESTS_SQL, {"q": None, "like": None, "brand": None, "category": None})
    for req in requests[: max(1, limit // 4)]:
        tests = coverage(req["category"], [])
        items.append({
            "kind": "request", "id": req["id"], "brand": req["brand"], "name": req["name"], "variant": req["variant"],
            "category": req["category"], "image_url": req["image_url"], "ingredients": None, "label_nutrition": None,
            "state": "requested", "grade": None, "grade_source": None, "report_kind": None, "lab": None,
            "tested_on": None, "openlabel_grade": None, "annotations": summarize({"name": req["name"], "tests": tests}),
        })
    return {"items": items}


@app.get("/api/sources")
def list_sources() -> list[dict]:
    return fetch(SOURCES_SQL)


def all_categories() -> list[str]:
    return [c["category"] for c in fetch(CATEGORIES_SQL)]


LISTED_CATEGORIES_SQL = f"SELECT category, count(*) AS product_count FROM products p WHERE {LISTABLE} GROUP BY category"


@app.get("/api/departments")
def list_departments() -> list[dict]:
    """Departments (groups of categories) in shelf order, with counts of listed products."""
    return departments.group({c["category"]: c["product_count"] for c in fetch(LISTED_CATEGORIES_SQL)})


BRANDS_SQL = f"""
SELECT max(p.brand) AS brand, count(*) AS product_count FROM products p
WHERE {LISTABLE} AND (%(categories)s::text[] IS NULL OR p.category = ANY(%(categories)s::text[]))
GROUP BY lower(p.brand) ORDER BY count(*) DESC, lower(p.brand) LIMIT %(limit)s
"""


@app.get("/api/brands")
def list_brands(category: str | None = None, dept: str | None = None, limit: int = Query(30, ge=1, le=100)) -> list[dict]:
    """Brands with the most products, optionally within a category or department."""
    cats = departments.with_aliases(category) if category else (departments.categories_in(dept, all_categories()) or ["-"]) if dept else None
    return fetch(BRANDS_SQL, {"categories": cats, "limit": limit})


@app.get("/api/categories")
def list_categories() -> list[dict]:
    return [{**c, "tests": names_for(c["category"])} for c in fetch(CATEGORIES_SQL)]


@app.get("/api/duplicates")
def find_duplicates(q: str = Query(min_length=2, max_length=300)) -> list[dict]:
    """Products and test requests matching most of the words in q, best match first."""
    return fetch(DUPLICATES_SQL, {"q": q})


@app.get("/api/test-requests")
def list_test_requests(q: str | None = None, brand: str | None = None, category: str | None = None) -> list[dict]:
    """Newest 24 requests matching the same filters as /api/products."""
    q = q.strip() if q and q.strip() else None
    return fetch(LIST_REQUESTS_SQL, {"q": q, "like": f"%{q}%" if q else None,
                                     "brand": brand or None, "category": category or None})


def request_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(404, "request not found") from None


@app.get("/api/test-requests/{rid}")
def get_test_request(rid: str) -> dict:
    rows = fetch(GET_REQUEST_SQL, (request_id(rid),))
    if not rows:
        raise HTTPException(404, "request not found")
    req = rows.pop()
    if req.pop("has_image"):
        req["image_url"] = f"/api/test-requests/{req['id']}/image"
    standard = tests_for(req["category"])
    return {**req, "tests": [t["name"] for t in standard], "standard_tests": [{"name": t["name"], "why": t["why"]} for t in standard]}


@app.get("/api/test-requests/{rid}/image")
def get_test_request_image(rid: str) -> Response:
    rows = fetch("SELECT image, image_type FROM test_requests WHERE id = %s AND image IS NOT NULL", (request_id(rid),))
    if not rows:
        raise HTTPException(404, "image not found")
    return Response(rows[0]["image"], media_type=rows[0]["image_type"],
                    headers={"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"})


THUMB_KNOWN_SQL = """
SELECT EXISTS (SELECT 1 FROM products WHERE image_url = %(u)s)
    OR EXISTS (SELECT 1 FROM test_requests WHERE image_url = %(u)s) AS ok
"""
REQUEST_IMAGE_PATH = re.compile(r"^/api/test-requests/([0-9a-fA-F-]{36})/image$")
MAX_REMOTE_IMAGE = 8 * 1024 * 1024


@lru_cache(maxsize=512)
def _thumb(src: str, width: int) -> bytes:
    """Only images we already hold a link to are fetched, so this can't be used to reach other hosts."""
    if m := REQUEST_IMAGE_PATH.match(src):
        rows = fetch("SELECT image FROM test_requests WHERE id = %s AND image IS NOT NULL", (uuid.UUID(m[1]),))
        if not rows:
            raise HTTPException(404, "image not found")
        return thumbnail(bytes(rows[0]["image"]), width)
    if not fetch(THUMB_KNOWN_SQL, {"u": src})[0]["ok"]:
        raise HTTPException(404, "image not found")
    resp = httpx.get(src, timeout=10, follow_redirects=True, headers={"User-Agent": "OpenLabel/1.0 (thumbnails)"})
    resp.raise_for_status()
    if len(resp.content) > MAX_REMOTE_IMAGE:
        raise HTTPException(404, "image too large")
    return thumbnail(resp.content, width)


@app.get("/api/thumb")
def thumb(src: str = Query(max_length=2000), w: int = Query(600, ge=64, le=1200)) -> Response:
    """Product photo with its flat border trimmed, as WebP. `src` must be an image_url we serve."""
    width = min(1200, -(-w // 100) * 100)  # round up to 100 px steps so the cache stays small
    try:
        data = _thumb(src, width)
    except HTTPException:
        raise
    except (httpx.HTTPError, OSError, ValueError):
        logging.warning("thumbnail failed for %s", src)
        raise HTTPException(404, "image unavailable") from None
    return Response(data, media_type="image/webp",
                    headers={"Cache-Control": "public, max-age=604800", "X-Content-Type-Options": "nosniff"})


@app.get("/api/prefill")
def prefill(url: str = Query(max_length=2000)) -> dict:
    try:
        asin, product = amazon.fetch(url)
    except amazon.NotAmazon as e:
        raise HTTPException(422, f"{e}. Paste an amazon.in product link.") from None
    except (amazon.Unreadable, httpx.HTTPError):
        logging.exception("prefill failed for %s", url)
        raise HTTPException(502, "Couldn't read that Amazon page. Please fill in the details yourself.") from None
    categories = [c["category"] for c in fetch(CATEGORIES_SQL)]
    fields = {"asin": asin, "brand": product["brand"] or "", "name": product["name"] or "", "variant": None}
    requested = fetch(DUPLICATE_REQUEST_SQL, fields)
    return {
        "asin": asin,
        "buy_url": f"https://www.amazon.in/dp/{asin}",
        "brand": product["brand"],
        "name": product["name"],
        "category": amazon.guess_category(product, categories),
        "image_url": product["image_url"],
        "manufacturer": product["manufacturer"],
        "net_quantity": product["net_quantity"],
        "existing_request": requested[0] if requested else None,
    }


@app.post("/api/test-requests", status_code=201)
def create_test_request(body: TestRequestBody) -> dict:
    fields = body.model_dump(exclude={"image_data"})
    fields["asin"] = amazon.asin_from_url(body.buy_url) if body.buy_url else None
    if existing := fetch(DUPLICATE_SQL, fields):
        raise HTTPException(409, {"message": "product already exists", "product_id": str(existing[0]["id"])})
    if requested := fetch(DUPLICATE_REQUEST_SQL, fields):
        raise HTTPException(409, {"message": "already requested", "request": requested[0]})
    image, image_type = None, None
    if body.image_data:
        match = DATA_URL_RE.match(body.image_data)
        if not match:
            raise HTTPException(422, "image must be a PNG, JPEG or WebP data URL")
        try:
            image = base64.b64decode(match[2], validate=True)
        except binascii.Error:
            raise HTTPException(422, "image is not valid base64") from None
        if len(image) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "image is larger than 5 MB")
        image_type = match[1]
    row = fetch(INSERT_REQUEST_SQL, {**fields, "image": image, "image_type": image_type})[0]
    return {"id": row["id"], "tests": names_for(body.category)}


@app.get("/api/{rest:path}", include_in_schema=False)
def api_not_found(rest: str) -> None:
    raise HTTPException(404, "not found")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str) -> FileResponse:
    file = (BUILD_DIR / path).resolve()
    if path and file.is_file() and file.is_relative_to(BUILD_DIR):
        immutable = path.startswith("assets/")
        return FileResponse(file, headers={"Cache-Control": "public, max-age=31536000, immutable" if immutable else "no-cache"})
    index = BUILD_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(404, "frontend not built")
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
