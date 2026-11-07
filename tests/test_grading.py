import pytest

from backend.annotate import findings
from backend.grading import honesty, letter, nutri_score, openlabel_grade, safety, safety_tier
from backend.standards import label_check, tolerance
from tests.test_annotate import KELLOGGS_LABEL, KELLOGGS_RESULTS, r


# ---- label tolerances (EU 2012 guidance, FDA for energy, FSSAI Nutra for supplements) ----

@pytest.mark.parametrize(("key", "declared", "tol"), [
    ("protein_g", 7.8, 2),        # below 10 g: ±2 g
    ("protein_g", 25, 5),         # 10–40 g: ±20%
    ("protein_g", 70, 8),         # above 40 g: ±8 g
    ("fat_g", 5, 1.5),
    ("saturated_fat_g", 2, 0.8),  # below 4 g: ±0.8 g
    ("sodium_mg", 236, 150),      # below 500 mg: ±150 mg
    ("sodium_mg", 800, 160),      # then ±20%
    ("energy_kcal", 375, 75),     # FDA: 120% of label
    ("energy_kcal", 5, 10),       # our 10 kcal floor
])
def test_tolerance_bands(key, declared, tol):
    assert tolerance(key, declared) == pytest.approx(tol)


def test_only_the_harmful_direction_counts():
    assert label_check("sodium_mg", 236, 500)["r"] > 1      # much more sodium: off
    assert label_check("sodium_mg", 236, 50)["r"] < 0       # less sodium: fine
    assert label_check("protein_g", 25, 18)["r"] > 1        # 28% less protein: off
    assert label_check(None, 100, 88, supplement=True)["r"] > 1   # supplement 12% under: off (FSSAI -10%)
    assert label_check(None, 100, 95, supplement=True)["r"] <= 1


def test_kelloggs_is_within_tolerance():
    # Sodium is 20% over the label, but 47 mg is inside the EU ±150 mg band for amounts under 500 mg.
    fnds = findings(KELLOGGS_RESULTS, KELLOGGS_LABEL, "breakfast_cereal")
    assert all(f["kind"] != "bad" for f in fnds)
    g = openlabel_grade(KELLOGGS_RESULTS, KELLOGGS_LABEL, fnds, [{"name": "Nutrition vs label claims", "tested": True}],
                        "breakfast_cereal")
    assert g["parts"] == {"honesty": 100, "safety": None, "nutrition": 59} and g["nutri_score"] == "C"


def test_honesty_steps():
    off = lambda dev, tol: {"kind": "bad", "deviation_pct": dev, "tolerance_pct": tol}
    assert honesty([off(30, 20)]) == 90    # 1.5x the tolerance
    assert honesty([off(50, 20)]) == 82    # 2.5x
    assert honesty([off(90, 20)]) == 75    # 4.5x
    assert honesty([{"kind": "info", "deviation_pct": 5, "tolerance_pct": 20}]) == 100
    assert honesty([]) is None


# ---- safety tiers ----

@pytest.mark.parametrize(("result", "tier"), [
    ({"parameter": "Salmonella spp.", "group": "other"}, "critical"),
    ({"parameter": "Melamine", "group": "spiking"}, "critical"),
    ({"parameter": "Sudan I", "group": "other"}, "critical"),
    ({"parameter": "Lead (Pb)", "group": "heavy_metal"}, "serious"),
    ({"parameter": "Enterobacteriaceae", "group": "other"}, "serious"),
    ({"parameter": "Total Plate Count", "group": "other"}, "minor"),
    ({"parameter": "Acid value", "group": "other"}, "minor"),
    ({"parameter": "Moisture", "group": "nutrition"}, "minor"),
    ({"parameter": "Protein", "group": "nutrition"}, None),
    ({"parameter": "Misleading claims", "group": "other"}, None),   # "lead" only as a whole word
    ({"parameter": "Urease activity", "group": "other"}, None),     # not "urea"
])
def test_safety_tiers(result, tier):
    assert safety_tier(result) == tier


def test_critical_forces_e():
    res = [{"parameter": "Salmonella", "group": "other", "status": "fail"}] + KELLOGGS_RESULTS
    g = openlabel_grade(res, KELLOGGS_LABEL, [], [], "breakfast_cereal")
    assert g["letter"] == "E" and g["safety_tier"] == "critical"


def test_serious_caps_at_d_and_escalates_at_5x():
    over = [r("Lead", 0.9, "mg/kg", group="heavy_metal", limit=0.3)]
    assert safety(over)[:2] == (40.0, "serious")
    g = openlabel_grade(over + KELLOGGS_RESULTS, KELLOGGS_LABEL, [], [], "breakfast_cereal")
    assert g["letter"] in "DE" and g["safety_failed"]
    assert safety([r("Lead", 1.6, "mg/kg", group="heavy_metal", limit=0.3)])[1] == "critical"


def test_minor_costs_points_without_cap():
    assert safety([{"parameter": "Yeast and mould", "group": "other", "status": "fail"}])[:2] == (85.0, "minor")
    assert safety([r("Aflatoxin B1", None, "ppb", group="toxin", status="pass", value_raw="ND")])[:2] == (100.0, None)
    assert safety(KELLOGGS_RESULTS)[0] is None


# ---- nutrition (updated Nutri-Score) ----

def test_nutri_score_models():
    oil = {"energy_kcal": 900, "fat_g": 100, "saturated_fat_g": 15, "sodium_mg": 0, "sugars_g": 0}
    assert nutri_score("cooking_oil", [], oil, "Extra virgin olive oil")["letter"] == "B"
    assert nutri_score("cooking_oil", [], {**oil, "saturated_fat_g": 10}, "Refined sunflower oil")["letter"] == "C"
    biscuit = {"energy_kcal": 530, "saturated_fat_g": 10, "sodium_mg": 400, "sugars_g": 35, "protein_g": 6, "fiber_g": 2}
    assert nutri_score("biscuits", [], biscuit)["letter"] == "E"
    milk = {"energy_kcal": 62, "saturated_fat_g": 2.1, "sodium_mg": 40, "sugars_g": 4.7, "protein_g": 3}
    assert nutri_score("milk", [], milk)["model"] == "beverages"
    assert nutri_score("milk", [], milk, "Toned milk, sucralose")["points"] == nutri_score("milk", [], milk)["points"] + 4


def test_not_scored_and_thin_data():
    assert nutri_score("protein_powder", [], {"energy_kcal": 400, "saturated_fat_g": 1, "sodium_mg": 100, "sugars_g": 3}) is None
    assert nutri_score("multivitamin", [], {"energy_kcal": 4, "saturated_fat_g": 0, "sodium_mg": 0, "sugars_g": 0}) is None
    assert nutri_score("biscuits", [], {"protein_g": 6}) is None


def test_score_matches_letter_band():
    # 0–100 always agrees with the Nutri-Score letter.
    for sugars in (0, 10, 25, 45):
        ns = nutri_score("biscuits", [], {"energy_kcal": 450, "saturated_fat_g": 3, "sodium_mg": 300, "sugars_g": sugars})
        assert letter(ns["score"]) == ns["letter"]


def test_provisional_until_standard_tests_done():
    g = openlabel_grade(KELLOGGS_RESULTS, KELLOGGS_LABEL, [], [{"name": "Aflatoxins", "tested": False}], "breakfast_cereal")
    assert g["provisional"]


def test_no_data_no_grade():
    assert openlabel_grade([], None, [], []) is None


def test_letters():
    assert [letter(s) for s in (90, 75, 60, 45, 10)] == ["A", "B", "C", "D", "E"]
