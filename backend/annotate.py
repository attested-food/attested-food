"""Rule-based notes: compare test results with the pack label and mark the ingredient list.

Everything here states numbers only. No judgement sentences are generated.
"""
import re

THRESHOLD = 10.0  # % difference from the label before a value counts as off its label

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


def split_ingredients(text: str) -> list[str]:
    """Split an ingredient list on top-level commas, keeping bracketed sub-lists together."""
    items, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            items.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        items.append(cur.strip())
    return [i for i in items if i]


def findings(results: list[dict], label_nutrition: dict | None) -> list[dict]:
    label_nutrition = label_nutrition or {}
    out = []
    for res in results:
        value, unit = res.get("value"), _unit(res.get("unit"))
        f = {"parameter": res["parameter"], "kind": "info", "label": None, "tested": value,
             "unit": unit or None, "deviation_pct": None, "text": f"{res.get('value_raw')} {unit}".strip()}
        mapped = _label_key(res["parameter"])
        label = res.get("label_claim")
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
            if f["kind"] == "info" and abs(dev) > THRESHOLD:
                worse = mapped[1] if mapped else True
                f["kind"] = "bad" if (dev > 0) == worse else "good"
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

    # Walk the text so separators are kept exactly.
    pieces, depth, start = [], 0, 0
    for i, ch in enumerate(ingredients):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            pieces.append(ingredients[start:i])
            start = i
            pieces.append(None)  # marker for separator start
    pieces.append(ingredients[start:])

    segs: list[dict] = []
    items: list[str] = []
    for chunk in pieces:
        if chunk is None:
            continue
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
        elif _has(t, SALT) and sodium and sodium["kind"] == "bad":
            s["mark"] = "circle"
            s["note"] = f"sodium {sodium['text']}"
        elif _has(t, FIBRE) and fibre and fibre["kind"] in ("good", "info"):
            s["mark"] = "good"
            s["note"] = f"fibre {fibre['text']}"
    if last_millet is not None and millet_pct is not None:
        last_millet["note"] = f"millets ~{millet_pct:.0f}%"
    return segs


def summarize(product: dict) -> dict:
    fnds = findings(product.get("results") or [], product.get("label_nutrition"))
    tests = product.get("tests") or []
    return {
        "segments": segments(product.get("ingredients"), product.get("name") or "", fnds),
        "findings": fnds,
        "counts": {"pass": sum(f["kind"] == "good" for f in fnds),
                   "fail": sum(f["kind"] == "bad" for f in fnds),
                   "untested": sum(not t.get("tested") for t in tests)},
    }
