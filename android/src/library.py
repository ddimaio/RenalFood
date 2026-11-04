"""
Ingredient library screen for the RenalFood phone app: browse and search
foods, see a food's values per 100 g, add it to the recipe, edit it, add a
new food or delete one. Changes are saved through the shared engine
(rc.save_db), so the desktop and Streamlit apps see the same library when
they share the file.
"""
import flet as ft

import renal_diet_calc as rc

CATEGORIES = ["food", "supplement", "binder", "commercial food", "imported"]
HIDDEN_KEYS = ("base_meq", "p_bind")       # technical; edited in other apps
GROUPS = [
    ("Main nutrients and minerals",
     ["kcal", "water", "protein", "fat", "carb", "fibre", "ca", "p", "na",
      "k", "mg"]),
    ("Vitamins", ["vit_a", "b1", "b2", "b3", "b5", "b6", "b12", "folate",
                  "choline", "vit_d", "vit_e", "vit_c"]),
    ("Other", ["epa_dha", "oxalate"]),
    ("Extended: amino acids, linoleic acid, trace minerals",
     list(getattr(rc, "EXT_KEYS", []))),
]
EXTRA_FIELDS = ("piece_g",)                # kept as they are when editing


# ---------------------------------------------------------------- logic
def filter_foods(db, query="", category="all"):
    """Food names matching the search text (all words, any order) and the
    category, sorted by name."""
    words = (query or "").lower().split()
    out = []
    for n, it in db.items():
        if category not in ("all", None, "") and it["category"] != category:
            continue
        hay = (n + " " + it.get("note", "")).lower()
        if all(w in n.lower() or w in hay for w in words):
            out.append(n)
    return sorted(out, key=str.lower)


def visible_keys(extended):
    """Nutrient keys shown/edited on the phone, grouped like GROUPS."""
    return [(title, [k for k in keys if k in rc.KEYS])
            for title, keys in GROUPS
            if keys and (extended or not title.startswith("Extended"))]


def value_text(item, k):
    """'12.5 mg', '≈3.2 mg (AAFCO min assumed)' or 'unknown'."""
    v = item["per100g"].get(k)
    unit = rc.UNIT.get(k, "")
    if v is not None:
        return f"{rc.fmt(v)} {unit}".strip()
    a = rc.assumed_value(item, k)
    if a is not None:
        return f"≈{rc.fmt(a)} {unit} (AAFCO min assumed)".strip()
    return "unknown"


def build_item(old, name, category, note, role, max_dose, assume, values):
    """A library item from the edit form. `values` maps nutrient keys to
    text ('' = unknown); keys not in `values` keep their old value. Raises
    ValueError naming the first invalid field."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Name is required.")
    per = dict((old or {}).get("per100g", {}))
    for k, txt in values.items():
        try:
            per[k] = rc.to_float(txt)
        except ValueError:
            raise ValueError(f"Invalid number for {rc.LABEL[k]}.")
    if per.get("kcal") is None:
        raise ValueError("Energy (kcal) is required.")
    item = {"name": name, "category": category or "food",
            "note": (note or "").strip(), "per100g": per,
            "assume_aafco": bool(assume),
            "role": role if role in rc.ROLES else None,
            "max_dose": (max_dose or "").strip() or None}
    for f in EXTRA_FIELDS:
        if old and f in old:
            item[f] = old[f]
    if item["max_dose"]:
        try:
            rc.parse_max_dose(item["max_dose"])
        except ValueError:
            raise ValueError("Recommended max: write e.g. 7, 0.18/kg or "
                             "5:4, 10:8.")
    return rc.normalise(item)


def store_item(db, recipe, old_name, item):
    """Put `item` in the library (replacing `old_name` when renamed), update
    the recipe's names, and save. Returns the stored name."""
    new = item["name"]
    if old_name and old_name != new:
        if new in db:
            raise ValueError(f"'{new}' already exists.")
        db.pop(old_name, None)
        for row in recipe:
            if row[0] == old_name:
                row[0] = new
    elif not old_name and new in db:
        raise ValueError(f"'{new}' already exists.")
    db[new] = item
    rc.save_db(db)
    return new


def is_excluded(name):
    """Left out of the generator (and of the optimiser while it shares the
    generator's list - the default)."""
    return name in rc.load_excluded()


def set_excluded(name, excluded):
    """Leave a food out of / back into the generator's list (shared with
    the optimiser unless that has its own list)."""
    ex = rc.load_excluded()
    ex = (ex | {name}) if excluded else (ex - {name})
    rc.save_excluded(ex)


def delete_item(db, recipe, name):
    """Remove a food from the library and the recipe, and save."""
    db.pop(name, None)
    recipe[:] = [r for r in recipe if r[0] != name]
    rc.save_db(db)


# ---------------------------------------------------------------- screen
class LibraryView:
    """List / detail / edit screens for the library inside one Column.
    `get_extended()` gives the Extended-nutrients switch; `on_changed()` is
    called after the library or recipe changed; `add_to_recipe(name, g)`
    adds a food to the recipe."""

    def __init__(self, page, db, recipe, get_extended, on_changed,
                 add_to_recipe):
        self.page, self.db, self.recipe = page, db, recipe
        self.get_extended, self.on_changed = get_extended, on_changed
        self.add_to_recipe = add_to_recipe
        self.query = ft.TextField(label="Search", dense=True, expand=True,
                                  prefix_icon=ft.Icons.SEARCH,
                                  on_change=lambda e: self.show_list())
        self.cat = ft.Dropdown(
            label="Category", value="all", width=170, dense=True,
            options=[ft.DropdownOption(key="all", text="All")] +
            [ft.DropdownOption(key=c, text=c) for c in CATEGORIES],
            on_select=lambda e: self.show_list())
        # the list screen is built once; typing only refreshes the results
        # (rebuilding the search box would drop its keyboard focus)
        self.count = ft.Text(size=11)
        self.list_col = ft.Column(spacing=0)
        self.more = ft.Text(size=11)
        self.list_screen = [
            ft.Row([ft.Text("Ingredient library", size=18,
                            weight=ft.FontWeight.BOLD),
                    ft.IconButton(icon=ft.Icons.ADD, tooltip="New food",
                                  on_click=lambda e: self.show_edit(None))],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([self.query, self.cat]), self.count, self.list_col,
            self.more]
        self.root = ft.Column(self.list_screen)
        self.show_list()

    # ---- helpers
    def _set(self, controls):
        self.root.controls = controls
        self.page.update()

    def toast(self, text):
        self.page.show_dialog(ft.SnackBar(ft.Text(text)))

    # ---- list
    def show_list(self, e=None):
        names = filter_foods(self.db, self.query.value, self.cat.value)
        ex = rc.load_excluded()
        tiles = [ft.ListTile(
            title=ft.Text(n),
            subtitle=ft.Text(f"{self.db[n]['category']} · "
                             f"{rc.ingredient_role(self.db[n])} · "
                             f"{rc.fmt(self.db[n]['per100g']['kcal'])} kcal"
                             "/100 g" + (" · left out of Improve"
                                         if n in ex else ""), size=11),
            dense=True, data=n, on_click=lambda e: self.show_detail(
                e.control.data))
            for n in names[:300]]
        more = (len(names) - 300) if len(names) > 300 else 0
        self.count.value = (f"{len(names)} of {len(self.db)} foods · "
                            "values per 100 g")
        self.list_col.controls = tiles
        self.more.value = (f"…and {more} more – refine the search."
                           if more else "")
        if self.root.controls is not self.list_screen:
            self.root.controls = self.list_screen
        self.page.update()

    # ---- detail
    def show_detail(self, name):
        it = self.db.get(name)
        if it is None:
            return self.show_list()
        grams = ft.TextField(label="g/day", width=100, dense=True,
                             keyboard_type=ft.KeyboardType.NUMBER)

        def add(e):
            try:
                g = float(str(grams.value).replace(",", "."))
            except (TypeError, ValueError):
                g = 0
            if g <= 0:
                grams.error = "Enter grams"
                self.page.update()
                return
            self.add_to_recipe(name, g)
            self.toast(f"Added {g:g} g of {name} to the recipe.")

        rows = []
        for title, keys in visible_keys(self.get_extended()):
            rows.append(ft.Text(title, weight=ft.FontWeight.BOLD))
            rows += [ft.Row([ft.Text(rc.LABEL[k], expand=True),
                             ft.Text(value_text(it, k))])
                     for k in keys]
        use = ft.Switch(label="Use in Improve (optimiser and generator)",
                        value=not is_excluded(name),
                        on_change=lambda e: (set_excluded(
                            name, not e.control.value), self.toast(
                            f"{name} " + ("can be used." if e.control.value
                                          else "left out of Improve."))))
        extra = [f"Category: {it['category']}",
                 f"Role: {rc.ingredient_role(it)}"
                 + (" (set by hand)" if it.get("role") else "")]
        if it.get("max_dose"):
            extra.append(f"Recommended max: {it['max_dose']}")
        if it.get("assume_aafco"):
            extra.append("Complete food: AAFCO minimums assumed for missing "
                         "extended nutrients")
        self._set([
            ft.Row([ft.IconButton(icon=ft.Icons.ARROW_BACK,
                                  tooltip="Back", on_click=self.show_list),
                    ft.Text(name, size=16, weight=ft.FontWeight.BOLD,
                            expand=True)]),
            ft.Row([grams, ft.FilledButton("Add to recipe", on_click=add)]),
            ft.Row([ft.OutlinedButton("Edit", icon=ft.Icons.EDIT,
                                      on_click=lambda e: self.show_edit(
                                          name)),
                    ft.OutlinedButton("Delete", icon=ft.Icons.DELETE_OUTLINE,
                                      on_click=lambda e: self.confirm_delete(
                                          name))]),
            use,
            ft.Text(" · ".join(extra), size=12),
            ft.Text(it.get("note", ""), size=12, italic=True,
                    selectable=True) if it.get("note") else ft.Container(),
            ft.Divider(),
            ft.Text("Values per 100 g", size=12),
            ft.Column(rows, spacing=2)])

    def confirm_delete(self, name):
        in_recipe = any(r[0] == name for r in self.recipe)

        def do(e):
            delete_item(self.db, self.recipe, name)
            self.page.pop_dialog()
            self.on_changed()
            self.show_list()
            self.toast(f"Deleted {name}.")
        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("Delete food?"),
            content=ft.Text(f"{name} will be removed from the library"
                            + (" and from the current recipe." if in_recipe
                               else ".") + " This cannot be undone."),
            actions=[ft.TextButton("Cancel",
                                   on_click=lambda e: self.page.pop_dialog()),
                     ft.FilledButton("Delete", on_click=do)]))

    # ---- edit / new
    def show_edit(self, name):
        old = self.db.get(name) if name else None
        ext = self.get_extended()
        f_name = ft.TextField(label="Name", value=name or "", dense=True)
        f_cat = ft.Dropdown(label="Category", dense=True, width=200,
                            value=(old or {}).get("category", "food"),
                            options=[ft.DropdownOption(key=c, text=c)
                                     for c in CATEGORIES])
        f_role = ft.Dropdown(label="Role", dense=True, width=170,
                             value=(old or {}).get("role") or "auto",
                             options=[ft.DropdownOption(key="auto",
                                                        text="automatic")]
                             + [ft.DropdownOption(key=r, text=r)
                                for r in rc.ROLES])
        f_note = ft.TextField(label="Note", value=(old or {}).get("note", ""),
                              multiline=True, min_lines=1, max_lines=4,
                              dense=True)
        f_max = ft.TextField(label="Recommended max g/day",
                             value=(old or {}).get("max_dose", "") or "",
                             dense=True,
                             helper="e.g. 7 · 0.18/kg · 5:4, 10:8")
        f_assume = ft.Checkbox(label="Complete food (assume AAFCO)",
                               value=bool((old or {}).get("assume_aafco")),
                               tooltip="Missing extended nutrients are taken "
                                       "at the AAFCO minimum - for complete "
                                       "commercial foods only.")
        err = ft.Text(color=ft.Colors.RED_700)
        fields = {}
        body = []
        for title, keys in visible_keys(ext):
            body.append(ft.Text(title, weight=ft.FontWeight.BOLD))
            for k in keys:
                v = (old or {}).get("per100g", {}).get(k)
                fields[k] = ft.TextField(
                    label=f"{rc.LABEL[k]} ({rc.UNIT[k]})",
                    value="" if v is None else f"{v:g}", dense=True,
                    keyboard_type=ft.KeyboardType.NUMBER)
                body.append(fields[k])

        def save(e):
            try:
                item = build_item(
                    old, f_name.value, f_cat.value, f_note.value,
                    f_role.value, f_max.value, f_assume.value,
                    {k: f.value or "" for k, f in fields.items()})
                stored = store_item(self.db, self.recipe, name, item)
            except ValueError as ex:
                err.value = str(ex)
                self.page.update()
                return
            self.on_changed()
            self.show_detail(stored)
            self.toast(f"Saved {stored}.")

        self._set([
            ft.Row([ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="Back",
                                  on_click=(lambda e: self.show_detail(name))
                                  if name else self.show_list),
                    ft.Text("Edit food" if name else "New food", size=16,
                            weight=ft.FontWeight.BOLD, expand=True),
                    ft.FilledButton("Save", on_click=save)]),
            err, f_name, ft.Row([f_cat, f_role], wrap=True), f_note, f_max,
            f_assume,
            ft.Text("Values per 100 g as fed; leave blank if unknown."
                    + ("" if ext else " Switch on Extended nutrients to "
                       "edit amino acids and trace minerals."), size=11),
        ] + body + [ft.FilledButton("Save", on_click=save)])
