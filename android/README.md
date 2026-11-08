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
    generator.py     the Generator screen (generator + optimiser)
    choices.py       per-food generator choices, shared by Library and Generator
    settings.py      the Settings screen (dog, feeding, stage), remembered
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

- [x] Settings tab: body weight, age + activity (suggested MER factor),
      max food per day, meals per day, IRIS stage, extended nutrients;
      remembered between launches and saved with each recipe; Daily targets
      (key nutrients per day at her energy need); Batch cooking (amounts ×
      number of meals, also on the printout)
- [x] Recipe, key nutrients vs stage targets (a food is listed once:
      adding it again changes its amount)
- [x] Full nutrient table (grouped; extended nutrients switch) and assessment
      (score, rating, energy % of target, key nutrients within range, then
      the notes); energy % of target also on every Generator result
- [x] Key nutrients, Other nutrients and Assessment can be shown or hidden
      (closed when a recipe is first shown; Key nutrients shows a count)
- [x] Save / open / delete recipes (kept on the phone)
- [x] Food check (all apps): foods toxic to dogs (Kovalkovičová et al. 2009)
      are flagged in the Library, on the Recipe screen and in the assessment,
      and never used by the generator or optimiser
- [x] Save the recipe as a library food (all apps): a meal (category
      custom) or biscuits (category treat, per 100 g baked – enter the
      baked batch weight or leave it blank to estimate; given by weight).
      Saved meals are in the Generator's food choices and are used only
      when set to Always include
- [x] Print recipe (bottom of the Recipe tab): the same A4 page as the other
      apps – opens in the browser on a computer, share sheet on a phone
- [x] Ingredient library (Library tab): search, category filter, a food's
      values per 100 g, add to recipe, edit, new food, delete; generator
      choices on each food's page (same as Generator → Food choices)
- [x] Generator tab: recipe generator (fixed base, vegetables, foods per
      recipe; food choices: leave out, always include with a minimum,
      maximum g – shared with the other apps' generator) and optimiser (lock foods; add / swap / remove; ranked
      options with Apply), progress bar and Cancel, Undo; foods left out
      via Food choices or a food's page in the Library
- [x] Writable data folder on the phone: the built app keeps the library,
      settings and saved recipes in its private storage
      (`RENALFOOD_DATA_DIR` = Flet's `FLET_APP_STORAGE_DATA`), starting from
      the bundled copies
