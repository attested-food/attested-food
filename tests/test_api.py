import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.category_tests import coverage

client = TestClient(main.app)

PRODUCT_KEYS = {"id", "brand", "name", "variant", "category", "image_url", "label_nutrition", "report_count",
                "has_user_report", "latest"}
DETAIL_KEYS = {"id", "brand", "name", "variant", "category", "manufacturer", "fssai_license", "barcode",
               "net_quantity", "image_url", "reports", "tests", "ingredients", "ingredients_source", "label_nutrition",
               "annotations"}
REPORT_KEYS = {"id", "kind", "lab", "publisher", "source_url", "report_number", "ulr_number", "batch_no", "mfg_date",
               "expiry_date", "tested_on", "issued_on", "verdict", "grade", "pdf_url", "pdf_sha256", "verification",
               "verified", "chain_tx", "fetched_at", "results"}
RESULT_KEYS = {"parameter", "group", "unit", "value", "value_raw", "label_claim", "limit", "detection_limit", "method", "status"}
SOURCE_KEYS = {"id", "name", "url", "accreditation"}


def products(**params) -> dict:
    resp = client.get("/api/products", params=params)
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture(scope="module")
def kelloggs() -> dict:
    items = products(q="Millet Muesli")["items"]
    return next(p for p in items if p["brand"] == "Kellogg's")


def test_health():
    assert client.get("/api/health").json() == {"ok": True}


def test_list_shape():
    body = products()
    assert body["page"] == 1 and body["page_size"] == 24 and body["total"] >= 1
    for item in body["items"]:
        assert set(item) == PRODUCT_KEYS
        if item["latest"] is not None:
            assert set(item["latest"]) == {"kind", "verdict", "grade", "publisher", "lab", "tested_on"}


@pytest.mark.parametrize("q", ["muesli", "MUES", "kellogg", "millet muesli", "choco"])
def test_search_matches(q, kelloggs):
    assert kelloggs["id"] in {p["id"] for p in products(q=q, page_size=100)["items"]}


@pytest.mark.parametrize("params", [
    {"q": "zzqqxx-no-such-product"},
    {"category": "zzqqxx-no-such-category"},
    {"brand": "zzqqxx-no-such-brand"},
])
def test_filters_exclude(params):
    assert products(**params) == {"items": [], "page": 1, "page_size": 24, "total": 0}


@pytest.mark.parametrize("params", [{"brand": "kellogg's"}, {"category": "breakfast_cereal"}])
def test_filters_include(params, kelloggs):
    body = products(**params, page_size=100)
    assert kelloggs["id"] in {p["id"] for p in body["items"]}
    key, value = next(iter(params.items()))
    assert all(p[key].lower() == value.lower() for p in body["items"])


def test_pagination():
    total = products()["total"]
    first = products(page=1, page_size=1)
    assert first["total"] == total and len(first["items"]) == 1
    beyond = products(page=total + 1, page_size=1)
    assert beyond["items"] == [] and beyond["total"] == total


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 0}, {"page_size": 101}])
def test_pagination_bounds(params):
    assert client.get("/api/products", params=params).status_code == 422


def test_product_detail(kelloggs):
    body = client.get(f"/api/products/{kelloggs['id']}").json()
    assert set(body) == DETAIL_KEYS
    assert body["reports"][0]["kind"] == "user"
    for report in body["reports"]:
        assert set(report) == REPORT_KEYS
        for src in (report["lab"], report["publisher"]):
            assert src is None or set(src) == SOURCE_KEYS
        for result in report["results"]:
            assert set(result) == RESULT_KEYS
            assert result["value"] is None or isinstance(result["value"], (int, float))
    report = body["reports"][0]
    assert report["lab"]["name"] == "Equinox Labs"
    assert report["tested_on"] == "2026-11-03"


@pytest.mark.parametrize("pid", ["00000000-0000-0000-0000-000000000000", "not-a-uuid", "123", "' or 1=1 --"])
def test_product_not_found(pid):
    assert client.get(f"/api/products/{pid}").status_code == 404


def test_sources():
    body = client.get("/api/sources").json()
    assert len(body) >= 7
    for s in body:
        assert set(s) == {"id", "type", "name", "url", "accreditation", "description", "report_count"}
        assert s["type"] in {"lab", "website"}
    assert next(s for s in body if s["name"] == "Equinox Labs")["report_count"] >= 1


def test_categories():
    body = client.get("/api/categories").json()
    assert {"category", "product_count", "tests"} == set(body[0])
    assert all(c["tests"] for c in body)
    cereal = next(c for c in body if c["category"] == "breakfast_cereal")
    assert cereal["product_count"] >= 1 and cereal["tests"] == ["Nutrition vs label claims"]


def test_product_tests_coverage(kelloggs):
    body = client.get(f"/api/products/{kelloggs['id']}").json()
    assert body["tests"] == [{"name": "Nutrition vs label claims", "tested": True}]


@pytest.mark.parametrize(("category", "results", "expected"), [
    ("protein_powder", [{"group": "heavy_metal", "parameter": "Lead"}], {"Heavy metals (lead, arsenic, cadmium, mercury)"}),
    ("ghee", [{"group": "other", "parameter": "Beta-sitosterol"}], {"Foreign fat adulteration (vegetable / animal fat)"}),
    ("honey", [{"group": "other", "parameter": "Hydroxymethylfurfural (HMF)"}], {"Freshness (HMF, diastase)"}),
    ("bread", [{"group": "toxin", "parameter": "Listeria"}], {"Microbiology (E. coli, Salmonella, Listeria)"}),
    ("vitamin_d_supplement", [], set()),
    ("zz_unknown", [{"group": "toxin", "parameter": "Total Aflatoxins"}], {"Aflatoxins"}),
])
def test_coverage(category, results, expected):
    assert {t["name"] for t in coverage(category, results) if t["tested"]} == expected


GOOD_REQUEST = {"brand": "Zzqq Test Brand", "name": "Zzqq Test Product", "category": "peanut_butter",
                "image_url": "https://example.com/p.jpg"}
PNG_1PX = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
           "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


@pytest.mark.parametrize("extra", [{}, {"image_url": None, "image_data": PNG_1PX, "fssai_license": "10012345678901",
                                        "barcode": "8901234567890", "buy_url": "https://amazon.in/x"}])
def test_test_request_created(extra):
    resp = client.post("/api/test-requests", json={**GOOD_REQUEST, **extra})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["tests"][0] == "Nutrition vs label claims"
    req = client.get(f"/api/test-requests/{body['id']}").json()
    assert req["brand"] == GOOD_REQUEST["brand"] and req["tests"] == body["tests"]
    if "image_data" in extra:
        assert req["image_url"] == f"/api/test-requests/{body['id']}/image"
        img = client.get(req["image_url"])
        assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content[:4] == b"\x89PNG"
    main.fetch("DELETE FROM test_requests WHERE id = %s RETURNING id", (body["id"],))


@pytest.mark.parametrize("change", [
    {"brand": ""},
    {"image_url": None},
    {"image_data": PNG_1PX},
    {"image_url": "ftp://x"},
    {"category": "Not A Category"},
    {"fssai_license": "123"},
    {"barcode": "abc"},
    {"unknown": "x"},
])
def test_test_request_invalid(change):
    assert client.post("/api/test-requests", json={**GOOD_REQUEST, **change}).status_code == 422


def test_test_request_bad_image():
    body = {**GOOD_REQUEST, "image_url": None, "image_data": "data:image/gif;base64,R0lGOD"}
    assert client.post("/api/test-requests", json=body).status_code == 422


def test_test_request_duplicate(kelloggs):
    body = {**GOOD_REQUEST, "brand": "KELLOGG'S", "name": "millet muesli", "variant": "choco"}
    resp = client.post("/api/test-requests", json=body)
    assert resp.status_code == 409
    assert resp.json()["detail"]["product_id"] == kelloggs["id"]


@pytest.mark.parametrize(("path", "status", "content"), [
    ("/", 200, "<html>spa</html>"),
    ("/products/abc", 200, "<html>spa</html>"),
    ("/_app/app.js", 200, "console.log(1)"),
    ("/api/unknown", 404, '{"detail":"not found"}'),
])
def test_frontend_serving(path, status, content, tmp_path, monkeypatch):
    (tmp_path / "_app").mkdir()
    (tmp_path / "index.html").write_text("<html>spa</html>")
    (tmp_path / "_app" / "app.js").write_text("console.log(1)")
    monkeypatch.setattr(main, "BUILD_DIR", tmp_path)
    resp = client.get(path)
    assert resp.status_code == status and resp.text == content


def test_test_request_already_requested():
    created = client.post("/api/test-requests", json={**GOOD_REQUEST, "buy_url": "https://www.amazon.in/x/dp/B0ZZQQ0001"})
    assert created.status_code == 201
    rid = created.json()["id"]
    try:
        same_link = {**GOOD_REQUEST, "name": "Other Name", "buy_url": "https://amazon.in/dp/B0ZZQQ0001?ref=y"}
        for body in (GOOD_REQUEST, same_link):
            resp = client.post("/api/test-requests", json=body)
            assert resp.status_code == 409
            assert resp.json()["detail"]["request"]["id"] == rid
        for q in ("zzqq test", "Zzqq Brand Product", "product zzqq", "Zzqq Test Brand Test Product Extra"):
            found = client.get("/api/duplicates", params={"q": q}).json()
            assert found[0] == {"kind": "request", "id": rid, "brand": GOOD_REQUEST["brand"], "name": GOOD_REQUEST["name"],
                                "variant": None, "category": "peanut_butter", "requested_on": found[0]["requested_on"]}
        for params in ({"q": "zzqq test"}, {"q": "ZZQQ"}, {"brand": "zzqq test brand"}, {"category": "peanut_butter", "q": "zzqq"}):
            listed = client.get("/api/test-requests", params=params).json()
            assert [r["id"] for r in listed] == [rid] and listed[0]["image_url"] == GOOD_REQUEST["image_url"]
        for params in ({"q": "zzqq", "category": "ghee"}, {"brand": "zzqq"}):
            assert client.get("/api/test-requests", params=params).json() == []
    finally:
        main.fetch("DELETE FROM test_requests WHERE id = %s RETURNING id", (rid,))


@pytest.mark.parametrize("url", ["https://example.com/dp/B08R3CLJ8H", "http://169.254.169.254/"])
def test_prefill_rejects_non_amazon(url):
    assert client.get("/api/prefill", params={"url": url}).status_code == 422


@pytest.mark.parametrize("rid", ["not-a-uuid", "00000000-0000-0000-0000-000000000000"])
def test_test_request_not_found(rid):
    assert client.get(f"/api/test-requests/{rid}").status_code == 404
    assert client.get(f"/api/test-requests/{rid}/image").status_code == 404


@pytest.mark.parametrize("q", ["Kellogg's Millet", "muesli kelloggs choco", "Kellogg's Choco Millet Muesli 400g"])
def test_duplicates_finds_product(q, kelloggs):
    found = client.get("/api/duplicates", params={"q": q}).json()
    assert {"kind": "product", "id": kelloggs["id"]}.items() <= found[0].items()


@pytest.mark.parametrize("q", ["zzqqxx nothing here", "%%", "__"])
def test_duplicates_no_match(q):
    assert client.get("/api/duplicates", params={"q": q}).json() == []


@pytest.mark.parametrize(("path", "cache"), [
    ("/", "no-cache"),
    ("/request", "no-cache"),
    ("/assets/x.js", "public, max-age=31536000, immutable"),
])
def test_frontend_cache_headers(path, cache, tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir(parents=True)
    (tmp_path / "index.html").write_text("<html>spa</html>")
    (tmp_path / "assets" / "x.js").write_text("1")
    monkeypatch.setattr(main, "BUILD_DIR", tmp_path)
    assert client.get(path).headers["cache-control"] == cache


WALL_KEYS = {"kind", "id", "brand", "name", "variant", "category", "image_url", "ingredients", "label_nutrition",
             "state", "grade", "grade_source", "report_kind", "lab", "tested_on", "annotations"}


def test_wall_shape():
    body = client.get("/api/wall", params={"limit": 4}).json()
    products_ = [i for i in body["items"] if i["kind"] == "product"]
    assert 1 <= len(products_) <= 4
    for item in body["items"]:
        assert set(item) == WALL_KEYS
        assert set(item["annotations"]) == {"segments", "findings", "counts"}
    first = products_[0]
    assert first["report_kind"] == "user" and first["grade"] is None


@pytest.mark.parametrize("limit", [0, 49])
def test_wall_limit_bounds(limit):
    assert client.get("/api/wall", params={"limit": limit}).status_code == 422


def test_detail_has_annotations(kelloggs):
    body = client.get(f"/api/products/{kelloggs['id']}").json()
    assert set(body["annotations"]["counts"]) == {"pass", "fail", "untested"}
    assert "ingredients" in body and "label_nutrition" in body


def test_evidence_filter():
    lab = client.get("/api/products", params={"evidence": "lab", "page_size": 100}).json()
    assert lab["total"] >= 1 and all(p["has_user_report"] for p in lab["items"])
    pub = client.get("/api/products", params={"evidence": "published", "page_size": 100}).json()
    assert pub["total"] >= 1 and not any(p["has_user_report"] for p in pub["items"])
    both = client.get("/api/products", params=[("evidence", "lab"), ("evidence", "published")]).json()
    assert both["total"] == lab["total"] + pub["total"]


@pytest.mark.parametrize(("param", "key", "check"), [
    ("no_added_sugar", "added_sugars_g", lambda v: v == 0),
    ("high_fibre", "fiber_g", lambda v: v >= 6),
    ("high_protein", "protein_g", lambda v: v >= 20),
])
def test_label_filters(param, key, check):
    body = client.get("/api/products", params={param: "true", "page_size": 100}).json()
    assert body["total"] >= 1
    assert all(check(p["label_nutrition"][key]) for p in body["items"])


def test_unknown_evidence_rejected():
    assert client.get("/api/products", params={"evidence": "rumour"}).status_code == 422


def test_thumb_refuses_unknown_images():
    assert client.get("/api/thumb", params={"src": "https://example.com/not-ours.jpg"}).status_code == 404
    assert client.get("/api/thumb", params={"src": "/api/test-requests/00000000-0000-0000-0000-000000000000/image"}).status_code == 404


def test_thumb_width_bounds():
    assert client.get("/api/thumb", params={"src": "x", "w": 10}).status_code == 422
