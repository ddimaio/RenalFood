"""
RenalFood phone app (Flet): dog settings, recipe (save / open), key
nutrients, the full nutrient table and the assessment notes, using the same
calculation engine as the desktop and Streamlit apps (renal_diet_calc.py).

Run on a PC or on a phone through the Flet app (QR code):
    flet run            (from the android/ folder)
Build the Android app:
    python sync_engine.py
    flet build apk

Approximate tool - not veterinary advice.
"""
import datetime
import os
import sys

# Engine: while developing, use the repo-root copy (android/../); in the
# built app the copy made by sync_engine.py sits next to this file and its
# data (library, settings, saved recipes) goes to the app's private,
# writable storage folder.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
if os.path.exists(os.path.join(_ROOT, "renal_diet_calc.py")):
    sys.path.insert(0, _ROOT)
elif os.environ.get("FLET_APP_STORAGE_DATA"):
    os.environ.setdefault("RENALFOOD_DATA_DIR",
                          os.environ["FLET_APP_STORAGE_DATA"])

import flet as ft                      # noqa: E402
import renal_diet_calc as rc           # noqa: E402
from library import LibraryView        # noqa: E402
from generator import GeneratorView        # noqa: E402
from settings import Dog, SettingsView  # noqa: E402

KEY_NUTRIENTS = ["Energy", "Protein", "Fat", "Phosphorus", "Calcium",
                 "Sodium", "Potassium", "EPA + DHA"]
_KEY_OF = {label: k for k, label, _ in rc.NUTRIENTS}
GROUPS = [
    ("Main nutrients and minerals",
     ["kcal", "water", "protein", "fat", "carb", "fibre", "ca", "p", "na",
      "k", "mg"]),
    ("Vitamins", ["vit_a", "b1", "b2", "b3", "b5", "b6", "b12", "folate",
                  "choline", "vit_d", "vit_e", "vit_c"]),
    ("Other", ["epa_dha", "oxalate", "base_meq", "p_bind"]),
    ("Extended: amino acids, linoleic acid, trace minerals",
     list(getattr(rc, "EXT_KEYS", []))),
]
SAVED_KEY = "phone_recipes"            # in the engine's settings file


# ---------------------------------------------------------------- logic
def need_kcal(bw, factor):
    """Daily energy need (MER) in kcal."""
    return rc.mer(bw, factor)


def analyse(recipe, db, bw, factor, stage, extended=False, max_g=None,
            meals=1):
    """Engine analysis of a recipe [[name, g], ...] for this dog."""
    need = need_kcal(bw, factor)
    ctx = rc.build_score_context(None, stage, need, bw, extended,
                                 max_g or None)
    return rc.analyse_recipe(recipe, db, need, stage, ctx, meals)


def _row(r, tag):
    """(nutrient, recipe amount, per 1000 kcal, target, status, tag)."""
    target = r[8] or (f"≥ {r[9]}" if r[9] else "")
    unit = f" {r[1]}" if r[1] else ""
    return (r[0], f"{r[2]}{unit}", r[5], target, r[-1], tag)


def key_rows(a):
    """Rows for the key nutrients."""
    return [_row(r, tag) for r, tag in a["rows"] if r[0] in KEY_NUTRIENTS]


def key_summary(rows):
    """'6 on target · 1 above · 1 below' for the collapsed Key nutrients."""
    syms = [short_status(r[4]) for r in rows]
    parts = [(sum(x.startswith(c) for x in syms), w) for c, w in
             (("✓", "on target"), ("↑", "above"), ("↓", "below"))]
    return " · ".join(f"{n} {w}" for n, w in parts if n) or "no targets"


def key_in_range(rows):
    """(in range, with a target, [out-of-range names with ↑/↓])."""
    rated = [(r[0], short_status(r[4])) for r in rows if short_status(r[4])]
    ok = sum(sym.startswith("✓") for _, sym in rated)
    off = [f"{n} {sym.rstrip('?')}" for n, sym in rated
           if not sym.startswith("✓")]
    return ok, len(rated), off


def assessment_markdown(a):
    """Score, rating and key nutrients in range, then the engine's notes."""
    lines = []
    extra = {lbl.split(" (")[0]: note for lbl, _, _, note in
             a.get("summary", []) if lbl.startswith(("Score", "Rating"))}
    if a.get("score") is not None:
        lines.append(f"- **Score {a['score']:.3f}** (0 = every target met)"
                     + (f" – {extra['Score']}" if extra.get("Score") else ""))
    if a.get("rating") is not None:
        lines.append(f"- **Rating {a['rating']:.0f}/100** (higher = better)"
                     + (f" – {extra['Rating']}" if extra.get("Rating")
                        else ""))
    if a.get("energy_text"):
        hint = {"ok": "", "warn": " – a little off: scale the recipe",
                "bad": " – scale the recipe (the score counts this too)"}
        lines.append(f"- **{a['energy_text']}**"
                     + hint.get(a.get("energy_tag"), ""))
    ok, n, off = key_in_range(key_rows(a))
    if n:
        lines.append(f"- **Key nutrients within range: {ok} of {n}**"
                     + (" – outside: " + ", ".join(off) if off else ""))
    head = "\n".join(lines)
    notes = notes_markdown(a.get("notes"))
    return head + ("\n\n" + notes if head and notes else notes)


def assessment_subtitle(a):
    """'score 0.012 · rating 81/100 · 7/8 key nutrients in range'."""
    parts = []
    if a.get("score") is not None:
        parts.append(f"score {a['score']:.3f}")
    if a.get("rating") is not None:
        parts.append(f"rating {a['rating']:.0f}/100")
    if a.get("energy_text"):
        parts.append(a["energy_text"].split(" (")[0].replace(
            "Energy", "energy").replace(" of target", ""))
    ok, n, _ = key_in_range(key_rows(a))
    if n:
        parts.append(f"{ok}/{n} key nutrients in range")
    return " · ".join(parts) or "notes for this recipe and stage"


def grouped_rows(a):
    """[(group title, rows)] for every nutrient the analysis returned except
    the key nutrients (shown in their own table), in the groups above
    (empty groups left out)."""
    by_key = {_KEY_OF.get(r[0]): (r, tag) for r, tag in a["rows"]
              if r[0] not in KEY_NUTRIENTS}
    out, seen = [], set()
    for title, keys in GROUPS:
        rows = [_row(*by_key[k]) for k in keys if k in by_key]
        seen.update(k for k in keys if k in by_key)
        if rows:
            out.append((title, rows))
    rest = [_row(r, tag) for r, tag in a["rows"]
            if _KEY_OF.get(r[0]) not in seen and r[0] not in KEY_NUTRIENTS]
    if rest:
        out.append(("More", rest))
    return out


def notes_markdown(notes):
    """Engine assessment notes ('• ' bullets) as Markdown."""
    lines = []
    for ln in (notes or "").splitlines():
        if ln.startswith("• "):
            lines.append("- " + ln[2:])
        else:
            lines.append(ln + ("  " if ln else ""))
    return "\n".join(lines)


def short_status(text):
    """Phone-width status: ✓ ok, ↑ above, ↓ below, ? data missing/assumed."""
    t = text or ""
    sym = ("↑" if "above" in t else "↓" if "below" in t else
           "✓" if t else "")
    if "missing" in t or "assumed" in t:
        sym += "?"
    return sym


def resolve_food(value, text, names):
    """The food meant by the picker: its selected value, else the typed
    text if it names exactly one food (exact match first)."""
    if value in names:
        return value
    t = (text or value or "").strip().lower()
    if not t:
        return None
    exact = [n for n in names if n.lower() == t]
    if exact:
        return exact[0]
    hits = [n for n in names if t in n.lower()]
    return hits[0] if len(hits) == 1 else None


# ---- saved recipes (same item format as the desktop/Streamlit files)
def print_html(recipe, db, dog, title="", batch=1):
    """The printable page (A4, same as the desktop and web apps); batch > 1
    adds a column for cooking that many meals (amount ÷ meals/day × batch)."""
    need = dog.need()
    ctx = rc.build_score_context(None, dog.stage, need, dog.bw, dog.extended,
                                 dog.max_g or None)
    return rc.recipe_print_html(
        recipe, db, need, dog.stage, ctx, dog.meals, bw=dog.bw,
        factor=dog.factor, title=title or "Renal diet recipe", batch=batch)


def print_file_name(title):
    safe = "".join(c if c.isalnum() else "_" for c in (title or "recipe"))
    return f"{safe.strip('_') or 'recipe'}_{datetime.date.today():%Y-%m-%d}.html"


def saved_recipes():
    """{name: {"items": [[food, g], ...], "bw", "factor", "stage",
    "extended", "saved"}} kept in the engine's settings file."""
    d = rc.load_prefs().get(SAVED_KEY, {})
    return d if isinstance(d, dict) else {}


def save_recipe(name, recipe, dog_values):
    """Store a recipe with the dog settings it was made for (same keys as
    the desktop/Streamlit recipe files: bw, age, activity, factor, max_g,
    meals, stage) plus 'extended'."""
    p = rc.load_prefs()
    d = p.get(SAVED_KEY, {})
    d = d if isinstance(d, dict) else {}
    d[name] = {"items": [[n, g] for n, g in recipe], **dog_values,
               "saved": datetime.date.today().isoformat()}
    p[SAVED_KEY] = d
    rc.save_prefs(p)


def delete_recipe(name):
    p = rc.load_prefs()
    d = p.get(SAVED_KEY, {})
    if isinstance(d, dict) and name in d:
        del d[name]
        p[SAVED_KEY] = d
        rc.save_prefs(p)


# ---------------------------------------------------------------- screen
TAG_COLOUR = {"ok": ft.Colors.GREEN_800, "warn": ft.Colors.ORANGE_800,
              "bad": ft.Colors.RED_700}
STATUS_ICON = {"✓": ft.Icons.CHECK, "↑": ft.Icons.ARROW_UPWARD,
               "↓": ft.Icons.ARROW_DOWNWARD}
COLUMNS = ("Nutrient", "Recipe", "/1000 kcal", "Target", "")


def status_cell(text, tag):
    """Status as an icon (fonts may lack ✓) plus '?' when data is missing
    or assumed; the full text shows as a tooltip (long press)."""
    sym = short_status(text)
    colour = TAG_COLOUR.get(tag)
    parts = [ft.Icon(STATUS_ICON[sym[0]], size=18, color=colour)] \
        if sym[:1] in STATUS_ICON else []
    if sym.endswith("?"):
        parts.append(ft.Text("?", weight=ft.FontWeight.BOLD, color=colour))
    return ft.DataCell(ft.Row(parts, spacing=0, tooltip=text or None))


def nutrient_table(rows):
    return ft.Row(scroll=ft.ScrollMode.AUTO, controls=[ft.DataTable(
        column_spacing=8, data_row_min_height=36,
        columns=[ft.DataColumn(ft.Text(c)) for c in COLUMNS],
        rows=[ft.DataRow(cells=[
            ft.DataCell(ft.Text(n)), ft.DataCell(ft.Text(amt)),
            ft.DataCell(ft.Text(p1000)), ft.DataCell(ft.Text(tgt)),
            status_cell(st, tag)])
            for n, amt, p1000, tgt, st, tag in rows])])


def legend():
    return ft.Row([ft.Icon(ft.Icons.CHECK, size=14),
                   ft.Text("in range", size=11),
                   ft.Icon(ft.Icons.ARROW_UPWARD, size=14),
                   ft.Text("high", size=11),
                   ft.Icon(ft.Icons.ARROW_DOWNWARD, size=14),
                   ft.Text("low", size=11),
                   ft.Text("? data missing or assumed · long-press a status "
                           "for details", size=11)],
                  wrap=True, spacing=4)


def main(page: ft.Page):
    page.title = "RenalFood"
    page.scroll = ft.ScrollMode.AUTO
    page.padding = 12
    db = rc.load_db()
    recipe = []
    state = {"name": ""}                       # name of the open recipe
    # Key / Other / Assessment sections: closed when a recipe is first
    # shown (new, opened or applied); kept as they are while it is edited
    opened = {"key": False, "all": False, "notes": False}

    def close_sections():
        opened.update(dict.fromkeys(opened, False))

    def tile_toggled(key):
        def f(e):
            opened[key] = bool(e.data) if isinstance(e.data, bool) \
                else str(e.data).lower() == "true"
        return f

    dog = Dog()                                # Settings tab values
    need_txt = ft.Text(size=12, expand=True)

    food = ft.Dropdown(label="Food", enable_filter=True, editable=True,
                       expand=5, menu_height=400, dense=True)

    def load_food_options():
        food.options = [ft.DropdownOption(key=n, text=n)
                        for n in sorted(db, key=str.lower)]
    load_food_options()
    grams = ft.TextField(label="g/day", expand=3, dense=True,
                         keyboard_type=ft.KeyboardType.NUMBER)
    title = ft.Text(weight=ft.FontWeight.BOLD)
    items = ft.Column(spacing=0)
    results = ft.Column()
    msg = ft.Text(color=ft.Colors.RED_700)

    def num(field, default):
        try:
            return float(str(field.value).replace(",", "."))
        except (TypeError, ValueError):
            return default

    def toast(text):
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    def refresh(e=None):
        need_txt.value = dog.summary()
        title.value = (f"Recipe: {state['name']}" if state["name"]
                       else "Recipe")
        per_meal = dog.meals > 1
        items.controls = [
            ft.Row([ft.Text(f"{n}", expand=1),
                    ft.Text(f"{g:g} g{rc.units_note(n, g)}"
                            + (("\n" if rc.units_note(n, g) else " · ")
                               + f"{g / dog.meals:.1f}/meal"
                               f"{rc.units_note(n, g / dog.meals)}"
                               if per_meal else ""), expand=1,
                            text_align=ft.TextAlign.RIGHT),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE,
                                  tooltip="Remove", data=i,
                                  on_click=remove)])
            for i, (n, g) in enumerate(recipe)]
        if not recipe:
            close_sections()                 # the next recipe starts closed
            results.controls = [ft.Text("Add foods to see the nutrients.",
                                        italic=True)]
            return
        a = analyse(recipe, db, dog.bw, dog.factor, dog.stage,
                    dog.extended, dog.max_g, dog.meals)
        over = dog.max_g and a["mass"] > dog.max_g
        tox = rc.toxic_foods_in(n for n, _ in recipe)
        results.controls = [
            ft.Text(f"{a['mass']:.0f} g, {a['totals']['kcal']:.0f} kcal"
                    + (f" · {a['mass'] / dog.meals:.0f} g per meal"
                       if per_meal else ""),
                    weight=ft.FontWeight.BOLD),
            ft.Text(f"More than the {dog.max_g:g} g/day food limit.",
                    color=ft.Colors.ORANGE_800, size=12) if over
            else ft.Container(),
            ft.Text("⚠ Toxic for dogs – remove: " + "; ".join(
                f"{n} ({t})" for n, lv, t in tox if lv == "toxic"),
                color=ft.Colors.RED_700, weight=ft.FontWeight.BOLD,
                size=13) if any(lv == "toxic" for _, lv, _ in tox)
            else ft.Container(),
            ft.ExpansionTile(
                title=ft.Text("Key nutrients", weight=ft.FontWeight.BOLD),
                subtitle=ft.Text(key_summary(key_rows(a)), size=11),
                expanded=opened["key"], on_change=tile_toggled("key"),
                controls=[ft.Column([nutrient_table(key_rows(a)),
                                     legend()])]),
            ft.ExpansionTile(
                title=ft.Text("Other nutrients"),
                expanded=opened["all"], on_change=tile_toggled("all"),
                subtitle=ft.Text("per recipe and per 1000 kcal vs targets",
                                 size=11),
                controls=[ft.Column([
                    ft.Text("Swipe a table sideways for targets and status.",
                            size=11, italic=True)] + [
                    c for gt, rows in grouped_rows(a) for c in (
                        ft.Text(gt, weight=ft.FontWeight.BOLD),
                        nutrient_table(rows))])]),
            ft.ExpansionTile(
                title=ft.Text("Assessment"),
                expanded=opened["notes"], on_change=tile_toggled("notes"),
                subtitle=ft.Text(assessment_subtitle(a), size=11),
                controls=[ft.Markdown(assessment_markdown(a),
                                      selectable=True)]),
        ]

    def add(e):
        g = num(grams, 0.0)
        name = resolve_food(food.value, food.text, db)
        if name is None or g <= 0:
            msg.value = "Pick a food and enter grams."
            return
        msg.value = ""
        note = put_food(name, g)
        food.value, food.text = None, ""    # ready for the next food
        grams.value = ""
        refresh()
        page.update()                       # before the message pops up
        if note:
            toast(note)

    def put_food(name, g):
        """Add a food, or change its amount if it is already in the recipe
        (a food is never listed twice). Returns what happened (with a
        warning if the food is toxic for dogs)."""
        warn = rc.toxic_warning(name)
        for r in recipe:
            if r[0] == name:
                old, r[1] = r[1], g
                return (f"{name} is already in the recipe – amount changed "
                        f"from {old:g} g to {g:g} g." + (f" {warn}"
                                                       if warn else ""))
        recipe.append([name, g])
        return warn

    def remove(e):
        recipe.pop(e.control.data)
        refresh()

    # ---- print: the same A4 page as the other apps. Computer: opens in the
    # web browser (print from there); phone: share sheet (open in Chrome /
    # save / send, then print); web: downloads the page.
    file_picker = ft.FilePicker()
    share = ft.Share()

    def open_batch(e):
        """Every amount × the number of meals to prepare (the recipe is
        not changed); Print then adds the batch column."""
        if not recipe:
            toast("Add foods first.")
            return
        n_f = ft.TextField(label="Number of meals to prepare",
                           value=str(state.get("batch", 1)), width=220,
                           keyboard_type=ft.KeyboardType.NUMBER)
        table = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, height=300)

        def fill(_=None):
            try:
                n = max(1, min(60, int(float(n_f.value))))
            except (TypeError, ValueError):
                n = 1
            state["batch"] = n
            mpd = max(1, int(dog.meals or 1))
            m = sum(g for _, g in recipe) / mpd
            rows = [ft.Text((f"One meal = the day recipe ÷ {mpd} meals a "
                             "day. " if mpd > 1 else "")
                            + f"Cook {m * n:.0f} g in total, split into {n} "
                            f"portions of {m:.0f} g.", size=12,
                            weight=ft.FontWeight.BOLD)]
            for nm, g in recipe:
                g = g / mpd
                u = rc.household_units(nm, g * n)
                rows.append(ft.Row([
                    ft.Text(nm, size=12, expand=True),
                    ft.Text(f"{g:.0f} → {g * n:.0f} g" + (f" ({u})" if u
                                                        else ""),
                            size=12, weight=ft.FontWeight.BOLD)]))
            table.controls = rows
            page.update()
        n_f.on_change = fill
        fill()

        async def do_print(e):
            page.pop_dialog()
            await send_page(rc.batch_print_html(
                recipe, db, state.get("batch", 1), meals=dog.meals,
                title=state["name"] or "Batch cooking"),
                "batch_cooking.html", state["name"] or "Batch cooking")
        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Batch cooking"),
            content=ft.Column([n_f, table], tight=True, width=420),
            actions=[ft.TextButton("Close",
                                   on_click=lambda e: page.pop_dialog()),
                     ft.FilledButton("Print batch sheet",
                                     on_click=do_print)]))

    async def print_recipe(e):
        if not recipe:
            toast("Add foods first.")
            return
        html_ = print_html(recipe, db, dog, state["name"],
                           state.get("batch", 1))
        await send_page(html_, print_file_name(state["name"]),
                        state["name"] or "Renal diet recipe")

    async def send_page(html_, name, subject):
        data = html_.encode("utf-8")
        try:
            if page.web:
                await file_picker.save_file(file_name=name, src_bytes=data,
                                            allowed_extensions=["html"])
            elif page.platform in (ft.PagePlatform.ANDROID,
                                   ft.PagePlatform.IOS):
                await share.share_files(
                    [ft.ShareFile.from_bytes(data, mime_type="text/html",
                                             name=name)],
                    subject=subject,
                    text="Open in a web browser to print.")
            else:
                import pathlib
                import tempfile
                import webbrowser
                fd, path = tempfile.mkstemp(suffix=".html",
                                            prefix="recipe_print_")
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                webbrowser.open(pathlib.Path(path).resolve().as_uri())
                toast("Opened in your web browser – print from there.")
        except Exception as ex:                     # keep the app alive
            toast(f"Could not print: {ex}")

    def clear(e):
        recipe.clear()
        state["name"] = ""
        refresh()

    # ---- save / open
    def open_save(e):
        if not recipe:
            toast("Add foods first.")
            return
        name_f = ft.TextField(label="Name", value=state["name"],
                              autofocus=True)

        def do_save(e):
            n = (name_f.value or "").strip()
            if not n:
                name_f.error = "Enter a name"
                return
            save_recipe(n, recipe, dog.values())
            state["name"] = n
            page.pop_dialog()
            refresh()
            toast(f"Saved “{n}”.")
        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Save recipe"), content=name_f,
            actions=[ft.TextButton("Cancel",
                                   on_click=lambda e: page.pop_dialog()),
                     ft.FilledButton("Save", on_click=do_save)]))

    def open_save_food(e):
        """Save the recipe as one library food: a meal ('custom') or
        biscuits ('treat', per 100 g baked)."""
        if not recipe:
            toast("Add foods first.")
            return
        name_f = ft.TextField(label="Name", value=state["name"],
                              autofocus=True)
        kind = ft.RadioGroup(value="custom", content=ft.Column([
            ft.Radio(value="custom", label="Meal (custom)"),
            ft.Radio(value="treat", label="Biscuits (treat)")], spacing=0))
        n_f = ft.TextField(label="Batch weight after baking, g "
                           "(blank = estimate)", value="",
                           keyboard_type=ft.KeyboardType.NUMBER,
                           visible=False)

        def kind_changed(e):
            n_f.visible = kind.value == "treat"
            page.update()
        kind.on_change = kind_changed
        err = ft.Text(color=ft.Colors.RED_700, size=12)

        def do_save(e):
            nm = (name_f.value or "").strip()
            try:
                if not nm:
                    raise ValueError("Enter a name.")
                if nm in db:
                    raise ValueError(f"“{nm}” is already in the library – "
                                     "choose another name.")
                k = kind.value or "custom"
                n = None
                if k == "treat" and (n_f.value or "").strip():
                    try:
                        n = float(n_f.value)
                    except (TypeError, ValueError):
                        raise ValueError("Enter the baked weight in g, "
                                         "or leave it blank.")
                    n = n if n > 0 else None
                db[nm] = rc.recipe_to_ingredient(recipe, db, nm, k, n)
                rc.save_db(db)
            except ValueError as ex:
                err.value = str(ex)
                page.update()
                return
            page.pop_dialog()
            library_changed()
            toast(f"Saved “{nm}” to the library (category {k}).")
        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Save as a library food"),
            content=ft.Column([
                name_f, kind, n_f,
                ft.Text("Saved as one food: a meal per 100 g of the mix, "
                        "biscuits per 100 g baked (given by weight). It "
                        "can be added to recipes. A saved meal is in the "
                        "Generator's food choices and is used only when "
                        "set to Always include.", size=11),
                err], tight=True),
            actions=[ft.TextButton("Cancel",
                                   on_click=lambda e: page.pop_dialog()),
                     ft.FilledButton("Save", on_click=do_save)]))

    def open_list(e):
        saved = saved_recipes()
        if not saved:
            toast("No saved recipes yet.")
            return

        def do_open(e):
            n = e.control.data
            d = saved_recipes().get(n, {})
            missing = [x for x, _ in d.get("items", []) if x not in db]
            recipe[:] = [[x, float(g)] for x, g in rc.merge_duplicates(
                [(x, g) for x, g in d.get("items", []) if x in db])]
            dog.update({k: v for k, v in d.items()
                        if k not in ("items", "saved", "name")})
            settings_view.load()                 # Settings tab shows them
            state["name"] = n
            close_sections()
            page.pop_dialog()
            refresh()
            if missing:
                toast("Not in the library (skipped): " + ", ".join(missing))

        def do_delete(e):
            delete_recipe(e.control.data)
            page.pop_dialog()
            open_list(None)
        rows = [ft.Row([
            ft.TextButton(f"{n}  ({d.get('saved', '')})", data=n,
                          on_click=do_open, expand=True),
            ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip="Delete",
                          data=n, on_click=do_delete)])
            for n, d in sorted(saved.items(), key=lambda kv: kv[0].lower())]
        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Open recipe"),
            content=ft.Container(
                ft.Column(rows, spacing=0, scroll=ft.ScrollMode.AUTO),
                width=320, height=min(52 * len(rows) + 8, 400)),
            actions=[ft.TextButton("Close",
                                   on_click=lambda e: page.pop_dialog())]))

    # ---- library screen (shares db and recipe with this screen)
    def library_changed():
        load_food_options()
        refresh()

    def add_from_library(name, g):
        note = put_food(name, g)
        refresh()
        page.update()
        return note or f"Added {g:g} g of {name} to the recipe."

    library = LibraryView(page, db, recipe, lambda: bool(dog.extended),
                          library_changed, add_from_library)

    # ---- generator screen (optimiser + generator)
    undo_stack = []

    def settings():
        return dog.as_tuple()

    def apply_result(rows, label):
        undo_stack.append(([list(r) for r in recipe], state["name"]))
        recipe[:] = [list(r) for r in rc.merge_duplicates(rows)]
        state["name"] = ""
        close_sections()
        refresh()
        generator.show()

    def undo():
        if not undo_stack:
            return False
        rows, name = undo_stack.pop()
        recipe[:] = rows
        state["name"] = name
        refresh()
        generator.show()
        return True

    generator = GeneratorView(page, db, recipe, settings, apply_result, undo)

    # ---- settings screen
    def dog_changed():
        refresh()

    settings_view = SettingsView(page, dog, dog_changed)

    def go_settings(e=None):
        page.navigation_bar.selected_index = 3
        switch(None)

    recipe_view = ft.Column([
        ft.Text("RenalFood", size=22, weight=ft.FontWeight.BOLD),
        ft.Row([ft.Icon(ft.Icons.PETS, size=16), need_txt,
                ft.TextButton("Settings", icon=ft.Icons.SETTINGS,
                              on_click=go_settings)]),
        ft.Divider(),
        ft.Row([title, ft.Row([
            ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip="Open",
                          on_click=open_list),
            ft.IconButton(icon=ft.Icons.SAVE, tooltip="Save",
                          on_click=open_save),
            ft.IconButton(icon=ft.Icons.LIBRARY_ADD,
                          tooltip="Save as a library food",
                          on_click=open_save_food),
            ft.IconButton(icon=ft.Icons.CLEAR_ALL, tooltip="Clear",
                          on_click=clear)], spacing=0)],
               alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Row([food, grams, ft.FilledButton("Add", on_click=add)]),
        msg, items, ft.Divider(), results,
        ft.Row([ft.OutlinedButton("Print recipe", icon=ft.Icons.PRINT,
                                  on_click=print_recipe),
                ft.OutlinedButton("Batch cooking", icon=ft.Icons.KITCHEN,
                                  on_click=open_batch)], wrap=True),
        ft.Text("Approximate tool – not veterinary advice.", size=11,
                italic=True),
    ])
    # All four screens stay on the page and only the selected one is
    # visible: changing a screen while it was detached (e.g. the recipe
    # replaced from the Generator) could show its rows twice.
    views = [recipe_view, library.root, generator.root, settings_view.root]
    for v in views[1:]:
        v.visible = False
    body = ft.Column(views)

    def switch(e):
        i = page.navigation_bar.selected_index
        for k, v in enumerate(views):
            v.visible = k == i
        if i == 1:
            library.show_list()
        elif i == 2:
            generator.show()
        page.update()
        page.run_task(page.scroll_to, offset=0)      # each tab from the top
    page.navigation_bar = ft.NavigationBar(
        selected_index=0, on_change=switch,
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.RESTAURANT,
                                        label="Recipe"),
            ft.NavigationBarDestination(icon=ft.Icons.MENU_BOOK,
                                        label="Library"),
            ft.NavigationBarDestination(icon=ft.Icons.AUTO_AWESOME,
                                        label="Generator"),
            ft.NavigationBarDestination(icon=ft.Icons.SETTINGS,
                                        label="Settings")])
    page.add(ft.SafeArea(content=body))
    refresh()


if __name__ == "__main__":
    ft.run(main)
