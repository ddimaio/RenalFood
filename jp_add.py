#!/usr/bin/env python3
"""
jp_add.py - add foods from the Standard Tables of Food Composition in Japan
2020 (8th revised edition), updated and enlarged 2023 (MEXT), and replace
estimated silken-tofu values with values measured on silken tofu.

Needs three of the MEXT Excel files (pandas not needed, openpyxl only):
    main table (本表)                       ..._02.xlsx
    amino acids per 100 g (アミノ酸 第1表)   ..._04.xlsx
    fatty acids per 100 g (脂肪酸 第1表)     ..._09.xlsx

    python jp_add.py MAIN.xlsx AMINO.xlsx FATTY.xlsx [--dry-run]

Writes imports/japan_foods.json and adds the foods to renal_ingredients.json
(existing foods are left alone). Conventions of the tables: values in
brackets are estimates and are used as numbers; Tr (trace) = 0; "-" (not
analysed) = unknown. Units as in afcd_fill.py: vitamin D IU = µg x 40,
vitamin E IU = mg alpha-tocopherol x 1.49, amino acids and linoleic acid
in g. Carbohydrate is the table's carbohydrate by difference (incl. fibre).
The Japanese tables have no choline.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "renal_ingredients.json")

# food number, library name, note, plant food?, role override
FOODS = [
    ("04051", "Okara (soy pulp), raw",
     "Soy pulp left from making soy milk/tofu: high fibre, low phosphorus.",
     True, "protein"),
    ("06016", "Edamame, boiled", "Shelled beans only.", True, None),
    ("04046", "Natto", "Fermented soybeans. High potassium.", True, None),
    ("04052", "Soy milk, unsweetened", "Plain soy milk, no additives.",
     True, "protein"),
    ("06049", "Kabocha squash, boiled", "", True, None),
    ("06135", "Daikon (white radish), boiled", "", True, None),
    ("06174", "Winter melon, boiled", "", True, None),
    ("06292", "Mung bean sprouts, boiled",
     "Boiling removes most of the potassium.", True, None),
    ("06318", "Lotus root, boiled", "", True, None),
    ("02005", "Shirataki (konjac noodles)",
     "Almost no energy or nutrients; bulk only. Cut short.", True, "other"),
    ("02061", "Mung bean glass noodles, boiled",
     "Near-pure starch: very low protein, P and K.", True, None),
    ("02034", "Potato starch",
     "Near-pure starch: energy with almost no P or K. Cook before use.",
     True, "starch"),
    ("01039", "Udon noodles, boiled",
     "Contains salt (Na 120 mg/100 g).", True, None),
    ("01044", "Somen noodles, boiled",
     "Contains salt (Na 85 mg/100 g).", True, None),
    ("14002", "Sesame oil", "", True, None),
    ("14005", "Soybean oil", "Rich in linoleic acid.", True, None),
    ("14007", "Corn oil", "Rich in linoleic acid.", True, None),
    ("14025", "Safflower oil (high linoleic)",
     "Richest linoleic acid source.", True, None),
    ("14024", "Perilla oil",
     "ALA (plant omega-3), not EPA/DHA.", True, None),
]
# library food -> (food number, keys to replace). These values were
# estimated earlier (AFCD firm tofu scaled for water); Japan has them
# measured on silken tofu.
REPLACE = {
    "Tofu, silken": ("04033", ("b5", "vit_e", "la", "mn", "i", "se")),
}

# library food -> Japanese food number used to fill EMPTY values only.
# Amino acids are scaled by protein (library / Japan), other nutrients by
# dry matter, so a dry (uncooked) Japanese entry can stand in for a boiled
# library food.
FILL = {
    "Asparagus, boiled": "06008",
    "Beetroot, boiled": "06244",
    "Buckwheat, boiled": "01126",
    "Butter (lima) beans, boiled": "04093",
    "Celery, raw": "06119",
    "Chia seeds, dry": "05046",
    "Chinese leaf cabbage, boiled": "06234",
    "Cottage cheese": "13033",
    "Cucumber, peeled, raw": "06065",
    "Haricot beans, boiled": "04008",
    "Mangetout (snow peas), boiled": "06021",
    "Millet, boiled": "01011",
    "Natural yoghurt (~3% fat)": "13025",
    "Okra, boiled": "06033",
    "Pak choi (bok choy), steamed": "06161",
    "Peanut butter, no added salt or sugar": "05037",
    "Pearl barley, boiled": "01170",
    "Polenta (cornmeal), boiled": "01132",
    "Quinoa, boiled": "01167",
    "Red pepper (capsicum), raw": "06247",
    "Rice noodles, boiled": "01115",
    "Ricotta": "13058",
    "Split peas, boiled": "04013",
    "Turnip, boiled": "06039",
    "Swiss chard (silverbeet), boiled": "06262",
    "Tapioca, boiled": "02057",
    "Vital wheat gluten (seitan base), dry": "01071",
    "Grapeseed oil": "14028",
    "Rice bran oil": "14003",
    "Mushrooms, oyster, raw weight": "08026",
    "Mushrooms, white (button), boiled": "08032",
    "Mushrooms, portobello, grilled": "08059",
}
AA_KEYS = ("arg", "his", "ile", "leu", "lys", "met", "met_cys", "phe",
           "phe_tyr", "thr", "trp", "val")
FILL_KEYS = AA_KEYS + ("b5", "cu", "mn", "i", "se", "la")

MAIN = {"kcal": "ENERC_KCAL", "water": "WATER", "protein": "PROT-",
        "fat": "FAT-", "carb": "CHOCDF-", "fibre": "FIB-", "ca": "CA",
        "p": "P", "na": "NA", "k": "K", "mg": "MG", "vit_a": "VITA_RAE",
        "b1": "THIA", "b2": "RIBF", "b3": "NIA", "b6": "VITB6A",
        "b12": "VITB12", "folate": "FOL", "b5": "PANTAC", "vit_c": "VITC",
        "fe": "FE", "cu": "CU", "mn": "MN", "zn": "ZN", "i": "ID",
        "se": "SE"}
FACTOR = {"VITD": 40, "TOCPHA": 1.49}
AMINO = {"arg": "ARG", "his": "HIS", "ile": "ILE", "leu": "LEU",
         "lys": "LYS", "met": "MET", "met_cys": "AAS", "phe": "PHE",
         "phe_tyr": "AAA", "thr": "THR", "trp": "TRP", "val": "VAL"}
PLANT_ZERO = ("b12", "vit_d", "epa_dha")
ALL_KEYS = ["kcal", "water", "protein", "fat", "carb", "fibre", "ca", "p",
            "na", "k", "mg", "vit_a", "b1", "b2", "b3", "b6", "b12",
            "folate", "b5", "choline", "vit_d", "vit_e", "vit_c", "epa_dha",
            "base_meq", "p_bind", "arg", "his", "ile", "leu", "lys", "met",
            "met_cys", "phe", "phe_tyr", "thr", "trp", "val", "la", "fe",
            "cu", "mn", "zn", "i", "se"]


def num(v):
    """Japanese table cell -> float or None."""
    if v is None:
        return None
    s = str(v).strip().strip("()").strip()
    if s in ("Tr", "0", ""):
        return 0.0 if s else None
    try:
        return float(s)
    except ValueError:
        return None                       # "-", "*" and other marks


def load(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    rows = list(wb["表全体"].iter_rows(values_only=True))
    hi = next(i for i, r in enumerate(rows) if r[3] == "成分識別子")
    ids = [str(c).strip() if c else None for c in rows[hi]]
    return {str(r[1]): {i: r[n] for n, i in enumerate(ids) if i}
            for r in rows[hi + 1:] if r[1]}, \
        {str(r[1]): str(r[3]).replace("　", " ") for r in rows[hi + 1:]
         if r[1]}


def values(code, main, aa, fa):
    r = main[code]
    v = {k: num(r.get(c)) for k, c in MAIN.items()}
    d, e = num(r.get("VITD")), num(r.get("TOCPHA"))
    v["vit_d"] = d * FACTOR["VITD"] if d is not None else None
    v["vit_e"] = e * FACTOR["TOCPHA"] if e is not None else None
    if code in aa:
        for k, c in AMINO.items():
            x = num(aa[code].get(c))
            v[k] = x / 1000 if x is not None else None
    if code in fa:
        la = num(fa[code].get("F18D2N6"))
        v["la"] = la / 1000 if la is not None else None
        epa, dha = num(fa[code].get("F20D5N3")), num(fa[code].get("F22D6N3"))
        if epa is not None or dha is not None:
            v["epa_dha"] = (epa or 0) + (dha or 0)
    return v


def rnd(x):
    return float(f"{x:.3g}") if x else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("main_xlsx")
    ap.add_argument("amino_xlsx")
    ap.add_argument("fatty_xlsx")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    main_t, names = load(a.main_xlsx)
    aa, _ = load(a.amino_xlsx)
    fa, _ = load(a.fatty_xlsx)

    new = []
    for code, name, note, plant, role in FOODS:
        v = values(code, main_t, aa, fa)
        v["base_meq"] = v["p_bind"] = 0.0
        if plant:
            for k in PLANT_ZERO:
                if v.get(k) is None:
                    v[k] = 0.0
        per = {k: (rnd(v[k]) if v.get(k) is not None else None)
               for k in ALL_KEYS}
        src = (f"From Standard Tables of Food Composition in Japan 2023 "
               f"(MEXT), {code} {names[code]}.")
        it = {"name": name, "category": "food",
              "note": " ".join(s for s in (note, src) if s), "per100g": per}
        if role:
            it["role"] = role
        new.append(it)
        print(f"{name[:36]:36} {per['kcal']:6} kcal  prot {per['protein']}"
              f"  P {per['p']}  K {per['k']}  Na {per['na']}")

    with open(LIB, encoding="utf-8") as f:
        lib = json.load(f)
    byname = {i["name"]: i for i in lib}
    for lname, (code, keys) in REPLACE.items():
        it = byname.get(lname)
        if not it:
            continue
        v = values(code, main_t, aa, fa)
        got = [k for k in keys if v.get(k) is not None]
        for k in got:
            it["per100g"][k] = rnd(v[k])
        note = it.get("note", "")
        # drop the earlier "Filled from AFCD ...: keys." remark it replaces
        note = " ".join(x for x in note.split("Filled from AFCD")[:1]).strip()
        tag = (f"{', '.join(got)} from Japan 2023 tables {code} "
               f"({names[code]}).")
        if "Japan 2023" not in note:
            it["note"] = (note + " " + tag).strip()
        print(f"{lname}: replaced {got}")
    # fill empty values of existing foods
    for lname, code in FILL.items():
        it = byname.get(lname)
        if not it or code not in main_t:
            continue
        per = it["per100g"]
        v = values(code, main_t, aa, fa)
        pj, pl = v.get("protein"), per.get("protein")
        wj, wl = v.get("water"), per.get("water")
        s_aa = pl / pj if pj and pl is not None else None
        s_dm = ((100 - wl) / (100 - wj) if wj is not None and wl is not None
                and wj < 99.5 else 1.0)
        got = []
        for k in FILL_KEYS:
            if per.get(k) is not None or v.get(k) is None:
                continue
            sc = s_aa if k in AA_KEYS else s_dm
            if sc is None:
                continue
            per[k] = rnd(v[k] * sc)
            got.append(k)
        if got:
            tag = (f"{', '.join(got)} from Japan 2023 tables {code} "
                   f"({names[code]}), scaled.")
            it["note"] = (it.get("note", "") + " " + tag).strip()
            print(f"{lname}: filled {got}")
    # no protein -> no amino acids; no fat -> no linoleic acid
    for it in lib + new:
        per = it["per100g"]
        if per.get("protein") is not None and per["protein"] <= 0.2:
            for k in AA_KEYS:
                if per.get(k) is None:
                    per[k] = 0.0
        if per.get("fat") is not None and per["fat"] <= 0.1 and \
                per.get("la") is None:
            per["la"] = 0.0
    if a.dry_run:
        return
    with open(LIB, "w", encoding="utf-8") as f:
        json.dump(lib, f, indent=1, ensure_ascii=False)
        f.write("\n")
    with open(os.path.join(HERE, "imports", "japan_foods.json"), "w",
              encoding="utf-8") as f:
        json.dump(new, f, indent=1, ensure_ascii=False)
        f.write("\n")
    lib += [i for i in new if i["name"] not in byname]
    lib.sort(key=lambda i: i["name"].lower())
    with open(LIB, "w", encoding="utf-8") as f:
        json.dump(lib, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"library: {len(lib)} ingredients")


if __name__ == "__main__":
    sys.exit(main())
