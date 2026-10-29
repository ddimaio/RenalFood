#!/usr/bin/env python3
"""
afcd_add.py - add dog-safe ingredients to the library from the Australian
Food Composition Database (AFCD) Release 3, FSANZ.

    python afcd_add.py "AFCD Release 3 - Nutrient profiles.xlsx"
    python afcd_add.py FILE --dry-run

Writes imports/afcd_foods.json and adds the foods to renal_ingredients.json
(foods already in the library are left alone). Units as in afcd_fill.py.
Energy = AFCD energy incl. fibre (kJ / 4.184); carbohydrate = available
carbohydrate + fibre. Nutrients AFCD did not analyse stay unknown, except
B12, vitamin D and EPA+DHA in plant foods, which are 0. AFCD has no
choline. Foods toxic to dogs (onion, garlic, leek, chives, grapes,
raisins, avocado, macadamia, xylitol) are deliberately not included.
"""
import argparse
import json
import os
import sys

from afcd_fill import HERE, LIB, SHEET, afcd_values, num, rnd

# AFCD key, library name, note, plant food?[, role override]
FOODS = [
    # vegetables
    ("F002377", "Cauliflower, boiled", "", True),
    ("F003319", "Cucumber, peeled, raw", "", True),
    ("F002390", "Celery, raw", "Chop finely (stringy).", True),
    ("F005191", "Lettuce, cos, raw", "", True),
    ("F002247", "Red pepper (capsicum), raw", "", True),
    ("F008806", "Bean sprouts, raw", "", True),
    ("F001913", "Brussels sprouts, boiled", "Can cause wind.", True,
     "veg"),
    ("F000151", "Asparagus, boiled", "", True),
    ("F001014", "Beetroot, boiled", "Moderate oxalate.", True),
    ("F009339", "Turnip, boiled", "", True),
    ("F009020", "Swede, boiled", "", True),
    ("F006327", "Parsnip, boiled", "", True),
    ("F008371", "Mangetout (snow peas), boiled", "", True),
    ("F008810", "Squash, summer (button), boiled", "", True),
    ("F007534", "Butternut squash, boiled", "", True),
    ("F001302", "Pak choi (bok choy), steamed", "", True),
    ("F001993", "Chinese leaf cabbage, boiled", "", True),
    ("F008266", "Swiss chard (silverbeet), boiled",
     "High oxalate - use sparingly.", True),
    ("F006194", "Okra, boiled", "", True),
    # starches
    ("F003235", "Couscous, boiled", "", True),
    ("F007596", "Quinoa, boiled", "Rinse before cooking (saponins).", True),
    ("F003227", "Polenta (cornmeal), boiled", "", True),
    ("F000378", "Pearl barley, boiled", "", True),
    ("F001918", "Buckwheat, boiled", "", True, "starch"),
    ("F005690", "Millet, boiled", "", True),
    ("F009089", "Tapioca, boiled", "Very low in protein, P and K.", True,
     "starch"),
    ("F006038", "Rice noodles, boiled", "", True),
    # protein foods
    ("F000459", "Soya beans, boiled", "", True),
    ("F000437", "Haricot beans, boiled", "", True, "protein"),
    ("F000442", "Butter (lima) beans, boiled", "", True),
    ("F006544", "Split peas, boiled", "", True),
    ("F004220", "Vital wheat gluten (seitan base), dry",
     "Very high protein, low phosphorus.", True),
    ("F002435", "Cottage cheese", "Check sodium on the label.", False),
    ("F002488", "Ricotta", "", False, "protein"),
    ("F009694", "Natural yoghurt (~3% fat)", "", False, "protein"),
    # fats / seeds
    ("F006579", "Peanut butter, no added salt or sugar",
     "Must be xylitol-free.", True),
    ("F008209", "Chia seeds, dry", "High in phosphorus.", True),
    ("F006185", "Rice bran oil", "", True),
    ("F006167", "Grapeseed oil",
     "Oil only - grapes and raisins themselves are toxic to dogs.", True),
]
PLANT_ZERO = ("b12", "vit_d", "epa_dha")
ALL_KEYS = ["kcal", "water", "protein", "fat", "carb", "fibre", "ca", "p",
            "na", "k", "mg", "vit_a", "b1", "b2", "b3", "b6", "b12",
            "folate", "b5", "choline", "vit_d", "vit_e", "vit_c", "epa_dha",
            "base_meq", "p_bind", "arg", "his", "ile", "leu", "lys", "met",
            "met_cys", "phe", "phe_tyr", "thr", "trp", "val", "la", "fe",
            "cu", "mn", "zn", "i", "se"]


def make(row, name, note, plant, role=None):
    v = afcd_values(row)
    kj = num(row.get("Energy with dietary fibre, equated  (kJ)"))
    v["kcal"] = kj / 4.184 if kj is not None else None
    avail = num(row.get("Available carbohydrate, without sugar alcohols  (g)"))
    if avail is not None:
        v["carb"] = avail + (v.get("fibre") or 0)
    epa = num(row.get("C20:5w3 (mg)"))
    dha = num(row.get("C22:6w3 (mg)"))
    if epa is not None or dha is not None:
        v["epa_dha"] = (epa or 0) + (dha or 0)
    v["base_meq"] = v["p_bind"] = 0.0
    if plant:
        for k in PLANT_ZERO:
            v.setdefault(k, 0.0)
    per = {k: (round(v[k], 1) if k == "kcal" else rnd(v[k]))
           if v.get(k) is not None else None for k in ALL_KEYS}
    src = f"AFCD R3 {row['Public Food Key']} ({row['Food Name'].strip()})."
    out = {"name": name, "category": "food",
           "note": " ".join(s for s in (note, "From " + src) if s),
           "per100g": per}
    if role:
        out["role"] = role
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    import pandas as pd
    d = pd.read_excel(a.xlsx, SHEET, header=2)
    d.columns = [str(c).replace("\n", " ").strip() for c in d.columns]
    table = {r["Public Food Key"]: r for r in d.to_dict("records")}
    new = [make(table[f[0]], *f[1:]) for f in FOODS]
    for it in new:
        p = it["per100g"]
        print(f"{it['name'][:40]:40} {p['kcal']:6} kcal  prot {p['protein']}"
              f"  P {p['p']}  K {p['k']}  Na {p['na']}")
    if a.dry_run:
        return
    with open(os.path.join(HERE, "imports", "afcd_foods.json"), "w",
              encoding="utf-8") as f:
        json.dump(new, f, indent=1, ensure_ascii=False)
        f.write("\n")
    with open(LIB, encoding="utf-8") as f:
        lib = json.load(f)
    have = {i["name"] for i in lib}
    lib += [i for i in new if i["name"] not in have]
    lib.sort(key=lambda i: i["name"].lower())
    with open(LIB, "w", encoding="utf-8") as f:
        json.dump(lib, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"library: {len(lib)} ingredients")


if __name__ == "__main__":
    sys.exit(main())
