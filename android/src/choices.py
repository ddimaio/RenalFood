"""
Per-food generator choices for the RenalFood phone app - one place for the
Library and the Generator tab's Food choices, so both show and change the
same settings: use (or leave out), always include, min g/day, max g/day.

Stored like the other apps' generator (the excluded-foods list and prefs
'gen': forced, min, max), so on a PC they are shared with the desktop and
Streamlit apps.
"""
import flet as ft

import renal_diet_calc as rc


def food_setting(name):
    """{'use', 'forced', 'min', 'max'} for one food."""
    gs = rc.load_gen_settings()
    return {"use": name not in rc.load_excluded(),
            "forced": name in gs["forced"],
            "min": gs["min"].get(name), "max": gs["max"].get(name)}


def set_food_setting(name, use=True, forced=False, min_g=None, max_g=None):
    """Store one food's choices (defaults = reset). Raises ValueError when
    min is larger than max."""
    if min_g is not None and max_g is not None and min_g > max_g:
        raise ValueError("Min g is larger than max g.")
    ex = rc.load_excluded()
    rc.save_excluded((ex - {name}) if use else (ex | {name}))
    gs = rc.load_gen_settings()
    gs["forced"] = [n for n in gs["forced"] if n != name] + \
        ([name] if forced else [])
    for key, v in (("min", min_g), ("max", max_g)):
        gs[key].pop(name, None)
        if v is not None:
            gs[key][name] = float(v)
    rc.save_gen_settings(gs)


def rename_food(old, new):
    """Carry a renamed food's choices over to its new name."""
    st = food_setting(old)
    set_food_setting(old)
    set_food_setting(new, st["use"], st["forced"], st["min"], st["max"])


def set_foods(db):
    """Foods with any non-default choice, sorted."""
    gs = rc.load_gen_settings()
    names = set(rc.load_excluded()) | set(gs["forced"]) | set(gs["min"]) \
        | set(gs["max"])
    return sorted((n for n in names if n in db), key=str.lower)


def setting_text(st):
    """'left out', 'always included · min 40 g', 'max 5 g' or 'default'."""
    parts = []
    if not st["use"]:
        parts.append("left out")
    if st["forced"]:
        parts.append("always included")
    if st["min"] is not None:
        parts.append(f"min {st['min']:g} g")
    if st["max"] is not None:
        parts.append(f"max {st['max']:g} g")
    return " · ".join(parts) or "default"


def open_dialog(page, name, on_saved=None):
    """The one dialog for changing a food's choices (Library and Generator).
    on_saved() is called after a successful save."""
    st = food_setting(name)
    use = ft.Switch(label="Use this food", value=st["use"])
    forced = ft.Checkbox(label="Always include", value=st["forced"])
    f_min = ft.TextField(label="Min g", expand=True, dense=True,
                         keyboard_type=ft.KeyboardType.NUMBER,
                         value="" if st["min"] is None else f"{st['min']:g}")
    f_max = ft.TextField(label="Max g", expand=True, dense=True,
                         keyboard_type=ft.KeyboardType.NUMBER,
                         value="" if st["max"] is None else f"{st['max']:g}")
    err = ft.Text(color=ft.Colors.RED_700, size=12)

    def save(e):
        try:
            try:
                mn = rc.to_float(f_min.value or "")
                mx = rc.to_float(f_max.value or "")
            except ValueError:
                raise ValueError("Enter numbers for min and max.")
            if (mn is not None and mn < 0) or (mx is not None and mx < 0):
                raise ValueError("Grams cannot be negative.")
            set_food_setting(name, bool(use.value), bool(forced.value),
                             mn, mx)
        except ValueError as ex:
            err.value = str(ex)
            page.update()
            return
        page.pop_dialog()
        if on_saved:
            on_saved()
    page.show_dialog(ft.AlertDialog(
        title=ft.Text(name, size=16),
        content=ft.Column([
            use, forced,
            ft.Row([f_min, f_max]),
            ft.Text("Grams per day. Used by the recipe generator (and "
                    "'Use' also by the optimiser). Min applies when the food is always "
                    "included (blank = 5 g, 0.5 g for oils/supplements). "
                    "Max caps the food whenever it is used.", size=11),
            err], tight=True),
        actions=[ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
                 ft.FilledButton("Save", on_click=save)]))
