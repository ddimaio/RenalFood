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


def analyse(recipe, db, bw, factor, stage, extended=False):
    """Engine analysis of a recipe [[name, g], ...] for this dog."""
    need = need_kcal(bw, factor)
    ctx = rc.build_score_context(None, stage, need, bw, extended)
    return rc.analyse_recipe(recipe, db, need, stage, ctx)


def _row(r, tag):
    """(nutrient, recipe amount, per 1000 kcal, target, status, tag)."""
    target = r[8] or (f"≥ {r[9]}" if r[9] else "")
    unit = f" {r[1]}" if r[1] else ""
    return (r[0], f"{r[2]}{unit}", r[5], target, r[-1], tag)


def key_rows(a):
    """Rows for the key nutrients."""
    return [_row(r, tag) for r, tag in a["rows"] if r[0] in KEY_NUTRIENTS]


def grouped_rows(a):
    """[(group title, rows)] for every nutrient the analysis returned, in
    the groups above (empty groups left out)."""
    by_key = {_KEY_OF.get(r[0]): (r, tag) for r, tag in a["rows"]}
    out, seen = [], set()
    for title, keys in GROUPS:
        rows = [_row(*by_key[k]) for k in keys if k in by_key]
        seen.update(k for k in keys if k in by_key)
        if rows:
            out.append((title, rows))
    rest = [_row(r, tag) for r, tag in a["rows"]
            if _KEY_OF.get(r[0]) not in seen]
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
def saved_recipes():
    """{name: {"items": [[food, g], ...], "bw", "factor", "stage",
    "extended", "saved"}} kept in the engine's settings file."""
    d = rc.load_prefs().get(SAVED_KEY, {})
    return d if isinstance(d, dict) else {}


def save_recipe(name, recipe, bw, factor, stage, extended):
    p = rc.load_prefs()
    d = p.get(SAVED_KEY, {})
    d = d if isinstance(d, dict) else {}
    d[name] = {"items": [[n, g] for n, g in recipe], "bw": bw,
               "factor": factor, "stage": stage, "extended": extended,
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

    bw = ft.TextField(label="Body weight (kg)", value="6", width=170,
                      keyboard_type=ft.KeyboardType.NUMBER, dense=True)
    factor = ft.TextField(label="MER factor", value="1.6", width=110,
                          keyboard_type=ft.KeyboardType.NUMBER, dense=True)
    stage = ft.Dropdown(label="IRIS stage", value="Stage 2", width=260,
                        dense=True,
                        options=[ft.DropdownOption(key=s, text=s)
                                 for s in rc.STAGES])
    ext = ft.Switch(label="Extended nutrients", value=False)
    need_txt = ft.Text()

    food = ft.Dropdown(label="Food", enable_filter=True, editable=True,
                       expand=True, menu_height=400, dense=True,
                       options=[ft.DropdownOption(key=n, text=n)
                                for n in sorted(db, key=str.lower)])
    grams = ft.TextField(label="g/day", width=90, dense=True,
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
        b, f = num(bw, 6.0), num(factor, 1.6)
        need_txt.value = f"Daily energy need: {need_kcal(b, f):.0f} kcal"
        title.value = (f"Recipe: {state['name']}" if state["name"]
                       else "Recipe")
        items.controls = [
            ft.Row([ft.Text(f"{n}", expand=True),
                    ft.Text(f"{g:g} g"),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE,
                                  tooltip="Remove", data=i,
                                  on_click=remove)])
            for i, (n, g) in enumerate(recipe)]
        if not recipe:
            results.controls = [ft.Text("Add foods to see the nutrients.",
                                        italic=True)]
            return
        a = analyse(recipe, db, b, f, stage.value, ext.value)
        results.controls = [
            ft.Text(f"{a['mass']:.0f} g, {a['totals']['kcal']:.0f} kcal",
                    weight=ft.FontWeight.BOLD),
            ft.Text("Key nutrients", size=16, weight=ft.FontWeight.BOLD),
            nutrient_table(key_rows(a)),
            legend(),
            ft.ExpansionTile(
                title=ft.Text("All nutrients"),
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
                subtitle=ft.Text("notes for this recipe and stage",
                                 size=11),
                controls=[ft.Markdown(notes_markdown(a["notes"]),
                                      selectable=True)]),
        ]

    def add(e):
        g = num(grams, 0.0)
        name = resolve_food(food.value, food.text, db)
        if name is None or g <= 0:
            msg.value = "Pick a food and enter grams."
            return
        msg.value = ""
        recipe.append([name, g])
        food.value, food.text = None, ""    # ready for the next food
        grams.value = ""
        refresh()

    def remove(e):
        recipe.pop(e.control.data)
        refresh()

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
            save_recipe(n, recipe, num(bw, 6.0), num(factor, 1.6),
                        stage.value, ext.value)
            state["name"] = n
            page.pop_dialog()
            refresh()
            toast(f"Saved “{n}”.")
        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Save recipe"), content=name_f,
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
            recipe[:] = [[x, float(g)] for x, g in d.get("items", [])
                         if x in db]
            bw.value = f"{d.get('bw', num(bw, 6.0)):g}"
            factor.value = f"{d.get('factor', num(factor, 1.6)):g}"
            if d.get("stage") in rc.STAGES:
                stage.value = d["stage"]
            ext.value = bool(d.get("extended", ext.value))
            state["name"] = n
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

    for c in (bw, factor):
        c.on_change = refresh
    stage.on_select = refresh
    ext.on_change = refresh

    page.add(ft.SafeArea(content=ft.Column([
        ft.Text("RenalFood", size=22, weight=ft.FontWeight.BOLD),
        ft.Row([bw, factor], wrap=True), stage, ext, need_txt,
        ft.Divider(),
        ft.Row([title, ft.Row([
            ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip="Open",
                          on_click=open_list),
            ft.IconButton(icon=ft.Icons.SAVE, tooltip="Save",
                          on_click=open_save),
            ft.IconButton(icon=ft.Icons.CLEAR_ALL, tooltip="Clear",
                          on_click=clear)], spacing=0)],
               alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Row([food, grams, ft.FilledButton("Add", on_click=add)]),
        msg, items, ft.Divider(), results,
        ft.Text("Approximate tool – not veterinary advice.", size=11,
                italic=True),
    ])))
    refresh()


if __name__ == "__main__":
    ft.run(main)
