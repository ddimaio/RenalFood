# RenalFood

Approximate composition calculator, optimiser and recipe generator for
home-made diets for dogs with chronic kidney disease (CKD).

**Not veterinary advice.** A home-made renal diet needs a balancing
supplement and should be checked by a vet / veterinary nutritionist.

## Apps

| File | Run | Needs |
|---|---|---|
| `renal_diet_calc.py` | `python renal_diet_calc.py` | Python + Tkinter (standard library) |
| `renal_diet_app.py` | `streamlit run renal_diet_app.py` | `pip install -r requirements.txt` |

Both share the same calculation engine (`renal_diet_calc.py`) and the same
ingredient library file, `renal_ingredients.json`, created next to the
scripts on first run.

## Features

- Nutrient composition per 100 g, dry matter, per 1000 kcal and per day:
  protein, fat, fibre, Ca, P, Na, K, Mg, vitamins A, B1, B2, B3, B5, B6,
  B12, folate, choline, D, E, C, EPA+DHA.
- Checks against ACVN renal-diet ranges, AAFCO adult minimums/maximums and
  IRIS stage guidance; Ca:P, calcium and vitamin D excess, acid load
  (indicative), fat share, phosphate binders (estimated binding).
- Daily energy need (MER = factor × 70 × BW^0.75) and scaling to body weight.
- Optimiser: best amounts for chosen ingredients + suggested additions.
- Generator: balanced recipes from the whole library, with protein and
  vegetable variety, optional fixed base (e.g. breakfast kibble).
- Ingredient import (CSV/JSON), add from a pet-food label, save/load recipes.

## Extra ingredients

`imports/` holds JSON files to import via **Import CSV/JSON**: dry white
rice, cooked egg white, and oils (rapeseed, coconut, linseed, hemp, walnut).

## Sources

- UC Davis – Nutritional Management of Chronic Renal Disease
- ACVN Nutrition Notes – Nutritional Management of CKD in Cats & Dogs
  (Today's Veterinary Practice, 2016)
- IRIS treatment recommendations
- AAFCO dog food nutrient profiles (adult maintenance)
- Ingredient values: approximations of USDA FoodData Central
