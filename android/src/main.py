"""
RenalFood phone app (Flet). First screen: dog settings, recipe and key
nutrients, using the same calculation engine as the desktop and Streamlit
apps (renal_diet_calc.py).

Run on a PC or on a phone through the Flet app (QR code):
    flet run            (from the android/ folder)
Build the Android app:
    python sync_engine.py
    flet build apk

Approximate tool - not veterinary advice.
"""
import os
import sys

# Engine: while developing, use the repo-root copy (android/../); in the
# built app the copy made by sync_engine.py sits next to this file.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
if os.path.exists(os.path.join(_ROOT, "renal_diet_calc.py")):
    sys.path.insert(0, _ROOT)

import flet as ft                      # noqa: E402
import renal_diet_calc as rc           # noqa: E402

KEY_NUTRIENTS = ["Energy", "Protein", "Fat", "Phosphorus", "Calcium",
                 "Sodium", "Potassium", "EPA + DHA"]


# ---------------------------------------------------------------- logic
def need_kcal(bw, factor):
    """Daily energy need (MER) in kcal."""
    return rc.mer(bw, factor)


def analyse(recipe, db, bw, factor, stage):
    """Engine analysis of a recipe [[name, g], ...] for this dog."""
    need = need_kcal(bw, factor)
    ctx = rc.build_score_context(None, stage, need, bw)
    return rc.analyse_recipe(recipe, db, need, stage, ctx)


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


def key_rows(a):
    """(nutrient, per day as fed, per 1000 kcal, target, status) for the
    key nutrients."""
    out = []
    for r, tag in a["rows"]:
        if r[0] in KEY_NUTRIENTS:
            target = r[8] or (f"≥ {r[9]}" if r[9] else "")
            out.append((r[0], f"{r[2]} {r[1]}", r[5], target, r[-1], tag))
    return out


# ---------------------------------------------------------------- screen
TAG_COLOUR = {"ok": ft.Colors.GREEN_800, "warn": ft.Colors.ORANGE_800,
              "bad": ft.Colors.RED_700}
STATUS_ICON = {"✓": ft.Icons.CHECK, "↑": ft.Icons.ARROW_UPWARD,
               "↓": ft.Icons.ARROW_DOWNWARD}


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


def main(page: ft.Page):
    page.title = "RenalFood"
    page.scroll = ft.ScrollMode.AUTO
    page.padding = 12
    db = rc.load_db()
    recipe = []

    bw = ft.TextField(label="Body weight (kg)", value="6", width=140,
                      keyboard_type=ft.KeyboardType.NUMBER, dense=True)
    factor = ft.TextField(label="MER factor", value="1.6", width=110,
                          keyboard_type=ft.KeyboardType.NUMBER, dense=True)
    stage = ft.Dropdown(label="IRIS stage", value="Stage 2", width=260,
                        dense=True,
                        options=[ft.DropdownOption(key=s, text=s)
                                 for s in rc.STAGES])
    need_txt = ft.Text()

    food = ft.Dropdown(label="Food", enable_filter=True, editable=True,
                       expand=True, menu_height=400, dense=True,
                       options=[ft.DropdownOption(key=n, text=n)
                                for n in sorted(db, key=str.lower)])
    grams = ft.TextField(label="g/day", width=90, dense=True,
                         keyboard_type=ft.KeyboardType.NUMBER)
    items = ft.Column(spacing=0)
    table = ft.Column()
    msg = ft.Text(color=ft.Colors.RED_700)

    def num(field, default):
        try:
            return float(str(field.value).replace(",", "."))
        except (TypeError, ValueError):
            return default

    def refresh(e=None):
        b, f = num(bw, 6.0), num(factor, 1.6)
        need_txt.value = f"Daily energy need: {need_kcal(b, f):.0f} kcal"
        items.controls = [
            ft.Row([ft.Text(f"{n}", expand=True),
                    ft.Text(f"{g:g} g"),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE,
                                  tooltip="Remove", data=i,
                                  on_click=remove)])
            for i, (n, g) in enumerate(recipe)]
        if not recipe:
            table.controls = [ft.Text("Add foods to see the nutrients.",
                                      italic=True)]
            return
        a = analyse(recipe, db, b, f, stage.value)
        rows = [ft.DataRow(cells=[
            ft.DataCell(ft.Text(n)), ft.DataCell(ft.Text(day)),
            ft.DataCell(ft.Text(p1000)), ft.DataCell(ft.Text(tgt)),
            status_cell(st, tag)])
            for n, day, p1000, tgt, st, tag in key_rows(a)]
        table.controls = [
            ft.Text(f"Recipe: {a['mass']:.0f} g, "
                    f"{a['totals']['kcal']:.0f} kcal", weight=ft.FontWeight.BOLD),
            ft.Row(scroll=ft.ScrollMode.AUTO, controls=[ft.DataTable(
                column_spacing=10, columns=[
                    ft.DataColumn(ft.Text(c)) for c in
                    ("Nutrient", "Recipe", "/1000 kcal", "Target", "")],
                rows=rows)]),
            ft.Row([ft.Icon(ft.Icons.CHECK, size=14), ft.Text("in range", size=11),
                    ft.Icon(ft.Icons.ARROW_UPWARD, size=14), ft.Text("high", size=11),
                    ft.Icon(ft.Icons.ARROW_DOWNWARD, size=14), ft.Text("low", size=11),
                    ft.Text("? data missing or assumed", size=11)],
                   wrap=True, spacing=4)]

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

    for c in (bw, factor):
        c.on_change = refresh
    stage.on_select = refresh

    page.add(ft.SafeArea(content=ft.Column([
        ft.Text("RenalFood", size=22, weight=ft.FontWeight.BOLD),
        ft.Row([bw, factor], wrap=True), stage, need_txt,
        ft.Divider(),
        ft.Row([food, grams, ft.FilledButton("Add", on_click=add)]),
        msg, items, ft.Divider(), table,
        ft.Text("Approximate tool – not veterinary advice.", size=11,
                italic=True),
    ])))
    refresh()


if __name__ == "__main__":
    ft.run(main)
