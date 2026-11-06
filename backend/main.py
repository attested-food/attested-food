import base64
import binascii
import logging
import os
import re
import uuid
from pathlib import Path

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
from backend.category_tests import coverage, names_for

load_dotenv()
set_json_loads(orjson.loads)

DATABASE_URL = os.environ["DATABASE_URL"]
BUILD_DIR = (Path(__file__).resolve().parent.parent / "frontend" / "build").resolve()

app = FastAPI(title="attested.food", default_response_class=ORJSONResponse)

SEARCH_TEXT = "p.brand || ' ' || p.name || ' ' || coalesce(p.variant, '')"
REPORT_ORDER = "r.kind = 'user' DESC, r.tested_on DESC NULLS LAST, r.issued_on DESC NULLS LAST, r.created_at DESC"
SOURCE_JSON = "CASE WHEN {a}.id IS NULL THEN NULL ELSE json_build_object('id', {a}.id, 'name', {a}.name, 'url', {a}.url, 'accreditation', {a}.accreditation) END"

LIST_SQL = f"""
WITH filtered AS (
    SELECT p.id, p.brand, p.name, p.variant, p.category, p.image_url,
           (SELECT count(*) FROM reports r WHERE r.product_id = p.id) AS report_count,
           EXISTS (SELECT 1 FROM reports r WHERE r.product_id = p.id AND r.kind = 'user') AS has_user_report
    FROM products p
    WHERE (%(q)s::text IS NULL
           OR to_tsvector('simple', {SEARCH_TEXT}) @@ plainto_tsquery('simple', %(q)s::text)
           OR {SEARCH_TEXT} ILIKE %(like)s::text)
      AND (%(brand)s::text IS NULL OR lower(p.brand) = lower(%(brand)s::text))
      AND (%(category)s::text IS NULL OR p.category = %(category)s::text)
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
    ORDER BY f.has_user_report DESC, f.brand, f.name, f.variant NULLS FIRST, f.id
    LIMIT %(limit)s OFFSET %(offset)s
)
SELECT (SELECT count(*) FROM filtered) AS total,
       (SELECT coalesce(json_agg(page), '[]'::json) FROM page) AS items
"""

DETAIL_SQL = f"""
SELECT p.id, p.brand, p.name, p.variant, p.category, p.manufacturer, p.fssai_license,
       p.barcode, p.net_quantity, p.image_url,
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

SEARCH_REQUESTS_SQL = f"""
SELECT {REQUEST_FIELDS} FROM test_requests
WHERE (brand || ' ' || name || ' ' || coalesce(variant, '')) ILIKE %(like)s
ORDER BY created_at DESC
LIMIT 8
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
    brand: str | None = None,
    category: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
) -> dict:
    q = q.strip() if q and q.strip() else None
    row = fetch(LIST_SQL, {
        "q": q,
        "like": f"%{q}%" if q else None,
        "brand": brand or None,
        "category": category or None,
        "limit": page_size,
        "offset": (page - 1) * page_size,
    })[0]
    return {"items": row["items"], "page": page, "page_size": page_size, "total": row["total"]}


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
    product["tests"] = coverage(product["category"], [x for r in product["reports"] for x in r["results"]])
    return product


@app.get("/api/sources")
def list_sources() -> list[dict]:
    return fetch(SOURCES_SQL)


@app.get("/api/categories")
def list_categories() -> list[dict]:
    return [{**c, "tests": names_for(c["category"])} for c in fetch(CATEGORIES_SQL)]


@app.get("/api/test-requests")
def search_test_requests(q: str = Query(min_length=2, max_length=200)) -> list[dict]:
    return fetch(SEARCH_REQUESTS_SQL, {"like": f"%{q.strip()}%"})


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
    return {**req, "tests": names_for(req["category"])}


@app.get("/api/test-requests/{rid}/image")
def get_test_request_image(rid: str) -> Response:
    rows = fetch("SELECT image, image_type FROM test_requests WHERE id = %s AND image IS NOT NULL", (request_id(rid),))
    if not rows:
        raise HTTPException(404, "image not found")
    return Response(rows[0]["image"], media_type=rows[0]["image_type"],
                    headers={"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"})


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
        return FileResponse(file)
    index = BUILD_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(404, "frontend not built")
    return FileResponse(index)
