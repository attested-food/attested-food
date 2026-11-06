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
