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
- EPA+DHA floor in renal stages from the ACVN therapeutic dose
  (140 mg × BW^0.75 a day) spread over the daily energy target.
- Missing nutrient values are not treated as zero: totals are minimums, so
  shortfalls in those nutrients are not scored, only excesses.
- Optional *extended nutrients* check (a toggle, off by default): essential
  amino acids, linoleic acid and trace minerals (Fe, Cu, Mn, Zn, I, Se) vs
  AAFCO adult minimums, plus iodine and selenium maximums. Hidden from the
  results and library editor unless switched on.
  A complete commercial food without these values can be flagged
  *Complete food (assume AAFCO)*: its missing extended nutrients are then
  taken as exactly the AAFCO adult minimum per 1000 kcal of that food, so
  the rest of the recipe can still be checked (shown as "assumed").
- Optional daily food limit (g/day) for a small appetite: the optimiser
  and generator then favour energy-dense recipes (less vegetable, more oil)
  that fit in that amount.
- Daily energy need (MER = factor × 70 × BW^0.75) and scaling to body weight.
- Optimiser: best amounts for chosen ingredients + suggested additions.
- Generator: balanced recipes from the whole library, with protein and
  vegetable variety, optional fixed base (e.g. breakfast kibble).
- Ingredient import (CSV/JSON), add from a pet-food label, save/load recipes.

## Filling extended nutrients from USDA

`fdc_fill.py` fills the extended nutrients in `renal_ingredients.json` from
USDA FoodData Central. It needs a free API key
(https://fdc.nal.usda.gov/api-key-signup). Run it (also from Spyder); it
asks you to match each library food to an FDC food once (saved in
`fdc_map.json`), then fills empty values only. Check matches are the same
preparation (cooked vs raw). Commercial foods and supplements are skipped:
use their labels. Iodine is rarely in FDC.

## Filling missing values from the Australian AFCD

`afcd_fill.py` fills empty values (iodine, B vitamins, vitamin E, trace
minerals...) from the Australian Food Composition Database, Release 3
(https://www.foodstandards.gov.au/science-data/food-nutrient-databases/afcd).
Download "AFCD Release 3 - Nutrient profiles.xlsx" and run
`python afcd_fill.py "AFCD Release 3 - Nutrient profiles.xlsx"`
(`--dry-run` to preview). Foods are matched by hand in the script, values
are scaled to the library food's water content, existing values are never
changed, and each filled ingredient's note records the AFCD food used.
AFCD has no choline; branded foods and algal/fish oil are not in it.

## Extra ingredients

`imports/` holds JSON files to import via **Import CSV/JSON**: dry white
rice, cooked egg white, oils (rapeseed, coconut, linseed, hemp, walnut)
and mushrooms (white, chestnut, portobello, shiitake, oyster; also in the
library).

`imports/afcd_foods.json` (also in the library) has 39 dog-safe foods from
the AFCD, added with `afcd_add.py`: vegetables (cauliflower, cucumber,
celery, cos lettuce, red pepper, bean sprouts, Brussels sprouts,
asparagus, beetroot, turnip, swede, parsnip, mangetout, summer and
butternut squash, pak choi, Chinese leaf, Swiss chard, okra), starches
(couscous, quinoa, polenta, pearl barley, buckwheat, millet, tapioca, rice
noodles), protein foods (soya, haricot and butter beans, split peas, vital
wheat gluten, cottage cheese, ricotta, natural yoghurt) and peanut butter,
chia seeds, rice bran and grapeseed oil. Foods toxic to dogs are left out.

`imports/japan_foods.json` (also in the library) has 19 foods from the
Standard Tables of Food Composition in Japan 2023 (MEXT), added with
`jp_add.py` from the main, amino-acid and fatty-acid Excel files: okara,
edamame, natto, soy milk, kabocha, daikon, winter melon, mung bean sprouts,
lotus root, shirataki, mung bean glass noodles, potato starch, udon, somen
and sesame, soybean, corn, safflower and perilla oil. The same script
replaces silken tofu's estimated values with measured ones and fills
missing amino acids, B5 and trace minerals of other foods (amino acids
scaled by protein, the rest by dry matter).

## Reference diets

`renal_references.json` holds commercial renal diets for comparison only
(not ingredients): Recipe tab → Composition → "Compare with a reference
diet" (Streamlit) or **Compare with reference…** (desktop) shows the
recipe and the reference per 1000 kcal side by side. Add more entries in
the same format (label values per 100 g as fed, with kcal; `added_only`
lists nutrients where the label gives only added amounts), or import them
like ingredients: Ingredient library tab → *Reference diets* (Streamlit) or
the buttons in the desktop comparison window. CSV (download the reference
template; blank = not declared; blank kcal is estimated from protein, fat,
fibre, ash and moisture) or JSON (a reference diet, a list, or an ingredient
JSON such as `imports/bonza_kibble.json`). Same-name entries are replaced.

To change a recipe so it resembles a reference diet, choose the optimiser
**Objective** "Match a reference diet" (energy target + closeness per 1000
kcal, weighted most for protein and phosphorus) or "Renal targets +
reference diet". Additions, substitutions and your own additions then work
towards that objective, and the results show the recipe vs the reference.

## Remembered exclusions

Foods you untick in the generator's list or the optimiser's suggested
additions are remembered and left out of both. The generator's Always
include ticks and Min g / Max g values are remembered too. The Streamlit app keeps them
in your browser (so they survive app restarts; per browser/device); the
desktop app keeps them in `renal_prefs.json` next to the program.

An ingredient may carry `"role": "starch"` (or protein, veg, oil,
supplement, other) in its JSON to override how the generator classes it;
otherwise the role comes from its energy split.

## Sources

- UC Davis – Nutritional Management of Chronic Renal Disease
- ACVN Nutrition Notes – Nutritional Management of CKD in Cats & Dogs
  (Today's Veterinary Practice, 2016)
- IRIS treatment recommendations
- AAFCO dog food nutrient profiles (adult maintenance)
- Ingredient values: approximations of USDA FoodData Central
- Extended nutrients (amino acids, linoleic acid, Fe, Cu, Mn, Zn, Se) for
  the generic foods: USDA National Nutrient Database SR26, matched by NDB
  number; pure salts/binders set to 0, oils' amino acids set to 0. Iodine
  is not in SR26 and stays empty. Commercial foods, yeast flakes, eggshell
  powder, Cauldron tofu, hemp and algal oil minerals are left empty.
