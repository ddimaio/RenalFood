#!/usr/bin/env python3
"""
oxalate_fill.py - set oxalate (mg per 100 g) for library ingredients.

Main source: Oxalosis & Hyperoxaluria Foundation (OHF) food oxalate list
(2024), https://ohf.org/wp-content/uploads/2024/02/Oxalate-List-022724.pdf
- values per serving converted to per 100 g (serving weights as listed).
Where OHF has no entry, the Standard Tables of Food Composition in Japan 2023
(organic acids table, oxalic acid) are used when they give a real value.
Foods with no reliable value stay unknown (null). Oils, salt, mineral
supplements and binders contain none (0).

Oxalate in plants varies a lot with variety, soil and cooking (boiling and
discarding the water removes part of the soluble oxalate). Treat values as
approximate. Tofu: OHF ~8 mg/100 g, Japan 0, but some published brands are
much higher; Cook & Atiee (Today's Vet Practice 2026) list tofu among foods
to avoid in calcium-oxalate stone formers.

    python oxalate_fill.py            # fill empty values only
    python oxalate_fill.py --overwrite
"""
import argparse
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "renal_ingredients.json")


def per100(mg, grams):
    return round(mg * 100.0 / grams, 1)


# name -> (mg per 100 g, source note)
OHF = "OHF 2024"
VALUES = {
    "Spinach, boiled": (per100(493, 87), OHF + " (boiled, 1/2 cup)"),
    "Swiss chard (silverbeet), boiled": (
        per100(293, 87.5), OHF + " (green chard, boiled; red chard ~680)"),
    "Beetroot, boiled": (per100(48, 85), OHF),
    "Sweet potato, boiled, no skin": (
        per100(158, 125), OHF + " (baked/boiled; mashed without skin ~42)"),
    "Potato, boiled, no skin": (per100(18, 78), OHF + " (white, boiled)"),
    "Tofu, firm (calcium-set)": (per100(10, 125), OHF + "; varies by brand"),
    "Tofu, silken": (per100(10, 125), OHF + "; varies by brand"),
    "Cauldron Authentic Tofu (organic, 396 g)": (
        per100(10, 125), OHF + " (tofu); varies by brand"),
    "Soy milk, unsweetened": (per100(9, 242), OHF),
    "Edamame, boiled": (per100(22, 75), OHF),
    "Soya beans, boiled": (per100(39, 86), OHF),
    "Peanut butter, no added salt or sugar": (per100(36, 29), OHF),
    "Okra, boiled": (per100(56, 56), OHF),
    "Carrot, boiled": (per100(9, 78), OHF),
    "Celery, raw": (per100(30, 120), OHF),
    "Green beans, boiled": (per100(15, 62), OHF),
    "Broccoli, boiled": (per100(4, 60), OHF),
    "Cauliflower, boiled": (per100(2, 60), OHF),
    "Cabbage, boiled": (per100(3, 78), OHF),
    "Chinese leaf cabbage, boiled": (per100(3, 78), OHF + " (cabbage)"),
    "Courgette, boiled": (per100(4, 100), OHF + " (summer squash)"),
    "Squash, summer (button), boiled": (per100(4, 100), OHF),
    "Butternut squash, boiled": (per100(4, 100), OHF + " (winter squash)"),
    "Kabocha squash, boiled": (per100(4, 100), OHF + " (winter squash)"),
    "Pumpkin, boiled": (per100(7, 120), OHF + " (canned pumpkin)"),
    "Pak choi (bok choy), steamed": (per100(5, 156), OHF + " (leaves+stalks)"),
    "Asparagus, boiled": (per100(5, 90), OHF),
    "Rice, white, boiled (unenriched)": (per100(1, 90), OHF),
    "Rice, white, raw (dry, unenriched)": (
        per100(1, 90) * 2.8, OHF + " (boiled value x dry-matter ratio)"),
    "Rice, brown, boiled": (per100(5, 90), OHF),
    "Oats, rolled, dry": (per100(8, 24.5), OHF + " (oat flour)"),
    "Quinoa, boiled": (per100(55, 90), OHF),
    "Buckwheat, boiled": (per100(105, 85), OHF + " (cereal, cooked)"),
    "Millet, boiled": (per100(32, 87), OHF + " (whole, cooked)"),
    "Pearl barley, boiled": (per100(9, 84), OHF),
    "Couscous, boiled": (per100(13, 78.5), OHF),
    "Pasta, boiled (unenriched)": (per100(24, 128), OHF),
    "Lentils, boiled": (per100(8, 96), OHF),
    "Chickpeas, boiled": (per100(9, 86), OHF),
    "Haricot beans, boiled": (per100(53, 95), OHF + " (navy beans)"),
    "Butter (lima) beans, boiled": (per100(10, 94), OHF),
    "Split peas, boiled": (per100(4, 98), OHF),
    "Peas, green, boiled": (per100(2, 80), OHF),
    "Chia seeds, dry": (per100(61, 13), OHF),
    "Mushrooms, chestnut (crimini), raw weight": (per100(1, 78), OHF),
    "Mushrooms, oyster, raw weight": (per100(1, 78), OHF),
    "Mushrooms, portobello, grilled": (per100(1, 78), OHF),
    "Mushrooms, shiitake, cooked": (per100(1, 78), OHF),
    "Mushrooms, white (button), boiled": (per100(1, 78), OHF),
    "Egg, whole, raw": (0.0, OHF),
    "Egg, whole, hard-boiled": (0.0, OHF),
    "Egg white, raw": (0.0, OHF),
    "Egg white, cooked (boiled/poached, no fat)": (0.0, OHF),
    "Egg yolk, raw": (0.0, OHF),
    "Cottage cheese": (0.0, OHF),
    "Ricotta": (0.0, OHF + " (cheese ~0)"),
    "Natural yoghurt (~3% fat)": (per100(4, 170), OHF),
    "Apple, peeled, raw": (per100(2, 138), OHF),
    "Banana": (per100(6, 118), OHF),
    "Cucumber, peeled, raw": (per100(5, 120), OHF),
    "Turnip, boiled": (per100(2, 78), OHF),
    "Parsnip, boiled": (per100(15, 78), OHF),
    "Swede, boiled": (per100(4, 85), OHF + " (rutabaga)"),
    "Daikon (white radish), boiled": (per100(1, 100), OHF + " (radish)"),
    "Polenta (cornmeal), boiled": (2.0, OHF + " (dry polenta, diluted)"),
    "Tapioca, boiled": (5.0, OHF + " (tapioca flour, diluted)"),
}
ZERO_CATEGORIES = ("binder",)
ZERO_NAMES = ("Calcium carbonate", "Calcium citrate (tetrahydrate)",
              "Eggshell powder", "Potassium citrate (monohydrate)",
              "Potassium gluconate", "Sodium bicarbonate",
              "Salt (sodium chloride)", "Fish oil (salmon)",
              "Algal oil (vegan omega-3)")


def oxalate_for(item):
    n = item["name"]
    if n in VALUES:
        return VALUES[n]
    v = item.get("per100g", {})
    if item.get("category") in ZERO_CATEGORIES or n in ZERO_NAMES:
        return 0.0, "none (mineral/binder/oil)"
    if item.get("category") == "supplement":
        return 0.0, "negligible at supplement doses"
    if (v.get("kcal") or 0) >= 800 and (v.get("fat") or 0) >= 95:
        return 0.0, "none (pure oil)"
    return None, None


def fill(items, overwrite=False):
    n = 0
    for it in items:
        per = it.setdefault("per100g", {})
        if per.get("oxalate") is not None and not overwrite:
            continue
        val, src = oxalate_for(it)
        if val is None:
            per.setdefault("oxalate", None)
            continue
        per["oxalate"] = round(val, 1)
        if src and "Oxalate" not in it.get("note", "") and val > 0:
            it["note"] = (it.get("note", "") + f" Oxalate: {src}.").strip()
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    for path in [LIB] + sorted(glob.glob(os.path.join(HERE, "imports",
                                                      "*.json"))):
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
        if not isinstance(items, list):
            continue
        n = fill(items, a.overwrite)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=1, ensure_ascii=False)
            f.write("\n")
        print(f"{os.path.relpath(path, HERE)}: {n} set")


if __name__ == "__main__":
    main()
