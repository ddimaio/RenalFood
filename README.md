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
| `android/` (phone app, in progress) | `cd android` then `flet run` | `pip install "flet[all]"` – see `android/README.md` |

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
   list of foods it may suggest is remembered. *Use the recipe generator's
   exclusions* (on by default) shares one excluded list with the
   generator; untick it to give the optimiser its own list (starts as a
   copy) without changing the generator's.
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

`imports/tahini.json` (also in the library): plain tahini from hulled, roasted
sesame (USDA SR26 12166). Oxalate left unknown (no reliable value).

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

## Generator: no limit on ingredients

Tick *No limit* in the generator to drop the limits on foods, vegetables
and extras (and allow extra proteins and starches). Foods are added while
the score improves, or stays the same and the rating rises by at least 1
point (safety cap 20 items). About twice as slow.

## Meal plans (a different recipe per meal)

Generator → *Meal plan* (desktop: **Make: Meal plan**; Streamlit: the 🍱
section). Builds 2–3 home-made recipes – one per meal, to cook and freeze
separately – with different starches and vegetables (and proteins where
possible). Only the DAY total is scored, so single meals need not be
complete; each meal keeps its share of the home-made energy (e.g. 50/50 or
60/40). Supplements (fish/algal oil, balancers, B-complex) are 'add at
serving' items, chosen for the day (one product per brand). Each meal keeps
a real amount of its protein food. A fixed base (e.g. breakfast kibble)
counts as an extra meal. Results show each meal's portion, energy and
phosphorus, the day check, *Use as day recipe* (puts the whole day on the
Recipe tab for the full analysis) and a printable page with each meal's
batch for N days. Raw flours are left out of daily recipes and meal plans
(they are for biscuits) unless forced.

### Working with an active meal plan

*Use this meal plan* (generator) makes the plan active. The Recipe tab /
recipe list then shows the meals (Meal A, Meal B…, At serving, Fixed) with
each meal's grams, energy and phosphorus; amounts and foods are edited per
meal (desktop: adding a food asks which meal; supplements go to At
serving). The analysis is the day total. The optimiser works per meal: the
limits table lists each meal's items, foods are tried in each meal,
supplements at serving, swaps stay within their meal, each meal keeps its
energy share, and Apply keeps the plan. Scaling rescales every meal;
loading or applying an ordinary recipe ends the plan (or *End meal plan* /
*Stop using the meal plan*). Undo and save/load (`"plan"` in the recipe JSON) include it, and the
printable recipe lists each meal as its own recipe (one portion and a batch
for N days, default 7) followed by the day's nutrients and assessment.

### Biscuits in a meal plan

Each generated biscuit recipe can be saved as a library ingredient
(*Save as ingredient*: category **treat**, values per 100 g of **baked**
biscuit – enter the batch weight after baking for exact values, or leave 0
to estimate it at ~8 % moisture). Biscuits are any size, so everything is
in grams. Treats are never suggested as foods.
*Add to meal plan* puts N grams of baked biscuit a day into the active plan (section
"Biscuits (treats)", amount locked); optimise the plan to rebalance the
meals around them. The meal-plan generator also has *Biscuits every day*
(a saved treat and grams a day), so new plans are balanced with the
biscuits included. Treats saved by older versions (per raw dough) still
work. The same "Biscuits (treat)" option exists in *Save as a library
food* for any recipe.

### Blood results remembered

The blood results you enter (and the targets adapted from them) are
remembered with My Dog – weight, age, activity, factor, food limit,
meals, stage – and shown at the top of My Dog (desktop: the 🩸 line under
the top bar, with *Enter / view…*), marked "targets adapted from these ✓"
or "not applied". On one computer the desktop and web apps share them
(renal_prefs.json); the web app also keeps them in the browser.

### Daily targets

My Dog (desktop: **Daily targets** button) lists the key nutrients per day
at the energy target – protein, phosphorus (with the stage aim), sodium,
potassium, calcium (AAFCO minimum and Ca:P 1–2 at the phosphorus aim),
magnesium, fat, EPA+DHA (therapeutic dose for her weight to the NRC upper
limit), oxalate, fibre and the treat allowance. They are the per-1000 kcal
targets the scoring uses, times the day's energy, so they follow weight,
factor, stage and any blood adaptation.

### Saved meals (custom foods)

*Save as a library food* (Recipe tab / desktop) stores the recipe, or one
meal of a meal plan, as one food (category **custom**, per 100 g of the
mix). Saved meals appear in the generator's ingredient list (role "saved
meal"); they are never suggested, and are used only when **Always
include** is ticked – e.g. a frozen lunch, with the generator building the
rest of the day around it (amount optimised, never below Min g). To keep
an exact amount instead, put it in the recipe and use the fixed base.

## Renal-friendly biscuits (treats)

Generator → *Renal-friendly biscuits* (desktop: **Make: biscuits**;
Streamlit: the 🍪 section). Builds doughs of 1–2 flours, 1–2 moist binders
(raw egg, pumpkin, apple, banana, yoghurt…) and optionally an oil or nut /
seed paste, from the ticked foods (Always-include foods that suit a dough
are added). Practical dough rules: flour 45–70 % of the dough, pure
starches (arrowroot, cornflour, potato starch) at most half of the flour,
and something that binds (egg, or wheat, gluten-free, oat or chickpea
flour); delicate omega-3 oils are not baked. Recipes are scored only on the
renal limits per 1000 kcal (phosphorus at or below the stage aim, sodium,
potassium, protein, oxalate, fat share) – treats are not complete food.
Each recipe gives the batch amounts, water to add, the estimated baked
weight, the energy per gram (baked and raw dough), the daily maximum in
grams (10 % treat allowance), method and a printable page. Biscuit recipes can be saved as JSON files (*Save as JSON* / *Save all as JSON*; desktop: *Save JSON…*) and loaded again (*Load biscuit recipes*; desktop: *Load biscuits (JSON)…* in the generator or *Load JSON…* in the results), re-checked with the current settings. Flours (rice, plain wheat, cornflour,
arrowroot, gluten-free plain, chickpea) were added from AFCD Release 3
with `afcd_add.py`.

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
raise the rating by at least 1 point. The rating is per 1000 kcal, so
it never depends on the amount.

## Taurine and L-carnitine check

Plant foods contain practically none, and food tables don't list them, so
they are not scored (dogs make both; there is no AAFCO/FEDIAF/NRC
minimum). Instead the assessment adds one line when a recipe without meat
or fish has no food that declares added taurine and/or L-carnitine
(Bonza, Omni, V-Integra, VEGDOG, Just Be Kind do; read from the label
note – write "adds taurine, L-carnitine" in a new product's note, or set
its `adds` field).

## Energy of target

Next to score and rating, every analysis, optimiser option, generated
recipe, meal plan and printout shows **Energy N% of target** (recipe kcal
against the daily target; ✓ within ±5 %, ⚠ within ±15 %, ✗ beyond). The
score includes an energy term, so a well-balanced recipe at the wrong
amount scores badly; this line shows when that is the reason – scale the
recipe. The rating is unaffected by amount.

## Batch cooking

Recipe tab → **Batch cooking** (desktop: *Batch cooking (several meals)…*;
phone: button next to Print): enter the number of meals to prepare. One
meal = the recipe (per day) ÷ meals per day (My dog); the batch is one
meal × that number, shown with kitchen units, the total to cook and the
portion size. The recipe itself is not changed; the printout gets
a batch column. **Print batch sheet** gives a one-page kitchen sheet:
batch amounts with tick boxes, total and portion size with kcal, steps,
and portion labels to cut out. (A meal plan's printout already has a batch
per meal.)

## Printing a recipe

**🖨️ Printable recipe** (Streamlit, Recipe tab) downloads an A4 page;
**Print…** (desktop, under the recipe) opens it in the browser. It has the
dog and settings, ingredients (g/day, g/meal, kcal, tick boxes), key
nutrients vs targets with status, the assessment, feeding notes and space
for the vet's notes. Open it and press Print (or Ctrl+P).

## Age and activity

Optional *Age* and *Activity* (sidebar / toolbar) suggest a starting MER
factor: adult 1.6 (neutered pet), senior still active 1.5, senior or adult
inactive 1.4 (NRC 2006 older dogs ≈105 / 95 kcal × BW^0.75). Senior from
10 years under 10 kg, 8 years up to 25 kg, 6 years above. Nothing changes
until you press *Use factor* (Streamlit) or confirm *Suggest factor*
(desktop); in CKD, adjust by body weight and muscle rather than age alone.

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
additions are remembered and left out of both. Each list has a **Select/Deselect
all** tick (phone: in Food choices) to use or leave out every food at
once, e.g. untick all and then tick the few you want. The generator's Always
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

- Bauer JE. Therapeutic use of fish oils in companion animals. JAVMA 2011;239:1441–51 (EPA+DHA 140 mg × BW^0.75 a day in CKD; NRC safe upper limit 370 mg × BW^0.75)
- Brown SA et al. 1998, J Lab Clin Med (fish oil vs safflower oil vs beef tallow in dogs with reduced renal mass)
- FEDIAF Nutritional Guidelines 2024 (adult minimums; the app checks against AAFCO, which is the same or stricter for the nutrients scored)

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
