"""Read product details from an amazon.in listing to pre-fill a test request."""

import logging
import re
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

HOSTS = {"amazon.in", "www.amazon.in", "m.amazon.in"}
SHORT_HOSTS = {"amzn.in", "www.amzn.in", "amzn.to", "a.co"}
ASIN_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d|product)/([A-Z0-9]{10})(?:[/?]|$)", re.I)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/130.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-IN,en;q=0.9",
}


class NotAmazon(ValueError):
    pass


class Unreadable(RuntimeError):
    pass


def asin_from_url(url: str) -> str | None:
    """ASIN of an amazon.in product URL, or None if it isn't one."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() not in HOSTS:
        return None
    match = ASIN_RE.search(parts.path)
    return match[1].upper() if match else None


def resolve_asin(url: str, client: httpx.Client) -> str:
    """ASIN from an amazon.in link, following amzn.in-style short links (only to Amazon hosts)."""
    for _ in range(4):
        if asin := asin_from_url(url):
            return asin
        parts = urlsplit(url.strip())
        if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() not in SHORT_HOSTS:
            raise NotAmazon("not an amazon.in product link")
        resp = client.get(url, follow_redirects=False)
        if "location" not in resp.headers:
            raise NotAmazon("short link did not lead to an amazon.in product")
        url = urljoin(url, resp.headers["location"])
    raise NotAmazon("too many redirects")


def parse(html: str) -> dict:
    s = BeautifulSoup(html, "html.parser")
    details = {}
    for tr in s.select("#productDetails_techSpec_section_1 tr, #productDetails_detailBullets_sections1 tr"):
        if (th := tr.find("th")) and (td := tr.find("td")):
            details[th.get_text(" ", strip=True).lower()] = td.get_text(" ", strip=True)
    for li in s.select("#detailBullets_feature_div li"):
        text = li.get_text(" ", strip=True).replace("‎", "").replace("‏", "")
        if ":" in text:
            key, value = text.split(":", 1)
            details[key.strip().lower()] = value.strip()

    title_el = s.select_one("#productTitle")
    title = title_el.get_text(" ", strip=True) if title_el else None
    brand_el = s.select_one("tr.po-brand td:last-child")
    brand = brand_el.get_text(" ", strip=True) if brand_el else details.get("brand")
    if not brand and (byline := s.select_one("#bylineInfo")):
        brand = re.sub(r"^(Visit the |Brand: )|( Store)$", "", byline.get_text(" ", strip=True)) or None
    image_el = s.select_one("#landingImage")
    image = image_el and (image_el.get("data-old-hires") or image_el.get("src"))
    net = details.get("net quantity")
    crumbs = s.select_one("#wayfinding-breadcrumbs_feature_div")

    name = title
    if title and brand and title.lower().startswith(brand.lower()):
        name = title[len(brand):].strip(" -:|")
    if name:
        name = re.split(r",| \| | - ", name)[0].strip()[:200] or None
    return {
        "brand": brand.title() if brand and brand.isupper() else brand,
        "name": name,
        "title": title,
        "generic_name": details.get("generic name"),
        "breadcrumbs": crumbs.get_text(" ", strip=True) if crumbs else None,
        "image_url": image or None,
        "manufacturer": (details.get("manufacturer") or None) and details["manufacturer"][:200],
        "net_quantity": re.sub(r"\.0\b", "", net) if net else None,
    }


def guess_category(product: dict, categories: list[str]) -> str | None:
    """Longest category label found in the generic name, else the breadcrumbs, else the title."""
    for key in ("generic_name", "breadcrumbs", "title"):
        text = (product.get(key) or "").lower()
        best = None
        for cat in categories:
            if cat == "other":
                continue
            words = cat.replace("_supplement", "").replace("_", " ")
            for label in (words, words.rstrip("s")):
                if re.search(rf"\b{re.escape(label)}\b", text) and (best is None or len(label) > best[0]):
                    best = (len(label), cat)
        if best:
            return best[1]
    return None


def fetch(url: str) -> tuple[str, dict]:
    """(asin, product details) for an amazon.in link. Raises NotAmazon or Unreadable."""
    with httpx.Client(headers=HEADERS, timeout=15) as client:
        asin = resolve_asin(url, client)
        resp = client.get(f"https://www.amazon.in/dp/{asin}", follow_redirects=True)
    if resp.status_code != 200 or "captcha" in resp.text[:20000].lower():
        logging.warning("amazon fetch for %s failed: status %s, %d bytes", asin, resp.status_code, len(resp.content))
        raise Unreadable("Amazon did not return the product page")
    product = parse(resp.text)
    if not product["title"]:
        logging.warning("amazon page for %s had no product title", asin)
        raise Unreadable("could not find product details on the page")
    return asin, product
