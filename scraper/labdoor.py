import io
import logging
import re
from datetime import datetime

import pdfplumber
from bs4 import BeautifulSoup

from scraper.common import Blocked, category_for, client, connect, number, parse_date, product_id, request, save_report, source_id

BASE = "https://labdoor.com"
INDIAN_BRANDS = {"bal-bharat": "Bal Bharat", "bon-iso-whey": "Bon", "muscleblaze": "MuscleBlaze"}
INDIA_EDITION_BRANDS = {"myprotein": "MyProtein"}
LAB_URLS = {"Anresco": "https://anresco.com"}

ROW_RE = re.compile(r"^(.+?)\s+(\S*/\S+|%)\s+(\S+)\s+(.+?)\s*●$")
TESTED_RE = re.compile(r"Tested\s*for\s*(\w+)\s*\|\s*(PASS|FAIL)", re.I)
SUBSTANCE_RE = re.compile(r"Substance\s*\|\s*(.+?)\s+Unit\b")
FIELD_RE = re.compile(r"^(Product\s*Lot|Expiration\s*Date|Sample\s*Tested)\s+(.+)$")
MONTH_YEAR_RE = re.compile(r"([A-Za-z]+)\s*(\d{1,2})?,?\s*(\d{4})\s*$")
GROUPS = {"heavymetals": "heavy_metal", "microbiology": "other"}


def spaced(text: str) -> str:
    """Re-space text from PDFs whose spaces were dropped: 'October3,2024' -> 'October 3, 2024'."""
    return re.sub(r",(\d)", r", \1", re.sub(r"([A-Za-z])(\d)", r"\1 \2", text))


def us_date(raw: str):
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", raw):
        return datetime.strptime(raw, "%m/%d/%Y").date()
    return parse_date(raw)


def sample_date(raw: str):
    """End of the sampling window: 'March 12 to June 07, 2021' -> June 7 2021, 'September-October2024' -> Oct 2024."""
    m = MONTH_YEAR_RE.search(raw)
    if not m:
        return parse_date(raw)
    month, day, year = m.groups()
    return parse_date(f"{month} {day}, {year}" if day else f"{month} {year}")


def parse_coa(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines()]
    fields, results, verdicts = {}, [], []
    status, section = None, ""
    for i, line in enumerate(lines):
        if m := FIELD_RE.match(line):
            fields[re.sub(r"\s", "", m.group(1))] = m.group(2).strip()
        elif m := TESTED_RE.search(line):
            status = "pass" if m.group(2).upper() == "PASS" else None
            verdicts.append(m.group(2).lower())
        elif m := SUBSTANCE_RE.search(line):
            section = re.sub(r"\s", "", m.group(1)).lower()
        elif re.match(r"RELEASE\s*DATE", line) and i + 1 < len(lines):
            if m := re.match(r"^(.+?)\s+Labdoor\s+(.+)$", lines[i + 1]):
                fields["Released"], fields["Lab"] = spaced(m.group(1)), m.group(2).split(" and ")[0].strip()
        elif m := ROW_RE.match(line):
            param, unit, third, found = m.groups()
            param = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", param)
            found = found.rstrip("*").strip()
            active = section == "activeingredients"
            group = ("spiking" if "amino" in param.lower() else "nutrition") if active else GROUPS.get(section, "other")
            results.append({
                "parameter": param, "group": group, "unit": unit, "value": number(found), "value_raw": found,
                "label_claim": number(third.rstrip("*")) if active else None,
                "limit": None if active else number(third.rstrip("*")),
                "method": "USP limit" if third.endswith("*") else None, "status": status,
            })
    return {
        "batch_no": fields.get("ProductLot"),
        "expiry_date": us_date(fields["ExpirationDate"]) if fields.get("ExpirationDate") else None,
        "tested_on": sample_date(spaced(fields["SampleTested"])) if fields.get("SampleTested") else None,
        "issued_on": parse_date(fields.get("Released")),
        "lab": fields.get("Lab"),
        "verdict": "fail" if "fail" in verdicts else "pass" if verdicts else None,
        "results": results,
    }


def coa(http, cert_html: str) -> tuple[str | None, dict | None]:
    link = BeautifulSoup(cert_html, "html.parser").select_one("a.productCoa")
    if not link:
        return None, None
    pdf_url = link["href"]
    r = request(http, "GET", pdf_url)
    if not r:
        return pdf_url, None
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        return pdf_url, parse_coa("\n".join(page.extract_text() or "" for page in pdf.pages))


def review_slugs(http) -> list[tuple[str, str]]:
    found = []
    for key, brand in {**INDIAN_BRANDS, **INDIA_EDITION_BRANDS}.items():
        r = request(http, "GET", f"{BASE}/{key}")
        if not r:
            continue
        slugs = dict.fromkeys(re.findall(r'href="/review/([a-z0-9-]+)', r.text))
        found += [(s, brand) for s in slugs if key in INDIAN_BRANDS or "india" in s.split("-")]
    return found


def product_fields(html: str, brand: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.h1.get_text(strip=True)
    name, _, variant = title.rpartition(" - ") if " - " in title else (title, "", None)
    if variant == "India":
        name, variant = f"{name} (India)", None
    ranking = soup.select_one("a.backLink").get_text(strip=True) if soup.select_one("a.backLink") else ""
    image = soup.select_one('meta[property="og:image"]')
    grade = soup.select_one(".labdoorScoreLetterWrap.active")
    score = soup.select_one(".labdoorScoreValue")
    return {
        "brand": brand, "name": name, "variant": variant or None,
        "category": category_for(f"{ranking} {title}"),
        "image_url": image["content"] if image else None,
        "grade": grade.get_text(strip=True) if grade else None,
        "score": score.get_text(strip=True) if score else None,
    }


def save(conn, pid: str, publisher: str, url: str, pdf_url: str | None, data: dict, extra: list[dict], **fields) -> int:
    lab = data["lab"]
    results = extra + data["results"]
    save_report(
        conn, pid, publisher, url, results, pdf_url=pdf_url,
        lab_id=source_id(conn, lab, "lab", LAB_URLS.get(lab)) if lab else None,
        **{k: data[k] for k in ("batch_no", "expiry_date", "tested_on", "issued_on")}, **fields,
    )
    return len(results)


def main() -> None:
    stats = {"products": 0, "reports": 0, "results": 0}
    with client() as http, connect() as conn:
        publisher = source_id(conn, "Labdoor", "website")
        for slug, brand in review_slugs(http):
            url = f"{BASE}/review/{slug}"
            try:
                page = request(http, "GET", url)
                certs = request(http, "GET", f"{url}/certifications")
                if not page or not certs:
                    logging.warning("Missing review or certifications page for %s", url)
                    continue
                prod = product_fields(page.text, brand)
                lots = re.findall(r'data-lot="(/review/[^"]+\?lot=\d+)"', certs.text)
                reports = [(url, *coa(http, certs.text))]
                for lot in lots[1:]:
                    r = request(http, "GET", BASE + lot)
                    reports.append((BASE + lot, *coa(http, r.text)) if r else (BASE + lot, None, None))
                with conn.transaction():
                    pid = product_id(conn, prod["brand"], prod["name"], prod["variant"], prod["category"], image_url=prod["image_url"])
                    for i, (source_url, pdf_url, data) in enumerate(reports):
                        if not data:
                            logging.warning("No certificate of analysis for %s", source_url)
                            continue
                        if i == 0:
                            score = [{"parameter": "Labdoor Score", "group": "other", "unit": "score",
                                      "value": number(prod["score"]), "value_raw": prod["score"]}] if prod["score"] else []
                            n = save(conn, pid, publisher, source_url, pdf_url, data, score, verdict="grade", grade=prod["grade"])
                        else:
                            n = save(conn, pid, publisher, source_url, pdf_url, data, [], verdict=data["verdict"])
                        stats["reports"] += 1
                        stats["results"] += n
                stats["products"] += 1
                logging.info("%s %s: grade %s, %d lots", prod["brand"], prod["name"], prod["grade"], len(reports))
            except Blocked:
                raise
            except Exception:
                logging.exception("Failed on %s", url)
    logging.info("Labdoor done: %s", stats)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("pdfminer").setLevel(logging.WARNING)
    main()
