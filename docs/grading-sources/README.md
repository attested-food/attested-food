# Sources behind the OpenLabel grade

Research notes (with source URLs and what couldn't be verified) for each part of `backend/grading.py`:

- `tolerances.json`: label honesty. EU 2012 tolerance guidance, FDA 21 CFR 101.9(g), FSSAI Labelling and Display
  Regulations 2020 reg 5(3)(d), FSSAI Nutra Regulations 2016 reg 3(11). Implemented in `backend/standards.py`.
- `severity.json`: safety tiers. FDA 21 CFR 7.3(m), EU RASFF, EU Reg 2073/2005, FSS Act 2006 s.3(1)(zz)/(zx).
- `nutrition.json`: Nutri-Score 2022/2023 algorithms, plus the status of FSSAI's draft Indian Nutrition Rating and
  the WHO South-East Asia nutrient profile model.

Where the notes say a value is OpenLabel's own choice (penalty steps, 5x/10x escalation, the 10 kcal energy floor),
the code marks it the same way. `../category-tests-sources/` holds the research behind
`backend/category_tests.json`.
