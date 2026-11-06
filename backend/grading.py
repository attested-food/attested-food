"""OpenLabel grade (A–E) for products tested through OpenLabel.

Three parts, each 0–100, blended by weight over the parts we have data for:

- honesty (40%): how close the lab values are to what the pack claims. Every nutrient more than 10% off
  in the direction that's worse for the buyer costs points, more the further off it is.
- safety (40%): contaminant results (heavy metals, toxins, pesticides, microbes, adulterants) against
  their limits. Any failure scores 0 and caps the grade at D.
- nutrition (20%): a Nutri-Score style score from the lab's nutrition values, falling back to the label.

The grade is "provisional" while any of the category's standard tests is still untested.
"""
from backend.annotate import _label_key

WEIGHTS = {"honesty": 40, "safety": 40, "nutrition": 20}
LETTERS = [(85, "A"), (70, "B"), (55, "C"), (40, "D")]
SAFETY_GROUPS = {"heavy_metal", "toxin", "pesticide", "microbiology", "spiking"}
SAFETY_WORDS = ("lead", "arsenic", "cadmium", "mercury", "aflatoxin", "pesticide", "melamine", "salmonella",
                "e. coli", "listeria", "coliform", "yeast", "mould", "mold", "argemone", "mineral oil")


def honesty(findings: list[dict]) -> float | None:
    compared = [f for f in findings if f.get("label") is not None and f.get("deviation_pct") is not None]
    if not compared:
        return None
    penalty = sum(min(1.0, (abs(f["deviation_pct"]) - 10) / 20) for f in compared if f["kind"] == "bad")
    return max(0.0, 100 - 25 * penalty)


def _is_safety(r: dict) -> bool:
    p = r["parameter"].lower()
    return r.get("group") in SAFETY_GROUPS or any(w in p for w in SAFETY_WORDS)


def safety(results: list[dict]) -> tuple[float | None, bool]:
    """(score, failed). None when no contaminant was tested."""
    checks = [r for r in results if _is_safety(r)]
    if not checks:
        return None, False
    failed = any(
        r.get("status") == "fail" or (r.get("value") is not None and r.get("limit") is not None and r["value"] > r["limit"])
        for r in checks
    )
    return (0.0 if failed else 100.0), failed


def _steps(value: float, thresholds: tuple[float, ...]) -> int:
    return sum(value > t for t in thresholds)


def nutrition(results: list[dict], label_nutrition: dict | None) -> float | None:
    """Nutri-Score style points per 100 g, mapped to 0–100 (higher is better)."""
    vals: dict[str, float] = {}
    for r in results:
        mapped = _label_key(r["parameter"])
        if mapped and r.get("value") is not None and mapped[0] not in vals:
            unit = (r.get("unit") or "").split("/")[0].strip().lower()
            v = float(r["value"])
            if mapped[0] == "sodium_mg" and unit == "g":
                v *= 1000
            vals[mapped[0]] = v
    for k, v in (label_nutrition or {}).items():
        if isinstance(v, (int, float)):
            vals.setdefault(k, float(v))
    if "sugars_g" not in vals and "added_sugars_g" in vals:
        vals["sugars_g"] = vals["added_sugars_g"]
    known = [k for k in ("energy_kcal", "sugars_g", "saturated_fat_g", "sodium_mg", "fiber_g", "protein_g") if k in vals]
    if len(known) < 3:
        return None
    neg = (
        min(10, int(vals.get("energy_kcal", 0) * 4.184 // 335))
        + min(10, int(vals.get("sugars_g", 0) // 4.5))
        + min(10, int(vals.get("saturated_fat_g", 0) // 1))
        + min(10, int(vals.get("sodium_mg", 0) // 90))
    )
    fibre = _steps(vals.get("fiber_g", 0), (0.9, 1.9, 2.8, 3.7, 4.7))
    protein = _steps(vals.get("protein_g", 0), (1.6, 3.2, 4.8, 6.4, 8.0))
    score = neg - fibre - (protein if neg < 11 else 0)  # Nutri-Score ignores protein for high-negative foods
    return max(0.0, min(100.0, 100 - (score + 10) * 2.5))


def letter(score: float) -> str:
    return next((l for cut, l in LETTERS if score >= cut), "E")


def openlabel_grade(results: list[dict], label_nutrition: dict | None, findings: list[dict], tests: list[dict]) -> dict | None:
    parts = {"honesty": honesty(findings), "nutrition": nutrition(results, label_nutrition)}
    parts["safety"], safety_failed = safety(results)
    have = {k: v for k, v in parts.items() if v is not None}
    if not have:
        return None
    score = sum(v * WEIGHTS[k] for k, v in have.items()) / sum(WEIGHTS[k] for k in have)
    grade = letter(score)
    if safety_failed and grade in "ABC":
        grade = "D"
    return {
        "letter": grade,
        "score": round(score),
        "provisional": any(not t.get("tested") for t in tests),
        "safety_failed": safety_failed,
        "parts": {k: (round(v) if v is not None else None) for k, v in parts.items()},
    }
