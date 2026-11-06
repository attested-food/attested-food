from datetime import date

import pytest

from scraper.common import parse_date, strip_brand
from scraper.trustified import brand_for, parse_value, status_for
from scraper.unbox import category, claim_key


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("5 Jan 2026", date(2026, 1, 5)),
        ("20.05.2026", date(2026, 5, 20)),
        ("Jul 31, 2026", date(2026, 7, 31)),
        ("APR-26", date(2026, 4, 1)),
        ("10/2025", date(2025, 10, 1)),
        ("01/Jul/2025", date(2025, 7, 1)),
        ("OCT25", date(2025, 10, 1)),
        ("26 September 2025", date(2025, 9, 26)),
        ("Best before 18 months", None),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize(
    ("brand", "name", "expected"),
    [
        ("MuscleBlaze", "Muscleblaze Biozyme Whey", "Biozyme Whey"),
        ("Beast Life", "BeastLife Pro Whey", "Pro Whey"),
        ("Amul", "Amul", "Amul"),
    ],
)
def test_strip_brand(brand, name, expected):
    assert strip_brand(brand, name) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("No Amino Spiking Found", "pass"),
        ("This product is spiked with Glutamic Acid and Glycine", "fail"),
        ("In tests, Pesticides are either not detected or found below limit of detection (LOQ)", "pass"),
        ("A total of 34 pesticide residues were detected, out of which 20 exceeded the permissible safety limits.", "fail"),
    ],
)
def test_status_for(text, expected):
    assert status_for(text) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("<0.5 μg/kg", ("<0.5", "μg/kg")), ("Not Detected", ("Not Detected", None)), ("BLQ", ("BLQ", None))],
)
def test_parse_value(raw, expected):
    assert parse_value(raw) == expected


@pytest.mark.parametrize(
    ("heading", "expected"),
    [("Muscleblaze Iso Zero", "MuscleBlaze"), ("Kelloggs", "Kellogg's"), ("Tata 1MG Calcium", "Tata 1mg"), ("Unknown Co", "Unknown Co")],
)
def test_brand_for(heading, expected):
    assert brand_for(heading) == expected


@pytest.mark.parametrize(
    ("a", "b"), [("Total Protein", "Protein"), ("Vit-D", "Vitamin D"), ("PUFA+MUFA", "MUFA+PUFA")]
)
def test_claim_key(a, b):
    assert claim_key(a) == claim_key(b)


@pytest.mark.parametrize(
    ("names", "expected"),
    [(["Protein Powders"], "protein_powder"), (["The Great Indian Product Hunt - Most Voted Products", "Peanut Butters"], "peanut_butter"), (["Cookies & Biscuits"], "biscuits")],
)
def test_category(names, expected):
    assert category(names) == expected


def test_off_nutrition_maps_and_converts():
    from scraper.off_details import off_nutrition

    got = off_nutrition({
        "energy-kcal_100g": 375, "proteins_100g": 7.8, "sugars_100g": 20.8, "added-sugars_100g": 13.7,
        "fiber_100g": 7, "sodium_100g": 0.236, "fat_100g": "n/a", "unrelated_100g": 5,
    })
    assert got == {"energy_kcal": 375, "protein_g": 7.8, "sugars_g": 20.8, "added_sugars_g": 13.7,
                   "fiber_g": 7, "sodium_mg": 236}


def test_off_nutrition_drops_implausible():
    from scraper.off_details import off_nutrition

    assert off_nutrition({"energy-kcal_100g": 955, "sugars_100g": 21.8, "added-sugars_100g": 32}) == {}


def test_pick_needs_most_name_words():
    from scraper.off_details import pick

    hits = [
        {"code": "1", "brands": "Kellogg's", "product_name": "Kellogg's crunchy muesli", "countries_tags": ["en:india"]},
        {"code": "2", "brands": "Kellogg's", "product_name": "Choco Millet Muesli", "countries_tags": ["en:india"]},
    ]
    assert pick(hits, "Kellogg's", "Millet Muesli", "Choco")["code"] == "2"
    assert pick(hits[:1], "Kellogg's", "Millet Muesli", "Choco") is None


def test_pick_skips_products_not_sold_in_india():
    from scraper.off_details import pick
    hits = [{"code": "4001234", "brands": "Double Diamond", "product_name": "Black Tea", "countries_tags": ["en:germany"]}]
    assert pick(hits, "Double Diamond", "Black Tea", None) is None
    hits[0]["code"] = "8901234567890"
    assert pick(hits, "Double Diamond", "Black Tea", None) is hits[0]


def test_clean_ingredients_drops_allergen_markers():
    from scraper.off_details import clean_ingredients
    assert clean_ingredients("_WHEAT_ GLUTEN,  _OATS_") == "WHEAT GLUTEN, OATS"
    assert clean_ingredients("  ") is None
