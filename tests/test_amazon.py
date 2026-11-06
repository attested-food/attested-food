import pytest

from backend import amazon

PAGE = """
<span id="productTitle"> PINTOLA High Protein Peanut Butter Crunchy 1kg, Added Whey, 30g Protein </span>
<table><tr class="po-brand"><td>Brand</td><td>PINTOLA</td></tr></table>
<img id="landingImage" src="https://m.media-amazon.com/small.jpg" data-old-hires="https://m.media-amazon.com/big.jpg">
<div id="wayfinding-breadcrumbs_feature_div">Grocery › Spreads › Peanut Butter</div>
<div id="detailBullets_feature_div"><ul>
  <li>Manufacturer &#8207; : &#8206; DAS FOODTECH PRIVATE LIMITED</li>
  <li>Net Quantity &#8207; : &#8206; 1000.0 Grams</li>
  <li>Generic Name &#8207; : &#8206; Peanut Butter</li>
</ul></div>
"""


def test_parse():
    p = amazon.parse(PAGE)
    assert p["brand"] == "Pintola"
    assert p["name"] == "High Protein Peanut Butter Crunchy 1kg"
    assert p["image_url"] == "https://m.media-amazon.com/big.jpg"
    assert p["manufacturer"] == "DAS FOODTECH PRIVATE LIMITED"
    assert p["net_quantity"] == "1000 Grams"
    assert amazon.guess_category(p, ["butter", "peanut_butter", "other"]) == "peanut_butter"


def test_parse_empty_page():
    assert amazon.parse("<html></html>")["title"] is None


@pytest.mark.parametrize(("url", "asin"), [
    ("https://www.amazon.in/Pintola-Protein/dp/B08R3CLJ8H?ref=x", "B08R3CLJ8H"),
    ("https://amazon.in/dp/b08r3clj8h", "B08R3CLJ8H"),
    ("https://www.amazon.in/gp/product/B08R3CLJ8H/", "B08R3CLJ8H"),
    ("https://m.amazon.in/gp/aw/d/B08R3CLJ8H", "B08R3CLJ8H"),
    ("https://www.amazon.com/dp/B08R3CLJ8H", None),
    ("https://evil.com/www.amazon.in/dp/B08R3CLJ8H", None),
    ("https://www.amazon.in.evil.com/dp/B08R3CLJ8H", None),
    ("ftp://www.amazon.in/dp/B08R3CLJ8H", None),
    ("https://www.amazon.in/s?k=pintola", None),
])
def test_asin_from_url(url, asin):
    assert amazon.asin_from_url(url) == asin


@pytest.mark.parametrize("url", ["https://example.com/x", "http://169.254.169.254/", "not a url"])
def test_resolve_rejects_other_hosts(url):
    with pytest.raises(amazon.NotAmazon):
        amazon.resolve_asin(url, client=None)
