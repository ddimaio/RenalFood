#!/usr/bin/env python3
"""
fdc_fill.py - fill the extended nutrients (essential amino acids, linoleic
acid, Fe, Cu, Mn, Zn, I, Se) in renal_ingredients.json from USDA
FoodData Central (FDC).

Needs a free FDC API key: https://fdc.nal.usda.gov/api-key-signup
Standard library only. Run next to renal_diet_calc.py:

    python fdc_fill.py --key YOUR_KEY            # match + fill
    (in Spyder just run it: it asks for the key, or set FDC_API_KEY)
    python fdc_fill.py --key YOUR_KEY --dry-run  # show what would change
    python fdc_fill.py --key YOUR_KEY --overwrite  # replace existing values

1. Matching: each library ingredient needs an FDC food. Matches are kept in
   fdc_map.json (name -> FDC id, or null = skip). For an unmatched
   ingredient the script searches FDC and asks you to pick one of the
   results (Enter = skip, s = skip permanently). You can also edit
   fdc_map.json by hand.
2. Filling: values are converted to per 100 g in the app's units. Only
   empty values are filled unless --overwrite. A backup of the library is
   written first (renal_ingredients.json.bak).

Commercial foods, supplements and binders are skipped unless mapped by
hand: their composition is on their label, not in FDC. Check the matched
food is the same preparation (cooked vs raw) as the library entry - FDC
values for raw foods are not valid for a cooked-weight entry.
"""
import argparse
import json
import os
import shutil
import sys
import urllib.parse
import urllib.request

import renal_diet_calc as rc

API = "https://api.nal.usda.gov/fdc/v1"
MAP_PATH = os.path.join(rc.APP_DIR, "fdc_map.json")

# app key -> (FDC nutrient numbers, FDC nutrient names), first match wins.
# Names are a fallback in case a number differs between FDC data types.
SOURCES = {
    "trp": (["501"], ["Tryptophan"]),
    "thr": (["502"], ["Threonine"]),
    "ile": (["503"], ["Isoleucine"]),
    "leu": (["504"], ["Leucine"]),
    "lys": (["505"], ["Lysine"]),
    "met": (["506"], ["Methionine"]),
    "cys": (["507"], ["Cystine", "Cysteine"]),
    "phe": (["508"], ["Phenylalanine"]),
    "tyr": (["509"], ["Tyrosine"]),
    "val": (["510"], ["Valine"]),
    "arg": (["511"], ["Arginine"]),
    "his": (["512"], ["Histidine"]),
    "la": (["618", "675"], ["PUFA 18:2", "PUFA 18:2 n-6 c,c",
                            "18:2 n-6 c,c"]),
    "fe": (["303"], ["Iron, Fe"]),
    "zn": (["309"], ["Zinc, Zn"]),
    "cu": (["312"], ["Copper, Cu"]),
    "i": (["314"], ["Iodine, I"]),
    "mn": (["315"], ["Manganese, Mn"]),
    "se": (["317"], ["Selenium, Se"]),
}
# target unit per app key (see renal_diet_calc.NUTRIENTS)
TO_UNIT = {k: rc.UNIT[k] for k in rc.EXT_KEYS}
TO_UNIT.update(cys="g", tyr="g")
FACTOR = {"g": 1.0, "mg": 1e-3, "µg": 1e-6, "ug": 1e-6}   # to grams


def get_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def search(key, query):
    q = urllib.parse.urlencode({"api_key": key, "query": query,
                                "pageSize": 8,
                                "dataType": "Foundation,SR Legacy"})
    return get_json(f"{API}/foods/search?{q}").get("foods", [])


def fetch(key, fdc_id):
    q = urllib.parse.urlencode({"api_key": key})
    return get_json(f"{API}/food/{fdc_id}?{q}")


def convert(amount, unit, to):
    unit = (unit or "").strip().lower().replace("μ", "µ")
    to = to.lower()
    if unit not in FACTOR or to not in FACTOR:
        return None
    return amount * FACTOR[unit] / FACTOR[to]


def extract(food):
    """Extended nutrients per 100 g in app units from an FDC food record
    (FDC values are per 100 g). Missing nutrients are left out."""
    rows = []
    for fn in food.get("foodNutrients", []):
        n = fn.get("nutrient") or {}
        amt = fn.get("amount")
        if amt is None:
            continue
        rows.append((str(n.get("number", "")), n.get("name", ""),
                     n.get("unitName", ""), float(amt)))
    got = {}
    for key, (numbers, names) in SOURCES.items():
        hit = next((r for num in numbers for r in rows if r[0] == num), None)
        hit = hit or next((r for nm in names for r in rows if r[1] == nm),
                          None)
        if hit:
            v = convert(hit[3], hit[2], TO_UNIT[key])
            if v is not None:
                got[key] = round(v, 4)
    for pair, (a, b) in {"met_cys": ("met", "cys"),
                         "phe_tyr": ("phe", "tyr")}.items():
        if a in got and b in got:
            got[pair] = round(got[a] + got[b], 4)
    return {k: v for k, v in got.items() if k in rc.EXT_KEYS}


def load_map():
    if os.path.exists(MAP_PATH):
        with open(MAP_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_map(m):
    with open(MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(m.items())), f, indent=1, ensure_ascii=False)


def choose(key, name):
    try:
        foods = search(key, name.split("(")[0])
    except Exception as e:                       # network / quota
        print(f"  search failed: {e}")
        return "later"
    if not foods:
        print("  no FDC results")
        return "later"
    for i, f in enumerate(foods, 1):
        print(f"  {i}. {f.get('description')}  [{f.get('dataType')}, "
              f"id {f.get('fdcId')}]")
    a = input("  pick 1-8, Enter = ask again next run, s = always skip: ")
    a = a.strip().lower()
    if a == "s":
        return None
    if a.isdigit() and 1 <= int(a) <= len(foods):
        return foods[int(a) - 1]["fdcId"]
    return "later"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--key", help="FDC API key (or set FDC_API_KEY; "
                                  "asked for if neither is given)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--overwrite", action="store_true",
                    help="replace values already in the library")
    ap.add_argument("--no-ask", action="store_true",
                    help="only use fdc_map.json, no interactive matching")
    a = ap.parse_args(argv)
    a.key = (a.key or os.environ.get("FDC_API_KEY")
             or input("FDC API key: ").strip())

    db = rc.load_db()
    fmap = load_map()
    for name in sorted(db, key=str.lower):
        if name in fmap or db[name]["category"] != "food" or a.no_ask:
            continue
        print(f"\nMatch: {name}")
        pick = choose(a.key, name)
        if pick != "later":
            fmap[name] = pick
            save_map(fmap)

    changes = 0
    for name, fdc_id in sorted(fmap.items()):
        if fdc_id is None or name not in db:
            continue
        try:
            vals = extract(fetch(a.key, fdc_id))
        except Exception as e:
            print(f"{name}: fetch failed ({e})")
            continue
        cur = db[name]["per100g"]
        upd = {k: v for k, v in vals.items()
               if a.overwrite or cur.get(k) is None}
        missing = [k for k in rc.EXT_KEYS if k not in vals]
        print(f"{name} <- FDC {fdc_id}: {len(upd)} values"
              + (f"; not in FDC: {', '.join(missing)}" if missing else ""))
        if upd and not a.dry_run:
            cur.update(upd)
            changes += len(upd)
    if changes:
        if os.path.exists(rc.DB_PATH):
            shutil.copy2(rc.DB_PATH, rc.DB_PATH + ".bak")
        rc.save_db(db)
        print(f"\nSaved {changes} values to {rc.DB_PATH} "
              "(backup: .bak).")
    else:
        print("\nNo changes written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
