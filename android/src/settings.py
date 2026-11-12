"""
Dog settings for the RenalFood phone app (Settings tab): body weight, age,
activity, MER factor (with the engine's suggestion from age and activity),
max food per day, meals per day, IRIS stage and Extended nutrients.
Remembered between launches in the engine's settings file ('phone_dog');
every tab reads them from one Dog object.
"""
import flet as ft

import renal_diet_calc as rc

PREFS_KEY = "phone_dog"
DEFAULTS = {"bw": 6.0, "age": 0.0, "activity": "normal", "factor": 1.6,
            "max_g": 0.0, "meals": 2, "stage": "Stage 2", "extended": False}


def clean(d):
    """Valid settings from a dict (unknown/invalid values -> defaults)."""
    d = d if isinstance(d, dict) else {}
    out = dict(DEFAULTS)
    for k in ("bw", "age", "factor", "max_g"):
        try:
            v = float(d.get(k, out[k]))
            if v >= 0:
                out[k] = v
        except (TypeError, ValueError):
            pass
    try:
        out["meals"] = max(1, min(6, int(d.get("meals", out["meals"]))))
    except (TypeError, ValueError):
        pass
    if d.get("activity") in rc.ACTIVITY:
        out["activity"] = d["activity"]
    if d.get("stage") in rc.STAGES:
        out["stage"] = d["stage"]
    if "extended" in d:
        out["extended"] = bool(d["extended"])
    if out["bw"] <= 0:
        out["bw"] = DEFAULTS["bw"]
    if out["factor"] <= 0:
        out["factor"] = DEFAULTS["factor"]
    return out


class Dog:
    """The current dog settings (attributes bw, age, activity, factor,
    max_g, meals, stage, extended)."""

    def __init__(self):
        self.__dict__.update(clean(rc.load_prefs().get(PREFS_KEY)))

    def values(self):
        return {k: getattr(self, k) for k in DEFAULTS}

    def update(self, d, save=True):
        """Apply (part of) a settings dict, e.g. from a saved recipe."""
        self.__dict__.update(clean({**self.values(), **(d or {})}))
        if save:
            self.save()

    def save(self):
        p = rc.load_prefs()
        p[PREFS_KEY] = self.values()
        rc.save_prefs(p)

    def need(self):
        """Daily energy need (MER) in kcal."""
        return rc.mer(self.bw, self.factor)

    def suggestion(self):
        """(factor, text) from age and activity, or None."""
        return rc.suggest_mer_factor(self.age, self.bw, self.activity)

    def as_tuple(self):
        """(bw, factor, stage, extended, need, max_g) for the other tabs."""
        return (self.bw, self.factor, self.stage, self.extended,
                self.need(), self.max_g or None)

    def summary(self):
        """One line for the Recipe tab."""
        return (f"{self.bw:g} kg · {self.stage} · {self.need():.0f} kcal/day"
                + (f" · {self.meals} meals" if self.meals > 1 else "")
                + (" · max " + f"{self.max_g:g} g" if self.max_g else ""))


def small(text):
    return ft.Text(text, size=12)


class SettingsView:
    """The Settings tab. on_changed() is called after any valid change."""

    def __init__(self, page, dog, on_changed):
        self.page, self.dog, self.on_changed = page, dog, on_changed
        num = ft.KeyboardType.NUMBER
        # short labels and fields that share the width, so they still fit
        # with large text (phone/computer text size); explanations are
        # ordinary text below that can wrap
        self.bw = ft.TextField(label="Weight (kg)", expand=True, dense=True,
                               keyboard_type=num)
        self.age = ft.TextField(label="Age (years)", expand=True, dense=True,
                                keyboard_type=num)
        self.activity = ft.Dropdown(
            label="Activity", expand=True, dense=True,
            options=[ft.DropdownOption(key=a, text=a) for a in rc.ACTIVITY])
        self.factor = ft.TextField(label="MER factor", expand=True,
                                   dense=True, keyboard_type=num)
        self.max_g = ft.TextField(label="Max g/day", expand=True, dense=True,
                                  keyboard_type=num)
        self.meals = ft.Dropdown(
            label="Meals/day", expand=True, dense=True,
            options=[ft.DropdownOption(key=str(i), text=str(i))
                     for i in range(1, 7)])
        self.stage = ft.Dropdown(
            label="IRIS stage", expand=True, dense=True,
            options=[ft.DropdownOption(key=s, text=s) for s in rc.STAGES])
        self.ext = ft.Switch(label="Extended nutrients")
        self.need = ft.Text(size=16, weight=ft.FontWeight.BOLD)
        self.targets = ft.Column(spacing=2)
        self.sugg = ft.Text(size=12)
        self.sugg_btn = ft.OutlinedButton("Use suggested factor",
                                          icon=ft.Icons.CHECK,
                                          on_click=self.use_suggestion)
        self.stage_note = ft.Text(size=12, italic=True)
        self.err = ft.Text(color=ft.Colors.RED_700, size=12)
        for c in (self.bw, self.age, self.factor, self.max_g):
            c.on_change = self.changed
        for c in (self.activity, self.meals, self.stage):
            c.on_select = self.changed
        self.ext.on_change = self.changed
        self.root = ft.Column([
            ft.Text("Settings", size=18, weight=ft.FontWeight.BOLD),
            ft.Text("Used on every tab (recipe analysis, Generator). "
                    "Remembered on this device.", size=12),
            ft.Text("Dog", weight=ft.FontWeight.BOLD),
            ft.Row([self.bw, self.age]),
            small("Weight: her ideal weight if she is over- or "
                  "underweight. Age: 0 = not set."),
            ft.Row([self.activity, self.factor]),
            small("Daily energy = MER factor × 70 × weight^0.75. About 1.6 "
                  "for a neutered adult, 1.2–1.4 if less active."),
            self.sugg, self.sugg_btn, self.need,
            ft.Divider(),
            ft.Text("Feeding", weight=ft.FontWeight.BOLD),
            ft.Row([self.max_g, self.meals]),
            small("Max g/day: the most food she will eat in a day "
                  "(0 = no limit)."),
            ft.Divider(),
            ft.Text("Kidney disease", weight=ft.FontWeight.BOLD),
            ft.Row([self.stage]), self.stage_note,
            ft.Divider(),
            ft.Text("Daily targets", weight=ft.FontWeight.BOLD),
            self.targets,
            small("The same targets the analysis and Generator use (per "
                  "1000 kcal × energy ÷ 1000), for the whole day – kibble, "
                  "treats and supplements included."),
            ft.Divider(),
            self.err,
            ft.Text("Approximate tool – not veterinary advice.", size=11,
                    italic=True)])
        self.load()

    def load(self):
        """Fill the fields from the Dog (e.g. after opening a recipe)."""
        d = self.dog
        self.bw.value = f"{d.bw:g}"
        self.age.value = f"{d.age:g}"
        self.activity.value = d.activity
        self.factor.value = f"{d.factor:g}"
        self.max_g.value = f"{d.max_g:g}"
        self.meals.value = str(d.meals)
        self.stage.value = d.stage
        self.ext.value = d.extended
        self.err.value = ""
        self._derived()

    def _derived(self):
        d = self.dog
        self.need.value = f"Daily energy need: {d.need():.0f} kcal"
        s = d.suggestion()
        self.sugg.value = s[1] if s else ("Enter her age for a suggested "
                                          "factor.")
        self.sugg_btn.visible = bool(s) and abs(s[0] - d.factor) > 1e-9
        if s:
            self.sugg_btn.content = f"Use suggested factor {s[0]:g}"
        self.stage_note.value = rc.STAGES[d.stage][1]
        ctx = rc.build_score_context(None, d.stage, d.need(), d.bw,
                                     d.extended, d.max_g or None)
        rows = []
        for nm, u, rg, aim, why in rc.daily_targets(ctx):
            val = f"{rg} {u}".strip() + (f" (aim {aim})" if aim else "")
            rows.append(ft.Row([ft.Text(nm, size=13, expand=True),
                                ft.Text(val, size=13,
                                        weight=ft.FontWeight.BOLD)]))
            rows.append(ft.Text(why, size=10, italic=True))
        self.targets.controls = rows

    def set_extended(self, v):
        """Extended nutrients (switch on the Generator tab)."""
        self.ext.value = bool(v)
        self.changed()

    def changed(self, e=None):
        vals = {"activity": self.activity.value, "stage": self.stage.value,
                "extended": bool(self.ext.value), "meals": self.meals.value}
        bad = []
        for k, f in (("bw", self.bw), ("age", self.age),
                     ("factor", self.factor), ("max_g", self.max_g)):
            try:
                v = rc.to_float(f.value or "")
            except ValueError:
                v = -1
            if v is None:
                v = 0.0 if k in ("age", "max_g") else -1
            if v < 0 or (k in ("bw", "factor") and v <= 0):
                bad.append(f.label)
            else:
                vals[k] = v
        self.err.value = ("Check: " + ", ".join(bad)) if bad else ""
        self.dog.update(vals)
        self._derived()
        self.page.update()
        self.on_changed()

    def use_suggestion(self, e=None):
        s = self.dog.suggestion()
        if s:
            self.factor.value = f"{s[0]:g}"
            self.changed()
