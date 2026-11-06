"""Merge per-department research JSON (name, why, group, keywords, source per test) into backend/category_tests.json.

    python scraper/merge_category_tests.py RESEARCH_DIR backend/category_tests.json
"""
import json, sys
from pathlib import Path
R = Path(sys.argv[1]); OUT = Path(sys.argv[2])
GROUPS = {"nutrition", "heavy_metal", "toxin", "pesticide", "spiking", "other", None}
merged, notes = {}, {}
for f in ["dairy_fats", "staples_snacks", "spreads_drinks", "protein_supplements"]:
    p = R / f"{f}.json"
    if not p.exists():
        print("missing", f); continue
    d = json.loads(p.read_text())
    notes[f] = d.pop("_notes", "")
    for cat, tests in d.items():
        assert cat not in merged, f"duplicate {cat}"
        clean = []
        for t in tests:
            assert set(t) >= {"name", "why", "group", "keywords", "source"}, (cat, t)
            assert t["group"] in GROUPS, (cat, t["name"], t["group"])
            kws = [k.lower().strip() for k in t["keywords"] if k.strip()]
            if t["name"] == "Nutrition vs label claims" and not kws:  # moisture / ash also land in "nutrition"
                kws = ["protein", "carbohydrate", "sugar", "energy", "sodium", "total fat", "saturated fat", "dietary fib"]
            clean.append({"name": t["name"].strip(), "why": t["why"].strip(), "group": t["group"], "keywords": kws, "source": t["source"].strip()})
        assert 1 <= len(clean) <= 8, (cat, len(clean))
        assert len({t["name"] for t in clean}) == len(clean), f"dup names in {cat}"
        merged[cat] = clean
HEAVY = {"name": "Heavy metals (lead, arsenic, cadmium, mercury)", "why": "Metals from soil, water or processing build up in the body over years; FSSAI caps them in every food.", "group": "heavy_metal", "keywords": [], "source": "FSSAI Contaminants, Toxins and Residues Regulations 2011, Reg 2.1"}
merged["packaged_food"] = [
    {"name": "Nutrition vs label claims", "why": "Checks that the nutrition table on the pack matches what's actually inside.", "group": "nutrition", "keywords": ["protein", "carbohydrate", "sugar", "energy", "sodium", "total fat", "saturated fat", "dietary fib"], "source": "FSSAI Labelling and Display Regulations 2020"},
    HEAVY,
    {"name": "Aflatoxins", "why": "Toxins from mould on grains, nuts and seeds; long-term exposure damages the liver.", "group": "toxin", "keywords": ["aflatoxin"], "source": "FSSAI CTR 2011, Reg 2.2"},
    {"name": "Microbiology (E. coli, Salmonella, Listeria)", "why": "Bacteria from poor hygiene or storage can cause food poisoning.", "group": None, "keywords": ["coli", "salmonella", "listeria", "plate count", "coliform", "yeast", "mould", "staphylo"], "source": "FSSAI FPS Regulations, Appendix B (microbiological standards)"},
]
OUT.write_text(json.dumps({"_about": "Standard tests per category. See backend/category_tests.py.", **dict(sorted(merged.items()))}, indent=1, ensure_ascii=False) + "\n")
print(len(merged), "categories,", sum(len(v) for v in merged.values()), "tests")
for k, v in notes.items(): print(f"\n[{k}] {v[:500]}")
