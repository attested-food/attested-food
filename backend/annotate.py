"""Rule-based notes: compare test results with the pack label and mark the ingredient list.

Everything here states numbers only. No judgement sentences are generated.
"""
import re

from backend.category_tests import matches, tests_for
from backend.departments import SUPPLEMENTS, department_of
from backend.standards import label_check


# parameter keywords -> (label_nutrition key, higher_is_worse)
LABEL_KEYS: list[tuple[tuple[str, ...], tuple[str, ...], str, bool]] = [
    # (must contain any, must not contain any, key, higher_is_worse)
    (("added sugar",), (), "added_sugars_g", True),
    (("sugar",), ("added",), "sugars_g", True),
    (("saturated",), ("unsaturated", "poly", "mono"), "saturated_fat_g", True),
    (("total fat", "fat"), ("saturated", "trans", "mufa", "pufa", "poly", "mono"), "fat_g", True),
    (("sodium",), (), "sodium_mg", True),
    (("energy", "calorie"), (), "energy_kcal", True),
    (("protein",), (), "protein_g", False),
    (("fibre", "fiber"), (), "fiber_g", False),
]

MILLET = ("millet", "ragi", "jowar", "bajra", "foxtail", "kodo", "barnyard", "proso", "kangni", "sorghum")
SUGARS = ("sugar", "jaggery", "honey", "glucose", "syrup", "maltodextrin", "dextrose", "fructose", "sucrose", "invert")
SALT = ("salt", "sodium")
FIBRE = ("bran", "fibre", "fiber")
PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def _fmt(x: float) -> str:
    return f"{x:.1f}"


def _pct(x: float) -> str:
    n = int(abs(x) + 0.5)
    return f"{'+' if x >= 0 else '-'}{n}%"


def _unit(unit: str | None) -> str:
    u = (unit or "").split("/")[0].strip()
    return "kcal" if u.lower() == "kcal" else u


def _label_key(parameter: str) -> tuple[str, bool] | None:
    p = parameter.lower()
    for want, avoid, key, worse in LABEL_KEYS:
        if any(w in p for w in want) and not any(a in p for a in avoid):
            return key, worse
    return None


UNCLOSED_PCT_RE = re.compile(r"\(\s*\d+(?:\.\d+)?\s*%\s*$")


def _top_level_commas(text: str) -> list[int]:
    """Indexes of commas outside brackets. A bracket like "(4.5%," that never closes is treated as closed."""
    stack, unmatched = [], set()
    for i, ch in enumerate(text):
        if ch in "([{":
            stack.append(i)
        elif ch in ")]}" and stack:
            stack.pop()
    unmatched = set(stack)  # opening brackets that never close are ignored
    commas, opens = [], []
    for i, ch in enumerate(text):
        if ch in "([{" and i not in unmatched:
            opens.append(i)
        elif ch in ")]}":
            if opens:
                opens.pop()
        elif ch == ",":
            if opens and UNCLOSED_PCT_RE.search(text[opens[-1]:i]):
                opens.pop()
            if not opens:
                commas.append(i)
    return commas


def split_ingredients(text: str) -> list[str]:
    """Split an ingredient list on top-level commas, keeping bracketed sub-lists together."""
    bounds = [-1, *_top_level_commas(text), len(text)]
    return [p for a, b in zip(bounds, bounds[1:]) if (p := text[a + 1:b].strip())]


def _is_score(res: dict) -> bool:
    return "score" in (res.get("unit") or "").lower() or "score" in res["parameter"].lower()


def findings(results: list[dict], label_nutrition: dict | None, category: str | None = None) -> list[dict]:
    label_nutrition = label_nutrition or {}
    supplement = department_of(category) == SUPPLEMENTS[0] if category else False
    out = []
    for res in results:
        value, unit = res.get("value"), _unit(res.get("unit"))
        f = {"parameter": res["parameter"], "kind": "info", "label": None, "tested": value,
             "unit": unit or None, "deviation_pct": None, "text": f"{res.get('value_raw')} {unit}".strip()}
        mapped = _label_key(res["parameter"])
        label = res.get("label_claim")
        if _is_score(res):
            # Rating-style results (e.g. Consumer Voice "VOICE score, out of 7") aren't label claims.
            label = None
            mapped = None
        if label is None and mapped and mapped[0] in label_nutrition:
            label = label_nutrition[mapped[0]]
            if mapped[0].endswith("_mg") and unit.lower() == "g":
                label = label / 1000
        if res.get("status") in ("pass", "fail"):
            f["kind"] = "good" if res["status"] == "pass" else "bad"
        elif value is not None and res.get("limit") is not None:
            f["kind"] = "bad" if value > res["limit"] else "good"
            f["text"] = f"{_fmt(value)} {unit}, limit {res['limit']}".strip()
        if value is not None and label not in (None, 0):
            raw = (value - label) / label * 100
            dev = round(raw, 1)
            f.update(label=label, deviation_pct=dev, text=f"{_fmt(value)} {unit}, {_pct(raw)} vs label")
            key = mapped[0] if mapped else None
            scale = 1000 if key == "sodium_mg" and unit.lower() == "g" else 1  # tolerances are in mg
            check = label_check(key, label * scale, value * scale, supplement=supplement and key is None)
            if check:
                f["tolerance_pct"] = round(check["tolerance"] / abs(label * scale) * 100, 1)
                if f["kind"] == "info":
                    # Off the label only past the official tolerance, and only in the direction that hurts the buyer.
                    if check["r"] > 1:
                        f["kind"] = "bad"
                    elif check["r"] < -1:
                        f["kind"] = "good"
        out.append(f)
    return out


def _has(text: str, words: tuple[str, ...]) -> bool:
    t = text.lower()
    return any(re.search(rf"\b{w}", t) for w in words)


def _millet_share(items: list[str]) -> float | None:
    shares = []
    for item in items:
        t = item.lower()
        m = re.search(r"\bmillets?\b[^%,]*?(\d+(?:\.\d+)?)\s*%", t)
        if m:
            return float(m.group(1))
        for alias in MILLET[1:]:
            m = re.search(rf"\b{alias}\b[^%,]*?(\d+(?:\.\d+)?)\s*%", t)
            if m:
                shares.append(float(m.group(1)))
    return round(sum(shares), 1) if shares else None


def segments(ingredients: str | None, name: str, fnds: list[dict]) -> list[dict]:
    """Ingredient list as segments that join back to the original text, with marks and notes."""
    if not ingredients:
        return []
    by_key = {}
    for f in fnds:
        mapped = _label_key(f["parameter"])
        if mapped:
            by_key.setdefault(mapped[0], f)
    sugar = by_key.get("added_sugars_g") or by_key.get("sugars_g")
    sodium, fibre = by_key.get("sodium_mg"), by_key.get("fiber_g")

    # Cut at top-level commas so separators are kept exactly.
    pieces, start = [], 0
    for i in _top_level_commas(ingredients):
        pieces.append(ingredients[start:i])
        start = i
    pieces.append(ingredients[start:])

    segs: list[dict] = []
    items: list[str] = []
    for chunk in pieces:
        lead = ""
        if chunk.startswith(","):
            m = re.match(r",\s*", chunk)
            lead, chunk = m.group(0), chunk[m.end():]
        trail = chunk[len(chunk.rstrip()):]
        core = chunk.rstrip()
        if lead:
            segs.append({"t": lead, "mark": None, "note": None})
        if core:
            segs.append({"t": core, "mark": None, "note": None})
            items.append(core)
        if trail:
            segs.append({"t": trail, "mark": None, "note": None})

    millet_name = "millet" in name.lower()
    millet_pct = _millet_share(items) if millet_name else None
    sugar_noted = False
    last_millet = None
    for s in segs:
        t = s["t"]
        if not t.strip() or t.lstrip().startswith(","):
            continue
        if millet_name and _has(t, MILLET):
            s["mark"] = "circle" if (millet_pct is None or millet_pct < 50) else "good"
            last_millet = s
        elif _has(t, SUGARS) and len(t) <= 40:
            s["mark"] = "hl"
            if sugar and not sugar_noted and sugar.get("tested") is not None:
                which = "added sugar" if _label_key(sugar["parameter"])[0] == "added_sugars_g" else "sugars"
                note = f"{_fmt(sugar['tested'])} g {which} / 100 g"
                if sugar.get("deviation_pct") is not None:
                    note += f", {_pct(sugar['tested'] / sugar['label'] * 100 - 100)} vs label"
                s["note"] = note
                sugar_noted = True
        elif _has(t, SALT) and len(t) <= 40 and sodium and sodium["kind"] == "bad":
            s["mark"] = "circle"
            s["note"] = f"sodium {sodium['text']}"
        elif _has(t, FIBRE) and len(t) <= 40 and fibre and fibre["kind"] in ("good", "info"):
            s["mark"] = "good"
            s["note"] = f"fibre {fibre['text']}"
    if last_millet is not None and millet_pct is not None:
        last_millet["note"] = f"millets ~{millet_pct:.0f}%"
    return segs


def test_statuses(category: str | None, results: list[dict], fnds: list[dict], tests: list[dict]) -> list[dict]:
    """Each standard test with a status: fail if any matching result is bad, pass if any is good, "measured" when
    the lab gave values but no verdict (e.g. Consumer Voice scores), "untested" when no result covers it.
    `fnds` must line up with `results` (findings(results, ...))."""
    defs = {t["name"]: t for t in tests_for(category)}
    out = []
    for t in tests:
        d = defs.get(t["name"])
        # A nutrient within the official label tolerance is a pass for the label test.
        kinds = [("good" if f["kind"] == "info" and f.get("tolerance_pct") else f["kind"])
                 for r, f in zip(results, fnds) if d and matches(d, r)]
        if not t.get("tested") or not kinds:
            status = "untested"
        elif "bad" in kinds:
            status = "fail"
        elif "good" in kinds:
            status = "pass"
        else:
            status = "measured"
        out.append({**t, "status": status})
    return out


def summarize(product: dict) -> dict:
    results = product.get("results") or []
    fnds = findings(results, product.get("label_nutrition"), product.get("category"))
    tests = product.get("tests") or []
    if tests and "status" not in tests[0]:
        tests = test_statuses(product.get("category"), results, fnds, tests)
    # Counted per standard test, so the numbers add up to the category's test list.
    count = lambda s: sum(t.get("status") == s for t in tests)
    return {
        "segments": segments(product.get("ingredients"), product.get("name") or "", fnds),
        "findings": fnds,
        "counts": {"pass": count("pass"), "fail": count("fail"), "measured": count("measured"), "untested": count("untested")},
    }
