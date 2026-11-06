"""Ingredients, nutrition, barcode and FSSAI licence read from Unbox back-of-pack photos.

The photos are read by Claude Code subagents following READ_RULES; each read is one JSON line,
{"product_id": ..., "read": {...}} matching SCHEMA, saved under scraper/pack_reads/ (git-ignored).
This module checks those reads and fills only empty columns, tagging them 'unbox_pack_photo'.

    python -m scraper.pack_reader check FILE.jsonl            # compare reads with data we already hold
    python -m scraper.pack_reader apply FILE.jsonl [--write]  # dry run unless --write
"""
import json
import logging
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

from psycopg.types.json import Jsonb

from scraper.common import connect
from scraper.unbox_details import plausible

SOURCE = "unbox_pack_photo"

NUTRIENTS = ("energy_kcal", "protein_g", "fat_g", "saturated_fat_g", "sugars_g", "added_sugars_g", "fiber_g", "sodium_mg")
NUM = {"anyOf": [{"type": "number"}, {"type": "null"}]}
STR = {"anyOf": [{"type": "string"}, {"type": "null"}]}
SCHEMA = {
    "type": "object",
    "properties": {
        "ingredients": STR,
        "nutrition_basis": {"type": "string", "enum": ["per_100g", "per_100ml", "per_serving", "none"]},
        "serving_size_g": NUM,
        "nutrition": {
            "type": "object",
            "properties": {k: NUM for k in NUTRIENTS},
            "required": list(NUTRIENTS),
            "additionalProperties": False,
        },
        "barcode": STR,
        "fssai_license": STR,
    },
    "required": ["ingredients", "nutrition_basis", "serving_size_g", "nutrition", "barcode", "fssai_license"],
    "additionalProperties": False,
}

READ_RULES = """You read Indian packaged-food labels from photos. Copy only what is printed in the photos. Never guess or fill anything in from general knowledge: if a field isn't shown or isn't fully legible, return null.

- ingredients: the complete ingredient list exactly as printed (the English text), without the "Ingredients:" heading. Keep percentages and additive codes such as INS 330. Null if the list isn't shown or part of it is unreadable.
- nutrition: values from the per 100 g (or per 100 ml) column, with nutrition_basis set to match. If the table gives only per-serving values, use those, set nutrition_basis to per_serving and give serving_size_g. If there is no nutrition table, set nutrition_basis to none and every nutrient to null.
  energy_kcal in kcal (if only kJ is printed, divide by 4.184). sodium_mg in mg (if only salt is printed, sodium mg = salt g x 400). sugars_g is total sugars. Null for anything not on the table.
- barcode: the digits printed under the barcode, only if all of them are readable.
- fssai_license: the 14-digit FSSAI licence number, only if all digits are readable.

The photos may show several products or languages; use only the label of the named product."""


UPDATE = """
UPDATE products SET
    ingredients_source = CASE WHEN ingredients IS NULL AND %(ingredients)s::text IS NOT NULL THEN %(source)s
                              ELSE ingredients_source END,
    ingredients = coalesce(ingredients, %(ingredients)s),
    label_nutrition_source = CASE WHEN label_nutrition IS NULL AND %(nutrition)s::jsonb IS NOT NULL THEN %(source)s
                                  ELSE label_nutrition_source END,
    label_nutrition = coalesce(label_nutrition, %(nutrition)s),
    barcode = coalesce(barcode, %(barcode)s),
    fssai_license = coalesce(fssai_license, %(fssai)s)
WHERE id = %(id)s
"""



# ---- turning a read into column values ----

def ingredients_of(read: dict) -> str | None:
    text = read.get("ingredients")
    if not text:
        return None
    text = re.sub(r"^\s*ingredients?\s*[:\-]\s*", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    return text if len(text) >= 3 else None


def nutrition_of(read: dict) -> dict:
    """Per-100 g label nutrition, or {} when the read is per serving without a size, too thin, or implausible."""
    basis, values = read.get("nutrition_basis"), read.get("nutrition") or {}
    if basis in ("per_100g", "per_100ml"):
        scale = 1.0
    elif basis == "per_serving" and (read.get("serving_size_g") or 0) > 0:
        scale = 100 / read["serving_size_g"]
    else:
        return {}
    out = {k: round(float(v) * scale, 2) for k, v in values.items() if k in NUTRIENTS and isinstance(v, (int, float)) and v >= 0}
    if len(out) < 3:  # a partial read is more likely a misread than a short table
        return {}
    return out if plausible(out) else {}


def _gs1_ok(digits: str) -> bool:
    body, check = digits[:-1], int(digits[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def barcode_of(read: dict) -> str | None:
    digits = re.sub(r"\D", "", read.get("barcode") or "")
    return digits if len(digits) in (8, 12, 13, 14) and _gs1_ok(digits) else None


def fssai_of(read: dict) -> str | None:
    digits = re.sub(r"\D", "", read.get("fssai_license") or "")
    return digits if len(digits) == 14 else None


# ---- commands ----


def reads(path: str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.5, 0.1 * abs(b))


def check(path: str) -> None:
    """How often the reads agree with ingredients and nutrition we already hold from other sources."""
    conn = connect()
    stats = {"nutrients": 0, "nutrients_ok": 0, "ingredients": 0, "ingredients_ok": 0}
    for item in reads(path):
        row = conn.execute("SELECT brand, name, ingredients, label_nutrition FROM products WHERE id = %s", (item["product_id"],)).fetchone()
        have_ing, have_nut = row[2], row[3] or {}
        got_nut, got_ing = nutrition_of(item["read"]), ingredients_of(item["read"])
        for k, v in got_nut.items():
            if isinstance(have_nut.get(k), (int, float)):
                stats["nutrients"] += 1
                if _close(v, have_nut[k]):
                    stats["nutrients_ok"] += 1
                else:
                    print(f"  {row[0]} {row[1]}: {k} read {v}, have {have_nut[k]}")
        if have_ing and got_ing:
            stats["ingredients"] += 1
            ratio = SequenceMatcher(None, have_ing.lower(), got_ing.lower()).ratio()
            if ratio >= 0.8:
                stats["ingredients_ok"] += 1
            else:
                print(f"  {row[0]} {row[1]}: ingredients differ ({ratio:.2f})\n    have: {have_ing[:120]}\n    read: {got_ing[:120]}")
    print(stats)


def apply(path: str, write: bool) -> None:
    conn = connect()
    stats = {"reads": 0, "ingredients": 0, "nutrition": 0, "barcode": 0, "fssai": 0}
    for item in reads(path):
        read = item["read"]
        values = {"id": item["product_id"], "source": SOURCE, "ingredients": ingredients_of(read),
                  "nutrition": nutrition_of(read) or None, "barcode": barcode_of(read), "fssai": fssai_of(read)}
        stats["reads"] += 1
        for k in ("ingredients", "nutrition", "barcode", "fssai"):
            stats[k] += values[k] is not None
        if write:
            values["nutrition"] = Jsonb(values["nutrition"]) if values["nutrition"] else None
            conn.execute(UPDATE, values)
    print(("wrote" if write else "would fill (where empty)"), stats)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    match args:
        case ["check", path]:
            check(path)
        case ["apply", path]:
            apply(path, "--write" in sys.argv)
        case _:
            print(__doc__)
