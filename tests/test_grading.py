from backend.annotate import findings
from backend.grading import honesty, letter, nutrition, openlabel_grade, safety
from tests.test_annotate import KELLOGGS_LABEL, KELLOGGS_RESULTS, r


def test_kelloggs_grade():
    fnds = findings(KELLOGGS_RESULTS, KELLOGGS_LABEL)
    g = openlabel_grade(KELLOGGS_RESULTS, KELLOGGS_LABEL, fnds, [{"name": "Nutrition vs label claims", "tested": True}])
    assert g["parts"]["safety"] is None  # cereal's standard tests don't include contaminants
    assert g["parts"]["honesty"] == 88  # sodium +20% vs label
    assert g["letter"] == "B" and not g["provisional"] and not g["safety_failed"]


def test_honesty_scales_with_how_far_off():
    assert honesty([{"label": 10, "deviation_pct": 5, "kind": "info"}]) == 100
    assert honesty([{"label": 10, "deviation_pct": 20, "kind": "bad"}]) == 87.5
    assert honesty([{"label": 10, "deviation_pct": 60, "kind": "bad"}]) == 75
    assert honesty([{"label": 10, "deviation_pct": -40, "kind": "good"}]) == 100
    assert honesty([]) is None


def test_safety_fail_caps_grade_at_d():
    res = [r("Lead", 0.9, "mg/kg", group="heavy_metal", limit=0.3)] + KELLOGGS_RESULTS
    assert safety(res) == (0.0, True)
    g = openlabel_grade(res, KELLOGGS_LABEL, [], [])
    assert g["safety_failed"] and g["letter"] in "DE"


def test_safety_pass_and_untested():
    assert safety([r("Aflatoxin B1", None, "ppb", group="toxin", status="pass", value_raw="ND")]) == (100.0, False)
    assert safety(KELLOGGS_RESULTS) == (None, False)


def test_nutrition_needs_three_values():
    assert nutrition([r("Protein", 20)], None) is None
    good = nutrition([], {"energy_kcal": 120, "sugars_g": 1, "saturated_fat_g": 0.2, "sodium_mg": 20, "fiber_g": 6, "protein_g": 9})
    bad = nutrition([], {"energy_kcal": 520, "sugars_g": 50, "saturated_fat_g": 15, "sodium_mg": 900})
    assert good > 90 and bad < 20


def test_provisional_until_standard_tests_done():
    g = openlabel_grade(KELLOGGS_RESULTS, KELLOGGS_LABEL, [], [{"name": "Aflatoxins", "tested": False}])
    assert g["provisional"]


def test_no_data_no_grade():
    assert openlabel_grade([], None, [], []) is None


def test_letters():
    assert [letter(s) for s in (90, 75, 60, 45, 10)] == ["A", "B", "C", "D", "E"]
