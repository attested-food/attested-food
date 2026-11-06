import logging
import os
import uuid
from pathlib import Path

import orjson
import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, ORJSONResponse
from psycopg.rows import dict_row
from psycopg.types.json import set_json_loads

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
    return rows[0]


@app.get("/api/sources")
def list_sources() -> list[dict]:
    return fetch(SOURCES_SQL)


@app.get("/api/categories")
def list_categories() -> list[dict]:
    return fetch(CATEGORIES_SQL)


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
