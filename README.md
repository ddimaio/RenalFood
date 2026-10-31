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

## Optimiser

Optimise tab (Streamlit) / **Optimise…** (desktop), in steps:

1. **Ingredients & limits** – min/max g per food, or lock an amount.
2. **Goal** – renal targets, a reference diet, or both; energy target;
   priorities and aims.
3. **Changes allowed** – *Allow everything* (default) adjusts amounts and
   tests adding, swapping and removing foods; untick it to choose. The
   list of foods it may suggest is remembered.
4. **Find options** → one list, **best first** (score, then rating), with
   ★ on the recommended option. Each row says what changes ("+ Fish oil
   3 g · − Lentils · Rice 150→60 g"). Pick one to see its amounts,
   nutrients and remaining gaps, then **Apply** it. Nothing changes before
   that, and Undo is on the Recipe tab.
5. **Fine-tune yourself** – add or remove specific foods and re-optimise,
   starting from the option picked.

`imports/dafy_v_integra_renal.json` (also in the library): Dafy V-Integra
Renal, a phosphorus-free vitamin-mineral balancer (vegetarian; mostly
calcium, potassium and magnesium carbonates). From the manufacturer's label.
`imports/dafy_v_integra_renal_met.json` (also in the library): Dafy V-Integra
Renal Met, the same balancer with added DL-methionine (5.8%), for recipes
low in methionine (e.g. plant-based). From the manufacturer's label.

## Recommended maximum amounts

An ingredient can carry a recommended maximum (label dose) in g/day:
column *Recommended max g/day* in the library (Streamlit), *Recommended
max g/day* in the desktop ingredient editor, or `max_dose` in JSON/CSV.
Write a fixed amount (`7`), an amount per kg body weight (`0.18/kg`) or a
weight table (`5:4, 10:8, 15:10` = up to 5 kg 4 g, up to 10 kg 8 g...).
The optimiser fills **Max g** with it for the dog's weight, says where
each value came from and flags current amounts above it; the generator and
suggested additions use it too. Concentrated EPA+DHA oils (fish, algal)
get a max from the upper limit of 2800 mg EPA+DHA per 1000 kcal of the
energy target. Set so far: ThorneVet B ComplexVET (1 chew per 11 kg =
0.176 g/kg), Dafy V-Integra Renal and Renal Met (label table) and V-Integra Adult
(7 g up to 10 kg - only that band is known).

## Only ingredients with complete data

Generator: "Only ingredients with complete data" (and "…but allow missing
choline", on by default - choline is not in the food tables used) leaves
out foods with any unknown value among the nutrients checked (all of them
with Extended nutrients on); the list shows each food's missing nutrients.
The optimiser has the same option for its suggested additions and
substitutions. Always-include and fixed-base items are kept.

## Rating (tie-breaker)

The score only counts problems, so many recipes reach 0. The **rating**
(0-100, higher = better) shows how well a recipe meets the targets:
phosphorus low within the renal range (25), AAFCO minimums covered incl.
vitamins and extended nutrients (25), data complete (15), oxalate low (15),
protein near the aim (10), sodium/potassium/EPA+DHA/Ca:P away from the
range edges (10). Generated recipes with the same score are ranked by it,
and the optimiser suggests additions/substitutions that keep the score but
raise the rating by at least 1 point.

## Printing a recipe

**🖨️ Printable recipe** (Streamlit, Recipe tab) downloads an A4 page;
**Print…** (desktop, under the recipe) opens it in the browser. It has the
dog and settings, ingredients (g/day, g/meal, kcal, tick boxes), key
nutrients vs targets with status, the assessment, feeding notes and space
for the vet's notes. Open it and press Print (or Ctrl+P).

## Meals per day

Recipes are daily totals. Set **Meals per day** (sidebar / toolbar, default
2) to also see per-meal amounts: a per-meal recipe table, a "Per meal"
column in the composition and g/meal in optimiser and generator results.

## Oxalate

Oxalate (mg/100 g) is tracked for library foods (`oxalate_fill.py`;
source: Oxalosis & Hyperoxaluria Foundation food list 2024). Recipes are
penalised above 50 mg/1000 kcal (app judgement - no canine standard; weight
"Oxalate ≤ limit" editable) and foods ≥100 mg/100 g (spinach, chard, chia,
sweet potato, peanut butter, buckwheat, okra) are flagged red in the
ingredient breakdown and named in the assessment. Background: Cook &
Atiee, "Understanding and Addressing Canine Calcium Oxalate Urolithiasis",
Today's Veterinary Practice, Jan/Feb 2026.

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
desktop app keeps them in `renal_prefs.json` in a fixed per-user folder (Windows: `%APPDATA%\RenalFood`, otherwise `~/.renalfood`), so they survive unzipping a new version into another folder; an older `renal_prefs.json` next to the program is carried over once.

An ingredient may carry `"role": "starch"` (or protein, veg, oil,
supplement, other) in its JSON to override how the generator classes it;
otherwise the role comes from its energy split.

## Recent literature additions

- Blood potassium 5.1–5.5 mmol/L ("high-normal") lowers the potassium
  ceiling to 1700 mg/1000 kcal (K > 5.1 was linked to faster progression;
  Miyakawa et al., JVIM 2021).
- Muscle condition score (0–3, the vet's) in the blood results: any loss
  raises the protein minimum/aim and energy; slightly heavy dogs (BCS 6–7)
  get no energy cut (muscle loss shortened and a heavier body condition
  lengthened survival; PLOS One 2020).
- Assessment flags recipes where calcium-rich supplements or binders give
  ≥40% of the calcium: ask for ionised calcium checks (IRIS).
- Assessment shows the water supplied by the food vs the ~1 ml/kcal total
  need; printout suggests adding warm water and feeding the renal recipe
  consistently (≥75% of the time was linked to longer survival).

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
