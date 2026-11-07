"""OpenLabel grade (A–E) for products tested through OpenLabel. Each part follows a published standard.

- honesty (40%): every nutrient on the pack's nutrition table, checked against the official label tolerances in
  backend/standards.py (EU 2012 guidance; FDA 120% for energy; FSSAI -10% for supplements). Within tolerance costs
  nothing; past it costs 10, 18 or 25 points as the difference reaches 1x, 2x or 3x the tolerance (our scale).
- safety (40%): failed contaminant, hygiene and quality results, sorted into three tiers that follow US FDA recall
  classes (21 CFR 7.3(m)), the EU food alert system's serious-risk criteria, EU Reg 2073/2005 (food safety vs
  process hygiene criteria) and the FSS Act 2006's "unsafe" vs "sub-standard":
    critical: pathogens, melamine, non-permitted dyes, banned drugs, or a metal/mycotoxin 5x over its limit.
              Forces the grade to E.
    serious:  a metal, mycotoxin, pesticide, drug or preservative over its limit, faecal/hygiene bacteria, or
              deliberate adulteration. Safety at most 40; the grade can't be better than D.
    minor:    FSSAI quality parameters (moisture, ash, acid value...), total plate count, yeast & mould.
              15 points each (25 if 1.5x out), no cap.
- nutrition (20%): the updated Nutri-Score (2022 solid foods, 2023 drinks), with its general, cheese,
  fats/oils/nuts and drinks algorithms. The fruit/vegetable/legume component counts 0 because we don't have it.
  Supplements, protein powders, infant formula, salt, spices, vinegar and plain tea/coffee aren't scored.

Weights and the letter cut-offs (A >= 85, B >= 70, C >= 55, D >= 40) are OpenLabel's own. A part without data is
left out and the others are re-weighted. The grade is "provisional" while a standard test is still untested.
"""
import re

from backend.annotate import _label_key
from backend.departments import SUPPLEMENTS, canonical, department_of

WEIGHTS = {"honesty": 40, "safety": 40, "nutrition": 20}
LETTERS = [(85, "A"), (70, "B"), (55, "C"), (40, "D")]

# ---- honesty ----

def _honesty_penalty(r: float) -> float:
    return 0 if r <= 1 else 10 if r <= 2 else 18 if r <= 3 else 25


def honesty(findings: list[dict]) -> float | None:
    """Findings carry `tolerance_pct` and `deviation_pct` from annotate.findings (official tolerances)."""
    compared = [f for f in findings if f.get("tolerance_pct") and f.get("deviation_pct") is not None]
    if not compared:
        return None
    penalty = 0.0
    for f in compared:
        if f["kind"] != "bad":
            continue
        r = abs(f["deviation_pct"]) / f["tolerance_pct"]
        penalty += _honesty_penalty(r)
    return max(0.0, 100 - penalty)


# ---- safety ----

def _words(*kw: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(k) for k in kw) + r")(?![a-z0-9])")


CRITICAL = _words(
    "salmonella", "salmonellae", "listeria", "monocytogenes", "o157", "stec", "vtec", "ehec", "shiga", "verotoxigenic",
    "cronobacter", "sakazakii", "botulinum", "vibrio cholerae", "vibrio parahaemolyticus", "shigella", "campylobacter",
    "yersinia", "enterotoxin", "hepatitis a", "norovirus", "melamine", "cyanuric acid", "sudan", "metanil", "rhodamine",
    "auramine", "orange ii", "malachite green", "lead chromate", "para red", "butter yellow", "non-permitted colour",
    "non permitted colour", "non-permitted color", "argemone", "sanguinarine", "chloramphenicol", "nitrofuran",
    "nitrofurans", "dmaa", "dmha", "dmba", "ephedrine", "sibutramine", "anabolic", "steroid", "banned substance",
    "banned stimulant", "potassium bromate", "bromate", "calcium carbide", "formalin", "formaldehyde", "mineral acid",
)
SERIOUS = _words(
    "lead", "pb", "arsenic", "cadmium", "mercury", "methylmercury", "nickel", "tin", "chromium", "antimony",
    "aluminium", "aluminum", "heavy metal", "aflatoxin", "alfatoxin", "ochratoxin", "patulin", "deoxynivalenol",
    "fumonisin", "zearalenone", "ergot", "mycotoxin", "histamine", "pesticide", "insecticide", "fungicide", "herbicide",
    "organophosphate", "organochlorine", "chlorpyrifos", "monocrotophos", "profenofos", "acephate", "carbendazim",
    "imidacloprid", "cypermethrin", "endosulfan", "ddt", "lindane", "glyphosate", "ethylene oxide", "2-chloroethanol",
    "antibiotic", "tetracycline", "oxytetracycline", "enrofloxacin", "ciprofloxacin", "fluoroquinolone", "ampicillin",
    "erythromycin", "sulfonamide", "veterinary drug", "enterobacteriaceae", "coliform", "coliforms", "e. coli",
    "e.coli", "escherichia coli", "faecal", "fecal", "staphylococcus aureus", "s. aureus", "coagulase",
    "bacillus cereus", "b. cereus", "clostridium perfringens", "sulphite reducing", "sulfite reducing", "phosphatase",
    "benzoic", "benzoate", "sorbic", "sorbate", "sulphur dioxide", "sulfur dioxide", "nitrite", "microbiological",
    "foreign fat", "animal fat", "animal body fat", "vegetable fat", "sugar syrup", "c4 sugar", "c4 sugars",
    "amino spiking", "free amino", "non-protein nitrogen", "non protein nitrogen", "urea", "detergent", "starch",
    "neutraliser", "neutralizer", "mineral oil",
)
MINOR = _words(
    "moisture", "water content", "total ash", "ash", "acid insoluble ash", "acid-insoluble ash", "ash insoluble",
    "sulphated ash", "insolubility index", "acid value", "acidity", "free fatty acid", "free fatty acids", "ffa",
    "peroxide", "peroxide value", "anisidine", "totox", "rancidity", "alcoholic acidity", "br reading", "butyro",
    "rm value", "reichert", "polenske", "iodine value", "saponification", "unsaponifiable", "refractive index",
    "baudouin", "bellier", "tss", "brix", "total soluble solids", "fruit content", "total solids", "milk solids",
    "crude fibre", "crude fiber", "volatile oil", "hmf", "hydroxymethylfurfural", "diastase", "total plate count", "tpc",
    "aerobic plate count", "standard plate count", "aerobic colony count", "total viable count", "yeast", "mould",
    "mold", "foreign matter", "extraneous matter", "uric acid",
)
# The nutrition group also holds Consumer Voice's moisture / ash rows; only those count toward safety.
MINOR_IN_NUTRITION = _words("moisture", "ash", "acid insoluble ash", "acid-insoluble ash", "acidity")
HYGIENE_COUNTS = _words("total plate count", "tpc", "aerobic plate count", "standard plate count",
                        "aerobic colony count", "total viable count", "yeast", "mould", "mold")
DECAY = _words("acid value", "peroxide", "peroxide value", "free fatty acid", "free fatty acids")


def safety_tier(result: dict) -> str | None:
    """Which tier a result belongs to, by its parameter name (whole words; critical first), else by group."""
    p = (result.get("parameter") or "").lower()
    group = result.get("group")
    if group == "nutrition":
        return "minor" if MINOR_IN_NUTRITION.search(p) else None
    if CRITICAL.search(p):
        return "critical"
    if SERIOUS.search(p) or group in ("heavy_metal", "toxin", "pesticide", "spiking"):
        return "serious"
    if MINOR.search(p):
        return "minor"
    return None


def _failed(r: dict, tier: str) -> bool:
    if r.get("status") in ("pass", "fail"):
        return r["status"] == "fail"
    # Quality limits can be minimums (fat, protein, TSS), so only contaminant limits are read as maximums.
    return tier != "minor" and r.get("value") is not None and r.get("limit") is not None and r["value"] > r["limit"]


def _ratio(r: dict) -> float | None:
    if r.get("value") is not None and r.get("limit"):
        return r["value"] / r["limit"]
    return None


def safety(results: list[dict]) -> tuple[float | None, str | None, list[dict]]:
    """(score, worst tier failed, failed results with their tier). Score None when nothing safety-related was tested."""
    checked = [(r, t) for r in results if (t := safety_tier(r))]
    if not checked:
        return None, None, []
    flags = []
    for r, tier in checked:
        if not _failed(r, tier):
            continue
        ratio = _ratio(r)
        p = r["parameter"].lower()
        if tier == "serious" and ratio is not None and ratio >= 5 and r.get("group") in ("heavy_metal", "toxin"):
            tier = "critical"  # IARC carcinogens at 5x the limit
        elif tier == "minor" and ratio is not None and ((HYGIENE_COUNTS.search(p) and ratio >= 10) or (DECAY.search(p) and ratio >= 3)):
            tier = "serious"  # gross contamination or decomposition (FSS Act s.3(1)(zz))
        flags.append({"parameter": r["parameter"], "tier": tier, "ratio": round(ratio, 2) if ratio else None})
    tiers = {f["tier"] for f in flags}
    if "critical" in tiers:
        return 0.0, "critical", flags
    score = 100.0
    serious = [f for f in flags if f["tier"] == "serious"]
    if serious:
        score = max(0.0, 40 - 10 * (len(serious) - 1))
    minor_cost = sum(25 if (f["ratio"] or 0) >= 1.5 else 15 for f in flags if f["tier"] == "minor")
    score = min(score, max(50.0, 100 - minor_cost)) if not serious else max(0.0, score - minor_cost)
    worst = "serious" if serious else "minor" if flags else None
    return score, worst, flags


# ---- nutrition (updated Nutri-Score) ----

ENERGY_KJ = [335, 670, 1005, 1340, 1675, 2010, 2345, 2680, 3015, 3350]
SUGARS = [3.4, 6.8, 10, 14, 17, 20, 24, 27, 31, 34, 37, 41, 44, 48, 51]
SAT_FAT = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
SALT = [0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.2, 3.4, 3.6, 3.8, 4.0]
FIBRE = [3.0, 4.1, 5.2, 6.3, 7.4]
PROTEIN = [2.4, 4.8, 7.2, 9.6, 12, 14, 17]
FATS_SAT_ENERGY_KJ = [120, 240, 360, 480, 600, 720, 840, 960, 1080, 1200]
FATS_SAT_RATIO = [10, 16, 22, 28, 34, 40, 46, 52, 58, 64]
DRINK_ENERGY_KJ = [30, 90, 150, 210, 240, 270, 300, 330, 360, 390]
DRINK_SUGARS = [0.5, 2, 3.5, 5, 6, 7, 8, 9, 10, 11]
DRINK_PROTEIN = [1.2, 1.5, 1.8, 2.1, 2.4, 2.7, 3.0]

NUTRI_MODEL = {
    **dict.fromkeys(["milk", "juice", "protein_milkshake", "electrolyte"], "beverages"),
    **dict.fromkeys(["cooking_oil", "ghee", "vanaspati", "butter", "nuts", "peanut_butter"], "fats"),
    **dict.fromkeys(["cheese", "paneer"], "cheese"),
}
NOT_SCORED = {"protein_powder", "mass_gainer", "creatine_supplement", "pre_workout", "infant_formula", "salt",
              "spices", "apple_cider_vinegar", "tea", "coffee_powder"}
# Letter bands from Nutri-Score points, mapped linearly onto OpenLabel's 0–100 letter bands.
BANDS = {
    "general": [(-17, 0, 100, 85, "A"), (1, 2, 84, 70, "B"), (3, 10, 69, 55, "C"), (11, 18, 54, 40, "D"), (19, 40, 39, 0, "E")],
    "fats": [(-17, -6, 100, 85, "A"), (-5, 2, 84, 70, "B"), (3, 10, 69, 55, "C"), (11, 18, 54, 40, "D"), (19, 40, 39, 0, "E")],
    "beverages": [(-18, 2, 84, 70, "B"), (3, 6, 69, 55, "C"), (7, 9, 54, 40, "D"), (10, 30, 39, 0, "E")],
}
SWEETENERS = re.compile(r"sucralose|aspartame|acesulfame|saccharin|steviol|stevia|neotame|advantame|cyclamate|"
                        r"\bins\s*(955|951|950|954|960|961|969|952)\b", re.I)
FRUIT_OILS = re.compile(r"\b(olive|avocado)\b", re.I)  # oils from listed fruits count as fruit/veg (Nutri-Score fats)
RED_MEAT = re.compile(r"\b(mutton|goat|lamb|beef|veal|pork|buffalo|carabeef|venison)\b", re.I)


def _pts(value: float, thresholds: list[float], inclusive: bool = False) -> int:
    return sum((value >= t) if inclusive else (value > t) for t in thresholds)


def nutrition_model(category: str | None) -> str | None:
    c = canonical(category) or ""
    if c in NOT_SCORED or department_of(c) == SUPPLEMENTS[0]:
        return None
    return NUTRI_MODEL.get(c, "general")


def _per_100(results: list[dict], label_nutrition: dict | None) -> dict[str, float]:
    """Lab values where we have them, else the label, per 100 g/ml."""
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
    return vals


def nutri_score(category: str | None, results: list[dict], label_nutrition: dict | None, ingredients: str | None = None,
                name: str = "") -> dict | None:
    """{"points", "letter", "score" (0–100), "model"} or None if the category isn't scored or data is too thin."""
    model = nutrition_model(category)
    if model is None:
        return None
    v = _per_100(results, label_nutrition)
    if sum(k in v for k in ("energy_kcal", "sugars_g", "saturated_fat_g", "sodium_mg")) < 3:
        return None
    kj = v.get("energy_kcal", 0) * 4.184
    sugars, sat, salt = v.get("sugars_g", 0), v.get("saturated_fat_g", 0), v.get("sodium_mg", 0) * 2.5 / 1000
    fibre, protein = v.get("fiber_g", 0), v.get("protein_g", 0)
    text = f"{ingredients or ''} {name}"

    if model == "beverages":
        n = _pts(kj, DRINK_ENERGY_KJ) + _pts(sugars, DRINK_SUGARS) + _pts(sat, SAT_FAT) + _pts(salt, SALT)
        n += 4 if SWEETENERS.search(text) else 0
        points = n - _pts(protein, DRINK_PROTEIN) - _pts(fibre, FIBRE)
        band = "beverages"
    elif model == "fats":
        ratio = 100 * sat / v["fat_g"] if v.get("fat_g") else 0
        n = _pts(sat * 37, FATS_SAT_ENERGY_KJ) + _pts(sugars, SUGARS) + _pts(ratio, FATS_SAT_RATIO, inclusive=True) + _pts(salt, SALT)
        fvl = 5 if canonical(category) == "cooking_oil" and FRUIT_OILS.search(text) else 0
        points = n - _pts(fibre, FIBRE) - fvl - (_pts(protein, PROTEIN) if n < 7 else 0)
        band = "fats"
    else:
        n = _pts(kj, ENERGY_KJ) + _pts(sugars, SUGARS) + _pts(sat, SAT_FAT) + _pts(salt, SALT)
        prot = _pts(protein, PROTEIN)
        if canonical(category) == "meat" and RED_MEAT.search(text):
            prot = min(prot, 2)
        counts_protein = model == "cheese" or n < 11
        points = n - _pts(fibre, FIBRE) - (prot if counts_protein else 0)
        band = "general"

    for lo, hi, s_hi, s_lo, letter in BANDS[band]:
        if points <= hi or (lo, hi) == BANDS[band][-1][:2]:
            p = min(max(points, lo), hi)
            score = s_hi - (p - lo) * (s_hi - s_lo) / (hi - lo) if hi != lo else s_hi
            return {"points": points, "letter": letter, "score": round(score), "model": model}
    return None


# ---- the grade ----

def letter(score: float) -> str:
    return next((l for cut, l in LETTERS if score >= cut), "E")


def openlabel_grade(results: list[dict], label_nutrition: dict | None, findings: list[dict], tests: list[dict],
                    category: str | None = None, ingredients: str | None = None, name: str = "") -> dict | None:
    ns = nutri_score(category, results, label_nutrition, ingredients, name)
    s_score, worst, flags = safety(results)
    parts = {"honesty": honesty(findings), "safety": s_score, "nutrition": ns["score"] if ns else None}
    have = {k: v for k, v in parts.items() if v is not None}
    if not have:
        return None
    score = sum(v * WEIGHTS[k] for k, v in have.items()) / sum(WEIGHTS[k] for k in have)
    grade = letter(score)
    if worst == "critical":
        grade = "E"
    elif worst == "serious" and grade in "ABC":
        grade = "D"
    return {
        "letter": grade,
        "score": round(score),
        "provisional": any(not t.get("tested") for t in tests),
        "safety_failed": worst in ("critical", "serious"),
        "safety_tier": worst,
        "safety_flags": flags,
        "nutri_score": ns["letter"] if ns else None,
        "parts": {k: (round(v) if v is not None else None) for k, v in parts.items()},
    }
