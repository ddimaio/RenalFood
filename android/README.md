# RenalFood – phone app (Flet)

The Android version of RenalFood, written in Python with
[Flet](https://flet.dev). It uses the **same calculation engine** as the
desktop and Streamlit apps (`renal_diet_calc.py` in the repo root), so
results match.

Approximate tool – not veterinary advice.

## Folder layout

```
android/
  pyproject.toml     app name, version, dependencies (flet)
  sync_engine.py     copies the engine + data files into src/ for building
  src/
    main.py          the phone app: Recipe screen + bottom navigation
    library.py       the Library screen
    improve.py       the Improve screen (generator + optimiser)
    choices.py       per-food generator choices, shared by Library and Improve
    assets/icon.png  app icon
```

`src/renal_diet_calc.py`, `src/renal_ingredients.json` and
`src/renal_references.json` are **copies** made by `sync_engine.py`; they
are not in git. Always edit the originals in the repo root.

## Run while developing

```bash
pip install "flet[all]"
cd android
flet run              # opens a window on the PC
```

`flet run` uses the repo-root engine directly – library edits made
while developing change the repo's `renal_ingredients.json`, as the
desktop app does. The built app edits its own copy on the phone. To try it on your phone
without building: install the **Flet** app from the Play Store, run
`flet run --android` (or plain `flet run` and scan the QR code) and the app
opens live on the phone, reloading as you edit.

## Build the Android app

```bash
cd android
python sync_engine.py      # copy the current engine + library into src/
flet build apk -v          # first build downloads Flutter automatically
```

The app file is `build/apk/app-release.apk`; copy it to the phone and
install it (allow installs from unknown sources). Run `flet doctor` if the
build reports a missing Android SDK or Java.

## Status

- [x] Dog settings, recipe, key nutrients vs stage targets
- [x] Full nutrient table (grouped; extended nutrients switch) and assessment notes
- [x] Save / open / delete recipes (kept on the phone)
- [x] Ingredient library (Library tab): search, category filter, a food's
      values per 100 g, add to recipe, edit, new food, delete; generator
      choices on each food's page (same as Improve → Food choices)
- [x] Improve tab: recipe generator (fixed base, vegetables, foods per
      recipe; food choices: leave out, always include with a minimum,
      maximum g – shared with the other apps' generator) and optimiser (lock foods; add / swap / remove; ranked
      options with Apply), progress bar and Cancel, Undo; foods left out
      via Food choices or a food's page in the Library
- [x] Writable data folder on the phone: the built app keeps the library,
      settings and saved recipes in its private storage
      (`RENALFOOD_DATA_DIR` = Flet's `FLET_APP_STORAGE_DATA`), starting from
      the bundled copies
