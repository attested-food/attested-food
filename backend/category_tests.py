"""Standard tests for each product category, and which of them a product's reports already cover.

The sets live in category_tests.json. They were researched from FSSAI's regulations (product standards,
contaminant limits, microbiology criteria, the DART adulteration book, the 2022 Nutra regulations) and from
what Trustified, Unbox Health and Consumer Voice actually test for each category.

Each test has a name, a one-line `why` for shoppers, a `group` (the result group it lands in, or null for any
group), `keywords` (lowercase substrings of a result's parameter; empty means any result in the group counts)
and a `source`. A test counts as done when some result matches its group and one of its keywords.
"""
import json
from pathlib import Path

from backend.departments import SUPPLEMENTS, canonical, department_of

DATA: dict = json.loads(Path(__file__).with_name("category_tests.json").read_text())
TESTS: dict[str, list[dict]] = {k: v for k, v in DATA.items() if not k.startswith("_")}
FALLBACK = "packaged_food"  # any category we haven't researched yet


def tests_for(category: str | None) -> list[dict]:
    c = canonical(category) or ""
    if c in TESTS:
        return TESTS[c]
    return TESTS["supplement" if department_of(c) == SUPPLEMENTS[0] else FALLBACK]


def names_for(category: str | None) -> list[str]:
    return [t["name"] for t in tests_for(category)]


def _matches(test: dict, result: dict) -> bool:
    if test["group"] is not None and result.get("group") != test["group"]:
        return False
    parameter = (result.get("parameter") or "").lower()
    return not test["keywords"] or any(k in parameter for k in test["keywords"])


def coverage(category: str | None, results: list[dict]) -> list[dict]:
    return [
        {"name": t["name"], "why": t["why"], "tested": any(_matches(t, r) for r in results)}
        for t in tests_for(category)
    ]
