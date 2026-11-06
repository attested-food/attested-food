"""Shop departments: groups of product categories, like aisles in a store.

Categories come from the scrapers and can be inconsistent; ALIASES folds duplicates into one
canonical category so a shopper sees each kind of product once.
"""

ALIASES = {
    "instant_noodle": "instant_noodles",
    "magnesium_glycinate": "magnesium_supplement",
    "vitamin_supplement": "multivitamin",
}

DEPARTMENTS: list[tuple[str, str, tuple[str, ...]]] = [
    ("protein-fitness", "Protein & fitness", ("protein_powder", "creatine_supplement", "pre_workout", "mass_gainer", "protein_bar", "protein_milkshake", "protein_chip", "electrolyte")),
    ("oils-ghee", "Oils & ghee", ("cooking_oil", "ghee", "vanaspati")),
    ("dairy", "Dairy", ("milk", "paneer", "curd", "butter", "cheese", "dairy_whitener")),
    ("breakfast-bakery", "Breakfast & bakery", ("breakfast_cereal", "muesli", "granola", "bread", "idli_dosa_batter")),
    ("staples", "Atta, rice & staples", ("flour", "rice", "salt", "spices", "jaggery_powder", "soya_chunks")),
    ("snacks", "Snacks & biscuits", ("biscuits", "snacks", "chips", "snack_bar", "nuts", "instant_noodles", "ready_to_eat", "meat")),
    ("sweets", "Chocolate & sweets", ("chocolate", "dark_chocolate", "sweets", "ice_cream", "cocoa_powder")),
    ("spreads", "Spreads & sauces", ("peanut_butter", "jam", "honey", "ketchup", "pickle", "apple_cider_vinegar")),
    ("drinks", "Tea, coffee & drinks", ("tea", "coffee_powder", "juice", "health_drink", "glucose_powder")),
    ("kids", "Baby & kids", ("infant_formula", "kids_nutrition_drink")),
]
SUPPLEMENTS = ("supplements", "Vitamins & supplements")
OTHER = ("other", "Other")


def canonical(category: str | None) -> str | None:
    return ALIASES.get(category, category) if category else category


def department_of(category: str | None) -> str:
    """Department key for a category. Anything supplement-like goes to supplements, the rest to other."""
    c = canonical(category) or ""
    for key, _, cats in DEPARTMENTS:
        if c in cats:
            return key
    if any(w in c for w in ("supplement", "vitamin", "collagen", "omega", "multivitamin", "astaxanthin", "shilajit", "ashwagandha", "moringa", "curcumin", "melatonin", "biotin", "berberine", "coq10", "msm", "hyaluronic", "milk_thistle", "sea_buckthorn")):
        return SUPPLEMENTS[0]
    return OTHER[0]


def department_names() -> list[tuple[str, str]]:
    return [(k, n) for k, n, _ in DEPARTMENTS] + [SUPPLEMENTS, OTHER]


def group(category_counts: dict[str, int]) -> list[dict]:
    """Departments in shelf order, each with its canonical categories and product counts (empty ones dropped)."""
    merged: dict[str, int] = {}
    for cat, n in category_counts.items():
        c = canonical(cat)
        if c:
            merged[c] = merged.get(c, 0) + n
    out = []
    for key, name in department_names():
        cats = sorted(((c, n) for c, n in merged.items() if department_of(c) == key), key=lambda x: -x[1])
        if cats:
            out.append({"key": key, "name": name, "product_count": sum(n for _, n in cats),
                        "categories": [{"category": c, "product_count": n} for c, n in cats]})
    return out


def categories_in(dept: str, all_categories: list[str]) -> list[str]:
    """Raw category values (aliases included) from all_categories that belong to a department."""
    return [c for c in all_categories if department_of(c) == dept]


def with_aliases(category: str) -> list[str]:
    """A category plus every raw value that folds into it."""
    c = canonical(category)
    return [c, *[a for a, target in ALIASES.items() if target == c]]
