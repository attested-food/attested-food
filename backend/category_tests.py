"""Tests we run for each product category, and which of them a product's reports already cover.

Each test is (name, result group or None for any group, parameter keywords). A test counts as done when a
result in that group has a parameter containing one of the keywords (any parameter if no keywords).
Sets are based on FSSAI standards and what Trustified, Unbox Health, Labdoor and Consumer Voice test.
"""

Test = tuple[str, str | None, tuple[str, ...]]

LABEL: Test = ("Nutrition vs label claims", "nutrition", ())
HEAVY: Test = ("Heavy metals (lead, arsenic, cadmium, mercury)", "heavy_metal", ())
AFLATOXIN: Test = ("Aflatoxins", "toxin", ("aflatoxin",))
PESTICIDE: Test = ("Pesticide residues", "pesticide", ())
MICRO: Test = ("Microbiology (E. coli, Salmonella, Listeria)", None,
               ("coli", "salmonella", "listeria", "microbio", "plate count", "yeast", "mould", "staphylo", "shigella"))
RANCIDITY: Test = ("Rancidity (acid value, peroxide value)", None, ("acid value", "peroxide", "rancid", "anisidine"))
ACTIVE: Test = ("Active ingredient vs label claim", "nutrition", ())
COLOUR: Test = ("Synthetic colours and adulterants", "spiking", ())

TESTS: dict[str, list[Test]] = {
    "breakfast_cereal": [LABEL],
    "packaged": [LABEL, HEAVY, AFLATOXIN, MICRO],
    "bakery": [LABEL, ("Potassium bromate / iodate", None, ("bromate", "iodate")), HEAVY, AFLATOXIN, MICRO],
    "snack": [LABEL, RANCIDITY, ("Mineral oil", "spiking", ("mineral",)), HEAVY, AFLATOXIN],
    "grain": [LABEL, AFLATOXIN, PESTICIDE, HEAVY],
    "nut": [LABEL, AFLATOXIN, PESTICIDE, HEAVY],
    "chocolate": [LABEL, HEAVY, AFLATOXIN],
    "sauce": [LABEL, COLOUR, ("Preservatives (benzoic acid, sorbic acid)", None, ("benzoic", "sorbic")), HEAVY, MICRO],
    "protein": [LABEL, ("Amino acid / melamine spiking", "spiking", ()), HEAVY, AFLATOXIN, PESTICIDE, MICRO],
    "kids": [LABEL, ("Melamine", None, ("melamine",)), AFLATOXIN, HEAVY, PESTICIDE, MICRO],
    "dairy": [("Fat, SNF and protein", "nutrition", ()), ("Adulterants (urea, detergent, starch, melamine)", "spiking", ()),
              ("Aflatoxin M1", "toxin", ("aflatoxin",)), HEAVY, MICRO],
    "ghee": [("Fatty acid profile", "nutrition", ("acid", "fat")),
             ("Foreign fat adulteration (vegetable / animal fat)", None,
              ("sitosterol", "baudouin", "butyro", "br reading", "reichert", "polenske", "foreign fat")),
             ("Aflatoxin M1", "toxin", ("aflatoxin",)), HEAVY, PESTICIDE],
    "oil": [("Fatty acid profile", "nutrition", ("acid", "fat")), ("Adulteration (argemone, mineral oil, other oils)", "spiking", ()),
            RANCIDITY, AFLATOXIN, HEAVY, PESTICIDE],
    "honey": [("Sugar profile", "nutrition", ("sugar", "fructose", "glucose", "sucrose")),
              ("Sugar syrup adulteration (C4 sugars)", "spiking", ()),
              ("Freshness (HMF, diastase)", None, ("hmf", "hydroxymethyl", "diastase")), HEAVY, PESTICIDE],
    "spice": [COLOUR, PESTICIDE, AFLATOXIN, HEAVY, MICRO],
    "coffee": [("Caffeine content", "nutrition", ("caffeine",)), ("Mycotoxins (aflatoxin, ochratoxin A)", "toxin", ()),
               PESTICIDE, HEAVY],
    "salt": [("Iodine content", "nutrition", ("iodine",)), ("Purity (sodium chloride, insoluble matter)", None,
                                                            ("sodium", "insoluble", "matter soluble")), HEAVY],
    "vinegar": [("Acetic acid content", "nutrition", ("acetic",)), HEAVY],
    "meat": [MICRO, ("Synthetic colours", None, ("dye", "colour")), ("Antibiotic residues", None, ("antibiotic",)), HEAVY],
    "supplement": [ACTIVE, HEAVY],
    "herbal": [ACTIVE, HEAVY, PESTICIDE],
    "omega": [ACTIVE, HEAVY, RANCIDITY],
}

FAMILY = {
    **dict.fromkeys(["bread", "biscuits"], "bakery"),
    **dict.fromkeys(["chips", "snacks", "instant_noodle", "instant_noodles", "ready_to_eat", "sweets", "protein_chip"], "snack"),
    **dict.fromkeys(["flour", "rice", "soya_chunks", "idli_dosa_batter", "muesli", "granola", "jaggery_powder"], "grain"),
    **dict.fromkeys(["peanut_butter", "nuts"], "nut"),
    **dict.fromkeys(["chocolate", "dark_chocolate", "cocoa_powder"], "chocolate"),
    **dict.fromkeys(["ketchup", "jam", "juice", "pickle"], "sauce"),
    **dict.fromkeys(["protein_powder", "mass_gainer", "protein_milkshake", "protein_bar", "snack_bar"], "protein"),
    **dict.fromkeys(["health_drink", "kids_nutrition_drink", "infant_formula", "glucose_powder"], "kids"),
    **dict.fromkeys(["milk", "curd", "paneer", "cheese", "ice_cream", "dairy_whitener"], "dairy"),
    **dict.fromkeys(["ghee", "butter"], "ghee"),
    **dict.fromkeys(["cooking_oil", "vanaspati"], "oil"),
    **dict.fromkeys(["spices", "tea"], "spice"),
    "honey": "honey", "coffee_powder": "coffee", "salt": "salt", "apple_cider_vinegar": "vinegar", "meat": "meat",
    "breakfast_cereal": "breakfast_cereal",
    **dict.fromkeys(["ashwagandha_supplement", "curcumin_supplement", "moringa_supplement", "shilajit_supplement",
                     "milk_thistle_supplement", "berberine_supplement"], "herbal"),
    **dict.fromkeys(["omega_3_supplement", "sea_buckthorn_oil"], "omega"),
}

SUPPLEMENT_HINTS = ("supplement", "vitamin", "collagen", "creatine", "magnesium", "electrolyte", "astaxanthin", "pre_workout")


def tests_for(category: str) -> list[Test]:
    family = FAMILY.get(category)
    if family is None:
        family = "supplement" if any(h in category for h in SUPPLEMENT_HINTS) else "packaged"
    return TESTS[family]


def names_for(category: str) -> list[str]:
    return [name for name, _, _ in tests_for(category)]


def coverage(category: str, results: list[dict]) -> list[dict]:
    def done(group: str | None, keywords: tuple[str, ...]) -> bool:
        return any(
            (group is None or r["group"] == group) and (not keywords or any(k in r["parameter"].lower() for k in keywords))
            for r in results
        )

    return [{"name": name, "tested": done(group, keywords)} for name, group, keywords in tests_for(category)]
