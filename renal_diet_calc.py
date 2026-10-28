#!/usr/bin/env python3
"""
renal_diet_calc.py - Approximate composition of home-made dog diets, checked
against chronic kidney disease (CKD) nutritional targets.

Run:  python renal_diet_calc.py        (standard library only: Tkinter)

What it covers (UC Davis "Nutritional Management of Chronic Renal Disease"):
  protein, phosphorus, calcium (and Ca:P), sodium, potassium, magnesium,
  water-soluble vitamins (B1, B2, B3, B6, B12, folate, C), vitamin A,
  acid-base load (PRAL index + added alkali), fat / energy density,
  calories vs. the dog's energy requirement, plus EPA+DHA (omega-3),
  phosphate binders (estimated binding) and calcium excess (Ca max, Ca:P).

Data sources / targets
  * Ingredient values: approximations of USDA FoodData Central, per 100 g,
    cooked weight where the name says so. None = unknown -> reported as
    "data incomplete" rather than silently counted as zero.
  * Renal ranges: ACVN Nutrition Notes (Cline, Today's Veterinary Practice,
    2016) - typical therapeutic renal diets for dogs, per 1000 kcal ME.
  * Minimums: AAFCO adult dog maintenance, per 1000 kcal ME.
  * Stage notes: IRIS serum phosphate targets.
  * PRAL: Remer & Manz (human) potential renal acid load - indicative only.

Approximate tool - not veterinary advice. Trace minerals (Zn, Cu, Fe, I, Se),
vitamins D/E, choline, essential fatty acids and amino-acid balance are NOT
checked; a home-made diet needs a vet-approved vitamin/mineral supplement.
"""

import csv
import json
import os
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, simpledialog
    from tkinter import font as tkfont
    HAS_TK = True
except ImportError:          # engine still importable (e.g. Streamlit app)
    from types import SimpleNamespace as _NS
    HAS_TK = False
    tk = _NS(Tk=object, Toplevel=object, TclError=Exception)
    ttk = filedialog = simpledialog = tkfont = None
    messagebox = _NS(showwarning=lambda *a, **k: None,
                     showerror=lambda *a, **k: None,
                     showinfo=lambda *a, **k: None)

ENGINE_VERSION = "2026.10.28"   # bump when the Streamlit app needs new code
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "renal_ingredients.json")

# --------------------------------------------------------------------------
# Nutrients (all values stored per 100 g of ingredient)
# --------------------------------------------------------------------------
NUTRIENTS = [
    ("kcal", "Energy", "kcal"),
    ("water", "Water", "g"),
    ("protein", "Protein", "g"),
    ("fat", "Fat", "g"),
    ("carb", "Carbohydrate (incl. fibre)", "g"),
    ("fibre", "Fibre", "g"),
    ("ca", "Calcium", "mg"),
    ("p", "Phosphorus", "mg"),
    ("na", "Sodium", "mg"),
    ("k", "Potassium", "mg"),
    ("mg", "Magnesium", "mg"),
    ("vit_a", "Vitamin A", "µg RAE"),
    ("b1", "Thiamine (B1)", "mg"),
    ("b2", "Riboflavin (B2)", "mg"),
    ("b3", "Niacin (B3)", "mg"),
    ("b6", "Vitamin B6", "mg"),
    ("b12", "Vitamin B12", "µg"),
    ("folate", "Folate", "µg"),
    ("b5", "Pantothenic acid (B5)", "mg"),
    ("choline", "Choline", "mg"),
    ("vit_d", "Vitamin D", "IU"),
    ("vit_e", "Vitamin E", "IU"),
    ("vit_c", "Vitamin C", "mg"),
    ("epa_dha", "EPA + DHA", "mg"),
    ("base_meq", "Added alkali (e.g. bicarbonate)", "mEq"),
    ("p_bind", "Phosphate binding (est.)", "mg P"),
]
KEYS = [k for k, _, _ in NUTRIENTS]
LABEL = {k: l for k, l, _ in NUTRIENTS}
UNIT = {k: u for k, _, u in NUTRIENTS}
# Keys that default to 0 (not "unknown") when absent from older files
OPTIONAL_ZERO = ("epa_dha", "base_meq", "p_bind")

# Renal-diet ranges for dogs, per 1000 kcal ME (ACVN Nutrition Notes, 2016)
RENAL = {
    "protein": (25, 55),     # g
    "p": (400, 1200),        # mg
    "na": (400, 1200),       # mg
    "k": (800, 2100),        # mg
    # EPA+DHA: 32 = lowest level in commercial renal diets (ACVN table, whose
    # 1200 top is just the highest diet, not a limit); upper bound = NRC 2006
    # safe upper limit for dogs, 280 mg/100 kcal
    "epa_dha": (32, 2800),   # mg
}
# AAFCO adult maintenance minimums, per 1000 kcal ME
AAFCO = {
    "protein": 45, "fat": 13.8, "ca": 1250, "p": 1000, "k": 1500, "na": 200,
    "mg": 150, "vit_a": 375,  # 1250 IU retinol = 375 µg
    "b1": 0.56, "b2": 1.3, "b3": 3.4, "b6": 0.38, "b12": 7, "folate": 54,
    "b5": 3.0, "choline": 340, "vit_d": 125, "vit_e": 12.5,
}
WATER_SOLUBLE = ["b1", "b2", "b3", "b5", "b6", "b12", "folate"]
# AAFCO adult maximum, per 1000 kcal ME (Ca 2.5% DM); Ca:P max 2:1
AAFCO_MAX = {"ca": 6250, "vit_d": 750}
# Nutrients added in a later version: filled in for built-in foods already
# saved in an older library file
NEW_KEYS = ("b5", "choline", "vit_d", "vit_e")
# Phosphate binders: relative phosphate-binding coefficients vs calcium
# carbonate (Daugirdas/Chertow, human in-vivo data) x ~39 mg P bound per g
# CaCO3 (commonly cited human estimate). Binding in dogs is not established -
# these only give an order of magnitude. Dose binders only as prescribed.
P_BIND_PER_G_CACO3 = 39

STAGES = {
    "Stage 1 – non-proteinuric": (
        False, "No renal diet needed yet; recipe is checked against AAFCO "
        "maintenance minimums. IRIS serum phosphate target 0.9–1.5 mmol/L "
        "(2.7–4.6 mg/dL)."),
    "Stage 1 – proteinuric": (
        True, "Protein-restricted renal diet recommended because of "
        "proteinuria. Serum phosphate target 0.9–1.5 mmol/L."),
    "Stage 2": (
        True, "Start phosphorus restriction (early-renal diets sit in the "
        "upper part of the ranges). Serum phosphate target 0.9–1.5 mmol/L "
        "(<4.6 mg/dL)."),
    "Stage 3": (
        True, "Full renal diet; phosphorus typically towards the lower end. "
        "Serum phosphate target <1.6 mmol/L (5.0 mg/dL); a phosphate binder "
        "may be needed."),
    "Stage 4": (
        True, "Full renal diet, lowest phosphorus; most dogs need a phosphate "
        "binder. Serum phosphate target <1.9 mmol/L (6.0 mg/dL). Priority is "
        "keeping her eating - never force-feed."),
}


# --------------------------------------------------------------------------
# Built-in ingredients (per 100 g; approx. USDA FDC)
# --------------------------------------------------------------------------
def _ing(name, category, zero=False, note="", **kw):
    vals = {k: (0.0 if zero else None) for k in KEYS}
    if not zero:
        for k in OPTIONAL_ZERO:
            vals[k] = 0.0
    vals.update(kw)
    return {"name": name, "category": category, "note": note,
            "per100g": vals}


def _supp(name, note="", **kw):
    return _ing(name, "supplement", zero=True, note=note, **kw)


def _binder(name, rpbc, note="", **kw):
    kw["p_bind"] = rpbc * P_BIND_PER_G_CACO3 * 100   # mg P per 100 g
    return _ing(name, "binder", zero=True,
                note=(note + " Binding is a human-derived estimate; give only "
                      "as prescribed by your vet, mixed into meals."),
                **kw)


BUILTIN = [
    # --- protein sources
    _ing("Tofu, firm (calcium-set)", "food",
         note="Calcium varies hugely with coagulant - check label.",
         kcal=144, water=70.8, protein=17.3, fat=8.7, carb=2.8, fibre=2.3,
         ca=683, p=190, na=14, k=237, mg=58, vit_a=0, b1=0.16, b2=0.10,
         b3=0.38, b6=0.09, b12=0, folate=29, vit_c=0.2),
    _ing("Tofu, silken", "food",
         kcal=55, water=87.3, protein=4.8, fat=2.7, carb=2.9, fibre=0.1,
         ca=31, p=62, na=5, k=180, mg=27, vit_a=0, b1=0.10, b2=0.04,
         b3=0.30, b6=0.01, b12=0, folate=44, vit_c=0),
    _ing("Egg white, raw", "food",
         kcal=52, water=87.6, protein=10.9, fat=0.2, carb=0.7, fibre=0,
         ca=7, p=15, na=166, k=163, mg=11, vit_a=0, b1=0.004, b2=0.44,
         b3=0.11, b6=0.005, b12=0.09, folate=4, vit_c=0),
    _ing("Egg, whole, raw", "food",
         kcal=143, water=76.2, protein=12.6, fat=9.5, carb=0.7, fibre=0,
         ca=56, p=198, na=142, k=138, mg=12, vit_a=160, b1=0.04, b2=0.46,
         b3=0.08, b6=0.17, b12=0.89, folate=47, vit_c=0, epa_dha=37),
    _ing("Egg, whole, hard-boiled", "food",
         kcal=155, water=74.6, protein=12.6, fat=10.6, carb=1.1, fibre=0,
         ca=50, p=172, na=124, k=126, mg=10, vit_a=149, b1=0.07, b2=0.51,
         b3=0.06, b6=0.12, b12=1.1, folate=44, vit_c=0, epa_dha=37),
    _ing("Egg yolk, raw", "food",
         kcal=322, water=52.3, protein=15.9, fat=26.5, carb=3.6, fibre=0,
         ca=129, p=390, na=48, k=109, mg=5, vit_a=381, b1=0.18, b2=0.53,
         b3=0.02, b6=0.35, b12=1.95, folate=146, vit_c=0, epa_dha=114),
    _ing("Lentils, boiled", "food",
         kcal=116, water=69.6, protein=9.0, fat=0.4, carb=20.1, fibre=7.9,
         ca=19, p=180, na=2, k=369, mg=36, vit_a=0, b1=0.17, b2=0.07,
         b3=1.06, b6=0.18, b12=0, folate=181, vit_c=1.5),
    _ing("Chickpeas, boiled", "food",
         kcal=164, water=60.2, protein=8.9, fat=2.6, carb=27.4, fibre=7.6,
         ca=49, p=168, na=7, k=291, mg=48, vit_a=1, b1=0.12, b2=0.06,
         b3=0.53, b6=0.14, b12=0, folate=172, vit_c=1.3),
    # --- starches
    _ing("Rice, white, boiled (unenriched)", "food",
         kcal=130, water=68.4, protein=2.7, fat=0.3, carb=28.2, fibre=0.4,
         ca=10, p=43, na=1, k=35, mg=12, vit_a=0, b1=0.02, b2=0.01,
         b3=0.4, b6=0.09, b12=0, folate=3, vit_c=0),
    _ing("Rice, brown, boiled", "food",
         kcal=123, water=70.3, protein=2.7, fat=1.0, carb=25.6, fibre=1.6,
         ca=3, p=103, na=4, k=86, mg=39, vit_a=0, b1=0.18, b2=0.07,
         b3=2.6, b6=0.12, b12=0, folate=9, vit_c=0),
    _ing("Pasta, boiled (unenriched)", "food",
         kcal=158, water=62.1, protein=5.8, fat=0.9, carb=30.9, fibre=1.8,
         ca=7, p=58, na=1, k=44, mg=18, vit_a=0, b1=0.02, b2=0.02,
         b3=0.4, b6=0.05, b12=0, folate=7, vit_c=0),
    _ing("Oats, rolled, dry", "food",
         kcal=379, water=10.8, protein=13.2, fat=6.5, carb=67.7, fibre=10.1,
         ca=52, p=410, na=6, k=362, mg=138, vit_a=0, b1=0.46, b2=0.16,
         b3=1.1, b6=0.1, b12=0, folate=32, vit_c=0),
    _ing("Potato, boiled, no skin", "food",
         kcal=86, water=77.5, protein=1.7, fat=0.1, carb=20.0, fibre=2.0,
         ca=8, p=40, na=5, k=328, mg=20, vit_a=0, b1=0.10, b2=0.02,
         b3=1.3, b6=0.27, b12=0, folate=10, vit_c=7.4),
    _ing("Sweet potato, boiled, no skin", "food",
         kcal=76, water=80.1, protein=1.4, fat=0.1, carb=17.7, fibre=2.5,
         ca=27, p=32, na=27, k=230, mg=18, vit_a=787, b1=0.06, b2=0.05,
         b3=0.54, b6=0.17, b12=0, folate=6, vit_c=12.8),
    # --- vegetables
    _ing("Carrot, boiled", "food",
         kcal=35, water=90.2, protein=0.8, fat=0.2, carb=8.2, fibre=3.0,
         ca=30, p=30, na=58, k=235, mg=10, vit_a=852, b1=0.07, b2=0.04,
         b3=0.65, b6=0.15, b12=0, folate=14, vit_c=3.6),
    _ing("Green beans, boiled", "food",
         kcal=35, water=89.2, protein=1.9, fat=0.3, carb=7.9, fibre=3.2,
         ca=44, p=29, na=1, k=146, mg=18, vit_a=35, b1=0.07, b2=0.10,
         b3=0.61, b6=0.06, b12=0, folate=33, vit_c=9.7),
    _ing("Broccoli, boiled", "food",
         kcal=35, water=89.3, protein=2.4, fat=0.4, carb=7.2, fibre=3.3,
         ca=40, p=67, na=41, k=293, mg=21, vit_a=77, b1=0.06, b2=0.12,
         b3=0.55, b6=0.20, b12=0, folate=108, vit_c=64.9),
    _ing("Courgette, boiled", "food",
         kcal=15, water=94.8, protein=1.1, fat=0.4, carb=2.7, fibre=1.0,
         ca=18, p=37, na=3, k=264, mg=19, b6=0.08, b12=0, folate=17,
         vit_c=12.9),
    _ing("Pumpkin, boiled", "food",
         kcal=20, water=93.7, protein=0.7, fat=0.1, carb=4.9, fibre=1.1,
         ca=15, p=30, na=1, k=230, mg=9, vit_a=288, b1=0.03, b2=0.08,
         b3=0.41, b6=0.04, b12=0, folate=9, vit_c=4.7),
    _ing("Peas, green, boiled", "food",
         kcal=84, water=77.9, protein=5.4, fat=0.2, carb=15.6, fibre=5.5,
         ca=27, p=117, na=3, k=271, mg=39, vit_a=40, b1=0.26, b2=0.15,
         b3=2.0, b6=0.22, b12=0, folate=63, vit_c=14.2),
    _ing("Spinach, boiled", "food", note="High oxalate and potassium.",
         kcal=23, water=91.2, protein=3.0, fat=0.3, carb=3.8, fibre=2.4,
         ca=136, p=56, na=70, k=466, mg=87, vit_a=524, b1=0.10, b2=0.24,
         b3=0.49, b6=0.24, b12=0, folate=146, vit_c=9.8),
    _ing("Cabbage, boiled", "food",
         kcal=23, water=92.6, protein=1.3, fat=0.1, carb=5.5, fibre=1.9,
         ca=48, p=33, na=8, k=196, mg=15, vit_a=4, b1=0.06, b2=0.04,
         b3=0.25, b6=0.11, b12=0, folate=30, vit_c=37.5),
    # --- fruit
    _ing("Apple, peeled, raw", "food",
         kcal=48, water=86.7, protein=0.3, fat=0.1, carb=12.8, fibre=1.3,
         ca=5, p=11, na=0, k=90, mg=4, vit_a=2, b1=0.02, b2=0.03,
         b3=0.09, b6=0.04, b12=0, folate=0, vit_c=4.0),
    _ing("Banana", "food",
         kcal=89, water=74.9, protein=1.1, fat=0.3, carb=22.8, fibre=2.6,
         ca=5, p=22, na=1, k=358, mg=27, vit_a=3, b1=0.03, b2=0.07,
         b3=0.67, b6=0.37, b12=0, folate=20, vit_c=8.7),
    # --- fats / oils
    _ing("Sunflower oil", "food", kcal=884, water=0, protein=0, fat=100,
         carb=0, fibre=0, ca=0, p=0, na=0, k=0, mg=0, vit_a=0, b1=0, b2=0,
         b3=0, b6=0, b12=0, folate=0, vit_c=0),
    _ing("Olive oil", "food", kcal=884, water=0, protein=0, fat=100,
         carb=0, fibre=0, ca=0, p=0, na=0, k=0, mg=0, vit_a=0, b1=0, b2=0,
         b3=0, b6=0, b12=0, folate=0, vit_c=0),
    _ing("Fish oil (salmon)", "supplement",
         note="EPA+DHA varies by product - edit to match label.",
         kcal=902, water=0, protein=0, fat=100, carb=0, fibre=0, ca=0, p=0,
         na=0, k=0, mg=0, vit_a=0, b1=0, b2=0, b3=0, b6=0, b12=0,
         folate=0, vit_c=0, epa_dha=31200),
    _ing("Algal oil (vegan omega-3)", "supplement",
         note="EPA+DHA varies by product - edit to match label.",
         kcal=900, water=0, protein=0, fat=100, carb=0, fibre=0, ca=0, p=0,
         na=0, k=0, mg=0, vit_a=0, b1=0, b2=0, b3=0, b6=0, b12=0,
         folate=0, vit_c=0, epa_dha=40000),
    # --- mineral supplements / alkalinisers
    _supp("Calcium carbonate", note="Phosphorus-free calcium; mild alkali.",
          ca=40000),
    _supp("Calcium citrate (tetrahydrate)", ca=21100),
    _supp("Eggshell powder", note="Approximate.", ca=38000, p=100),
    _supp("Potassium citrate (monohydrate)", note="Potassium + alkaliniser.",
          k=36100),
    _supp("Potassium gluconate", k=16700),
    _supp("Sodium bicarbonate", note="Alkaliniser; adds sodium.",
          na=27400, base_meq=1190),
    _supp("Salt (sodium chloride)", na=39300),
    # --- phosphate binders (vet-prescribed; amounts are locked in the
    #     optimiser and never suggested)
    _binder("Calcium carbonate (as phosphate binder)", 1.0,
            note="Adds calcium (40%).", ca=40000),
    _binder("Calcium acetate (as phosphate binder)", 1.0,
            note="Adds calcium (25%).", ca=25300),
    _binder("Aluminium hydroxide (as phosphate binder)", 1.5,
            note="No calcium; long-term use can cause aluminium toxicity."),
]


# B5 (mg), choline (mg), vitamin D (IU; µg x 40), vitamin E (IU; mg
# alpha-tocopherol x 1.49), per 100 g - approximate USDA values. None =
# unknown. Supplements/binders are 0 for all four unless edited.
EXTRA_VITS = {
    "Tofu, firm (calcium-set)": (0.13, 28.8, 0, 0.01),
    "Tofu, silken": (None, None, 0, None),
    "Egg white, raw": (0.19, 1.1, 0, 0),
    "Egg, whole, raw": (1.53, 294, 82, 1.56),
    "Egg, whole, hard-boiled": (1.40, 294, 87, 1.53),
    "Egg yolk, raw": (2.99, 820, 218, 3.84),
    "Lentils, boiled": (0.64, 32.7, 0, 0.16),
    "Chickpeas, boiled": (0.29, 42.8, 0, 0.52),
    "Rice, white, boiled (unenriched)": (0.39, 2.1, 0, 0.06),
    "Rice, brown, boiled": (0.38, 9.2, 0, 0.04),
    "Pasta, boiled (unenriched)": (0.11, 6.4, 0, 0.09),
    "Oats, rolled, dry": (1.12, 40.4, 0, 0.63),
    "Potato, boiled, no skin": (0.51, 13.2, 0, 0.01),
    "Sweet potato, boiled, no skin": (0.53, 11.4, 0, 1.40),
    "Carrot, boiled": (0.23, 8.8, 0, 1.53),
    "Green beans, boiled": (0.07, 16.9, 0, 0.69),
    "Broccoli, boiled": (0.62, 40.1, 0, 2.16),
    "Courgette, boiled": (None, None, 0, 0.18),
    "Pumpkin, boiled": (0.20, 6.2, 0, 1.19),
    "Peas, green, boiled": (0.15, 27.5, 0, 0.21),
    "Spinach, boiled": (0.15, 24.8, 0, 3.10),
    "Cabbage, boiled": (None, None, 0, 0.18),
    "Apple, peeled, raw": (0.06, 3.4, 0, 0.07),
    "Banana": (0.33, 9.8, 0, 0.15),
    "Sunflower oil": (0, 0, 0, 61.2),
    "Olive oil": (0, 0, 0, 21.4),
    "Fish oil (salmon)": (0, 0, None, None),
    "Algal oil (vegan omega-3)": (0, 0, None, None),
}
for _item in BUILTIN:
    if _item["name"] in EXTRA_VITS:
        _item["per100g"].update(zip(NEW_KEYS, EXTRA_VITS[_item["name"]]))


# --------------------------------------------------------------------------
# Database & calculations
# --------------------------------------------------------------------------
def load_db():
    db = {}
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, encoding="utf-8") as f:
                for item in json.load(f):
                    db[item["name"]] = normalise(item)
        except (OSError, ValueError, KeyError) as e:
            messagebox.showwarning("Database", f"Could not read database:\n{e}")
    for item in BUILTIN:          # add any built-ins not already present
        if item["name"] in db:    # fill nutrients added in later versions
            cur = db[item["name"]]["per100g"]
            for k in NEW_KEYS:
                if cur.get(k) is None and item["per100g"].get(k) is not None:
                    cur[k] = float(item["per100g"][k])
        db.setdefault(item["name"], normalise(item))
    save_db(db)
    return db


def normalise(item):
    vals = item.get("per100g", {})
    return {"name": str(item["name"]).strip(),
            "category": item.get("category", "food"),
            "note": item.get("note", ""),
            "per100g": {k: (0.0 if (k in OPTIONAL_ZERO and k not in vals)
                              else None if vals.get(k) is None
                              else float(vals[k])) for k in KEYS}}


def save_db(db):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(db.values(), key=lambda d: d["name"].lower()), f,
                  indent=1, ensure_ascii=False)


def to_float(s):
    s = str(s).strip().replace(",", ".")
    if s == "" or s.lower() in ("none", "na", "n/a", "-", "?"):
        return None
    return float(s)


def compute(recipe, db):
    """recipe: list of (name, grams). Returns mass, totals, missing names."""
    totals = {k: 0.0 for k in KEYS}
    missing = {k: [] for k in KEYS}
    mass = 0.0
    for name, grams in recipe:
        item = db.get(name)
        if item is None or grams <= 0:
            continue
        mass += grams
        for k in KEYS:
            v = item["per100g"][k]
            if v is None:
                missing[k].append(name)
            else:
                totals[k] += v * grams / 100.0
    return mass, totals, missing


def pral(t):
    """Potential renal acid load (Remer & Manz, human), mEq, minus added
    alkali. Positive = acidifying, negative = alkalinising. Indicative only."""
    return (0.49 * t["protein"] + 0.037 * t["p"] - 0.021 * t["k"]
            - 0.026 * t["mg"] - 0.013 * t["ca"] - t["base_meq"])


def net_p(t):
    """Dietary phosphorus minus estimated binder capacity (not below 0)."""
    return max(0.0, t["p"] - t["p_bind"])


def mer(bw, factor):
    return factor * 70.0 * bw ** 0.75 if bw > 0 else 0.0


def fmt(v):
    if v is None:
        return "–"
    a = abs(v)
    if a >= 100:
        return f"{v:,.0f}"
    if a >= 10:
        return f"{v:.1f}"
    if a >= 0.1:
        return f"{v:.2f}"
    return f"{v:.3f}" if v else "0"


# Extra limits that blood results can tighten (defaults = AAFCO)
DEFAULT_LIMITS = {"ca_p": (1.0, 2.0), "ca_max": AAFCO_MAX["ca"]}


def get_ranges(ctx=None):
    """Renal ranges + Ca limits, with any blood-adapted overrides in
    ctx['ranges'] applied."""
    r = {**RENAL, **DEFAULT_LIMITS}
    for k, v in ((ctx or {}).get("ranges") or {}).items():
        r[k] = tuple(v) if isinstance(v, (list, tuple)) else v
    return r


def status_for(k, per1000, renal_mode, ranges=None):
    """Returns (text, tag) comparing a nutrient per 1000 kcal to targets."""
    msgs, tag = [], ""
    R = ranges or RENAL
    if renal_mode and k in RENAL:
        lo, hi = R[k]
        if per1000 < lo:
            msgs.append("below renal range")
            tag = "warn" if k in ("epa_dha", "na") else "bad"
        elif per1000 > hi:
            msgs.append("above NRC safe upper limit" if k == "epa_dha"
                        else "above renal range")
            tag = "bad"
        else:
            msgs.append("in renal range")
            tag = "ok"
    elif k in AAFCO:
        if per1000 < AAFCO[k]:
            msgs.append("below AAFCO min")
            tag = "warn"
        elif k in AAFCO_MAX and per1000 > AAFCO_MAX[k]:
            msgs.append("above AAFCO max")
            tag = "bad"
        else:
            msgs.append("≥ AAFCO min")
            tag = "ok"
    return ", ".join(msgs), tag


# --------------------------------------------------------------------------
# Optimiser
# --------------------------------------------------------------------------
# Approach: daily energy is held at the target by scaling the free
# ingredients, so the search only changes their *proportions*. The score is
# a weighted sum of squared relative deviations outside each target band
# (0 = every target met). scipy (L-BFGS-B) is used if installed, followed by
# a bounded pattern search; without scipy the pattern search runs alone.
try:
    from scipy.optimize import minimize as _sp_minimize
except Exception:                     # scipy is optional
    _sp_minimize = None

KI = {k: i for i, k in enumerate(KEYS)}
OPT_WEIGHTS = {"energy": 10.0, "phosphorus": 5.0, "protein": 4.0,
               "ca_p": 3.0, "sodium": 1.0, "potassium": 1.0, "omega3": 1.0,
               "micros": 1.0, "vitamins": 1.0, "fat": 1.0, "fibre": 2.0,
               "aim": 0.5, "acid": 0.0}
WEIGHT_LABELS = {"energy": "Energy", "phosphorus": "Phosphorus",
                 "protein": "Protein", "ca_p": "Ca:P ratio",
                 "sodium": "Sodium", "potassium": "Potassium",
                 "omega3": "EPA+DHA", "micros": "Fat/Ca/Mg minimums",
                 "vitamins": "Vitamin minimums",
                 "fat": "Fat ≤55% kcal", "fibre": "Fibre ≤15 g/1000kcal",
                 "aim": "Pull to aims", "acid": "Acid load (PRAL)"}
# Practical bulk limit (app default, not a published renal target): total
# dietary fibre per 1000 kcal. Stops the optimiser filling up on vegetables.
FIBRE_MAX = 15.0
# Aim points inside the ACVN ranges (per 1000 kcal). These are this app's
# editable defaults - early stages higher, late stages lower - NOT published
# targets. Confirm with your vet.
AIMS = {"Stage 1 – non-proteinuric": {},
        "Stage 1 – proteinuric": {"protein": 40, "p": 900},
        "Stage 2": {"protein": 45, "p": 900},
        "Stage 3": {"protein": 40, "p": 700},
        "Stage 4": {"protein": 35, "p": 550}}
MICROS = ("fat", "ca", "mg")
VITAMINS = ("vit_a", "b1", "b2", "b3", "b5", "b6", "b12", "folate",
            "choline", "vit_d", "vit_e")


def default_bounds(item, kcal_target=None):
    """Default (min, max) grams per day for an ingredient (editable in the
    optimiser dialog). Low-energy foods (vegetables/fruit) are capped at
    0.25 g per kcal of daily target to keep bulk sensible."""
    kcal = item["per100g"]["kcal"] or 0
    if kcal >= 800:                       # oils
        return 0.0, 20.0
    if item["category"] == "supplement":  # powders
        return 0.0, 5.0
    if kcal < 60 and kcal_target:
        return 0.0, round(0.25 * kcal_target)
    return 0.0, 500.0


def _vec(item):
    return [item["per100g"][k] or 0.0 for k in KEYS]   # unknown -> 0


def _totals(g, vecs):
    t = [0.0] * len(KEYS)
    for gi, v in zip(g, vecs):
        if gi > 0:
            f = gi / 100.0
            for j, val in enumerate(v):
                if val:
                    t[j] += val * f
    return t


def _band(v, lo, hi):
    if lo is not None and v < lo:
        return ((lo - v) / lo) ** 2
    if hi is not None and v > hi:
        return ((v - hi) / hi) ** 2
    return 0.0


def per1000_from(g, vecs):
    t = _totals(g, vecs)
    kcal = t[KI["kcal"]]
    f = 1000.0 / kcal if kcal > 0 else 0.0
    return kcal, {k: t[KI[k]] * f for k in KEYS}, t


def score_amounts(g, vecs, ctx):
    """Penalty score for gram amounts g (0 = all targets met) and its terms."""
    kcal, per, t = per1000_from(g, vecs)
    if kcal <= 1e-6:
        return 1e6, {"Energy": 1e6}
    W, terms = ctx["weights"], {}
    R = get_ranges(ctx)

    def add(name, w, val):
        if val > 0 and w > 0:
            terms[name] = terms.get(name, 0.0) + w * val

    tgt = ctx["kcal_target"]
    add("Energy", W["energy"], ((kcal - tgt) / tgt) ** 2)
    # phosphorus net of any (locked) binder
    p_eff = max(0.0, per["p"] - per["p_bind"])
    if ctx["renal"]:
        add("Phosphorus", W["phosphorus"], _band(p_eff, *R["p"]))
        add("Protein", W["protein"], _band(per["protein"], *R["protein"]))
        add("Sodium", W["sodium"], _band(per["na"], *R["na"]))
        add("Potassium", W["potassium"], _band(per["k"], *R["k"]))
        add("EPA+DHA", W["omega3"], _band(per["epa_dha"], *R["epa_dha"]))
        for k, aim in ctx["aims"].items():
            if aim:
                v = p_eff if k == "p" else per[k]
                add(f"{LABEL[k]} vs aim", W["aim"], ((v - aim) / aim) ** 2)
    else:
        add("Protein", W["protein"], _band(per["protein"], AAFCO["protein"], None))
        add("Phosphorus", W["phosphorus"], _band(per["p"], AAFCO["p"], None))
        add("Sodium", W["sodium"], _band(per["na"], AAFCO["na"], None))
        add("Potassium", W["potassium"], _band(per["k"], AAFCO["k"], None))
    if per["p"] > 0:
        add("Ca:P ratio", W["ca_p"], _band(per["ca"] / per["p"], *R["ca_p"]))
    add("Calcium (max)", W["ca_p"], _band(per["ca"], None, R["ca_max"]))
    if W.get("acid"):                    # set from low blood bicarbonate
        add("Acid load", W["acid"], (max(0.0, pral(per)) / 50.0) ** 2)
    add("Vitamin D (max)", W["ca_p"], _band(per["vit_d"], None,
                                            AAFCO_MAX["vit_d"]))
    for k in MICROS:
        add(LABEL[k], W["micros"] * 0.5, _band(per[k], AAFCO[k], None))
    for k in VITAMINS:
        add(LABEL[k], W.get("vitamins", W["micros"]) * 0.5,
            _band(per[k], AAFCO[k], None))
    fat_me = 8.5 * t[KI["fat"]]
    me = (fat_me + 3.5 * t[KI["protein"]] +
          3.5 * max(0.0, t[KI["carb"]] - t[KI["fibre"]]))
    if me > 0:
        add("Fat % of calories", W["fat"], _band(fat_me / me, None, 0.55))
    add("Fibre (bulk)", W.get("fibre", 0), _band(per["fibre"], None, FIBRE_MAX))
    return sum(terms.values()), terms


def _pattern_search(f, x, lo, hi, max_evals=5000):
    n = len(x)
    fx = f(x)
    steps = [(hi[i] - lo[i]) / 4.0 for i in range(n)]
    tol = [max(0.01, (hi[i] - lo[i]) * 1e-3) for i in range(n)]
    evals = 1
    while evals < max_evals and any(steps[i] > tol[i] for i in range(n)):
        improved = False
        for i in range(n):
            if steps[i] <= tol[i]:
                continue
            for d in (1, -1):
                y = list(x)
                y[i] = min(hi[i], max(lo[i], x[i] + d * steps[i]))
                if y[i] == x[i]:
                    continue
                fy = f(y)
                evals += 1
                if fy < fx:
                    x, fx, improved = y, fy, True
                    break
        if not improved:
            steps = [s * 0.5 for s in steps]
    return x, fx


def optimise(names, db, bounds, x0, ctx, use_scipy=True, max_evals=5000):
    """names: ingredients; bounds: [(min, max, locked)] in g/day; x0: start
    grams (locked items keep x0). Returns (grams, score, terms)."""
    vecs = [_vec(db[n]) for n in names]
    kc = [v[KI["kcal"]] for v in vecs]
    free = [i for i, (lo, hi, lk) in enumerate(bounds) if not lk and hi > 0]
    fixed = [i for i in range(len(names)) if i not in free]
    tgt = ctx["kcal_target"]

    def amounts(y):
        g = [0.0] * len(names)
        for i in fixed:
            g[i] = x0[i] if bounds[i][2] else 0.0
        kfix = sum(g[i] * kc[i] / 100.0 for i in fixed)
        kfree = sum(y[j] * kc[i] / 100.0 for j, i in enumerate(free))
        s = max(0.0, (tgt - kfix) / kfree) if kfree > 1e-9 else 1.0
        for j, i in enumerate(free):
            g[i] = y[j] * s
        return g

    def obj(y):
        g = amounts(y)
        sc, _ = score_amounts(g, vecs, ctx)
        for i in free:
            lo, hi, _ = bounds[i]
            if g[i] > hi:
                sc += 10.0 * ((g[i] - hi) / max(hi, 1.0)) ** 2
            if g[i] < lo:
                sc += 10.0 * ((lo - g[i]) / max(lo, 1.0)) ** 2
        return sc

    if free:
        yhi = [bounds[i][1] for i in free]
        ylo = [0.0] * len(free)
        y = [min(yhi[j], max(0.0, x0[i])) or yhi[j] * 0.05
             for j, i in enumerate(free)]
        if _sp_minimize is not None and use_scipy:
            try:
                r = _sp_minimize(obj, y, method="L-BFGS-B",
                                 bounds=list(zip(ylo, yhi)))
                if r.fun < obj(y):
                    y = [float(v) for v in r.x]
            except Exception:
                pass
        y, _ = _pattern_search(obj, y, ylo, yhi, max_evals)
        g = amounts(y)
    else:
        g = amounts([])
    g = [round(v, 1) if not bounds[i][2] else v for i, v in enumerate(g)]
    sc, terms = score_amounts(g, vecs, ctx)
    return g, sc, terms


def suggest_additions(names, db, bounds, x0, ctx, candidates, max_add=3,
                      progress=None):
    """Optimise the chosen set, then test each candidate as an addition and
    build a greedy best combination of up to max_add additions."""
    base = optimise(names, db, bounds, x0, ctx)
    singles = []
    for idx, c in enumerate(candidates):
        if progress:
            progress(idx, len(candidates), c)
        lo, hi = default_bounds(db[c], ctx["kcal_target"])
        g, s, t = optimise(names + [c], db, bounds + [(lo, hi, False)],
                           list(base[0]) + [0.0], ctx)
        if s < base[1] * 0.98 and g[-1] >= 0.1:
            singles.append((c, g, s, t))
    singles.sort(key=lambda r: r[2])

    cur_n, cur_b, cur_g, cur_s, cur_t = (list(names), list(bounds),
                                         list(base[0]), base[1], base[2])
    added = []
    pool = [r[0] for r in singles[:8]]
    for _ in range(max_add):
        best = None
        for c in pool:
            if c in cur_n:
                continue
            lo, hi = default_bounds(db[c], ctx["kcal_target"])
            g, s, t = optimise(cur_n + [c], db, cur_b + [(lo, hi, False)],
                               cur_g + [0.0], ctx)
            if g[-1] >= 0.1 and (best is None or s < best[2]):
                best = (c, g, s, t)
        if best is None or best[2] > cur_s * 0.98:
            break
        lo, hi = default_bounds(db[best[0]], ctx["kcal_target"])
        cur_n, cur_b = cur_n + [best[0]], cur_b + [(lo, hi, False)]
        cur_g, cur_s, cur_t = best[1], best[2], best[3]
        added.append(best[0])
    return base, singles, (cur_n, cur_g, cur_s, cur_t, added)


ROLES = ("protein", "starch", "veg", "oil", "supplement", "complete",
         "other", "binder")


def ingredient_role(item):
    """Heuristic role from category and macronutrient energy split."""
    v = item["per100g"]
    kcal = v["kcal"] or 0.0
    if item["category"] == "binder":
        return "binder"
    if item["category"] == "supplement" and kcal < 800:
        return "supplement"
    if kcal >= 800 or (v["fat"] or 0) >= 80:
        return "oil"
    if item["category"] == "commercial food":
        return "complete"
    if kcal <= 0:
        return "other"
    prot = (v["protein"] or 0) * 4 / kcal
    dcarb = max(0.0, (v["carb"] or 0) - (v["fibre"] or 0)) * 4 / kcal
    # protein foods: >=30% of energy from protein AND a real amount of it
    # (silken tofu 4.8 g/100 g = protein; spinach 3 g, broccoli 2.4 g = veg)
    if prot >= 0.30 and (kcal >= 60 or (v["protein"] or 0) >= 4):
        return "protein"
    if kcal >= 75 and dcarb >= 0.60:
        return "starch"
    if kcal < 75:
        return "veg"
    return "other"


def _family(name):
    """Food family: 'Egg, whole, raw' / 'Egg yolk' -> 'egg'."""
    return name.split(",")[0].split("(")[0].split()[0].lower()


def generate_recipes(db, pool, ctx, n_recipes=5, max_ing=6, fixed=(),
                     progress=None, cancelled=lambda: False, n_veg=2,
                     veg_max_uses=2, veg_min_g=None, forced=None):
    """Build balanced recipes from scratch.
    Stage 1: every protein x starch x vegetable base (amounts optimised).
    Stage 2: best bases get vegetables added up to n_veg (forced, for
             variety), then grow greedily with oils, supplements and other
             foods up to max_ing ingredients.
    Variety: protein families round-robin, at most 2 recipes per protein
    family, each vegetable in at most veg_max_uses recipes, every vegetable
    kept at >= veg_min_g grams.
    fixed: [(name, grams)] always included at locked amounts (e.g. kibble).
    forced: {name: min_grams} always included, amounts optimised (>= min).
            A forced protein/starch/vegetable fills that role in the base.
    Returns up to n_recipes distinct (names, grams, score, terms), best first.
    """
    forced = {n: m for n, m in (forced or {}).items()
              if n in db and n not in [f for f, _ in fixed]}
    fx_names = [n for n, _ in fixed]
    fx_g = [g for _, g in fixed]
    fx_b = [(g, g, True) for g in fx_g]
    nfx = len(fx_names)
    fo_names = list(forced)
    base_names = fx_names + fo_names    # in every recipe, in this order
    nb = len(base_names)
    tgt = ctx["kcal_target"]
    roles = {n: ingredient_role(db[n]) for n in pool}
    for n in base_names:
        roles.setdefault(n, ingredient_role(db[n]))
    by = {r: [n for n in pool if roles[n] == r and n not in base_names]
          for r in ROLES}
    filled = {roles[n] for n in fo_names}        # roles covered by forced
    groups = [by[r] for r in ("protein", "starch", "veg")
              if by[r] and r not in filled]
    if not groups and not fo_names:
        groups = [[n for n in pool if n not in base_names
                   and roles[n] not in ("binder", "supplement")]]
    combos = [[]]
    for grp in groups:
        combos = [c + [x] for c in combos for x in grp]

    def bnd(n):
        lo, hi = default_bounds(db[n], tgt)
        if roles.get(n) == "veg" and veg_min_g:
            lo = min(veg_min_g, hi)
        if n in forced:
            dflt = 0.5 if roles.get(n) in ("oil", "supplement") else 5.0
            lo = max(lo, forced[n] or dflt)
            hi = max(hi, lo)
        return (lo, hi, False)

    fo_b = [bnd(n) for n in fo_names]
    fo_x0 = [max(b[0], 1.0) for b in fo_b]

    def vegs(names, grams=None, variety=False):
        """Vegetables in a recipe (forced ones count towards n_veg but not
        towards the variety caps)."""
        start = nb if variety else nfx
        return [n for i, n in enumerate(names) if i >= start and
                roles.get(n) == "veg" and (grams is None or grams[i] >= 2)]

    # ---- stage 1
    bases = []
    for i, combo in enumerate(combos):
        if cancelled():
            return []
        if progress and i % 5 == 0:
            progress("Testing base combinations", i, len(combos))
        names = base_names + combo
        g, s, t = optimise(names, db, fx_b + fo_b + [bnd(n) for n in combo],
                           fx_g + fo_x0 + [0.0] * len(combo), ctx,
                           use_scipy=False, max_evals=1500)
        bases.append((s, names, g))
    bases.sort(key=lambda b: b[0])

    # ---- diverse shortlist: round-robin across protein families, one per
    #      protein/starch pair, each vegetable family capped
    n_keep = max(2 * n_recipes, 6)
    keep, seen, vuse = [], set(), {}
    for strict in (True, False):
        fams = {}
        for b in bases:
            first = b[1][nb] if len(b[1]) > nb else ""
            fams.setdefault(_family(first), []).append(b)
        while len(keep) < n_keep and any(fams.values()):
            for fam in sorted(fams, key=lambda f: fams[f][0][0] if fams[f]
                              else 1e9):
                while fams[fam]:
                    s, names, g = fams[fam].pop(0)
                    key = tuple(names[nb:][:2])
                    vf = [_family(v) for v in vegs(names, variety=True)]
                    if key in seen or (strict and any(
                            vuse.get(f, 0) >= veg_max_uses for f in vf)):
                        continue
                    seen.add(key)
                    for f in vf:
                        vuse[f] = vuse.get(f, 0) + 1
                    keep.append((s, names, g))
                    break
                if len(keep) >= n_keep:
                    break
        if len(keep) >= n_keep:
            break

    # ---- stage 2
    results = []
    used = {}                            # vegetable family -> recipes so far
    # keep each base's protein identity: no second main-protein food
    extra_pool = [n for n in pool if n not in base_names
                  and roles[n] not in ("binder", "protein")]

    def try_add(cur_n, cur_b, cur_g, cands):
        best = None
        for c in cands:
            gg, ss, tt = optimise(cur_n + [c], db, cur_b + [bnd(c)],
                                  cur_g + [0.0], ctx, use_scipy=False,
                                  max_evals=1500)
            if gg[-1] >= 0.1 and (best is None or ss < best[1]):
                best = (c, ss, gg)
        return best

    for bi, (s, names, g) in enumerate(keep):
        cur_n, cur_g, cur_s = list(names), list(g), s
        cur_b = fx_b + fo_b + [bnd(n) for n in names[nb:]]
        if progress:
            progress(f"Refining recipe {bi + 1}/{len(keep)}", bi, len(keep))

        def allowed(c, strict=True):
            fams_in = {_family(n) for n in cur_n}
            if c in cur_n:
                return False
            if (_family(c) in fams_in and
                    roles[c] not in ("supplement", "oil")):
                return False
            if strict and roles[c] == "veg" and \
                    used.get(_family(c), 0) >= veg_max_uses:
                return False
            return True

        # (a) vegetables up to n_veg - added even at a small score cost
        while len(vegs(cur_n)) < n_veg and \
                len(cur_n) - nfx < max_ing:
            if cancelled():
                return []
            cands = [c for c in by["veg"] if allowed(c)] or \
                    [c for c in by["veg"] if allowed(c, strict=False)]
            best = try_add(cur_n, cur_b, cur_g, cands)
            if best is None:
                break
            cur_n.append(best[0])
            cur_b.append(bnd(best[0]))
            cur_g, cur_s = best[2], best[1]

        # (b) greedy improvements with anything else
        while len(cur_n) - nfx < max_ing and cur_s >= 1e-4:
            if cancelled():
                return []
            best = try_add(cur_n, cur_b, cur_g,
                           [c for c in extra_pool if allowed(c)])
            if best is None or best[1] > cur_s * 0.97:
                break
            cur_n.append(best[0])
            cur_b.append(bnd(best[0]))
            cur_g, cur_s = best[2], best[1]

        # final polish, drop trivial amounts (vegetables keep their minimum)
        g2, s2, t2 = optimise(cur_n, db, cur_b, cur_g, ctx)
        keep_idx = [i for i, (n, a) in enumerate(zip(cur_n, g2))
                    if i < nb or a >= (0.1 if roles.get(n) in
                                       ("supplement", "oil") else 2.0)]
        cur_n = [cur_n[i] for i in keep_idx]
        cur_b = [cur_b[i] for i in keep_idx]
        g2, s2, t2 = optimise(cur_n, db, cur_b, [g2[i] for i in keep_idx],
                              ctx)
        for f in {_family(v) for v in vegs(cur_n, g2, variety=True)}:
            used[f] = used.get(f, 0) + 1
        results.append((cur_n, g2, s2, t2))

    # best score first; ties (e.g. several at 0) -> fewer ingredients
    results.sort(key=lambda r: (round(r[2], 4), len(r[0])))

    def main_protein(r):
        cand = [(a * (db[n]["per100g"]["kcal"] or 0), n)
                for n, a in zip(r[0], r[1])
                if roles.get(n) == "protein" and n not in base_names]
        return _family(max(cand)[1]) if cand else None

    out, sigs, per_prot, per_veg = [], [], {}, {}
    for strict in (True, False):         # 2nd pass fills up if needed
        for r in results:
            if r in out:
                continue
            sig = frozenset(n for n, a in zip(r[0], r[1])
                            if a >= 2 and roles.get(n) not in
                            ("supplement", "oil"))
            if any(len(sig & o) / max(1, len(sig | o)) > 0.75 for o in sigs):
                continue
            mp = main_protein(r)
            vf = {_family(v) for v in vegs(r[0], r[1], variety=True)}
            if strict and (per_prot.get(mp, 0) >= 2 or any(
                    per_veg.get(f, 0) >= veg_max_uses for f in vf)):
                continue
            sigs.append(sig)
            per_prot[mp] = per_prot.get(mp, 0) + 1
            for f in vf:
                per_veg[f] = per_veg.get(f, 0) + 1
            out.append(r)
            if len(out) >= n_recipes:
                return sorted(out, key=lambda x: (round(x[2], 4), len(x[0])))
    return sorted(out, key=lambda x: (round(x[2], 4), len(x[0])))


def improvement_reasons(before, after, n=3):
    diffs = sorted(((before.get(k, 0) - after.get(k, 0), k)
                    for k in set(before) | set(after)), reverse=True)
    return [k for d, k in diffs[:n] if d > 1e-6]


def assess_recipe(stage_name, recipe, db, t, miss, mass, kcal, need, capr,
                  acid, k1000, renal_mode, stage_note, fat_frac, ranges=None,
                  blood_note=""):
    """Plain-language assessment notes for a recipe."""
    R = ranges or get_ranges()
    out = [f"{stage_name}: {stage_note}"]
    if blood_note:
        out.append(blood_note)
    out.append("")
    if not kcal or not k1000:
        return "\n".join(out + ["Energy unknown – cannot assess."])
    per = {k: t[k] * k1000 for k in KEYS}

    p_eff = net_p(t) * k1000
    if renal_mode:
        lo, hi = R["p"]
        if p_eff > hi:
            out.append(f"• PHOSPHORUS {p_eff:.0f} mg/1000 kcal"
                       + (" (net of binder)" if t["p_bind"] else "") +
                       " is above "
                       f"the renal range ({lo}–{hi}). Phosphorus restriction "
                       "is the best-supported intervention: reduce "
                       "high-P foods (egg yolk, lentils, chickpeas, oats, "
                       "brown rice, tofu) or ask your vet about a binder.")
        if per["protein"] < R["protein"][0]:
            out.append(f"• PROTEIN is below {R['protein'][0]:g} g/1000 kcal – "
                       "risk of protein malnutrition and muscle loss.")
        elif per["protein"] > R["protein"][1]:
            out.append("• PROTEIN is above the renal range – may worsen "
                       "uraemic signs and adds phosphorus.")
        if per["na"] > R["na"][1]:
            out.append("• SODIUM above renal range – relevant for blood "
                       "pressure. Restrict gradually, not severely.")
        if per["k"] < R["k"][0]:
            out.append("• POTASSIUM below renal range – hypokalaemia is "
                       "common in CKD; supplement only per bloodwork.")
        elif per["k"] > R["k"][1]:
            out.append("• POTASSIUM above renal range – check bloodwork; "
                       "some CKD dogs run high.")
        if per["epa_dha"] < R["epa_dha"][0]:
            out.append("• EPA+DHA is very low – renal diets add long-chain "
                       "omega-3 (fish or algal oil).")
    else:
        if per["p"] > 2000:
            out.append("• Phosphorus is well above typical maintenance "
                       "levels; consider moderating even at stage 1.")

    if capr is not None and capr < R["ca_p"][0]:
        out.append(f"• Ca:P ratio {capr:.2f} is below {R['ca_p'][0]:g}:1. "
                   "Add P-free "
                   "calcium (calcium carbonate/citrate) rather than bone "
                   "meal, which also adds phosphorus.")
    if (capr is not None and capr > R["ca_p"][1]) or per["ca"] > R["ca_max"]:
        out.append(f"• CALCIUM is high (Ca:P {capr:.2f}, {per['ca']:.0f} "
                   f"mg/1000 kcal; limits {R['ca_p'][1]:g}:1 and "
                   f"{R['ca_max']:g}). In CKD blood "
                   "calcium can rise as well as fall, and high calcium "
                   "with high phosphorus promotes tissue calcification. "
                   "Reduce added calcium unless your vet advises it.")
    if t["p_bind"]:
        binders = [n for n, g in recipe if g > 0 and
                   db[n]["category"] == "binder"]
        ca_binders = [n for n in binders if
                      (db[n]["per100g"]["ca"] or 0) > 0]
        frac = min(t["p_bind"], t["p"]) / t["p"] if t["p"] else 0
        out.append(f"• Phosphate binder ({', '.join(binders)}): estimated "
                   f"to bind ≈{frac * 100:.0f}% of dietary phosphorus. "
                   "This is a human-derived estimate – the real effect is "
                   "judged by serum phosphate, rechecked every 4–6 weeks "
                   "until stable. Give with meals, at the prescribed dose.")
        if frac > 0.5:
            out.append("• The binder estimate exceeds half of dietary "
                       "phosphorus – the dose is probably high for this "
                       "diet, or the estimate overstates binding.")
        if ca_binders:
            out.append("• Calcium-based binder adds calcium (counted in Ca "
                       "and Ca:P above). Ask your vet to monitor (ionised) "
                       "calcium; a non-calcium binder is used if calcium "
                       "rises.")
        if not renal_mode:
            out.append("• A binder is usually only used from stage 2–3 "
                       "onwards, when diet alone does not keep phosphate "
                       "in the IRIS target.")
    low_b = [LABEL[k] for k in WATER_SOLUBLE if per[k] < AAFCO[k]]
    if low_b:
        out.append("• Below AAFCO minimum: " + ", ".join(low_b) +
                   ". CKD increases urinary loss of water-soluble "
                   "vitamins – renal diets are supplemented above these "
                   "minimums (B-complex).")
    for k in ("ca", "mg", "vit_a", "vit_e", "choline"):
        if per[k] < AAFCO[k]:
            out.append(f"• {LABEL[k]} below AAFCO minimum.")
    if per["vit_d"] > AAFCO_MAX["vit_d"]:
        out.append(f"• VITAMIN D {per['vit_d']:.0f} IU/1000 kcal is above "
                   "the AAFCO maximum (750). Excess vitamin D raises "
                   "calcium and phosphorus – a real risk in CKD.")
    elif per["vit_d"] < AAFCO["vit_d"]:
        out.append(f"• Vitamin D {per['vit_d']:.0f} IU/1000 kcal is below "
                   "the AAFCO minimum (125); plant foods contain almost "
                   "none. Cover it only through a vet-approved balancing "
                   "supplement – in CKD, vitamin D is managed by the vet "
                   "(calcitriol is a separate, prescribed treatment).")
    a_supps = [n for n, g in recipe if g > 0 and
               db[n]["category"] == "supplement" and
               (db[n]["per100g"]["vit_a"] or 0) > 0]
    if a_supps:
        out.append("• Vitamin A from supplements (" + ", ".join(a_supps) +
                   ") – UC Davis advises against vitamin A supplements in "
                   "renal failure.")
    if fat_frac > 0.5:
        out.append(f"• Fat provides {fat_frac * 100:.0f}% of calories. "
                   "Higher fat helps energy density and palatability but "
                   "watch for vomiting, diarrhoea, abdominal pain.")
    acid1000 = acid * k1000
    if renal_mode and acid1000 > 0:
        out.append(f"• Net acid load +{acid1000:.0f} mEq/1000 kcal "
                   "(PRAL, indicative). Renal diets are alkalinising; "
                   "potassium citrate is the usual addition if blood "
                   "bicarbonate is low.")
    if need:
        pct = kcal / need * 100
        out.append(f"• This recipe supplies {kcal:.0f} kcal = {pct:.0f}% of "
                   f"the estimated daily need ({need:.0f} kcal). "
                   f"Feed ≈ {need / kcal * mass:.0f} g/day to meet MER.")
    missing = sorted({n for k in KEYS for n in miss[k]})
    if missing:
        out.append("• Incomplete data for: " + ", ".join(missing) +
                   " – values marked ≥ are minimums.")
    out += ["", "Not checked: trace minerals (Zn, Cu, Fe, I, Se), vitamin "
            "K, biotin, essential fatty acids, amino-acid balance. A "
            "home-made renal diet should be balanced by a vet "
            "nutritionist. Never force-feed (food aversion)."]
    return "\n".join(out)


BRK_KEYS = [("kcal", "kcal"), ("protein", "protein"), ("fat", "fat"),
            ("p", "p"), ("ca", "ca"), ("na", "na"), ("k", "k"),
            ("epa", "epa_dha")]


def breakdown_rows(recipe, db, mass, t):
    """Per-ingredient contribution rows (strings) + TOTAL row."""
    rows = []
    for n, g in recipe:
        if n not in db or g <= 0:
            continue
        v = db[n]["per100g"]
        amt = {c: (None if v[k] is None else v[k] * g / 100)
               for c, k in BRK_KEYS}

        def f(x):
            return "?" if x is None else fmt(x)

        pk = (amt["kcal"] / t["kcal"] * 100
              if amt["kcal"] is not None and t["kcal"] else None)
        pp = (amt["p"] / t["p"] * 100
              if amt["p"] is not None and t["p"] else None)
        rows.append((n, fmt(g), f"{g / mass * 100:.1f}", f(amt["kcal"]),
                     "?" if pk is None else f"{pk:.0f}", f(amt["protein"]),
                     f(amt["fat"]), f(amt["p"]),
                     "?" if pp is None else f"{pp:.0f}",
                     f(amt["ca"]), f(amt["na"]), f(amt["k"]), f(amt["epa"])))
    rows.append(("TOTAL", fmt(mass), "100", fmt(t["kcal"]), "100",
                 fmt(t["protein"]), fmt(t["fat"]), fmt(t["p"]), "100",
                 fmt(t["ca"]), fmt(t["na"]), fmt(t["k"]), fmt(t["epa_dha"])))
    return rows


def analyse_recipe(recipe, db, need, stage_name, sctx=None):
    """Everything the results screens show, independent of the GUI.
    Returns dict: mass, totals, missing, summary [(name, unit, value,
    status)], rows [(values10, tag)], breakdown [13-tuples], notes."""
    renal_mode, stage_note = STAGES[stage_name]
    if sctx and "renal" in sctx:
        renal_mode = sctx["renal"]
    ranges = get_ranges(sctx)
    mass, t, miss = compute(recipe, db)
    res = {"mass": mass, "totals": t, "missing": miss, "summary": [],
           "rows": [], "breakdown": [], "score": None, "terms": {}}
    if mass <= 0:
        res["notes"] = ("Add ingredients to the recipe.\n\nStage guidance: "
                        + stage_note)
        return res
    kcal = t["kcal"]
    dm = mass - t["water"]
    k1000 = 1000.0 / kcal if kcal > 0 else None
    day = need / 1000.0 if need else None
    prot_me = 3.5 * t["protein"]
    fat_me = 8.5 * t["fat"]
    carb_me = 3.5 * max(0.0, t["carb"] - t["fibre"])
    me_sum = prot_me + fat_me + carb_me or 1
    capr = t["ca"] / t["p"] if t["p"] else None
    acid = pral(t)
    summary = [
        ("Recipe weight", "g", fmt(mass), ""),
        ("Dry matter", "g", f"{fmt(dm)}  ({dm / mass * 100:.0f}% of weight)",
         ""),
        ("Energy density", "kcal/g", f"{kcal / mass:.2f} as fed, "
                                     f"{kcal / dm:.2f} DM" if dm > 0 else
         f"{kcal / mass:.2f}", ""),
        ("Energy split (protein/fat/carb)", "% ME",
         f"{prot_me / me_sum * 100:.0f} / {fat_me / me_sum * 100:.0f} / "
         f"{carb_me / me_sum * 100:.0f}", ""),
        ("Ca : P ratio", "", fmt(capr) + f"  (target {ranges['ca_p'][0]:g}–"
         f"{ranges['ca_p'][1]:g} : 1)", ""),
        ("Phosphorus net of binder (est.)", "mg/1000 kcal",
         (fmt(net_p(t) * k1000) + f"  (binds ≈{fmt(min(t['p_bind'], t['p']))}"
          " mg)") if (t["p_bind"] and k1000) else "no binder", ""),
        ("Acid load (PRAL − added alkali)", "mEq/1000 kcal",
         fmt(acid * k1000) if k1000 else "–", ""),
        ("Energy requirement (MER)", "kcal/day", fmt(need), ""),
        ("Recipe needed to meet MER", "g/day",
         fmt(need / kcal * mass) if kcal > 0 and need else "–", ""),
    ]
    if sctx and sctx["kcal_target"] > 0:
        names = [n for n, g in recipe if n in db]
        sc, terms = score_amounts([g for n, g in recipe if n in db],
                                  [_vec(db[n]) for n in names], sctx)
        res["score"], res["terms"] = sc, terms
        top = [k for k, v in sorted(terms.items(), key=lambda kv: -kv[1])
               if v > 1e-3][:3]
        summary.insert(0, ("Score (0 = all targets met)", "", f"{sc:.3f}",
                           "gaps: " + ", ".join(top) if top
                           else "all targets met"))
    res["summary"] = summary

    for k in KEYS:
        if k in ("base_meq", "p_bind") and t[k] == 0:
            continue
        inc = "≥" if miss[k] else ""
        per100 = t[k] / mass * 100
        perdm = t[k] / dm * 100 if dm > 0 else None
        p1000 = t[k] * k1000 if k1000 else None
        pday = p1000 * day if (p1000 is not None and day) else None
        renal = (f"{ranges[k][0]:g}–{ranges[k][1]:g}" if k in RENAL else "")
        aafco = f"{AAFCO[k]:g}" if k in AAFCO else ""
        st, tag = ("", "")
        if p1000 is not None and k not in ("kcal", "p_bind"):
            st, tag = status_for(k, p1000, renal_mode, ranges)
        if miss[k]:
            st = (st + "; " if st else "") + f"data missing ({len(miss[k])})"
            if tag == "ok":
                tag = "warn"
        res["rows"].append(((LABEL[k], UNIT[k], inc + fmt(t[k]),
                             inc + fmt(per100), inc + fmt(perdm),
                             inc + fmt(p1000), inc + fmt(pday), renal, aafco,
                             st), tag))
    res["breakdown"] = breakdown_rows(recipe, db, mass, t)
    res["notes"] = assess_recipe(stage_name, recipe, db, t, miss, mass, kcal,
                                 need, capr, acid, k1000, renal_mode,
                                 stage_note, fat_me / me_sum, ranges,
                                 (sctx or {}).get("blood_note", ""))
    return res


LABEL_FIELDS = [("moist", "Moisture %"), ("protein", "Crude protein %"),
                ("fat", "Crude fat / oils %"), ("fibre", "Crude fibre %"),
                ("ash", "Crude ash %"), ("ca", "Calcium %"),
                ("p", "Phosphorus %"), ("na", "Sodium %"),
                ("k", "Potassium %"), ("mg", "Magnesium %"),
                ("epa_dha", "EPA + DHA %"), ("kcalkg", "Energy kcal/kg"),
                ("vitA_iu", "Vitamin A IU/kg"),
                ("vitD_iu", "Vitamin D3 IU/kg"),
                ("vitE_mg", "Vitamin E mg/kg (or IU/kg)"),
                ("choline_mg", "Choline mg/kg")]


def per100g_from_label(v):
    """Pet-food label (as-fed %, per-kg values; None = not stated) ->
    per-100 g nutrient dict. kcal estimated with modified Atwater factors
    if not given."""
    per = {k: None for k in KEYS}
    per.update(epa_dha=None, base_meq=0.0, p_bind=0.0)
    per["water"] = v["moist"]
    per["protein"] = v["protein"]
    per["fat"] = v["fat"]
    per["fibre"] = v["fibre"]
    core = [v[x] for x in ("moist", "protein", "fat", "fibre", "ash")]
    nfe = None
    if all(x is not None for x in core):
        nfe = max(0.0, 100 - sum(core))
        per["carb"] = nfe + v["fibre"]
    for k in ("ca", "p", "na", "k", "mg", "epa_dha"):
        if v[k] is not None:
            per[k] = v[k] * 1000.0          # % -> mg/100 g
    if v["kcalkg"] is not None:
        per["kcal"] = v["kcalkg"] / 10.0
    elif nfe is not None:
        per["kcal"] = 3.5 * v["protein"] + 8.5 * v["fat"] + 3.5 * nfe
    if v["vitA_iu"] is not None:
        per["vit_a"] = v["vitA_iu"] * 0.3 / 10.0  # IU/kg -> µg/100 g
    if v["vitD_iu"] is not None:
        per["vit_d"] = v["vitD_iu"] / 10.0        # IU/kg -> IU/100 g
    if v["vitE_mg"] is not None:      # pet-food vit E is the acetate:
        per["vit_e"] = v["vitE_mg"] / 10.0        # 1 mg = 1 IU
    if v["choline_mg"] is not None:
        per["choline"] = v["choline_mg"] / 10.0
    return per



# --------------------------------------------------------------------------
# Blood results -> stage, ranges, aims, priorities
# --------------------------------------------------------------------------
# Inputs use UK units. Thresholds: IRIS staging (creatinine, SDMA, UPC,
# blood pressure, phosphate targets by stage, bicarbonate 18-24 mmol/L);
# other cut-offs are typical canine reference intervals - labs differ, so
# the lab's own range wins. The size of each adjustment is this app's
# judgement, not a published rule. Everything here is for discussion with
# the vet, not a substitute for it.
BLOOD_FIELDS = [
    # key, label, unit, typical reference / IRIS cut-offs (text)
    ("creat", "Creatinine", "µmol/L", "IRIS: <125 st1, 125–250 st2, 251–440 st3, >440 st4"),
    ("sdma", "SDMA", "µg/dL", "IRIS: <18 st1, 18–35 st2, 36–54 st3, >54 st4"),
    ("phos", "Phosphate", "mmol/L", "IRIS target 0.9–1.5 (st1–2), <1.6 (st3), <1.9 (st4)"),
    ("upc", "Urine protein:creatinine (UPC)", "", "<0.2 normal, 0.2–0.5 borderline, >0.5 proteinuric"),
    ("urea", "Urea", "mmol/L", "typical ~2.5–9.6"),
    ("alb", "Albumin", "g/L", "typical ~23–40"),
    ("k", "Potassium", "mmol/L", "typical ~3.5–5.8"),
    ("tco2", "Bicarbonate / total CO2", "mmol/L", "IRIS target 18–24"),
    ("ica", "Ionised calcium", "mmol/L", "typical ~1.20–1.45"),
    ("tca", "Total calcium", "mmol/L", "typical ~2.2–3.0"),
    ("sbp", "Systolic blood pressure", "mmHg", "IRIS: <140 normal, 140–159 pre-, 160–179 hypertensive, ≥180 severe"),
    ("pcv", "PCV / haematocrit", "%", "typical ~37–55"),
    ("bcs", "Body condition score", "1–9", "ideal 4–5"),
]
STAGE_NAMES = {1: "Stage 1 – non-proteinuric", 2: "Stage 2", 3: "Stage 3",
               4: "Stage 4"}
PHOS_TARGET = {1: (0.9, 1.5), 2: (0.9, 1.5), 3: (0.9, 1.6), 4: (0.9, 1.9)}


def _num(x):
    try:
        return None if x is None or x == "" else float(x)
    except (TypeError, ValueError):
        return None


def adapt_from_bloods(b, current_stage="Stage 2"):
    """b: dict of BLOOD_FIELDS keys (None = not tested) plus optional
    'weight_trend' ('stable'|'losing'|'gaining') and 'date'.
    Returns dict: stage, renal_force, aims, ranges, weights, mer_delta,
    findings [(test, value, reference, finding, change)], changes
    [(target, default, adapted)], note (one line)."""
    v = {k: _num(b.get(k)) for k, *_ in BLOOD_FIELDS}
    trend = b.get("weight_trend") or "stable"
    F = []                                    # findings

    def unit(k):
        return next(u for kk, _, u, _ in BLOOD_FIELDS if kk == k)

    def ref(k):
        return next(r for kk, _, _, r in BLOOD_FIELDS if kk == k)

    def fv(k):
        return f"{v[k]:g} {unit(k)}".strip()

    # ---- stage
    st_c = st_s = None
    if v["creat"] is not None:
        c = v["creat"]
        st_c = 1 if c < 125 else 2 if c <= 250 else 3 if c <= 440 else 4
        F.append(("Creatinine", fv("creat"), ref("creat"),
                  f"IRIS stage {st_c} range", ""))
    if v["sdma"] is not None:
        sd = v["sdma"]
        st_s = 1 if sd < 18 else 2 if sd <= 35 else 3 if sd <= 54 else 4
        F.append(("SDMA", fv("sdma"), ref("sdma"), f"IRIS stage {st_s} range",
                  "SDMA higher than creatinine stage → treat as the higher "
                  "stage (IRIS)" if st_c and st_s > st_c else ""))
    if st_c or st_s:
        n = max(x for x in (st_c, st_s) if x)
    else:
        n = next((k for k, nm in STAGE_NAMES.items() if nm == current_stage),
                 1 if current_stage.startswith("Stage 1") else 2)
    proteinuric = v["upc"] is not None and v["upc"] > 0.5
    stage = ("Stage 1 – proteinuric" if n == 1 and proteinuric
             else STAGE_NAMES[n])
    renal = STAGES[stage][0]
    renal_force = False

    aims = dict(AIMS[stage]) or {}
    R = {**RENAL, **DEFAULT_LIMITS}
    W = dict(OPT_WEIGHTS)
    mer_delta = 0.0

    # ---- phosphate
    if v["phos"] is not None:
        lo_t, hi_t = PHOS_TARGET[n]
        ph = v["phos"]
        base = aims.get("p", 900)
        if ph > hi_t:
            if not renal:
                renal_force = True
                aims.setdefault("protein", 45)
            ex = ph - hi_t
            cut = 150 if ex <= 0.2 else 250 if ex <= 0.5 else 350
            aims["p"] = max(450, base - cut)
            R["p"] = (400, aims["p"] + 150)
            W["phosphorus"] *= 2
            F.append(("Phosphate", fv("phos"), f"target {lo_t}–{hi_t}",
                      f"ABOVE target by {ex:.2f}",
                      f"Phosphorus aim → {aims['p']}, max → {R['p'][1]} "
                      "mg/1000 kcal. If still above target after 4–6 weeks "
                      "the vet may add a phosphate binder."))
        elif ph < lo_t:
            aims["p"] = min(1200, base + 200)
            R["p"] = (aims["p"] - 200, 1200)
            F.append(("Phosphate", fv("phos"), f"target {lo_t}–{hi_t}",
                      "BELOW target – probably over-restricted",
                      f"Phosphorus aim → {aims['p']}, min → {R['p'][0]}."))
        else:
            F.append(("Phosphate", fv("phos"), f"target {lo_t}–{hi_t}",
                      "within target", "Keep current phosphorus."))

    # ---- protein: proteinuria -> urea -> albumin (albumin sets the floor)
    p_lo, p_hi = R["protein"]
    if v["upc"] is not None:
        u = v["upc"]
        if u > 0.5:
            aims["protein"] = min(aims.get("protein", 45), 35)
            p_hi = 45
            W["protein"] *= 1.5
            F.append(("UPC", fv("upc"), ref("upc"), "PROTEINURIC",
                      "Protein aim → 35, max → 45 g/1000 kcal; omega-3 kept "
                      "up. The vet usually adds an ACE-inhibitor/ARB."))
            R["epa_dha"] = (max(R["epa_dha"][0], 300), R["epa_dha"][1])
        elif u >= 0.2:
            F.append(("UPC", fv("upc"), ref("upc"), "borderline",
                      "No change; recheck."))
        else:
            F.append(("UPC", fv("upc"), ref("upc"), "normal", ""))
    if v["urea"] is not None and renal | renal_force:
        if v["urea"] > 15:
            aims["protein"] = max(30, aims.get("protein", 45) - 5)
            F.append(("Urea", fv("urea"), ref("urea"), "HIGH",
                      f"Protein aim → {aims['protein']} g/1000 kcal (more so "
                      "if nausea, poor appetite, ammonia breath)."))
        elif v["urea"] > 9.6:
            F.append(("Urea", fv("urea"), ref("urea"),
                      "raised – expected in CKD",
                      "No change unless uraemic signs."))
        else:
            F.append(("Urea", fv("urea"), ref("urea"), "normal", ""))
    low_alb = v["alb"] is not None and v["alb"] < 25
    if v["alb"] is not None:
        if low_alb:
            p_lo = max(p_lo, 35)
            aims["protein"] = max(aims.get("protein", 40), 40)
            F.append(("Albumin", fv("alb"), ref("alb"), "LOW",
                      "Protein min → 35, aim ≥ 40 g/1000 kcal – do not cut "
                      "protein further; check energy intake. With "
                      "proteinuria this needs the vet promptly."))
        else:
            F.append(("Albumin", fv("alb"), ref("alb"), "ok", ""))
    if trend == "losing" or (v["bcs"] is not None and v["bcs"] < 4):
        p_lo = max(p_lo, 35)
        mer_delta += 0.2
        F.append(("Weight / BCS", trend if v["bcs"] is None else
                  f"{trend}, BCS {v['bcs']:g}", "ideal BCS 4–5",
                  "losing weight / thin",
                  "MER factor +0.2, protein min → 35 g/1000 kcal."))
    elif trend == "gaining" or (v["bcs"] is not None and v["bcs"] > 6):
        mer_delta -= 0.1
        F.append(("Weight / BCS", trend if v["bcs"] is None else
                  f"{trend}, BCS {v['bcs']:g}", "ideal BCS 4–5",
                  "gaining / overweight", "MER factor −0.1."))
    if p_lo > p_hi:
        p_hi = p_lo + 10
    if "protein" in aims and aims["protein"] < p_lo + 5:
        aims["protein"] = min(p_hi, p_lo + 5)   # weight loss/low albumin win
    R["protein"] = (p_lo, p_hi)

    # ---- potassium
    if v["k"] is not None:
        if v["k"] < 3.5:
            R["k"] = (1500, R["k"][1])
            W["potassium"] *= 3
            F.append(("Potassium", fv("k"), ref("k"), "LOW",
                      "Potassium min → 1500 mg/1000 kcal. The vet may "
                      "prescribe potassium (gluconate/citrate) – add it at "
                      "that dose and lock it."))
        elif v["k"] > 5.5:
            R["k"] = (R["k"][0], 1300)
            W["potassium"] *= 3
            F.append(("Potassium", fv("k"), ref("k"), "HIGH",
                      "Potassium max → 1300 mg/1000 kcal; avoid spinach, "
                      "potato, beet greens, banana; boil and drain "
                      "vegetables; no potassium citrate."))
        else:
            F.append(("Potassium", fv("k"), ref("k"), "ok", ""))

    # ---- acid-base
    if v["tco2"] is not None:
        if v["tco2"] < 18:
            W["acid"] = 2.0
            F.append(("Bicarbonate", fv("tco2"), ref("tco2"),
                      "LOW – metabolic acidosis",
                      "Acid-load priority on (prefers alkalinising "
                      "recipes). Avoid methionine-rich supplements; the vet "
                      "may prescribe potassium citrate or sodium "
                      "bicarbonate."))
        elif v["tco2"] > 24:
            F.append(("Bicarbonate", fv("tco2"), ref("tco2"), "high",
                      "Do not add alkalinisers."))
        else:
            F.append(("Bicarbonate", fv("tco2"), ref("tco2"), "ok", ""))

    # ---- calcium (ionised preferred)
    ca_state = None
    if v["ica"] is not None:
        ca_state = "high" if v["ica"] > 1.45 else "low" if v["ica"] < 1.20 \
            else "ok"
        ca_row = ("Ionised calcium", fv("ica"), ref("ica"))
    elif v["tca"] is not None:
        ca_state = "high" if v["tca"] > 3.0 else "low" if v["tca"] < 2.2 \
            else "ok"
        ca_row = ("Total calcium", fv("tca"), ref("tca"))
    if ca_state == "high":
        R["ca_p"] = (R["ca_p"][0], 1.5)
        R["ca_max"] = 2500
        W["ca_p"] *= 2
        F.append(ca_row + ("HIGH", "Ca:P max → 1.5, Ca max → 2500 mg/1000 "
                           "kcal; cut added calcium. If on a calcium-based "
                           "binder the vet may switch; no vitamin D unless "
                           "prescribed."))
    elif ca_state == "low":
        F.append(ca_row + ("LOW", "No automatic change – discuss with the "
                           "vet (often improves once phosphate is "
                           "controlled)."))
    elif ca_state == "ok":
        F.append(ca_row + ("ok", ""))

    # ---- blood pressure
    if v["sbp"] is not None:
        if v["sbp"] >= 160:
            R["na"] = (R["na"][0], 800)
            W["sodium"] *= 3
            F.append(("Blood pressure", fv("sbp"), ref("sbp"), "HYPERTENSIVE",
                      "Sodium max → 800 mg/1000 kcal (reduce gradually). "
                      "Needs vet treatment."))
        elif v["sbp"] >= 140:
            R["na"] = (R["na"][0], 1000)
            W["sodium"] *= 2
            F.append(("Blood pressure", fv("sbp"), ref("sbp"),
                      "pre-hypertensive", "Sodium max → 1000 mg/1000 kcal."))
        else:
            F.append(("Blood pressure", fv("sbp"), ref("sbp"), "normal", ""))

    # ---- anaemia
    if v["pcv"] is not None:
        if v["pcv"] < 37:
            R["protein"] = (max(R["protein"][0], 30), R["protein"][1])
            F.append(("PCV", fv("pcv"), ref("pcv"), "LOW – anaemia",
                      "Protein min → 30; keep the vitamin/mineral supplement "
                      "(iron, B12). Treatment (e.g. EPO) is the vet's."))
        else:
            F.append(("PCV", fv("pcv"), ref("pcv"), "ok", ""))

    if not (renal or renal_force):          # stage 1 non-proteinuric
        aims = {}
    # ---- summary of changes vs defaults
    D = {**RENAL, **DEFAULT_LIMITS}
    d_aims = AIMS[stage]
    changes = []
    labels = {"protein": "Protein (g/1000 kcal)", "p": "Phosphorus (mg/1000 kcal)",
              "na": "Sodium (mg/1000 kcal)", "k": "Potassium (mg/1000 kcal)",
              "epa_dha": "EPA+DHA (mg/1000 kcal)", "ca_p": "Ca:P ratio",
              "ca_max": "Calcium max (mg/1000 kcal)"}
    for k, lab in labels.items():
        a, b2 = D[k], R[k]
        fa = f"{a[0]:g}–{a[1]:g}" if isinstance(a, tuple) else f"{a:g}"
        fb = f"{b2[0]:g}–{b2[1]:g}" if isinstance(b2, tuple) else f"{b2:g}"
        if k in ("protein", "p"):
            fa += f" (aim {d_aims[k]})" if k in d_aims else ""
            fb += f" (aim {aims[k]})" if k in aims else ""
        changes.append((lab, fa, fb))
    if W["acid"]:
        changes.append(("Acid-load priority", "off", f"{W['acid']:g}"))
    if mer_delta:
        changes.append(("MER factor", "current", f"{mer_delta:+.1f}"))
    diff = [c for c in changes if c[1] != c[2]]
    note = ("Targets adapted from blood results"
            + (f" of {b['date']}" if b.get("date") else "") + ": "
            + ("; ".join(f"{c[0].split(' (')[0]} {c[2]}" for c in diff)
               if diff else "no changes needed")
            + ". Discuss with your vet.")
    return {"stage": stage, "renal_force": renal_force, "aims": aims,
            "ranges": {k: R[k] for k in D}, "weights": W,
            "mer_delta": mer_delta, "findings": F, "changes": changes,
            "note": note}


def build_score_context(sc, stage, need):
    """Scoring ctx from saved settings `sc` (optimiser run and/or blood
    adaptation). Saved aims/ranges only apply to the stage they were made
    for."""
    sc = sc or {}
    same = sc.get("stage") == stage
    ctx = {"kcal_target": sc.get("kcal_override") or need,
           "renal": STAGES[stage][0] or bool(same and sc.get("renal_force")),
           "weights": {**OPT_WEIGHTS, **sc.get("weights", {})},
           "aims": (dict(sc["aims"]) if same and "aims" in sc
                    else dict(AIMS[stage]))}
    if same and sc.get("ranges"):
        ctx["ranges"] = {k: tuple(v) if isinstance(v, (list, tuple)) else v
                         for k, v in sc["ranges"].items()}
    if same and sc.get("blood_note"):
        ctx["blood_note"] = sc["blood_note"]
    return ctx


def store_score_context(old, ctx, stage, need):
    """Settings to keep after an optimiser/generator result is applied
    (keeps any blood adaptation for the same stage)."""
    old = old or {}
    new = {"stage": stage, "weights": dict(ctx["weights"]),
           "aims": dict(ctx["aims"])}
    if ctx.get("ranges"):
        new["ranges"] = dict(ctx["ranges"])
    if old.get("stage") == stage:
        for k in ("renal_force", "bloods", "blood_note"):
            if k in old:
                new[k] = old[k]
    if abs(ctx["kcal_target"] - need) > 1:
        new["kcal_override"] = ctx["kcal_target"]
    return new


def blood_score_context(adapt, bloods):
    """Saved settings produced by applying a blood adaptation."""
    return {"stage": adapt["stage"], "weights": dict(adapt["weights"]),
            "aims": dict(adapt["aims"]), "ranges": dict(adapt["ranges"]),
            "renal_force": adapt["renal_force"], "bloods": dict(bloods),
            "blood_note": adapt["note"]}


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------
def to_clipboard(widget, text):
    widget.clipboard_clear()
    widget.clipboard_append(text)
    widget.update()          # keep clipboard after the window closes


def make_readonly(txt):
    """Text stays selectable/copyable but cannot be edited."""
    def on_key(e):
        ctrl = e.state & 0x4
        if ctrl and e.keysym.lower() in ("c", "a"):
            return None
        if e.keysym in ("Left", "Right", "Up", "Down", "Home", "End",
                        "Prior", "Next"):
            return None
        return "break"
    txt.bind("<Key>", on_key)
    txt.bind("<<Paste>>", lambda e: "break")
    txt.bind("<<Cut>>", lambda e: "break")


def text_copy_menu(txt):
    """Ctrl+A / right-click menu (Copy, Copy all) for a Text widget."""
    def sel_all(_e=None):
        txt.tag_add("sel", "1.0", "end-1c")
        return "break"

    def copy_sel():
        try:
            to_clipboard(txt, txt.get("sel.first", "sel.last"))
        except tk.TclError:          # nothing selected -> copy everything
            to_clipboard(txt, txt.get("1.0", "end-1c"))

    m = tk.Menu(txt, tearoff=0)
    m.add_command(label="Copy", command=copy_sel)
    m.add_command(label="Copy all",
                  command=lambda: to_clipboard(txt, txt.get("1.0", "end-1c")))
    m.add_command(label="Select all", command=sel_all)
    txt.bind("<Control-a>", sel_all)
    txt.bind("<Control-A>", sel_all)
    txt.bind("<Button-3>", lambda e: (txt.focus_set(),
                                      m.tk_popup(e.x_root, e.y_root)))
    txt.bind("<Button-1>", lambda e: txt.focus_set(), add="+")


class IngredientDialog(tk.Toplevel):
    """Add / edit an ingredient, values per 100 g. Blank = unknown."""

    def __init__(self, parent, item=None):
        super().__init__(parent)
        self.title("Edit ingredient" if item else "New ingredient")
        self.transient(parent)
        self.result = None
        item = item or {"name": "", "category": "food", "note": "",
                        "per100g": {k: None for k in KEYS}}
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Name").grid(row=0, column=0, sticky="w")
        self.name = ttk.Entry(frm, width=40)
        self.name.insert(0, item["name"])
        self.name.grid(row=0, column=1, columnspan=3, sticky="we", pady=2)
        ttk.Label(frm, text="Category").grid(row=1, column=0, sticky="w")
        self.cat = ttk.Combobox(frm, values=["food", "supplement", "binder",
                                             "commercial food", "imported"])
        self.cat.set(item["category"])
        self.cat.grid(row=1, column=1, sticky="we", pady=2)
        ttk.Label(frm, text="Note").grid(row=2, column=0, sticky="w")
        self.note = ttk.Entry(frm, width=40)
        self.note.insert(0, item.get("note", ""))
        self.note.grid(row=2, column=1, columnspan=3, sticky="we", pady=2)
        ttk.Label(frm, text="Values per 100 g (leave blank if unknown)",
                  font=("TkDefaultFont", 9, "italic")).grid(
            row=3, column=0, columnspan=4, sticky="w", pady=(8, 2))

        self.entries = {}
        half = (len(KEYS) + 1) // 2
        for i, k in enumerate(KEYS):
            r, c = 4 + i % half, (i // half) * 2
            ttk.Label(frm, text=f"{LABEL[k]} ({UNIT[k]})").grid(
                row=r, column=c, sticky="w", padx=(0, 4))
            e = ttk.Entry(frm, width=12)
            v = item["per100g"].get(k)
            if v is not None:
                e.insert(0, f"{v:g}")
            e.grid(row=r, column=c + 1, sticky="w", pady=1, padx=(0, 12))
            self.entries[k] = e

        btns = ttk.Frame(frm)
        btns.grid(row=5 + half, column=0, columnspan=4, pady=(10, 0))
        ttk.Button(btns, text="Save", command=self.ok).pack(side="left",
                                                            padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(
            side="left", padx=4)
        self.grab_set()
        self.name.focus_set()

    def ok(self):
        name = self.name.get().strip()
        if not name:
            messagebox.showerror("Ingredient", "Name is required.", parent=self)
            return
        vals = {}
        for k, e in self.entries.items():
            try:
                vals[k] = to_float(e.get())
            except ValueError:
                messagebox.showerror("Ingredient",
                                     f"Invalid number for {LABEL[k]}.",
                                     parent=self)
                return
        self.result = {"name": name, "category": self.cat.get() or "food",
                       "note": self.note.get().strip(), "per100g": vals}
        self.destroy()


class LabelDialog(tk.Toplevel):
    """Create an ingredient from a pet-food label (guaranteed analysis, %)."""
    FIELDS = LABEL_FIELDS

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add from pet-food label")
        self.transient(parent)
        self.result = None
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Name").grid(row=0, column=0, sticky="w")
        self.name = ttk.Entry(frm, width=36)
        self.name.grid(row=0, column=1, sticky="we", pady=2)
        self.entries = {}
        for i, (k, lab) in enumerate(self.FIELDS, start=1):
            ttk.Label(frm, text=lab).grid(row=i, column=0, sticky="w")
            e = ttk.Entry(frm, width=12)
            e.grid(row=i, column=1, sticky="w", pady=1)
            self.entries[k] = e
        ttk.Label(frm, wraplength=330, foreground="#555",
                  text="As-fed values from the label. Blank = unknown. If "
                       "kcal/kg is missing it is estimated with modified "
                       "Atwater factors (3.5 / 8.5 / 3.5).").grid(
            row=len(self.FIELDS) + 1, column=0, columnspan=2, pady=6)
        b = ttk.Frame(frm)
        b.grid(row=len(self.FIELDS) + 2, column=0, columnspan=2)
        ttk.Button(b, text="Save", command=self.ok).pack(side="left", padx=4)
        ttk.Button(b, text="Cancel", command=self.destroy).pack(side="left",
                                                                padx=4)
        self.grab_set()

    def ok(self):
        name = self.name.get().strip()
        if not name:
            messagebox.showerror("Label", "Name is required.", parent=self)
            return
        try:
            v = {k: to_float(e.get()) for k, e in self.entries.items()}
        except ValueError:
            messagebox.showerror("Label", "Invalid number.", parent=self)
            return
        per = per100g_from_label(v)
        self.result = {"name": name, "category": "commercial food",
                       "note": "From label (as fed).", "per100g": per}
        self.destroy()


class BloodDialog(tk.Toplevel):
    """Enter blood/urine results; adapt stage, ranges, aims, priorities."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Blood results → adapted targets")
        self.transient(app)
        self.adapt = None
        prev = (app.score_ctx or {}).get("bloods") or app.bloods or {}
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        top = ttk.Frame(frm)
        top.pack(fill="x")
        ttk.Label(top, text="Test date").pack(side="left")
        self.date = tk.StringVar(value=prev.get("date", ""))
        ttk.Entry(top, textvariable=self.date, width=12).pack(side="left",
                                                              padx=4)
        ttk.Label(top, text="   Weight trend").pack(side="left")
        self.trend = ttk.Combobox(top, values=["stable", "losing", "gaining"],
                                  state="readonly", width=9)
        self.trend.set(prev.get("weight_trend", "stable"))
        self.trend.pack(side="left", padx=4)
        ttk.Label(top, foreground="#555", text="   leave blank anything not "
                  "tested · use your lab's ranges if they differ").pack(
            side="left")

        g = ttk.Frame(frm)
        g.pack(fill="x", pady=6)
        for c, h in enumerate(("Test", "Value", "Unit", "Reference / IRIS")):
            ttk.Label(g, text=h, font=("TkDefaultFont", 10, "bold")).grid(
                row=0, column=c, sticky="w", padx=4)
        self.e = {}
        for r, (k, lab, unit, ref) in enumerate(BLOOD_FIELDS, start=1):
            ttk.Label(g, text=lab).grid(row=r, column=0, sticky="w", padx=4)
            var = tk.StringVar(value="" if prev.get(k) is None
                               else f"{prev[k]:g}")
            ttk.Entry(g, textvariable=var, width=9).grid(row=r, column=1,
                                                         padx=4, pady=1)
            ttk.Label(g, text=unit).grid(row=r, column=2, sticky="w", padx=4)
            ttk.Label(g, text=ref, foreground="#555").grid(
                row=r, column=3, sticky="w", padx=4)
            self.e[k] = var

        b = ttk.Frame(frm)
        b.pack(fill="x", pady=(4, 4))
        ttk.Button(b, text="Evaluate", command=self.evaluate).pack(
            side="left")
        self.mer_too = tk.BooleanVar(value=True)
        ttk.Checkbutton(b, text="also adjust MER factor",
                        variable=self.mer_too).pack(side="left", padx=8)
        self.apply_btn = ttk.Button(b, text="Apply to targets",
                                    command=self.apply)
        self.apply_btn.pack(side="left")
        self.apply_btn.state(["disabled"])
        ttk.Button(b, text="Reset targets to defaults",
                   command=self.reset).pack(side="left", padx=6)
        ttk.Button(b, text="Close", command=self.destroy).pack(side="right")

        self.out = tk.Text(frm, height=18, wrap="word",
                           font=("TkFixedFont", 10))
        self.out.pack(fill="both", expand=True)
        make_readonly(self.out)
        text_copy_menu(self.out)
        if prev:
            self.evaluate()

    def values(self):
        d = {"date": self.date.get().strip(), "weight_trend": self.trend.get()}
        for k, var in self.e.items():
            d[k] = to_float(var.get())
        return d

    def evaluate(self):
        try:
            b = self.values()
        except ValueError:
            messagebox.showerror("Blood results", "Values must be numbers.",
                                 parent=self)
            return
        self.adapt = a = adapt_from_bloods(b, self.app.stage.get())
        self.bvals = b
        L = [f"Suggested stage: {a['stage']}"
             + ("  (renal ranges applied because of high phosphate)"
                if a["renal_force"] else ""), ""]
        if a["findings"]:
            L.append("FINDINGS")
            for t, v, ref, f, ch in a["findings"]:
                L.append(f"  {t:<16} {v:<14} {f}")
                if ch:
                    L.append(f"  {'':<16} → {ch}")
        else:
            L.append("No results entered.")
        L += ["", "TARGETS (per 1000 kcal)", f"  {'':<28} {'default':<20} "
              "adapted"]
        for lab, d0, d1 in a["changes"]:
            flag = "  *" if d0 != d1 else ""
            L.append(f"  {lab:<28} {d0:<20} {d1}{flag}")
        L += ["", "Adjustment sizes are this app's rules of thumb – review "
              "with your vet. Recheck phosphate/calcium 4–6 weeks after a "
              "change, then every 12 weeks (IRIS)."]
        self.out.delete("1.0", "end")
        self.out.insert("end", "\n".join(L))
        self.apply_btn.state(["!disabled"])

    def apply(self):
        if not self.adapt:
            return
        a, app = self.adapt, self.app
        app.bloods = dict(self.bvals)
        app.stage.set(a["stage"])
        app.score_ctx = blood_score_context(a, self.bvals)
        if self.mer_too.get() and a["mer_delta"]:
            try:
                f = float(app.factor.get().replace(",", "."))
                app.factor.set(f"{min(3.0, max(0.8, f + a['mer_delta'])):.1f}")
            except ValueError:
                pass
        app.recalc()
        messagebox.showinfo("Blood results", f"Applied: {a['stage']}.\n\n"
                            + a["note"] + "\n\nThe optimiser and generator "
                            "now use these targets.", parent=self)

    def reset(self):
        self.app.score_ctx = None
        self.app.recalc()
        messagebox.showinfo("Blood results", "Targets reset to the defaults "
                            "for the current stage.", parent=self)


class GeneratorDialog(tk.Toplevel):
    """Generate balanced recipes from the library without choosing
    ingredients first."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Generate balanced recipes")
        self.transient(app)
        self._cancel = False
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        ctx = app.score_context()

        r0 = ttk.Frame(frm)
        r0.pack(fill="x")
        ttk.Label(r0, text=f"{app.stage.get()}  –  target kcal/day").pack(
            side="left")
        self.kcal = tk.StringVar(value=f"{ctx['kcal_target']:.0f}")
        ttk.Entry(r0, textvariable=self.kcal, width=7).pack(side="left",
                                                            padx=4)
        ttk.Label(r0, text="   recipes").pack(side="left")
        self.n = tk.StringVar(value="5")
        ttk.Spinbox(r0, from_=1, to=10, textvariable=self.n, width=4).pack(
            side="left", padx=4)
        ttk.Label(r0, text="   max. ingredients each").pack(side="left")
        self.max_ing = tk.StringVar(value="6")
        ttk.Spinbox(r0, from_=3, to=9, textvariable=self.max_ing,
                    width=4).pack(side="left", padx=4)

        r1 = ttk.Frame(frm)
        r1.pack(fill="x", pady=(6, 0))
        ttk.Label(r1, text="Vegetables per recipe").pack(side="left")
        self.n_veg = tk.StringVar(value="2")
        ttk.Spinbox(r1, from_=0, to=4, textvariable=self.n_veg,
                    width=4).pack(side="left", padx=4)
        ttk.Label(r1, text="   same vegetable in max.").pack(side="left")
        self.veg_uses = tk.StringVar(value="2")
        ttk.Spinbox(r1, from_=1, to=10, textvariable=self.veg_uses,
                    width=4).pack(side="left", padx=4)
        ttk.Label(r1, text="recipes   min. g per vegetable").pack(
            side="left")
        self.veg_min = tk.StringVar(value=f"{round(0.04 * ctx['kcal_target'])}")
        ttk.Entry(r1, textvariable=self.veg_min, width=6).pack(side="left",
                                                               padx=4)

        self.use_fixed = tk.BooleanVar(value=False)
        fixed_txt = ", ".join(f"{n} {g:g} g" for n, g in app.recipe) or \
            "recipe is empty"
        ttk.Checkbutton(frm, variable=self.use_fixed,
                        text="Keep the current recipe items as a fixed base "
                             f"(e.g. breakfast kibble): {fixed_txt}").pack(
            anchor="w", pady=(8, 2))
        if not app.recipe:
            self.use_fixed.set(False)
        self.ignore_vit = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm, variable=self.ignore_vit,
                        text="Ignore vitamin minimums (A, B vitamins, folate, "
                             "choline, D, E) – I will add a vitamin "
                             "supplement").pack(
            anchor="w", pady=2)
        ttk.Label(frm, foreground="#555", wraplength=700, justify="left",
                  text="Recommended: whole eggs are the only B12 source in "
                       "the library, so without this every recipe is pushed "
                       "towards egg yolk. Home-made diets need a balancing "
                       "supplement anyway. Fat, calcium and magnesium "
                       "minimums still apply.").pack(anchor="w")

        ttk.Label(frm, foreground="#555", wraplength=700, justify="left",
                  text="Uses the priorities and aims from the last "
                       "optimiser run for this stage (or the defaults). "
                       "Roles are assigned automatically from each "
                       "ingredient's energy split. Untick anything you do "
                       "not want used (e.g. animal products). Binders are "
                       "never added.").pack(anchor="w", pady=4)

        lf = ttk.Frame(frm)
        lf.pack(fill="both", expand=True)
        self.names = sorted(
            (n for n in app.db
             if app.db[n]["per100g"]["kcal"] is not None
             and ingredient_role(app.db[n]) != "binder"),
            key=lambda n: (ROLES.index(ingredient_role(app.db[n])),
                           n.lower()))
        self.lb = tk.Listbox(lf, selectmode="multiple", height=16,
                             exportselection=False, width=70)
        sb = ttk.Scrollbar(lf, command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        for n in self.names:
            self.lb.insert("end", f"[{ingredient_role(app.db[n])}]  {n}")
        self.lb.select_set(0, "end")
        self.lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        bb = ttk.Frame(frm)
        bb.pack(fill="x", pady=2)
        ttk.Button(bb, text="All", command=lambda: self.lb.select_set(
            0, "end")).pack(side="left")
        ttk.Button(bb, text="None", command=lambda: self.lb.select_clear(
            0, "end")).pack(side="left", padx=4)

        ff = ttk.LabelFrame(frm, text="Always include (amount optimised, "
                                      "at least the minimum)", padding=6)
        ff.pack(fill="x", pady=(6, 0))
        r2 = ttk.Frame(ff)
        r2.pack(fill="x")
        self.f_pick = ttk.Combobox(r2, values=sorted(app.db, key=str.lower),
                                   width=42)
        self.f_pick.pack(side="left")
        ttk.Label(r2, text=" min g").pack(side="left")
        self.f_min = tk.StringVar(value="")
        ttk.Entry(r2, textvariable=self.f_min, width=6).pack(side="left",
                                                             padx=4)
        ttk.Button(r2, text="Add", command=self.add_forced).pack(side="left")
        ttk.Button(r2, text="Remove selected",
                   command=self.remove_forced).pack(side="left", padx=4)
        self.forced = {}
        self.f_list = tk.Listbox(ff, height=3, exportselection=False)
        self.f_list.pack(fill="x", pady=(4, 0))
        ttk.Label(ff, foreground="#555", wraplength=700, justify="left",
                  text="A forced protein, starch or vegetable fills that role "
                       "(no second one is added). Blank min = 5 g (0.5 g for "
                       "oils/supplements).").pack(anchor="w")

        bot = ttk.Frame(frm)
        bot.pack(fill="x", pady=(8, 0))
        self.run_btn = ttk.Button(bot, text="Generate", command=self.run)
        self.run_btn.pack(side="left")
        ttk.Button(bot, text="Stop", command=self.stop).pack(side="left",
                                                             padx=4)
        ttk.Button(bot, text="Close", command=self.close).pack(side="left")
        self.pb = ttk.Progressbar(bot, length=220, mode="determinate")
        self.pb.pack(side="left", padx=10)
        self.status = ttk.Label(bot, foreground="#555")
        self.status.pack(side="left")
        self.protocol("WM_DELETE_WINDOW", self.close)

    def add_forced(self):
        n = self.f_pick.get().strip()
        if n not in self.app.db:
            messagebox.showerror("Always include", "Pick an ingredient from "
                                 "the list.", parent=self)
            return
        try:
            m = to_float(self.f_min.get())
        except ValueError:
            messagebox.showerror("Always include", "Min g must be a number.",
                                 parent=self)
            return
        self.forced[n] = m
        self._refresh_forced()

    def remove_forced(self):
        for i in reversed(self.f_list.curselection()):
            self.forced.pop(list(self.forced)[i], None)
        self._refresh_forced()

    def _refresh_forced(self):
        self.f_list.delete(0, "end")
        for n, m in self.forced.items():
            self.f_list.insert("end", f"{n}  –  min "
                               + (f"{m:g} g" if m else "default"))

    def stop(self):
        self._cancel = True

    def close(self):
        self._cancel = True
        self.destroy()

    def run(self):
        app = self.app
        try:
            ctx = app.score_context()
            ctx["kcal_target"] = float(self.kcal.get())
            if self.ignore_vit.get():
                ctx["weights"]["vitamins"] = 0.0
            n = int(self.n.get())
            max_ing = int(self.max_ing.get())
            n_veg = int(self.n_veg.get())
            veg_uses = int(self.veg_uses.get())
            veg_min = to_float(self.veg_min.get()) or 0.0
        except ValueError:
            messagebox.showerror("Generate", "Check the numbers.", parent=self)
            return
        pool = [self.names[i] for i in self.lb.curselection()]
        pool += [n for n in self.forced if n not in pool]
        if len(pool) < 2:
            messagebox.showerror("Generate", "Select more ingredients.",
                                 parent=self)
            return
        fixed = [(nm, g) for nm, g in app.recipe] if self.use_fixed.get() \
            else []
        self._cancel = False
        self.run_btn.state(["disabled"])

        def progress(text, i, total):
            if not self.winfo_exists():
                return
            self.pb["maximum"] = max(1, total)
            self.pb["value"] = i
            self.status.config(text=f"{text} ({i}/{total})")
            self.update()

        try:
            res = generate_recipes(app.db, pool, ctx, n, max_ing, fixed,
                                   progress, lambda: self._cancel,
                                   n_veg=n_veg, veg_max_uses=veg_uses,
                                   veg_min_g=veg_min,
                                   forced=dict(self.forced))
        except tk.TclError:              # window closed mid-run
            return
        if not self.winfo_exists():
            return
        self.run_btn.state(["!disabled"])
        self.pb["value"] = 0
        if self._cancel:
            self.status.config(text="Stopped.")
            return
        self.status.config(text=f"Done – {len(res)} recipes.")
        if res:
            GenResultsWindow(app, ctx, res, len(fixed), set(self.forced))


class GenResultsWindow(tk.Toplevel):
    def __init__(self, app, ctx, results, n_fixed, forced=()):
        super().__init__(app)
        self.app, self.ctx, self.results = app, ctx, results
        self.forced = set(forced)
        self.title("Generated recipes")
        self.geometry("900x760")
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)
        txt = tk.Text(frm, wrap="word", font=("TkFixedFont", 10))
        sb = ttk.Scrollbar(frm, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(fill="both", expand=True)
        txt.insert("end", self.report(n_fixed))
        make_readonly(txt)
        text_copy_menu(txt)
        self.txt = txt
        b = ttk.Frame(self, padding=(8, 0, 8, 8))
        b.pack(fill="x")
        ttk.Label(b, text="Recipe #").pack(side="left")
        self.pick = tk.StringVar(value="1")
        ttk.Spinbox(b, from_=1, to=len(results), width=4,
                    textvariable=self.pick).pack(side="left")
        ttk.Button(b, text="Apply to main screen",
                   command=self.apply).pack(side="left", padx=6)
        ttk.Button(b, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Copy all", command=lambda: to_clipboard(
            self, self.txt.get("1.0", "end-1c"))).pack(side="right", padx=6)

    def report(self, n_fixed):
        db, ctx = self.app.db, self.ctx
        L = [f"{len(self.results)} recipes, best first  ({self.app.stage.get()}"
             f", {ctx['kcal_target']:.0f} kcal/day). Score 0 = every target "
             "met.", ""]
        for i, (names, g, s, terms) in enumerate(self.results, start=1):
            vecs = [_vec(db[n]) for n in names]
            kcal, per, _ = per1000_from(g, vecs)
            L.append(f"RECIPE {i}   score {s:.3f}   "
                     f"({sum(g):.0f} g/day, {kcal:.0f} kcal)")
            w = max(len(n) for n in names) + 2
            for j, (n, a) in enumerate(zip(names, g)):
                kc = (db[n]["per100g"]["kcal"] or 0) * a / 100
                tag = ("  (fixed)" if j < n_fixed else
                       "  (forced)" if n in self.forced else "")
                L.append(f"  {n:<{w}} {a:>7.1f} g  {kc:>5.0f} kcal{tag}")
            capr = per["ca"] / per["p"] if per["p"] else 0
            L.append(f"  per 1000 kcal: protein {per['protein']:.0f} g, "
                     f"P {max(0, per['p'] - per['p_bind']):.0f} mg, "
                     f"Na {per['na']:.0f}, K {per['k']:.0f} mg, "
                     f"Ca:P {capr:.2f}, EPA+DHA {per['epa_dha']:.0f} mg")
            gaps = [f"{k} {v:.3f}" for k, v in
                    sorted(terms.items(), key=lambda kv: -kv[1])[:4]
                    if v > 1e-3]
            L.append("  remaining gaps: " + (", ".join(gaps) or "none"))
            L.append("")
        if ctx["weights"].get("vitamins", 1) == 0:
            L.append("Vitamin minimums were IGNORED for these recipes – add a "
                     "vitamin supplement (B-complex incl. B12; vitamin A only "
                     "if your vet agrees). The Composition tab still shows "
                     "where each vitamin stands.\n")
        L.append("Notes: unknown nutrient values count as 0. Gaps no food can "
                 "close (often B12) need a supplement – add your product and "
                 "regenerate. Check any new diet with your vet and switch "
                 "gradually.")
        return "\n".join(L)

    def apply(self):
        try:
            i = int(self.pick.get()) - 1
            names, g, s, _ = self.results[i]
        except (ValueError, IndexError):
            return
        self.app.apply_recipe(names, g, s, f"Generated recipe #{i + 1}",
                              self.ctx, self)


def scale_to_target(recipe, db, target_kcal, fixed):
    """Scale non-fixed amounts so the day's recipe supplies target_kcal.
    Returns (new recipe, scale factor) or raises ValueError."""
    kc = {n: (db[n]["per100g"]["kcal"] or 0.0) for n, _ in recipe}
    k_fix = sum(g * kc[n] / 100 for n, g in recipe if n in fixed)
    k_free = sum(g * kc[n] / 100 for n, g in recipe if n not in fixed)
    if k_free <= 0:
        raise ValueError("No energy-providing ingredients left to scale.")
    s = (target_kcal - k_fix) / k_free
    if s <= 0:
        raise ValueError(f"The fixed items already supply {k_fix:.0f} kcal, "
                         f"more than the target {target_kcal:.0f} kcal.")
    out = []
    for n, g in recipe:
        if n in fixed:
            out.append([n, g])
        else:
            v = g * s
            out.append([n, round(v, 1) if v < 20 else round(v)])
    return out, s


class ScaleDialog(tk.Toplevel):
    """Rescale the recipe to the dog's daily energy need (body weight)."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Scale amounts to body weight")
        self.transient(app)
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        _, t, _ = compute(app.recipe, app.db)
        need = app.current_mer()
        ttk.Label(frm, text=f"Body weight {app.bw.get()} kg × MER factor "
                            f"{app.factor.get()}  →  daily need ≈ {need:.0f} "
                            f"kcal\nCurrent recipe supplies {t['kcal']:.0f} "
                            "kcal").grid(row=0, column=0, columnspan=3,
                                         sticky="w")
        ttk.Label(frm, text="Target kcal/day").grid(row=1, column=0,
                                                    sticky="w", pady=6)
        self.target = tk.StringVar(value=f"{need:.0f}")
        ttk.Entry(frm, textvariable=self.target, width=8).grid(
            row=1, column=1, sticky="w")
        ttk.Label(frm, text="Ingredient", font=("TkDefaultFont", 10,
                                                "bold")).grid(row=2, column=0,
                                                              sticky="w")
        ttk.Label(frm, text="Current g", font=("TkDefaultFont", 10,
                                               "bold")).grid(row=2, column=1)
        ttk.Label(frm, text="Keep fixed", font=("TkDefaultFont", 10,
                                                "bold")).grid(row=2, column=2)
        self.fix = {}
        for r, (n, g) in enumerate(app.recipe, start=3):
            binder = app.db[n]["category"] == "binder"
            var = tk.BooleanVar(value=binder)
            ttk.Label(frm, text=n).grid(row=r, column=0, sticky="w", padx=4)
            ttk.Label(frm, text=f"{g:g}").grid(row=r, column=1, padx=4)
            cb = ttk.Checkbutton(frm, variable=var)
            cb.grid(row=r, column=2)
            if binder:
                cb.state(["disabled"])
            self.fix[n] = var
        r = len(app.recipe) + 3
        ttk.Label(frm, foreground="#555", wraplength=480, justify="left",
                  text="Everything not fixed is scaled by the same factor, so "
                       "the proportions (and the per-1000 kcal analysis) stay "
                       "the same. Tick e.g. the breakfast kibble to keep it at "
                       "its set amount. If she is over- or underweight use her "
                       "ideal weight; in CKD weigh her regularly and adjust "
                       "the MER factor to keep weight stable.").grid(
            row=r, column=0, columnspan=3, sticky="w", pady=8)
        b = ttk.Frame(frm)
        b.grid(row=r + 1, column=0, columnspan=3)
        ttk.Button(b, text="Scale", command=self.apply).pack(side="left",
                                                             padx=4)
        ttk.Button(b, text="Cancel", command=self.destroy).pack(side="left",
                                                                padx=4)
        self.grab_set()

    def apply(self):
        try:
            target = float(self.target.get().replace(",", "."))
            fixed = {n for n, v in self.fix.items() if v.get()}
            new, s = scale_to_target(self.app.recipe, self.app.db, target,
                                     fixed)
        except ValueError as e:
            messagebox.showerror("Scale", str(e), parent=self)
            return
        self.app.recipe = new
        self.app.refresh_recipe()
        self.destroy()
        messagebox.showinfo("Scale", f"Scaled by ×{s:.2f} to {target:.0f} "
                            "kcal/day.")


class OptimiseDialog(tk.Toplevel):
    """Set bounds, priorities and aims; run the optimiser."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Optimise recipe")
        self.transient(app)
        stage = app.stage.get()
        ctx0 = app.score_context()
        self.renal = ctx0["renal"]
        self.ranges = ctx0.get("ranges", {})
        R0 = get_ranges(ctx0)
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        top = ttk.Frame(frm)
        top.pack(fill="x")
        ttk.Label(top, text=f"{stage}  –  target energy (kcal/day)").pack(
            side="left")
        self.kcal = tk.StringVar(value=f"{app.current_mer():.0f}")
        ttk.Entry(top, textvariable=self.kcal, width=8).pack(side="left",
                                                             padx=4)
        ttk.Label(top, foreground="#555",
                  text="default = MER; covers the whole day, so lock "
                       "breakfast kibble if it is in the recipe").pack(
            side="left")

        ing = ttk.LabelFrame(frm, text="Recipe ingredients (g/day)",
                             padding=6)
        ing.pack(fill="x", pady=6)
        for c, h in enumerate(("Ingredient", "Current", "Min", "Max",
                               "Lock at current")):
            ttk.Label(ing, text=h, font=("TkDefaultFont", 10, "bold")).grid(
                row=0, column=c, sticky="w", padx=4)
        self.rows = []
        for r, (n, g) in enumerate(app.recipe, start=1):
            lo, hi = default_bounds(app.db[n], app.current_mer())
            vmin = tk.StringVar(value=f"{lo:g}")
            vmax = tk.StringVar(value=f"{max(hi, g):g}")
            is_binder = app.db[n]["category"] == "binder"
            lk = tk.BooleanVar(value=is_binder)
            ttk.Label(ing, text=n + ("  (binder – vet dose, locked)"
                                     if is_binder else "")).grid(
                row=r, column=0, sticky="w", padx=4)
            ttk.Label(ing, text=f"{g:g}").grid(row=r, column=1, sticky="e",
                                               padx=4)
            ttk.Entry(ing, textvariable=vmin, width=7).grid(row=r, column=2,
                                                            padx=4)
            ttk.Entry(ing, textvariable=vmax, width=7).grid(row=r, column=3,
                                                            padx=4)
            cbt = ttk.Checkbutton(ing, variable=lk)
            cbt.grid(row=r, column=4)
            if is_binder:
                cbt.state(["disabled"])
            self.rows.append((n, g, vmin, vmax, lk))

        wf = ttk.LabelFrame(frm, text="Priorities (higher = more important;"
                                      " 0 = ignore)", padding=6)
        wf.pack(fill="x", pady=4)
        self.w = {}
        for i, (k, v) in enumerate(ctx0["weights"].items()):
            r, c = (i // 5) * 2, i % 5
            ttk.Label(wf, text=WEIGHT_LABELS.get(k, k)).grid(row=r, column=c,
                                                      sticky="w", padx=6)
            var = tk.StringVar(value=f"{v:g}")
            ttk.Entry(wf, textvariable=var, width=7).grid(
                row=r + 1, column=c, sticky="w", padx=6, pady=(0, 4))
            self.w[k] = var

        self.aims = {}
        if self.renal:
            af = ttk.LabelFrame(frm, text="Aims per 1000 kcal (editable; "
                                          + ("adapted from blood results"
                                             if self.ranges else
                                             "defaults inside the ACVN range")
                                          + ")", padding=6)
            af.pack(fill="x", pady=4)
            for c, k in enumerate(("protein", "p")):
                ttk.Label(af, text=f"{LABEL[k]} ({UNIT[k]}), range "
                                   f"{R0[k][0]:g}–{R0[k][1]:g}").grid(
                    row=0, column=c * 2, sticky="w", padx=6)
                var = tk.StringVar(value=f"{ctx0['aims'].get(k, ''):}")
                ttk.Entry(af, textvariable=var, width=8).grid(
                    row=0, column=c * 2 + 1, padx=6)
                self.aims[k] = var

        sf = ttk.LabelFrame(frm, text="Suggest additional ingredients",
                            padding=6)
        sf.pack(fill="both", expand=True, pady=4)
        row = ttk.Frame(sf)
        row.pack(fill="x")
        self.do_suggest = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="Test additions from the library",
                        variable=self.do_suggest).pack(side="left")
        ttk.Label(row, text="   max. to combine").pack(side="left")
        self.max_add = tk.StringVar(value="3")
        ttk.Spinbox(row, from_=1, to=6, textvariable=self.max_add,
                    width=4).pack(side="left", padx=4)
        ttk.Button(row, text="All", command=lambda: self.cand.select_set(
            0, "end")).pack(side="right")
        ttk.Button(row, text="None", command=lambda: self.cand.select_clear(
            0, "end")).pack(side="right", padx=4)
        ttk.Label(sf, foreground="#555",
                  text="Candidates (click to include/exclude, e.g. untick "
                       "animal products):").pack(anchor="w", pady=(4, 0))
        self.cand_names = sorted(
            (n for n in app.db if n not in dict(app.recipe)
             and app.db[n]["category"] != "binder"
             and app.db[n]["per100g"]["kcal"] is not None), key=str.lower)
        self.cand = tk.Listbox(sf, selectmode="multiple", height=9,
                               exportselection=False)
        for n in self.cand_names:
            self.cand.insert("end", n)
        self.cand.select_set(0, "end")
        self.cand.pack(fill="both", expand=True)

        bot = ttk.Frame(frm)
        bot.pack(fill="x", pady=(8, 0))
        self.run_btn = ttk.Button(bot, text="Run optimisation",
                                  command=self.run)
        self.run_btn.pack(side="left")
        ttk.Button(bot, text="Close", command=self.destroy).pack(side="left",
                                                                 padx=6)
        self.status = ttk.Label(bot, foreground="#555")
        self.status.pack(side="left", padx=10)

    def run(self):
        app = self.app
        try:
            ctx = {"kcal_target": float(self.kcal.get()),
                   "renal": self.renal, "ranges": dict(self.ranges),
                   "weights": {k: float(v.get()) for k, v in self.w.items()},
                   "aims": {k: to_float(v.get()) for k, v in
                            self.aims.items()}}
            ctx["aims"] = {k: v for k, v in ctx["aims"].items() if v}
            names, bounds, x0 = [], [], []
            for n, g, vmin, vmax, lk in self.rows:
                lo, hi = float(vmin.get()), float(vmax.get())
                if lo > hi:
                    raise ValueError(f"Min > max for {n}")
                names.append(n)
                bounds.append((lo, hi, lk.get()))
                x0.append(g)
            max_add = int(self.max_add.get())
        except ValueError as e:
            messagebox.showerror("Optimise", f"Check the inputs:\n{e}",
                                 parent=self)
            return
        if ctx["kcal_target"] <= 0 or not names:
            messagebox.showerror("Optimise", "Need a recipe and a positive "
                                 "energy target.", parent=self)
            return
        self.run_btn.state(["disabled"])
        vecs = [_vec(app.db[n]) for n in names]
        before = score_amounts(x0, vecs, ctx)

        def progress(i, total, name):
            self.status.config(text=f"Testing {i + 1}/{total}: {name}")
            self.update()

        try:
            if self.do_suggest.get():
                cands = [self.cand_names[i] for i in self.cand.curselection()]
                base, singles, combo = suggest_additions(
                    names, app.db, bounds, x0, ctx, cands, max_add, progress)
            else:
                self.status.config(text="Optimising…")
                self.update()
                base, singles, combo = (optimise(names, app.db, bounds, x0,
                                                 ctx), [], None)
        finally:
            if self.winfo_exists():
                self.run_btn.state(["!disabled"])
                self.status.config(text="Done.")
        ResultsWindow(app, ctx, names, x0, before, base, singles, combo)


class ResultsWindow(tk.Toplevel):
    def __init__(self, app, ctx, names, x0, before, base, singles, combo):
        super().__init__(app)
        self.app = app
        self.title("Optimisation results")
        self.geometry("980x760")
        self.names, self.base, self.singles, self.combo = (names, base,
                                                           singles, combo)
        self.ctx = ctx
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)
        txt = tk.Text(frm, wrap="word", font=("TkFixedFont", 10))
        sb = ttk.Scrollbar(frm, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(fill="both", expand=True)
        txt.insert("end", self.report(ctx, x0, before))
        make_readonly(txt)
        text_copy_menu(txt)
        self.txt = txt

        b = ttk.Frame(self, padding=(8, 0, 8, 8))
        b.pack(fill="x")
        ttk.Button(b, text="Apply optimised amounts",
                   command=lambda: self.apply(names, base[0], base[1],
                                              "Optimised recipe")).pack(
            side="left")
        if combo and combo[4]:
            ttk.Button(b, text="Apply best combination",
                       command=lambda: self.apply(
                           combo[0], combo[1], combo[2],
                           "Optimised + " + ", ".join(combo[4]))).pack(
                side="left", padx=6)
        if singles:
            ttk.Label(b, text="  Single addition #").pack(side="left")
            self.pick = tk.StringVar(value="1")
            ttk.Spinbox(b, from_=1, to=len(singles), width=4,
                        textvariable=self.pick).pack(side="left")
            ttk.Button(b, text="Apply", command=self.apply_single).pack(
                side="left", padx=4)
        ttk.Button(b, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Copy all", command=lambda: to_clipboard(
            self, self.txt.get("1.0", "end-1c"))).pack(side="right", padx=6)

    def report(self, ctx, x0, before):
        db = self.app.db
        names, (g, s, terms) = self.names, self.base
        L = []
        L.append(f"Score (0 = every target met): current {before[0]:.3f} → "
                 f"optimised {s:.3f}")
        L.append(f"Energy target: {ctx['kcal_target']:.0f} kcal/day\n")
        L.append("OPTIMISED DAILY AMOUNTS")
        w = max(len(n) for n in names) + 2
        for n, a, b in zip(names, x0, g):
            L.append(f"  {n:<{w}} {a:>7.1f} g → {b:>7.1f} g")
        dropped = [n for n, b in zip(names, g) if b < 0.1]
        if dropped:
            L.append("  (0 g = the optimiser would leave these out: "
                     + ", ".join(dropped) + ")")
        L.append("")
        L += self.metrics(names, g, ctx)
        L.append("\nREMAINING GAPS (largest first)")
        L += self.gaps(terms)

        if self.singles:
            L.append("\nSUGGESTED ADDITIONS – each tested alone, all amounts "
                     "re-optimised")
            for i, (c, gg, ss, tt) in enumerate(self.singles[:10], start=1):
                pct = (1 - ss / s) * 100 if s > 0 else 0
                why = ", ".join(improvement_reasons(terms, tt)) or "–"
                L.append(f"  {i:>2}. + {gg[-1]:.1f} g {c}  → score {ss:.3f} "
                         f"(−{pct:.0f}%)   improves: {why}")
        elif self.combo is not None:
            L.append("\nNo single library ingredient improved the score by "
                     "≥2%.")

        if self.combo and self.combo[4]:
            cn, cg, cs, ct, added = self.combo
            L.append(f"\nBEST COMBINATION (adds {', '.join(added)})  → "
                     f"score {cs:.3f}")
            w2 = max(len(n) for n in cn) + 2
            for n, a in zip(cn, cg):
                tag = "  (new)" if n in added else ""
                L.append(f"  {n:<{w2}} {a:>7.1f} g{tag}")
            L.append("")
            L += self.metrics(cn, cg, ctx)
            L.append("\nREMAINING GAPS")
            L += self.gaps(ct)
        L.append("\nNOTES\n  • Unknown nutrient values count as 0 here, so "
                 "items with missing data can look better than they are.\n"
                 "  • Gaps that no food in the library can close (often B12, "
                 "vitamin A, Ca on plant-based recipes) point to a supplement "
                 "– add your product via New/From label and re-run.\n"
                 "  • Aims are this app's editable defaults inside the ACVN "
                 "range, not published targets. Check any change with your "
                 "vet, and switch foods gradually.")
        return "\n".join(L)

    def metrics(self, names, g, ctx):
        vecs = [_vec(self.app.db[n]) for n in names]
        kcal, per, t = per1000_from(g, vecs)
        rows = [f"Per 1000 kcal  ({kcal:.0f} kcal/day, {sum(g):.0f} g/day):"]
        for k in ("protein", "p", "na", "k", "ca", "epa_dha"):
            R = get_ranges(ctx)
            st, _ = status_for(k, per[k], ctx["renal"], R)
            rng = (f"renal {R[k][0]:g}–{R[k][1]:g}" if ctx["renal"] and
                   k in RENAL else f"AAFCO ≥{AAFCO.get(k, '–')}")
            rows.append(f"  {LABEL[k]:<12} {per[k]:>8.1f} {UNIT[k]:<4} "
                        f"[{rng}]  {st}")
        if per["p_bind"]:
            pe = max(0.0, per["p"] - per["p_bind"])
            rows.append(f"  P net of binder (est.) {pe:>8.1f} mg")
        if per["p"]:
            rows.append(f"  Ca:P ratio   {per['ca'] / per['p']:>8.2f}      "
                        f"[1–2]")
        return rows

    @staticmethod
    def gaps(terms):
        items = sorted(terms.items(), key=lambda kv: -kv[1])
        return ([f"  {k:<26} {v:.3f}" for k, v in items[:8] if v > 1e-4]
                or ["  none – all targets met"])

    def apply(self, names, g, score, label):
        self.app.apply_recipe(names, g, score, label, self.ctx, self)

    def apply_single(self):
        try:
            i = int(self.pick.get()) - 1
            c, g, s, t = self.singles[i]
        except (ValueError, IndexError):
            return
        self.apply(self.names + [c], g, s, f"Optimised + {c}")


class App(tk.Tk):
    RES_COLS = [("nutrient", "Nutrient", 230), ("unit", "Unit", 90),
                ("total", "Recipe total", 170), ("per100", "/100 g fed", 95),
                ("dm", "/100 g DM", 95), ("per1000", "/1000 kcal", 100),
                ("day", "Per day", 90), ("renal", "Renal range", 110),
                ("aafco", "AAFCO min", 100), ("status", "Status", 260)]

    BRK_COLS = [("ing", "Ingredient", 260), ("g", "g", 75),
                ("pw", "% weight", 75), ("kcal", "kcal", 70),
                ("pk", "% kcal", 70), ("protein", "Protein g", 85),
                ("fat", "Fat g", 70), ("p", "P mg", 75), ("pp", "% of P", 70),
                ("ca", "Ca mg", 75), ("na", "Na mg", 70), ("k", "K mg", 70),
                ("epa", "EPA+DHA mg", 95)]

    def __init__(self):
        super().__init__()
        self.title("Renal Diet Composition Calculator (dogs)")
        self.geometry("1500x860")
        self._style()
        self.db = load_db()
        self.recipe = []            # list of [name, grams]
        self.score_ctx = None       # settings from the last optimiser run
        self.recipe_note = ""       # e.g. "Optimised recipe – score 0.29"
        self.applied_recipe = None  # snapshot of the applied recipe
        self.bloods = {}            # last blood results entered
        self._build()
        self.refresh_list()
        self.recalc()

    # ---------------- layout
    def _style(self):
        """Size table rows from the real font height so text is never
        clipped on high-DPI / scaled displays."""
        st = ttk.Style(self)
        fonts = [tkfont.nametofont(n) for n in
                 ("TkDefaultFont", "TkTextFont", "TkHeadingFont")]
        line = max(f.metrics("linespace") for f in fonts)
        st.configure("Treeview", rowheight=int(line * 1.45))
        st.configure("Treeview.Heading", padding=(4, 4))

    def _build(self):
        top = ttk.Frame(self, padding=(8, 6))
        top.pack(fill="x")
        ttk.Label(top, text="Body weight (kg)").pack(side="left")
        self.bw = tk.StringVar(value="6")
        ttk.Entry(top, textvariable=self.bw, width=6).pack(side="left",
                                                           padx=(2, 12))
        ttk.Label(top, text="MER factor (× 70·BW^0.75)").pack(side="left")
        self.factor = tk.StringVar(value="1.6")
        ttk.Entry(top, textvariable=self.factor, width=5).pack(side="left",
                                                               padx=(2, 12))
        ttk.Label(top, text="IRIS stage").pack(side="left")
        self.stage = tk.StringVar(value="Stage 2")
        cb = ttk.Combobox(top, textvariable=self.stage, values=list(STAGES),
                          state="readonly", width=26)
        cb.pack(side="left", padx=(2, 12))
        cb.bind("<<ComboboxSelected>>", lambda e: self.recalc())
        for var in (self.bw, self.factor):
            var.trace_add("write", lambda *a: self.recalc())
        ttk.Button(top, text="Export results CSV",
                   command=self.export_results).pack(side="right")
        ttk.Button(top, text="Copy results",
                   command=lambda: self.copy_table(False, notes=True)).pack(
            side="right", padx=6)

        pw = ttk.PanedWindow(self, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=6, pady=4)

        # ---- left: ingredient library + recipe
        left = ttk.Frame(pw, padding=4)
        pw.add(left, weight=1)
        lib = ttk.LabelFrame(left, text="Ingredient library", padding=4)
        lib.pack(fill="both", expand=True)
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *a: self.refresh_list())
        ttk.Entry(lib, textvariable=self.search).pack(fill="x")
        self.lib_list = tk.Listbox(lib, height=14, exportselection=False)
        self.lib_list.pack(fill="both", expand=True, pady=3)
        self.lib_list.bind("<Double-Button-1>", lambda e: self.add_to_recipe())
        self.lib_list.bind("<<ListboxSelect>>", self.show_note)
        self.note_lbl = ttk.Label(lib, foreground="#555", wraplength=380)
        self.note_lbl.pack(fill="x")
        row = ttk.Frame(lib)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="Amount (g)").pack(side="left")
        self.amount = tk.StringVar(value="100")
        ttk.Entry(row, textvariable=self.amount, width=8).pack(side="left",
                                                               padx=4)
        ttk.Button(row, text="Add to recipe →",
                   command=self.add_to_recipe).pack(side="left")
        r2 = ttk.Frame(lib)
        r2.pack(fill="x")
        for txt, cmd in [("New", self.new_ing), ("Edit", self.edit_ing),
                         ("Delete", self.delete_ing),
                         ("From label…", self.label_ing)]:
            ttk.Button(r2, text=txt, command=cmd).pack(side="left", padx=1)
        r3 = ttk.Frame(lib)
        r3.pack(fill="x", pady=(2, 0))
        for txt, cmd in [("Import CSV/JSON", self.import_db),
                         ("CSV template", self.export_template),
                         ("Export library", self.export_db)]:
            ttk.Button(r3, text=txt, command=cmd).pack(side="left", padx=1)

        rec = ttk.LabelFrame(left, text="Recipe (double-click to change grams)",
                             padding=4)
        rec.pack(fill="both", expand=True, pady=(6, 0))
        self.rec_tree = ttk.Treeview(rec, columns=("g", "kcal"), height=10)
        self.rec_tree.heading("#0", text="Ingredient")
        self.rec_tree.heading("g", text="g")
        self.rec_tree.heading("kcal", text="kcal")
        self.rec_tree.column("#0", width=200, stretch=True)
        self.rec_tree.column("g", width=60, anchor="e", stretch=False)
        self.rec_tree.column("kcal", width=60, anchor="e", stretch=False)
        self.rec_tree.pack(fill="both", expand=True)
        self.rec_tree.bind("<Double-Button-1>", lambda e: self.edit_amount())
        r4 = ttk.Frame(rec)
        r4.pack(fill="x", pady=3)
        ttk.Button(rec, text="🩸  Blood results → adapt targets…",
                   command=lambda: BloodDialog(self)).pack(fill="x",
                                                           pady=(4, 0))
        ttk.Button(rec, text="✨  Generate balanced recipes from library…",
                   command=self.open_generator).pack(fill="x", pady=(4, 0))
        ttk.Button(rec, text="⚖  Scale amounts to body weight…",
                   command=self.open_scale).pack(fill="x", pady=(4, 0))
        ttk.Button(rec, text="⚙  Optimise amounts & suggest additions…",
                   command=self.open_optimiser).pack(fill="x", pady=(4, 0))
        for txt, cmd in [("Change g", self.edit_amount),
                         ("Remove", self.remove_item), ("Clear", self.clear),
                         ("Save recipe", self.save_recipe),
                         ("Load recipe", self.load_recipe)]:
            ttk.Button(r4, text=txt, command=cmd).pack(side="left", padx=1)

        # ---- right: results
        right = ttk.Frame(pw, padding=4)
        pw.add(right, weight=3)
        self.info_lbl = ttk.Label(right, foreground="#1b5e20",
                                  font=("TkDefaultFont", 11, "bold"))
        self.info_lbl.pack(fill="x", pady=(0, 4))
        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill="both", expand=True)
        comp = ttk.Frame(self.tabs)
        brk = ttk.Frame(self.tabs)
        self.tabs.add(comp, text="Composition")
        self.tabs.add(brk, text="Ingredient breakdown")

        bcols = [c for c, _, _ in self.BRK_COLS]
        self.brk = ttk.Treeview(brk, columns=bcols, show="headings")
        for c, t, w in self.BRK_COLS:
            self.brk.heading(c, text=t)
            self.brk.column(c, width=w, anchor="w" if c == "ing" else "e")
        self.brk.tag_configure("head", background="#eef2f7")
        self.brk.pack(fill="both", expand=True)
        ttk.Label(brk, foreground="#555", text="What each ingredient "
                  "contributes to the recipe. '?' = value unknown for that "
                  "ingredient.").pack(anchor="w", pady=2)
        self._tree_copy(self.brk, self.BRK_COLS)

        cols = [c for c, _, _ in self.RES_COLS]
        self.res = ttk.Treeview(comp, columns=cols, show="headings",
                                height=24)
        for c, t, w in self.RES_COLS:
            self.res.heading(c, text=t.replace("\n", " "))
            self.res.column(c, width=w, anchor="w" if c in (
                "nutrient", "status", "unit") else "e")
        self.res.tag_configure("ok", foreground="#1b7a1b")
        self.res.tag_configure("warn", foreground="#b36b00")
        self.res.tag_configure("bad", foreground="#c0392b")
        self.res.tag_configure("head", background="#eef2f7")
        self.res.pack(fill="both", expand=True)
        nb = ttk.LabelFrame(right, text="Assessment & notes", padding=4)
        nb.pack(fill="both", expand=False, pady=(6, 0))
        self.notes = tk.Text(nb, height=13, wrap="word", font=(
            "TkDefaultFont", 10))
        self.notes.pack(fill="both", expand=True)
        make_readonly(self.notes)
        text_copy_menu(self.notes)

        # copy from the results table (tab-separated -> pastes into Excel)
        self._tree_copy(self.res, self.RES_COLS, with_notes=True)

    def _tree_copy(self, tree, cols, with_notes=False):
        menu = tk.Menu(tree, tearoff=0)
        menu.add_command(label="Copy selected rows",
                         command=lambda: self.copy_tree(tree, cols, True))
        menu.add_command(label="Copy whole table",
                         command=lambda: self.copy_tree(tree, cols, False))
        if with_notes:
            menu.add_command(label="Copy table + notes",
                             command=lambda: self.copy_table(False, True))

        def popup(e):
            row = tree.identify_row(e.y)
            if row and row not in tree.selection():
                tree.selection_set(row)
            menu.tk_popup(e.x_root, e.y_root)
        tree.bind("<Button-3>", popup)
        tree.bind("<Control-c>", lambda e: self.copy_tree(tree, cols, True))
        tree.bind("<Control-C>", lambda e: self.copy_tree(tree, cols, True))
        tree.bind("<Control-a>", lambda e: tree.selection_set(
            tree.get_children()))

    # ---------------- library actions
    def refresh_list(self):
        q = self.search.get().lower().strip()
        self.lib_list.delete(0, "end")
        self._shown = sorted((n for n in self.db if q in n.lower()),
                             key=lambda n: (self.db[n]["category"] != "food",
                                            n.lower()))
        for n in self._shown:
            cat = self.db[n]["category"]
            self.lib_list.insert("end", n if cat == "food" else f"{n}  [{cat}]")

    def selected_lib(self):
        sel = self.lib_list.curselection()
        return self._shown[sel[0]] if sel else None

    def show_note(self, _e=None):
        n = self.selected_lib()
        if n:
            item = self.db[n]
            unk = [LABEL[k] for k in KEYS if item["per100g"][k] is None]
            txt = item.get("note", "")
            if unk:
                txt += ("  " if txt else "") + "Unknown: " + ", ".join(unk)
            self.note_lbl.config(text=txt)

    def _store(self, item, old_name=None):
        if old_name and old_name != item["name"]:
            self.db.pop(old_name, None)
            for r in self.recipe:
                if r[0] == old_name:
                    r[0] = item["name"]
        self.db[item["name"]] = normalise(item)
        save_db(self.db)
        self.refresh_list()
        self.refresh_recipe()

    def new_ing(self):
        d = IngredientDialog(self)
        self.wait_window(d)
        if d.result:
            if d.result["name"] in self.db and not messagebox.askyesno(
                    "Overwrite", f"'{d.result['name']}' exists. Overwrite?"):
                return
            self._store(d.result)

    def edit_ing(self):
        n = self.selected_lib()
        if not n:
            return
        d = IngredientDialog(self, self.db[n])
        self.wait_window(d)
        if d.result:
            self._store(d.result, old_name=n)

    def label_ing(self):
        d = LabelDialog(self)
        self.wait_window(d)
        if d.result:
            self._store(d.result)

    def delete_ing(self):
        n = self.selected_lib()
        if n and messagebox.askyesno("Delete", f"Delete '{n}' from library?"):
            self.db.pop(n)
            self.recipe = [r for r in self.recipe if r[0] != n]
            save_db(self.db)
            self.refresh_list()
            self.refresh_recipe()

    def import_db(self):
        path = filedialog.askopenfilename(filetypes=[
            ("CSV or JSON", "*.csv *.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            items = []
            if path.lower().endswith(".json"):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                items = data if isinstance(data, list) else [data]
            else:
                with open(path, newline="", encoding="utf-8-sig") as f:
                    for row in csv.DictReader(f):
                        row = {(k or "").strip().lower(): v
                               for k, v in row.items()}
                        nm = (row.get("name") or "").strip()
                        if not nm or nm.startswith("#"):
                            continue
                        per = {k: (0.0 if (k in OPTIONAL_ZERO and k not in row)
                                   else to_float(row.get(k, "") or ""))
                               for k in KEYS}
                        items.append({"name": row["name"].strip(),
                                      "category": (row.get("category") or
                                                   "imported").strip(),
                                      "note": (row.get("note") or "").strip(),
                                      "per100g": per})
            new = sum(1 for i in items if i["name"] not in self.db)
            for i in items:
                self.db[str(i["name"]).strip()] = normalise(i)
            save_db(self.db)
            self.refresh_list()
            self.recalc()
            messagebox.showinfo("Import", f"Imported {len(items)} "
                                f"({new} new, {len(items) - new} updated).")
        except (OSError, ValueError, KeyError) as e:
            messagebox.showerror("Import", f"Import failed:\n{e}")

    def export_template(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            initialfile="ingredients_template.csv")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "category", "note"] + KEYS)
            w.writerow(["# units per 100 g ->", "", ""] +
                       [UNIT[k] for k in KEYS])
            ex = self.db.get("Lentils, boiled")
            if ex:
                w.writerow([ex["name"] + " (example)", ex["category"], ""] +
                           ["" if ex["per100g"][k] is None else
                            ex["per100g"][k] for k in KEYS])
        messagebox.showinfo("Template", "Template saved. Delete the units "
                            "row and example before importing (rows whose "
                            "name starts with '#' are skipped anyway).")

    def export_db(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            initialfile="ingredient_library.csv")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "category", "note"] + KEYS)
            for n in sorted(self.db, key=str.lower):
                it = self.db[n]
                w.writerow([n, it["category"], it.get("note", "")] +
                           ["" if it["per100g"][k] is None else
                            it["per100g"][k] for k in KEYS])

    # ---------------- recipe actions
    def add_to_recipe(self):
        n = self.selected_lib()
        if not n:
            return
        try:
            g = float(self.amount.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Amount", "Enter grams as a number.")
            return
        for r in self.recipe:
            if r[0] == n:
                r[1] += g
                break
        else:
            self.recipe.append([n, g])
        self.refresh_recipe()

    def refresh_recipe(self):
        self.rec_tree.delete(*self.rec_tree.get_children())
        for i, (n, g) in enumerate(self.recipe):
            kc = self.db[n]["per100g"]["kcal"] if n in self.db else None
            self.rec_tree.insert("", "end", iid=str(i), text=n, values=(
                f"{g:g}", "?" if kc is None else f"{kc * g / 100:.0f}"))
        self.recalc()

    def _sel_recipe(self):
        sel = self.rec_tree.selection()
        return int(sel[0]) if sel else None

    def edit_amount(self):
        i = self._sel_recipe()
        if i is None:
            return
        g = simpledialog.askfloat("Amount", f"Grams of {self.recipe[i][0]}:",
                                  initialvalue=self.recipe[i][1],
                                  minvalue=0, parent=self)
        if g is not None:
            self.recipe[i][1] = g
            self.refresh_recipe()

    def remove_item(self):
        i = self._sel_recipe()
        if i is not None:
            self.recipe.pop(i)
            self.refresh_recipe()

    def clear(self):
        self.recipe = []
        self.refresh_recipe()

    def save_recipe(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            initialfile="recipe.json")
        if path:
            d = {"items": self.recipe, "bw": self.bw.get(),
                 "factor": self.factor.get(), "stage": self.stage.get(),
                 "note": self.recipe_note}
            if self.score_ctx:
                d["optimiser"] = self.score_ctx
            with open(path, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=1, ensure_ascii=False)
            if self.recipe == self.applied_recipe or not self.recipe_note:
                base = (self.recipe_note or "Recipe").split(" – saved as")[0]
                self.recipe_note = base + f" – saved as {os.path.basename(path)}"
                self.applied_recipe = [list(r) for r in self.recipe]
            self.recalc()

    def load_recipe(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        missing = [n for n, _ in d.get("items", []) if n not in self.db]
        self.recipe = [[n, float(g)] for n, g in d.get("items", [])
                       if n in self.db]
        self.bw.set(d.get("bw", self.bw.get()))
        self.factor.set(d.get("factor", self.factor.get()))
        if d.get("stage") in STAGES:
            self.stage.set(d["stage"])
        self.score_ctx = d.get("optimiser")
        self.recipe_note = f"Loaded {os.path.basename(path)}" + (
            f" – {d['note']}" if d.get("note") else "")
        self.applied_recipe = [list(r) for r in self.recipe]
        self.refresh_recipe()
        if missing:
            messagebox.showwarning("Recipe", "Not in library (skipped):\n" +
                                   "\n".join(missing))

    @staticmethod
    def tree_lines(tree, cols, selected=False):
        rows = tree.selection() if selected else ()
        rows = rows or tree.get_children()
        lines = ["\t".join(t for _, t, _ in cols)]
        for iid in rows:
            lines.append("\t".join(str(v) for v in tree.item(iid, "values")))
        return lines

    def copy_tree(self, tree, cols, selected=True):
        to_clipboard(self, "\n".join(self.tree_lines(tree, cols, selected)))

    def copy_table(self, selected=True, notes=False):
        lines = [self.recipe_note] if self.recipe_note else []
        lines += ["Recipe (g/day)"] + [f"{n}\t{g:g}" for n, g in self.recipe]
        lines += [""] + self.tree_lines(self.res, self.RES_COLS, selected)
        lines += [""] + self.tree_lines(self.brk, self.BRK_COLS)
        if notes:
            lines += ["", self.notes.get("1.0", "end-1c")]
        to_clipboard(self, "\n".join(lines))

    def score_context(self):
        """Scoring settings: last optimiser run / blood adaptation if for the
        same stage, else defaults."""
        return build_score_context(self.score_ctx, self.stage.get(),
                                   self.current_mer())

    def current_mer(self):
        try:
            return mer(float(self.bw.get().replace(",", ".")),
                       float(self.factor.get().replace(",", ".")))
        except ValueError:
            return 0.0

    def apply_recipe(self, names, g, score, label, ctx, parent):
        self.recipe = [[n, float(a)] for n, a in zip(names, g) if a >= 0.1]
        self.score_ctx = store_score_context(self.score_ctx, ctx,
                                             self.stage.get(),
                                             self.current_mer())
        self.recipe_note = (f"{label} – score {score:.3f} "
                            f"({ctx['kcal_target']:.0f} kcal/day, "
                            f"{self.stage.get()})")
        self.applied_recipe = [list(r) for r in self.recipe]
        self.refresh_recipe()
        self.lift()
        if messagebox.askyesno("Recipe applied", "The recipe is now on the "
                               "main screen (see 'Ingredient breakdown' for "
                               "each component).\n\nSave it now?",
                               parent=parent):
            self.save_recipe()

    def open_generator(self):
        if self.current_mer() <= 0:
            messagebox.showerror("Generate", "Enter body weight and MER "
                                 "factor first.")
            return
        GeneratorDialog(self)

    def open_scale(self):
        if not self.recipe:
            messagebox.showinfo("Scale", "Add ingredients to the recipe "
                                "first.")
            return
        if self.current_mer() <= 0:
            messagebox.showerror("Scale", "Enter body weight and MER factor.")
            return
        ScaleDialog(self)

    def open_optimiser(self):
        if not self.recipe:
            messagebox.showinfo("Optimise", "Add the ingredients you want "
                                "to use to the recipe first.")
            return
        OptimiseDialog(self)

    # ---------------- calculation & display
    def recalc(self):
        if not hasattr(self, "res"):
            return
        self.res.delete(*self.res.get_children())
        self.brk.delete(*self.brk.get_children())
        self.notes.delete("1.0", "end")
        note = self.recipe_note
        if note and self.recipe != self.applied_recipe:
            note += "   (edited since)"
        self.info_lbl.config(text=note)
        a = analyse_recipe(self.recipe, self.db, self.current_mer(),
                           self.stage.get(), self.score_context())
        for name, unit, val, status in a["summary"]:
            self.res.insert("", "end", values=(name, unit, val, "", "", "",
                                               "", "", "", status),
                            tags=("head",))
        for values, tag in a["rows"]:
            self.res.insert("", "end", tags=(tag,) if tag else (),
                            values=values)
        if a["mass"] > 0:
            for i, row in enumerate(a["breakdown"]):
                last = i == len(a["breakdown"]) - 1
                self.brk.insert("", "end", values=row,
                                tags=("head",) if last else ())
        self.notes.insert("end", a["notes"])

    def assess(self, t, miss, mass, kcal, need, capr, acid, k1000,
               renal_mode, stage_note, fat_frac):
        return assess_recipe(self.stage.get(), self.recipe, self.db, t, miss,
                             mass, kcal, need, capr, acid, k1000, renal_mode,
                             stage_note, fat_frac)

    def export_results(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            initialfile="diet_results.csv")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if self.recipe_note:
                w.writerow([self.recipe_note])
            w.writerow(["Recipe", "g/day"])
            for n, g in self.recipe:
                w.writerow([n, g])
            w.writerow([])
            w.writerow([t for _, t, _ in self.BRK_COLS])
            for iid in self.brk.get_children():
                w.writerow(self.brk.item(iid, "values"))
            w.writerow([])
            w.writerow([t.replace("\n", " ") for _, t, _ in self.RES_COLS])
            for iid in self.res.get_children():
                w.writerow(self.res.item(iid, "values"))
            w.writerow([])
            for line in self.notes.get("1.0", "end").splitlines():
                w.writerow([line])


if __name__ == "__main__":
    App().mainloop()
