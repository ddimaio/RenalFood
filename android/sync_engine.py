#!/usr/bin/env python3
"""
sync_engine.py - copy the shared calculation engine and data files from the
repo root into src/ so `flet build` packs them into the phone app.

Only needed for building (flet build apk). While developing, `flet run`
uses the repo-root engine directly, so changes there show up at once.

    python sync_engine.py
"""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FILES = ["renal_diet_calc.py", "renal_ingredients.json", "renal_references.json"]

for name in FILES:
    src = os.path.join(ROOT, name)
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(HERE, "src", name))
        print(f"copied {name}")
    else:
        print(f"missing {name} (skipped)")
