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


def test_unbox_claims_nutrition():
    from scraper.unbox_details import claims_nutrition
    n = claims_nutrition("Wheat flour | Claims per 100g: 7.9g Protein, 79.5g Carbs, 10.6g Fat, 21.2g Sugar, 5.1g Saturated Fat, 5.2g PUFA+MUFA, 0g Trans Fat, 316mg Sodium.")
    assert n == {"protein_g": 7.9, "fat_g": 10.6, "sugars_g": 21.2, "saturated_fat_g": 5.1, "sodium_mg": 316}


def test_unbox_claims_skip_per_serving_and_nonsense():
    from scraper.unbox_details import claims_nutrition
    assert claims_nutrition("Fish oil | Claims per capsule: 300mg EPA, 1g Fat") == {}
    assert claims_nutrition("Whey | Claims: 24g Protein per scoop (30g)") == {}
    assert claims_nutrition("Bar | Claims per 100g: 120g Protein") == {}
    assert claims_nutrition(None) == {}
    assert claims_nutrition("Honey | Claims: 80g Sugar, 0g Fat")["sugars_g"] == 80


def test_pick_ignores_variant_words_and_brand_typos():
    from scraper.off_details import pick
    hits = [{"code": "0793591862460", "brands": "Byond Snack", "product_name": "Kerala Banana Chips", "countries_tags": ["en:india"]}]
    assert pick(hits, "Beyond Snack", "Banana Chips", "Kerala Style Salted")["code"] == "0793591862460"
    marie = [{"code": "8901063162648", "brands": "Britannia", "product_name": "Marie Gold", "countries_tags": ["en:india"]}]
    assert pick(marie, "Britannia", "Marie Gold", "Marie Biscuits")["code"] == "8901063162648"
    assert pick(marie, "Parle", "Marie Gold", None) is None


# ---- pack photo reader ----
from scraper.pack_reader import barcode_of, fssai_of, ingredients_of, nutrition_of

NUT = {"energy_kcal": 480, "protein_g": 7, "fat_g": 22, "saturated_fat_g": 10, "sugars_g": 30,
       "added_sugars_g": None, "fiber_g": None, "sodium_mg": 250}


def test_pack_nutrition_per_100g():
    assert nutrition_of({"nutrition_basis": "per_100g", "nutrition": NUT}) == {
        "energy_kcal": 480, "protein_g": 7, "fat_g": 22, "saturated_fat_g": 10, "sugars_g": 30, "sodium_mg": 250}


def test_pack_nutrition_per_serving_is_scaled():
    out = nutrition_of({"nutrition_basis": "per_serving", "serving_size_g": 25, "nutrition": NUT})
    assert out == {}  # scales to 1920 kcal per 100 g: implausible, rejected
    half = {k: (v / 4 if v else v) for k, v in NUT.items()}
    assert nutrition_of({"nutrition_basis": "per_serving", "serving_size_g": 25, "nutrition": half})["energy_kcal"] == 480


def test_pack_nutrition_rejects_unusable_reads():
    assert nutrition_of({"nutrition_basis": "per_serving", "serving_size_g": None, "nutrition": NUT}) == {}
    assert nutrition_of({"nutrition_basis": "none", "nutrition": NUT}) == {}
    assert nutrition_of({"nutrition_basis": "per_100g", "nutrition": {**dict.fromkeys(NUT), "protein_g": 5}}) == {}
    assert nutrition_of({"nutrition_basis": "per_100g", "nutrition": {**NUT, "saturated_fat_g": 40}}) == {}


def test_pack_ingredients_cleaned():
    assert ingredients_of({"ingredients": "Ingredients: Wheat flour (60%),  sugar, INS 503(ii)."}) == "Wheat flour (60%), sugar, INS 503(ii)"
    assert ingredients_of({"ingredients": None}) is None
    assert ingredients_of({"ingredients": " - "}) is None


def test_pack_barcode_needs_valid_check_digit():
    assert barcode_of({"barcode": "8 901058 000290"}) == "8901058000290"  # real EAN-13
    assert barcode_of({"barcode": "8901058000291"}) is None
    assert barcode_of({"barcode": "1234"}) is None


def test_pack_fssai_is_14_digits():
    assert fssai_of({"fssai_license": "Lic. No. 10012022000123"}) == "10012022000123"
    assert fssai_of({"fssai_license": "1001202200012"}) is None

