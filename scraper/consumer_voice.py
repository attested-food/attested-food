import difflib
import io
import logging
import re
import string
import sys
from urllib.parse import unquote

import httpx
import pdfplumber

from scraper.common import (
    Blocked, category_for, client, connect, norm, number, parse_date, product_id, request, save_report, source_id,
)

BASE = "https://consumeraffairs.nic.in/sites/default/files/file-uploads/ctocpas/"
ARCHIVE = "https://web.archive.org/web/{}id_/"
SNAPSHOTS = ("2025", "2022", "2019", "2016")

# Consumer VOICE comparative food tests listed at
# https://consumeraffairs.nic.in/consumer-corner/comparative-test-of-consumer-products-and-services
# (file name, product name, category)
PDFS = [
    ("corn%20flakes-12.pdf", "Corn Flakes", "breakfast_cereal"),
    ("Milk%20Packaged-11.pdf", "Packaged Milk", "milk"),
    ("Groundnut%20Oils.pdf", "Groundnut Oil", "cooking_oil"),
    ("Patato%20chips%20adn%20snack%20foods-11.pdf", "Potato Chips", "snacks"),
    ("HealthDrinks.pdf", "Health Drink", "health_drink"),
    ("PackagedFoodSeries_MarieBiscuit.pdf", "Marie Biscuit", "biscuits"),
    ("Mixed%20Pickles_13.pdf", "Mixed Pickle", "pickle"),
    ("RiceBranOIl.pdf", "Rice Bran Oil", "cooking_oil"),
    ("DairyWhiteners.pdf", "Dairy Whitener", "dairy_whitener"),
    ("Table%20Butter.pdf", "Table Butter", "butter"),
    ("SUNFLOWER%20OIL%20.pdf", "Sunflower Oil", "cooking_oil"),
    ("BasmatiRice.pdf", "Basmati Rice", "rice"),
    ("Groundnut%20Oil-13.pdf", "Groundnut Oil", "cooking_oil"),
    ("soan%20papdi-12.pdf", "Soan Papdi", "sweets"),
    ("Honey.pdf", "Honey", "honey"),
    ("Honey_0.pdf", "Honey", "honey"),
    ("PackagedFoodSeries_MutterPaneer_13.pdf", "Mutter Paneer", "ready_to_eat"),
    ("Mustard%20Oil-11.pdf", "Kachchi Ghani Mustard Oil", "cooking_oil"),
    ("MixedFruitJam.pdf", "Mixed Fruit Jam", "jam"),
    ("TondMilk.pdf", "Toned Milk", "milk"),
    ("sunfloweroil.pdf", "Sunflower Oil", "cooking_oil"),
    ("Black-Tea.pdf", "Black Tea", "tea"),
    ("Chocolates.pdf", "Chocolate", "chocolate"),
    ("Health_Drink.pdf", "Health Drink", "health_drink"),
    ("GlucosePowder.pdf", "Glucose Powder", "glucose_powder"),
    ("Patato-Chips.pdf", "Potato Chips", "snacks"),
    ("Salt_0.pdf", "Iodised Salt", "salt"),
    ("MixedFruitJuices.pdf", "Mixed Fruit Juice", "juice"),
    ("PackagedFullCreamMilk.pdf", "Full Cream Milk", "milk"),
    ("Oats.pdf", "Oats", "breakfast_cereal"),
    ("biscuit-12.pdf", "Biscuit", "biscuits"),
    ("WheatFlour%28Atta%29.pdf", "Whole Wheat Atta", "flour"),
    ("CT_Paneer-13.pdf", "Paneer", "paneer"),
    ("brown%20%26%20white%20Bread-12.pdf", "Bread", "bread"),
    ("DigestiveBiscuits.pdf", "Digestive Biscuit", "biscuits"),
    ("Ghee.pdf", "Ghee", "ghee"),
    ("ketchup_13.pdf", "Tomato Ketchup", "ketchup"),
    ("NOODLES_June2021.pdf", "Instant Noodles", "instant_noodles"),
    ("Vansapti%20Ghee.pdf", "Vanaspati", "vanaspati"),
    ("CPT.pdf", "Atta / Oats Noodles", "instant_noodles"),
    ("Diabetes_Care_Nutritional_Food.pdf", "Diabetes Care Nutritional Food", "supplement"),
    ("Tomato_Ketchup_Sep2021.pdf", "Tomato Ketchup", "ketchup"),
    ("Mixed%20Fruit%20Jam_0.pdf", "Mixed Fruit Jam", "jam"),
    ("Packaged%20Toned%20Milk.pdf", "Toned Milk", "milk"),
    ("Seasonings.pdf", "Seasoning", "spices"),
    ("Dairy%20Whitener.pdf", "Dairy Whitener", "dairy_whitener"),
    ("Groundnut_oil.pdf", "Groundnut Oil", "cooking_oil"),
    ("RiceBranOil_Dec2021.pdf", "Rice Bran Oil", "cooking_oil"),
    ("Rice_Bran_Oil.pdf", "Rice Bran Oil", "cooking_oil"),
    ("WhiteBreads_R.pdf", "White Bread", "bread"),
    ("Instant%20Masala%20Noodles%20Story.pdf", "Instant Masala Noodles", "instant_noodles"),
    ("SUBNFLOWER_OIL.pdf", "Sunflower Oil", "cooking_oil"),
    ("Desi_Ghee.pdf", "Desi Ghee", "ghee"),
    ("CowGhee_2023.pdf", "Cow Ghee", "ghee"),
    ("Mixed%20Fruit%20Jam.pdf", "Mixed Fruit Jam", "jam"),
    ("CURD.pdf", "Curd", "curd"),
    ("Refined_Soyabean_Oil.pdf", "Refined Soyabean Oil", "cooking_oil"),
    ("TableButter.pdf", "Table Butter", "butter"),
    ("RICEBRANOIL.pdf", "Rice Bran Oil", "cooking_oil"),
    ("SUNFLOWEROIL.pdf", "Sunflower Oil", "cooking_oil"),
    ("COW%20GHEE.pdf", "Cow Ghee", "ghee"),
    ("TOMATO%20KETCHUP.pdf", "Tomato Ketchup", "ketchup"),
    ("GROUND_NUT_OIL.pdf", "Groundnut Oil", "cooking_oil"),
    ("Curd%20%28Dahi%29.pdf", "Dahi", "curd"),
]

HEADER_RE = re.compile(r"^((parameters?\s+)?brands?|(test )?parameters?)\b", re.I)
SUB_RE = re.compile(r"^(claim|declared|results?)\b", re.I)
LIMIT_RE = re.compile(r"^(requirements?|specifications?|standards?|limits?|permissible|fssai|bis\b|as per (fssai|bis|is))", re.I)
LIMIT = "__limit__"
RANK_RE = re.compile(r"^rank\b|total score|manufactured|marketed by", re.I)
PARAM_HDR = re.compile(r"^(test )?parameters?\b(?!.*brand)", re.I)
WEIGHT_RE = re.compile(r"^%|^(wt\b|weigh)|weigh\w*-?\s*$|\batge\b", re.I)
PARAM_HINT = re.compile(
    r"%|\(|/|,|rank|score|mrp|price|weight|value|content|test|fat|protein|sugar|moisture|ash|acid|fibre|fiber|energy"
    r"|vitamin|sodium|iron|calcium|appearance|aroma|taste|texture|accept|shelf|before|manufactur|pack|type|grade"
    r"|mark|net|lead|count|colou?r|flavou?r|claim|carbohydrate|salt|bite|odou?r|consistency|overall|mineral|starch|result",
    re.I,
)
SKIP_ROW = re.compile(r"^(wt\.?|weightage|%\s*(wt|weight)|score rating|\*|note|source|results?$|brands?\b)", re.I)
ISSUE_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s*((?:19|20)\d\d)\b", re.I
)
UNIT_RE = re.compile(r"%|/|\b(mg|mcg|µg|μg|g|gm|grams?|kcal|k cal|cal|ppm|ppb|cfu|ml|litres?|kg|meq|mm|iu|rs)\b", re.I)
PASS_RE = re.compile(r"^(pass(ed)?|absent|negative|not detected|nd|complies|conforms|nil)$", re.I)
FAIL_RE = re.compile(r"^(fail(ed)?|present|positive|detected|does not comply|not conform)$", re.I)
GROUPS = (
    ("heavy_metal", r"\b(lead|arsenic|cadmium|mercury|copper|tin|chromium|nickel|heavy metal)"),
    ("toxin", r"aflatoxin|mycotoxin|patulin|ochratoxin"),
    ("pesticide", r"pesticide|residue|ethion|quinalphos|dicofol|glyphosate|chlorpyrifos"),
    ("spiking", r"iron (particles|filings)|argemone|mineral oil|melamine|adulter|foreign fat|vanaspati|c4 sugar|sugar syrup|colou?ring matter"
                r"|synthetic colou?r|starch|urea|detergent|neutrali[sz]er|castor|cotton ?seed|sesame oil test|hexane|bha"),
    ("nutrition", r"protein|fat|carbohydrate|sugar|energy|calori|fibre|fiber|vitamin|iron|calcium|sodium|salt|moisture"
                  r"|\bash\b|cholesterol|fatty|mufa|pufa|trans|saturat|iodine|zinc|potassium|phosphorus|solid|snf|palmitic|stearic"
                  r"|oleic|linole|omega"),
)


def clean(cell: str | None) -> str:
    text = re.sub(r"\s+", " ", (cell or "").replace("’", "'").replace("‘", "'")).strip()
    return re.sub(r"(\w)- (\w)", r"\1\2", text)


def page_tables(page: pdfplumber.page.Page) -> list[list[list[str]]]:
    """Text printed sideways comes out reversed; flip such cells, and put the header first in sideways tables."""
    sideways = lambda c: not c["upright"]
    out = []
    for t in page.find_tables():
        rows = t.extract()
        if len(rows) < 3:
            continue
        inside = lambda box: [c for c in page.chars if box[0] <= c["x0"] <= box[2] and box[1] <= c["top"] <= box[3]]
        if sum(map(sideways, chars := inside(t.bbox))) * 2 > len(chars):
            rows = [[c[::-1] if c else c for c in row] for row in reversed(rows)]
        else:
            for r, row in enumerate(t.rows):
                for j, box in enumerate(row.cells):
                    if box and rows[r][j] and sum(map(sideways, chars := inside(box))) * 2 > len(chars):
                        rows[r][j] = rows[r][j][::-1]
        out.append([[clean(c) for c in row] for row in rows])
    return out


def split_unit(label: str) -> tuple[str, str | None]:
    """'Protein, %' -> ('Protein', '%'); 'Salt (in %)' -> ('Salt', '%')."""
    label = re.sub(r"^\d+(\.\d+)*\.?\s+|\*+$", "", label).strip()
    m = (re.match(r"^(.*?)\s*\((?:in\s+)?([^()]*)\)\s*$", label) or re.match(r"^(.*),\s*([^,]+)$", label)
         or re.match(r"^(.*?)\s*(%)$", label))
    if m and UNIT_RE.search(m.group(2)):
        return m.group(1).strip(" ,:") or label, m.group(2).strip()
    return label, None


def group_for(name: str) -> str:
    return next((g for g, pat in GROUPS if re.search(pat, name, re.I)), "other")


def status_for(raw: str) -> str | None:
    return "pass" if PASS_RE.match(raw) else "fail" if FAIL_RE.match(raw) else None


def value_of(raw: str) -> float | None:
    return number(re.sub(r"[\s*%]+$", "", raw).replace(",", ""))


def display(label: str) -> str:
    """'MURGiNNS' / 'kellogg's' -> 'Murginns' / 'Kellogg's'; normal casing kept."""
    letters = [c for c in label if c.isalpha()]
    upper = sum(c.isupper() for c in letters)
    odd = label.islower() or (0 < len(letters) - upper < upper and upper > 3)
    return string.capwords(label) if odd else label


class Brands:
    def __init__(self) -> None:
        self.names: dict[str, str] = {}

    def match(self, label: str, add: bool | str) -> str | None:
        """Key of the closest known brand; add=True adds unmatched labels, add='new' adds every distinct label."""
        label = re.sub(r"[*#]+|\s*\(value for money\)", "", clean(label), flags=re.I).strip(" .")
        n = norm(label)
        if len(n) < 2 or n.isdigit() or re.search(r"\bloose\b", label, re.I):
            return None
        if add == "new":
            near = next((k for k in self.names if difflib.SequenceMatcher(None, k, n).ratio() >= 0.9), n)
            self.names.setdefault(near, label)
            return near
        flipped = norm(" ".join(reversed(label.split())))
        if flipped in self.names and n not in self.names:
            n = flipped
        best = max(
            self.names,
            key=lambda k: (k == n, len(min(k, n, key=len)) >= 4 and (k.startswith(n) or n.startswith(k)),
                           difflib.SequenceMatcher(None, k, n).ratio()),
            default=None,
        )
        if best and (best == n or (len(min(best, n, key=len)) >= 4 and (best.startswith(n) or n.startswith(best)))
                     or difflib.SequenceMatcher(None, best, n).ratio() >= 0.75):
            if self.names[best] != display(self.names[best]) and display(label) == label:
                self.names[best] = label
            return best
        if add:
            self.names[n] = label
            return n
        return None


def header_index(table: list[list[str]], brands: Brands) -> tuple[int, str, bool] | None:
    """Header row, orientation ('rows': one brand per row, 'cols': one brand per column), explicit brand header."""
    for i, row in enumerate(table[:4]):
        for c, cell in enumerate(row):
            if not HEADER_RE.match(cell):
                continue
            if PARAM_HDR.match(cell):
                return i, "cols", True
            others = [x for j, x in enumerate(row) if j != c and x]
            if others:
                hinted = sum(bool(PARAM_HINT.search(x)) for x in others)
                return i, "rows" if hinted * 2 >= len(others) else "cols", True
        if sum(brands.match(x, False) is not None for x in row if x and not PARAM_HINT.search(x)) >= 3:
            return i, "cols", False
    return None


def is_text(x: str) -> bool:
    return bool(x) and not re.fullmatch(r"[\d.,/\s%-]+", x)


def headers(table: list[list[str]], h: int, orient: str, brands: Brands) -> tuple[list[str], list[str | None], int]:
    """Column labels and Claim/Result sub-labels, folding a second header row (brands, units, Result/Declared) in."""
    head, nxt = list(table[h]), table[h + 1] if h + 1 < len(table) else []
    if not nxt or nxt[0] or not any(is_text(x) for x in nxt) or any(re.fullmatch(r"[\d.]+", x) for x in nxt):
        return head, [None] * len(head), h + 1
    if orient == "cols":
        if sum(brands.match(x, False) is not None for x in nxt) <= sum(brands.match(x, False) is not None for x in head):
            return head, [None] * len(head), h + 1
        return [x or (head[j] if j < len(head) else "") for j, x in enumerate(nxt)], [None] * len(nxt), h + 2
    subs: list[str | None] = []
    for j, x in enumerate(nxt):
        if j < len(head) and not head[j] and j:
            head[j] = head[j - 1] if SUB_RE.match(x) else x
        elif x and not SUB_RE.match(x) and j < len(head):
            head[j] = x if not head[j] or SUB_RE.match(head[j]) else head[j] if HEADER_RE.match(head[j]) else f"{head[j]} {x}"
        subs.append(x if SUB_RE.match(x) else None)
    return head, subs, h + 2


def collect(tables: list[list[list[str]]], brands: Brands, add: bool | str) -> list[tuple[str, str, str, str | None]]:
    """Flatten tables into (brand key or LIMIT, column/row label, raw value, sub-label e.g. Claim/Result)."""
    cells, prev_labels, prev_keys = [], None, None
    for table in tables:
        found = header_index(table, brands)
        if not found:
            if prev_keys and table and not table[0][0] and len(table) - 1 == len(prev_keys):
                head = table[0]
                cells += [(k, head[j], x, None) for k, row in zip(prev_keys, table[1:]) if k
                          for j, x in enumerate(row) if j and head[j] and x]
            continue
        h, orient, explicit = found
        head, subs, start = headers(table, h, orient, brands)
        body = table[start:]
        if orient == "rows":
            b = next((c for c, x in enumerate(head) if HEADER_RE.match(x)), 0)
            if b + 1 < len(head) and not head[b + 1] and sum(map(is_text, (r[b + 1] for r in body))) > sum(map(is_text, (r[b] for r in body))):
                b += 1
            wrow = next((row for row in body if WEIGHT_RE.search(row[b])), None)
            labels = [f"{x} [score/{wrow[j]}]" if wrow and re.fullmatch(r"[\d.]+", wrow[j]) else x for j, x in enumerate(head)]
            prev_keys = []
            for row in body:
                if LIMIT_RE.match(row[b]):
                    key = LIMIT
                elif SKIP_ROW.match(row[b]) or WEIGHT_RE.search(row[b]) or not any(x for j, x in enumerate(row) if j != b):
                    key = None
                else:
                    key = brands.match(row[b], add)
                prev_keys.append(key)
                if key:
                    cells += [(key, labels[j], x, subs[j]) for j, x in enumerate(row) if j != b and labels[j] and x]
            continue
        prev_keys = None
        known = any(brands.match(x, False) for x in head)
        bcols = {j: LIMIT if LIMIT_RE.match(x) else brands.match(x, add is True and explicit and known)
                 for j, x in enumerate(head) if x and not HEADER_RE.match(x) and not WEIGHT_RE.search(x)}
        bcols = {j: k for j, k in bcols.items() if k}
        if not bcols:
            continue
        first = min(bcols)
        labels = [" ".join(x for j, x in enumerate(row[:first]) if is_text(x) and not WEIGHT_RE.search(head[j])) for row in body]
        weights = [next((x for j, x in enumerate(row[:first]) if WEIGHT_RE.search(head[j])), None) for row in body]
        if not any(labels) and prev_labels and len(prev_labels[0]) == len(body):
            labels, weights = prev_labels
        prev_labels = (labels, weights)
        for label, weight, row in zip(labels, weights, body):
            if not label or SKIP_ROW.match(label):
                continue
            if weight and re.fullmatch(r"[\d.]+", weight):
                label = f"{label} [score/{weight}]"
            cells += [(k, label, row[j], None) for j, k in bcols.items() if j < len(row) and row[j]]
    return cells


def parse(pdf_bytes: bytes) -> dict | None:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        tables = [t for p in pdf.pages for t in page_tables(p)]
    if len(text.strip()) < 200:
        return None
    brands = Brands()
    ranked = [t for t in tables if any(RANK_RE.search(x) for row in t[:2] for x in row)]
    collect(ranked, brands, add="new")
    if len(brands.names) < 3:
        collect(tables, brands, add=True)
        collect(tables, brands, add=True)
    reports: dict[str, dict] = {}
    for key, label, raw, sub in collect(tables, brands, add=False):
        rep = reports.setdefault(key, {"results": {}, "fields": {}})
        low = label.lower()
        score = re.search(r" \[score/([\d.]+)\]$", label)
        if re.search(r"manufactured|marketed|^manufacturer$", low):
            rep["fields"].setdefault("manufacturer", raw.rstrip(" ,."))
            continue
        if re.search(r"total score|overall score|rounded off score", low):
            out_of = re.search(r"out of (\d+)", low)
            rep["fields"].setdefault("grade", raw if "/" in raw else f"{raw}/{out_of.group(1) if out_of else 100}")
            continue
        if not score and not sub and "%" not in raw + label and re.search(
            r"net (weight|wt|quantity|content|volume)|pack size|^weight|^quantity", low
        ):
            qty = raw.split("/")[0] if "mrp" in low else raw
            unit = split_unit(label.split("/")[0])[1]
            rep["fields"].setdefault("net_quantity", f"{qty} {unit}" if unit and number(qty) is not None else qty)
            continue
        if not score and not sub and re.search(r"rank|mrp|price|cost|best before|shelf|type|packag|claim|mark|grade|retail"
                                               r"|variant|declaration|ingredient|comment", low):
            continue
        param, unit = split_unit(label[: score.start()] if score else label)
        if score:
            unit = f"score out of {score.group(1)}"
            param = f"{param} (VOICE score)"
        res = rep["results"].setdefault(norm(param) + norm(unit), {"parameter": param, "group": group_for(param), "unit": unit})
        if sub and re.match(r"claim|declared", sub, re.I):
            res["label_claim"] = value_of(raw)
        elif "value_raw" not in res:
            res.update(value_raw=raw, value=value_of(raw), status=status_for(raw))
    limits = reports.pop(LIMIT, {"results": {}})["results"]
    for rep in reports.values():
        for k, res in rep["results"].items():
            if k in limits and "value_raw" in limits[k]:
                res["limit"] = limits[k]["value"]
    issue = ISSUE_RE.search(text)
    return {
        "issued_on": parse_date(f"{issue.group(1)} {issue.group(2)}") if issue else None,
        "brands": brands.names,
        "reports": {k: {**r, "results": [x for x in r["results"].values() if "value_raw" in x]} for k, r in reports.items()},
    }


def fetch(http: httpx.Client, url: str, state: dict) -> bytes | None:
    """Origin first; consumeraffairs.nic.in now times out, so fall back to Wayback Machine snapshots.

    Recent snapshots of some files redirect to the site's new domain (where they 404), so redirects are
    followed only while they stay on archived consumeraffairs.nic.in URLs.
    """
    targets = [] if state.get("archive") else [url]
    for target in targets + [ARCHIVE.format(ts) + url for ts in SNAPSHOTS]:
        r = None
        try:
            for _ in range(5):
                try:
                    r = request(http, "GET", target, follow_redirects=False)
                    break
                except httpx.HTTPStatusError as e:
                    target = e.response.headers.get("location", "")
                    if not (e.response.is_redirect and target.startswith("https://web.archive.org/")
                            and "consumeraffairs.nic.in" in target):
                        logging.warning("Snapshot redirects off-site: %s", target)
                        break
        except httpx.TransportError:
            logging.exception("Fetch failed for %s", target)
            state["archive"] = True
            continue
        if r is not None and r.content.startswith(b"%PDF") and b"%%EOF" in r.content[-2048:]:
            return r.content
    return None


BRAND_FIXES = {"Haldiram'sTakatak": ("Haldiram's", "Takatak"), "hAFEd": ("HAFED", None), "JeevanAmrit": ("Jeevan Amrit", None)}
PAREN_RE = re.compile(r"^(.+?)\s*\((.+)\)$")


def split_brand(label: str, known: list[str]) -> tuple[str, str | None]:
    """'Britannia Marie Gold' -> ('Britannia', 'Marie Gold') when 'Britannia' is a known brand; the rest is the variant.
    'Horlicks (MaltBased)' -> ('Horlicks', 'Malt Based')."""
    if label in BRAND_FIXES:
        return BRAND_FIXES[label]
    if m := PAREN_RE.match(label):
        return m.group(1).strip(), re.sub(r"([a-z])([A-Z])", r"\1 \2", m.group(2)).strip()
    for b in sorted(known, key=len, reverse=True):
        if norm(label).startswith(norm(b)) and norm(b):
            words = label.split()
            for k in range(1, len(words) + 1):
                if norm(" ".join(words[:k])) == norm(b):
                    return b, " ".join(words[k:]) or None
    return label, None


def main(only: str | None) -> None:
    stats = {"pdfs": 0, "skipped": [], "reports": 0, "results": 0, "merged": 0, "fields": {}}
    state: dict = {}
    with client() as http, connect() as conn:
        publisher = source_id(conn, "Consumer Voice", "website")
        known = [b for (b,) in conn.execute("SELECT DISTINCT brand FROM products")]
        for fname, title, category in PDFS:
            if only and only.lower() not in unquote(fname).lower():
                continue
            url = BASE + fname
            try:
                pdf = fetch(http, url, state)
                data = parse(pdf) if pdf else None
                if not data or not any(r["results"] for r in data["reports"].values()):
                    stats["skipped"].append(unquote(fname))
                    logging.warning("No usable tables in %s", url)
                    continue
                stats["pdfs"] += 1
                for key, rep in data["reports"].items():
                    if not rep["results"]:
                        continue
                    label = display(data["brands"][key])
                    brand, variant = split_brand(label, known)
                    fields = rep["fields"]
                    with conn.transaction():
                        pid = product_id(
                            conn, brand, title, variant, category or category_for(title),
                            manufacturer=fields.get("manufacturer"), net_quantity=fields.get("net_quantity"),
                        )
                        save_report(
                            conn, pid, publisher, f"{url}#{key}", rep["results"], pdf_url=url,
                            issued_on=data["issued_on"], grade=fields.get("grade"),
                        )
                        existed = conn.execute(
                            "SELECT 1 FROM reports WHERE product_id = %s AND publisher_id <> %s LIMIT 1", (pid, publisher)
                        ).fetchone()
                    stats["merged"] += bool(existed)
                    stats["reports"] += 1
                    stats["results"] += len(rep["results"])
                    for f in ("manufacturer", "net_quantity", "grade"):
                        stats["fields"][f] = stats["fields"].get(f, 0) + bool(fields.get(f))
                    logging.info("%s | %s %s: %d results", title, brand, variant or "", len(rep["results"]))
            except Blocked:
                raise
            except Exception:
                logging.exception("Failed on %s", url)
                stats["skipped"].append(unquote(fname))
    logging.info("Consumer Voice done: %s", stats)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    main(sys.argv[1] if len(sys.argv) > 1 else None)
