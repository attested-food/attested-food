from backend.annotate import findings, segments, split_ingredients, summarize

KELLOGGS_INGREDIENTS = (
    "MULTIGRAIN MIX (69.1%) WHEAT (20.3%), RICE (18.6%), CORN GRITS & CORN MEAL (9.6%), RAGI FLOUR (6.7%), "
    "ROLLED BARLEY (5%), ROLLED OATS (5%), JOWAR FLOUR (4.5%), SUGAR, CANDIED & DRY FRUITS & SEEDS (9%), "
    "WHEAT BRAN, COCOA SOLIDS, IODIZED SALT"
)
KELLOGGS_LABEL = {"energy_kcal": 375, "protein_g": 7.8, "sugars_g": 20.8, "added_sugars_g": 13.7,
                  "fiber_g": 7.0, "saturated_fat_g": 0.8, "sodium_mg": 236}


def r(parameter, value, unit="g/100g", **kw):
    return {"parameter": parameter, "group": "nutrition", "unit": unit, "value": value,
            "value_raw": str(value), "label_claim": None, "limit": None, "detection_limit": None,
            "method": None, "status": None, **kw}


KELLOGGS_RESULTS = [
    r("Sodium", 282.83, "mg/100g"),
    r("Added Sugars", 14.87),
    r("Dietary Fibre", 8.01),
    r("Protein", 8.31),
    r("Cholesterol", None, "mg/100g", value_raw="<1.0"),
]


def by_param(fnds, name):
    return next(f for f in fnds if f["parameter"] == name)


def test_split_respects_brackets():
    assert split_ingredients("Malt (66.7%) [Barley (32%), Wheat], sugar") == ["Malt (66.7%) [Barley (32%), Wheat]", "sugar"]


def test_findings_sodium_over_label():
    s = by_param(findings(KELLOGGS_RESULTS, KELLOGGS_LABEL), "Sodium")
    assert s["kind"] == "bad"
    assert s["deviation_pct"] == 19.8
    assert s["text"] == "282.8 mg, +20% vs label"


def test_findings_fibre_good():
    assert by_param(findings(KELLOGGS_RESULTS, KELLOGGS_LABEL), "Dietary Fibre")["kind"] == "good"


def test_findings_within_ten_percent_is_info():
    assert by_param(findings(KELLOGGS_RESULTS, KELLOGGS_LABEL), "Protein")["kind"] == "info"


def test_findings_raw_value_no_crash():
    c = by_param(findings(KELLOGGS_RESULTS, KELLOGGS_LABEL), "Cholesterol")
    assert c["kind"] == "info" and c["deviation_pct"] is None


def test_findings_label_claim_wins_over_label_nutrition():
    f = findings([r("Protein", 15.6, label_claim=25)], {"protein_g": 15})[0]
    assert f["kind"] == "bad" and f["label"] == 25


def test_findings_status_and_limit():
    fnds = findings([r("Lead", 0.4, "mg/kg", group="heavy_metal", limit=0.3),
                     r("Aflatoxin", None, "ppb", group="toxin", status="pass", value_raw="Not detected")], None)
    assert [f["kind"] for f in fnds] == ["bad", "good"]


def test_segments_millet_share():
    segs = segments(KELLOGGS_INGREDIENTS, "Millet Muesli", findings(KELLOGGS_RESULTS, KELLOGGS_LABEL))
    millet = [s for s in segs if s["mark"] == "circle" and ("RAGI" in s["t"] or "JOWAR" in s["t"])]
    assert len(millet) == 2
    assert [s["note"] for s in segs if s["note"] and "millet" in s["note"]] == ["millets ~11%"]


def test_segments_sugar_highlight_and_salt():
    segs = segments(KELLOGGS_INGREDIENTS, "Millet Muesli", findings(KELLOGGS_RESULTS, KELLOGGS_LABEL))
    sugar = next(s for s in segs if s["t"] == "SUGAR")
    salt = next(s for s in segs if s["t"] == "IODIZED SALT")
    assert sugar["mark"] == "hl" and sugar["note"] == "14.9 g added sugar / 100 g, +9% vs label"
    assert salt["mark"] == "circle" and salt["note"] == "sodium 282.8 mg, +20% vs label"


def test_segments_rejoin_to_original_text():
    segs = segments(KELLOGGS_INGREDIENTS, "Millet Muesli", [])
    assert "".join(s["t"] for s in segs) == KELLOGGS_INGREDIENTS


def test_no_ingredients():
    assert segments(None, "x", []) == []


def test_summary_counts():
    product = {"name": "Millet Muesli", "ingredients": KELLOGGS_INGREDIENTS, "label_nutrition": KELLOGGS_LABEL,
               "results": KELLOGGS_RESULTS, "tests": [{"name": "Nutrition vs label claims", "tested": True},
                                                       {"name": "Aflatoxins", "tested": False}]}
    s = summarize(product)
    assert s["counts"] == {"pass": 1, "fail": 1, "untested": 1}
    assert set(s) == {"segments", "findings", "counts"}


def test_split_tolerates_unclosed_percent_bracket():
    text = "RAGI FLOUR (6.7%), JOWAR FLOUR (4.5%, SUGAR, IODIZED SALT"
    assert split_ingredients(text) == ["RAGI FLOUR (6.7%)", "JOWAR FLOUR (4.5%", "SUGAR", "IODIZED SALT"]
    segs = segments(text, "Millet Muesli", [])
    assert "".join(s["t"] for s in segs) == text
    assert next(s for s in segs if s["t"] == "SUGAR")["mark"] == "hl"


def test_split_ignores_bracket_that_never_closes():
    text = "SEEDS (9%) (CRANBERRIES (3%), WHEAT BRAN, IODIZED SALT"
    assert split_ingredients(text) == ["SEEDS (9%) (CRANBERRIES (3%)", "WHEAT BRAN", "IODIZED SALT"]
