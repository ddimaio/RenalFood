#!/usr/bin/env python3
"""
afcd_fill.py - fill missing nutrient values in renal_ingredients.json (and
the matching files in imports/) from the Australian Food Composition
Database (AFCD) Release 3, Food Standards Australia New Zealand:
https://www.foodstandards.gov.au/science-data/food-nutrient-databases/afcd

Download "AFCD Release 3 - Nutrient profiles.xlsx" from the AFCD data-files
page and run (needs pandas + openpyxl):

    python afcd_fill.py "AFCD Release 3 - Nutrient profiles.xlsx"
    python afcd_fill.py FILE --dry-run     # show what would change

Only empty (null) values are filled; existing values are never changed.
Library ingredients are matched to AFCD foods by hand in AFCD_MAP below,
always the same preparation (boiled vs raw). Values are per 100 g,
converted to the app's units:
  vitamin A  µg RAE = retinol + beta-carotene equivalents / 12
  vitamin D  IU     = µg vitamin D3 equivalents x 40
  vitamin E  IU     = mg alpha-tocopherol x 1.49
  amino acids, linoleic acid in g; Fe/Cu/Mn/Zn mg; I/Se µg.
AFCD has no choline. Branded products, supplements and algal/fish oil are
not in the AFCD and are left as they are.
"""
import argparse
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "renal_ingredients.json")
OPTIONAL_ZERO = ("epa_dha", "base_meq", "p_bind")
SHEET = "All solids & liquids per 100 g"

# library name -> AFCD Public Food Key. Values are scaled by dry matter,
# (100 - library water) / (100 - AFCD water), so a food cooked with a
# different amount of water (or silken vs firm tofu) is put on the library
# food's basis.
AFCD_MAP = {
    "Apple, peeled, raw": "F000108",
    "Banana": "F000262",
    "Broccoli, boiled": "F001900",
    "Cabbage, boiled": "F002014",
    "Carrot, boiled": "F002275",
    "Chickpeas, boiled": "F002882",
    "Courgette, boiled": "F009773",
    "Egg white, cooked (boiled/poached, no fat)": "F003705",
    "Egg white, raw": "F003706",
    "Egg yolk, raw": "F003737",
    "Egg, whole, hard-boiled": "F003721",
    "Egg, whole, raw": "F003729",
    "Green beans, boiled": "F000430",
    "Lentils, boiled": "F005177",
    "Mushrooms, chestnut (crimini), raw weight": "F005946",
    "Oats, rolled, dry": "F006143",
    "Pasta, boiled (unenriched)": "F006456",
    "Peas, green, boiled": "F006535",
    "Potato, boiled, no skin": "F007320",
    "Pumpkin, boiled": "F007554",
    "Rice, brown, boiled": "F007641",
    "Rice, white, boiled (unenriched)": "F007661",
    "Rice, white, raw (dry, unenriched)": "F007682",
    "Spinach, boiled": "F008760",
    "Sweet potato, boiled, no skin": "F009034",
    "Tofu, firm (calcium-set)": "F009176",
    "Tofu, silken": "F009176",
    "Cauldron Authentic Tofu (organic, 396 g)": "F009176",
    "Rapeseed oil": "F006159",
    "Coconut oil": "F006163",
    "Linseed (flaxseed) oil": "F006168",
    "Hemp seed oil": "F009855",
    "Olive oil": "F006177",
    "Sunflower oil": "F006189",
}

# app key -> AFCD column (per 100 g) and factor to the app's unit
DIRECT = {
    "kcal": None, "water": ("Moisture (water)  (g)", 1),
    "protein": ("Protein  (g)", 1), "fat": ("Fat, total  (g)", 1),
    "fibre": ("Total dietary fibre  (g)", 1),
    "ca": ("Calcium (Ca)  (mg)", 1), "p": ("Phosphorus (P)  (mg)", 1),
    "na": ("Sodium (Na)  (mg)", 1), "k": ("Potassium (K)  (mg)", 1),
    "mg": ("Magnesium (Mg)  (mg)", 1),
    "b1": ("Thiamin (B1)  (mg)", 1), "b2": ("Riboflavin (B2)  (mg)", 1),
    "b3": ("Niacin (B3)  (mg)", 1), "b5": ("Pantothenic acid (B5)  (mg)", 1),
    "b6": ("Pyridoxine (B6)  (mg)", 1), "b12": ("Cobalamin (B12)  (ug)", 1),
    "folate": ("Total folates  (ug)", 1), "vit_c": ("Vitamin C  (mg)", 1),
    "vit_d": ("Vitamin D3 equivalents  (ug)", 40),
    "vit_e": ("Alpha tocopherol  (mg)", 1.49),
    "la": ("C18:2w6 (g)", 1),
    "fe": ("Iron (Fe)  (mg)", 1), "cu": ("Copper (Cu)  (mg)", 1),
    "mn": ("Manganese (Mn)  (mg)", 1), "zn": ("Zinc (Zn)  (mg)", 1),
    "i": ("Iodine (I)  (ug)", 1), "se": ("Selenium (Se)  (ug)", 1),
}
AMINO = {"arg": "Arginine", "his": "Histidine", "ile": "Isoleucine",
         "leu": "Leucine", "lys": "Lysine", "met": "Methionine",
         "phe": "Phenylalanine", "thr": "Threonine", "trp": "Tryptophan",
         "val": "Valine", "cys": "Cystine plus cysteine",
         "tyr": "Tyrosine"}


def num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def afcd_values(row):
    """AFCD row -> {app key: value per 100 g} for the values AFCD has."""
    out = {}
    for k, src in DIRECT.items():
        if src:
            v = num(row.get(src[0]))
            if v is None and k == "vit_e":
                v = num(row.get("Vitamin E  (mg)"))
            if v is not None:
                out[k] = v * src[1]
    ret = num(row.get("Retinol (preformed vitamin A)  (ug)"))
    bce = num(row.get("Beta-carotene equivalents (provitamin A)  (ug)"))
    if ret is not None or bce is not None:
        out["vit_a"] = (ret or 0) + (bce or 0) / 12
    aa = {k: num(row.get(f"{n}  (mg)")) for k, n in AMINO.items()}
    for k, v in aa.items():
        if v is not None and k not in ("cys", "tyr"):
            out[k] = v / 1000
    for pair, (a, b) in {"met_cys": ("met", "cys"),
                         "phe_tyr": ("phe", "tyr")}.items():
        if aa[a] is not None and aa[b] is not None:
            out[pair] = (aa[a] + aa[b]) / 1000
    return out


def rnd(v):
    return float(f"{v:.3g}") if v else 0.0


def fill(items, table, log):
    changed = 0
    for it in items:
        m = AFCD_MAP.get(it["name"])
        if not m or m not in table:
            continue
        key = m
        row = table[key]
        vals = afcd_values(row)
        per = it["per100g"]
        wa, wl = num(row.get("Moisture (water)  (g)")), per.get("water")
        scale = 1.0
        if wa is not None and wl is not None and wa < 99.5:
            scale = (100 - wl) / (100 - wa)
        got = []
        for k, v in vals.items():
            if k in ("water", "protein", "fat", "fibre"):
                continue                # composition basis: keep library's
            if per.get(k) is None and k not in OPTIONAL_ZERO:
                per[k] = rnd(v * scale)
                got.append(k)
        if got:
            src = f"AFCD R3 {key} ({row['Food Name']})"
            if abs(scale - 1) > 0.05:
                src += f", scaled x{scale:.2f} for water content"
            note = it.get("note", "")
            tag = f"Filled from {src}: {', '.join(got)}."
            if "AFCD" not in note:
                it["note"] = (note + " " + tag).strip()
            log.append(f"{it['name']}: {', '.join(got)}  <- {src}")
            changed += 1
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    import pandas as pd
    d = pd.read_excel(a.xlsx, SHEET, header=2)
    d.columns = [str(c).replace("\n", " ").strip() for c in d.columns]
    table = {r["Public Food Key"]: r for r in d.to_dict("records")}
    files = [LIB] + sorted(glob.glob(os.path.join(HERE, "imports", "*.json")))
    for path in files:
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
        log = []
        n = fill(items, table, log)
        if n:
            print(f"== {os.path.relpath(path, HERE)}: {n} ingredient(s)")
            print("\n".join("  " + s for s in log))
            if not a.dry_run:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(items, f, indent=1, ensure_ascii=False)
                    f.write("\n")


if __name__ == "__main__":
    sys.exit(main())
