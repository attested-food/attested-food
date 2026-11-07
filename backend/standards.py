"""Official rules the OpenLabel grade is built on. Each block names its source.

Label tolerances: how far a lab value may differ from the pack's nutrition table before it counts as off the
label. From the European Commission's December 2012 "Guidance document for competent authorities for the control
of compliance with EU legislation ... with regard to the setting of tolerances for nutrient values declared on a
label" (Table 1; the bands already include measurement uncertainty). Energy has no EU row, so it uses US FDA
21 CFR 101.9(g)(5): no more than 120% of the label. Only the direction that hurts the buyer counts (FDA 101.9(g)(4)
to (6), EU section 2.3): more energy, fat, saturated fat, sugars or sodium than declared, or less protein or fibre.
Supplements use FSSAI's Nutraceutical Regulations 2016, reg 3(11): no more than 10% below the declared amount.
"""

# nutrient key -> (bands, bad direction). A band is (declared below, absolute tolerance, % tolerance); the first
# band whose limit is above the declared value applies; None means "and above".
TOLERANCES: dict[str, tuple[list[tuple[float | None, float | None, float | None]], str]] = {
    "energy_kcal": ([(None, None, 20)], "over"),
    "protein_g": ([(10, 2, None), (40, None, 20), (None, 8, None)], "under"),
    "fiber_g": ([(10, 2, None), (40, None, 20), (None, 8, None)], "under"),
    "sugars_g": ([(10, 2, None), (40, None, 20), (None, 8, None)], "over"),
    "added_sugars_g": ([(10, 2, None), (40, None, 20), (None, 8, None)], "over"),
    "fat_g": ([(10, 1.5, None), (40, None, 20), (None, 8, None)], "over"),
    "saturated_fat_g": ([(4, 0.8, None), (None, None, 20)], "over"),
    "sodium_mg": ([(500, 150, None), (None, None, 20)], "over"),
}
ENERGY_FLOOR_KCAL = 10  # OpenLabel's own floor so a 2 kcal drink isn't "off" by 1 kcal (not an official rule)
SUPPLEMENT_UNDER_PCT = 10


def tolerance(key: str, declared: float) -> float | None:
    """Allowed difference, in the nutrient's own unit, around a declared value."""
    if key not in TOLERANCES:
        return None
    bands, _ = TOLERANCES[key]
    d = abs(declared)
    for below, absolute, pct in bands:
        if below is None or d < below:
            tol = absolute if absolute is not None else d * pct / 100
            return max(tol, ENERGY_FLOOR_KCAL) if key == "energy_kcal" else tol
    return None


def label_check(key: str | None, declared: float, tested: float, supplement: bool = False) -> dict | None:
    """How a lab value compares with the label: ratio r of the harmful difference to the tolerance.

    r <= 0: same or better than the label; 0 < r <= 1: within the official tolerance; r > 1: off the label.
    Returns None when there is no rule for this nutrient.
    """
    if key in TOLERANCES and not supplement:
        tol = tolerance(key, declared)
        direction = TOLERANCES[key][1]
    elif supplement or key is None:
        # Active ingredients and vitamins in supplements: no more than 10% under the label (FSSAI Nutra reg 3(11)).
        tol, direction = abs(declared) * SUPPLEMENT_UNDER_PCT / 100, "under"
    else:
        return None
    if not tol:
        return None
    harm = tested - declared if direction == "over" else declared - tested
    return {"tolerance": tol, "direction": direction, "r": harm / tol}
