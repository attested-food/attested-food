import pytest
from fastapi.testclient import TestClient

from backend import main

client = TestClient(main.app)

PRODUCT_KEYS = {"id", "brand", "name", "variant", "category", "image_url", "report_count", "has_user_report", "latest"}
DETAIL_KEYS = {"id", "brand", "name", "variant", "category", "manufacturer", "fssai_license", "barcode",
               "net_quantity", "image_url", "reports"}
REPORT_KEYS = {"id", "kind", "lab", "publisher", "source_url", "report_number", "ulr_number", "batch_no", "mfg_date",
               "expiry_date", "tested_on", "issued_on", "verdict", "grade", "pdf_url", "pdf_sha256", "verification",
               "verified", "chain_tx", "fetched_at", "results"}
RESULT_KEYS = {"parameter", "group", "unit", "value", "value_raw", "label_claim", "limit", "method", "status"}
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
    assert {"category", "product_count"} == set(body[0])
    assert any(c["category"] == "breakfast_cereal" and c["product_count"] >= 1 for c in body)


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
