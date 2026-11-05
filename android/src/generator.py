"""
Generator screen for the RenalFood phone app: the recipe generator (new
balanced recipes from the library) and the optimiser (better versions of
the current recipe), both through the shared engine. Long runs go to a background
thread with a progress bar and a Cancel button; nothing changes until a
result is applied (and Undo restores the previous recipe).
"""
import time

import flet as ft

import renal_diet_calc as rc
from choices import (food_setting, open_dialog, set_food_setting,  # noqa
                     set_foods, setting_text)


class Cancelled(Exception):
    """Raised from a progress callback when the user presses Cancel."""


# ---------------------------------------------------------------- logic
def context(stage, need, bw, extended, ignore_vitamins=False, max_g=None):
    """Scoring context for this dog (same as the other apps' defaults);
    max_g = daily food limit (g) or None."""
    ctx = rc.build_score_context(None, stage, need, bw, extended,
                                 max_g or None)
    if ignore_vitamins:
        ctx["weights"]["vitamins"] = 0.0
    return ctx


def usable(db, n):
    it = db.get(n)
    return (it is not None and it["category"] != "binder"
            and it["per100g"]["kcal"] is not None)


def opt_bounds(recipe, db, kcal, bw, locked=()):
    """names, bounds [(min, max, locked)], x0 for the optimiser - limits as
    in the other apps (default bounds, recommended max; binders locked)."""
    names, bounds, x0 = [], [], []
    for n, g in recipe:
        lo, hi = rc.default_bounds(db[n], kcal, bw)
        rec = rc.recommended_max(db[n], bw, kcal)
        names.append(n)
        x0.append(float(g))
        bounds.append((lo, hi if rec else max(hi, float(g)),
                       n in locked or db[n]["category"] == "binder"))
    return names, bounds, x0


def opt_candidates(recipe, db, extended=False, complete=False):
    """Foods the optimiser may add or swap in: not in the recipe, not
    binders, not excluded (the optimiser's remembered list)."""
    ex = rc.load_excluded(rc.opt_excluded_key())
    inr = {n for n, _ in recipe}
    c = [n for n in sorted(db, key=str.lower)
         if n not in inr and n not in ex and usable(db, n)]
    return rc.complete_only(c, db, extended) if complete else c


def run_optimiser(recipe, db, ctx, cands, max_add=3, add=True, swap=True,
                  remove=True, locked=(), progress=None):
    """(current, options) like the other apps' optimiser. progress(label,
    i, total) may raise Cancelled."""
    kcal, bw = ctx["kcal_target"], ctx.get("bw")
    names, bounds, x0 = opt_bounds(recipe, db, kcal, bw, locked)
    vecs = [rc._vec(db[n]) for n in names]
    before = rc.score_amounts(x0, vecs, ctx)

    def step(label):
        return (lambda i, t, nm: progress(label, i, t)) if progress else None
    if add and cands:
        base, singles, combo = rc.suggest_additions(
            names, db, bounds, x0, ctx, cands, max_add, step("Additions"))
    else:
        if progress:
            progress("Adjusting amounts", 0, 1)
        base, singles, combo = rc.optimise(names, db, bounds, x0, ctx), \
            [], None
    subs = rc.suggest_substitutions(names, db, bounds, base, ctx, cands,
                                    step("Swaps")) if swap and cands else []
    if remove:
        if progress:
            progress("Removals", 0, 1)
        rems = rc.suggest_removals(names, db, bounds, base, ctx)
    else:
        rems = []
    r = {"ctx": ctx, "names": names, "x0": x0, "before": before[0],
         "base": base, "singles": singles, "combo": combo, "subs": subs,
         "rems": rems, "bounds": bounds, "manual": None}
    return rc.optimiser_options(r, db)


def gen_pool(db, extended=False, complete=False, keep=()):
    """Foods the generator may use: not binders, not excluded (the
    generator's remembered list); `keep` always kept."""
    ex = rc.load_excluded()
    pool = [n for n in sorted(db, key=str.lower)
            if usable(db, n) and (n not in ex or n in keep)]
    return rc.complete_only(pool, db, extended, True, keep=set(keep)) \
        if complete else pool


def gen_inputs(db, extended=False, complete=False, fixed=()):
    """(pool, forced {name: min g or None}, max_each {name: g}) for
    rc.generate_recipes from the stored settings, as the other apps do:
    forced foods are always in the pool."""
    gs = rc.load_gen_settings()
    forced = {n: gs["min"].get(n) for n in gs["forced"] if usable(db, n)}
    max_each = {n: g for n, g in gs["max"].items() if n in db}
    keep = set(forced) | {n for n, _ in fixed}
    return gen_pool(db, extended, complete, keep), forced, max_each


def summary(names, grams, db, ctx):
    """Key figures of a recipe: mass, kcal, P and protein per 1000 kcal,
    rating."""
    vecs = [rc._vec(db[n]) for n in names]
    kcal, per, _ = rc.per1000_from(grams, vecs)
    return {"g": sum(grams), "kcal": kcal, "p": per["p"],
            "protein": per["protein"],
            "rating": rc.recipe_rating(names, grams, db, ctx)[0]}


# ---------------------------------------------------------------- screen
class GeneratorView:
    """Generate / Optimise inside one Column. `get_settings()` returns
    (bw, factor, stage, extended, need, max_g); `apply(recipe_rows, label)` puts a
    result in the Recipe screen; `undo()` restores the previous recipe."""

    def __init__(self, page, db, recipe, get_settings, apply, undo):
        self.page, self.db, self.recipe = page, db, recipe
        self.get_settings, self.apply_cb, self.undo_cb = \
            get_settings, apply, undo
        self.cancel_flag = False
        self.running = False
        self.mode = ft.SegmentedButton(
            selected=["gen"], allow_empty_selection=False,
            segments=[ft.Segment(value="gen", label=ft.Text("Generate"),
                                 icon=ft.Icon(ft.Icons.AUTO_AWESOME)),
                      ft.Segment(value="opt", label=ft.Text("Optimise"),
                                 icon=ft.Icon(ft.Icons.TUNE))],
            on_change=self._mode_changed)
        # optimiser settings
        self.o_add = ft.Checkbox(label="Add foods", value=True)
        self.o_swap = ft.Checkbox(label="Swap foods", value=True)
        self.o_rem = ft.Checkbox(label="Remove foods", value=True)
        self.o_max = ft.Dropdown(label="Add up to", value="3", expand=True,
                                 dense=True,
                                 options=[ft.DropdownOption(key=str(i),
                                                            text=f"{i} foods")
                                          for i in range(1, 7)])
        self.o_full = ft.Checkbox(label="Only foods with complete data",
                                  value=False)
        self.locks = {}
        # generator settings
        self.g_n = self._num_dd("Recipes", 1, 6, 3)
        self.g_max = self._num_dd("Foods each", 3, 9, 6)
        self.g_vmin = self._num_dd("Veg min", 0, 4, 1)
        self.g_vmax = self._num_dd("Veg max", 0, 6, 3)
        self.g_fixed = ft.Checkbox(
            label="Current recipe as fixed base", value=False,
            tooltip="Keeps the current recipe's foods at their amounts "
                    "(e.g. breakfast kibble) and builds the rest around them.")
        self.g_ign = ft.Checkbox(
            label="Ignore vitamin minimums", value=True,
            tooltip="Tick if you add a vitamin supplement: otherwise every "
                    "recipe is pushed towards egg yolk for vitamin B12.")
        self.g_full = ft.Checkbox(label="Only foods with complete data",
                                  value=False)
        # run state
        self.bar = ft.ProgressBar(value=0, visible=False)
        self.status = ft.Text(size=12)
        self.run_btn = ft.FilledButton("Find options", icon=ft.Icons.PLAY_ARROW,
                                       on_click=self.run)
        self.cancel_btn = ft.OutlinedButton("Cancel", icon=ft.Icons.STOP,
                                            on_click=self.cancel,
                                            visible=False)
        self.results = ft.Column()
        self.results_for = {"opt": [], "gen": []}
        self.root = ft.Column()
        self.show()

    def _mode_changed(self, e=None):
        if not self.running:
            self.status.value = ""
        self.show()

    @staticmethod
    def _num_dd(label, lo, hi, val):
        return ft.Dropdown(label=label, value=str(val), expand=True,
                           dense=True,
                           options=[ft.DropdownOption(key=str(i), text=str(i))
                                    for i in range(lo, hi + 1)])

    def toast(self, text):
        self.page.show_dialog(ft.SnackBar(ft.Text(text)))

    # ---- layout
    def show(self, e=None):
        opt = "opt" in self.mode.selected
        self.run_btn.content = "Find options" if opt else "Generate"
        head = [ft.Row([ft.Text("Generator", size=18,
                                weight=ft.FontWeight.BOLD),
                        ft.TextButton("Undo last change", icon=ft.Icons.UNDO,
                                      on_click=lambda e: self.undo())],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                self.mode]
        body = self._opt_settings() if opt else self._gen_settings()
        self.results.controls = self.results_for["opt" if opt else "gen"]
        self.root.controls = head + body + [
            ft.Row([self.run_btn, self.cancel_btn]), self.bar, self.status,
            self.results]
        self.page.update()

    def _opt_settings(self):
        if not self.recipe:
            return [ft.Text("Add foods on the Recipe tab first, then come "
                            "back to find better versions of it.",
                            italic=True)]
        self.locks = {n: self.locks.get(n) or ft.Checkbox(
            label="lock", value=self.db[n]["category"] == "binder",
            disabled=self.db[n]["category"] == "binder")
            for n, _ in self.recipe}
        rows = [ft.Row([ft.Text(f"{n}", expand=True), ft.Text(f"{g:g} g"),
                        self.locks[n]]) for n, g in self.recipe]
        n_ex = len(rc.load_excluded(rc.opt_excluded_key()))
        return [ft.Text("Finds better versions of the current recipe. "
                        "Lock a food to keep its amount (e.g. kibble). "
                        f"{n_ex} food{'s' if n_ex != 1 else ''} left out "
                        "(Generate → Food choices, or a food's page in the "
                        "Library).", size=12),
                ft.Column(rows, spacing=0),
                ft.Row([self.o_add, self.o_swap, self.o_rem], wrap=True),
                ft.Row([self.o_max, ft.Container(expand=True)]),
                self.o_full]

    def _gen_settings(self):
        return [ft.Text("Builds new balanced recipes from the library.",
                        size=12),
                ft.Row([self.g_n, self.g_max]),
                ft.Row([self.g_vmin, self.g_vmax]),
                self.g_fixed, self.g_ign, self.g_full,
                self._food_choices()]

    def _food_choices(self):
        """Per-food settings: leave out, always include, min g, max g."""
        pick = ft.Dropdown(label="Food", enable_filter=True, editable=True,
                           expand=True, menu_height=350, dense=True,
                           options=[ft.DropdownOption(key=n, text=n)
                                    for n in sorted(self.db, key=str.lower)
                                    if usable(self.db, n)])

        def open_pick(e):
            n = pick.value if pick.value in self.db else next(
                (x for x in self.db if (pick.text or "").strip().lower()
                 and x.lower() == (pick.text or "").strip().lower()), None)
            if n is None:
                self.toast("Pick a food first.")
                return
            self.edit_food(n)
        rows = [ft.Row([
            ft.Text(n, expand=True, size=13),
            ft.Text(setting_text(food_setting(n)), size=11),
            ft.IconButton(icon=ft.Icons.EDIT, tooltip="Change", data=n,
                          on_click=lambda e: self.edit_food(e.control.data)),
            ft.IconButton(icon=ft.Icons.RESTART_ALT, tooltip="Reset",
                          data=n, on_click=self._reset_food)])
            for n in set_foods(self.db)]
        def toggled(e):
            self.choices_open = bool(e.data) if isinstance(e.data, bool) \
                else str(e.data).lower() == "true"
        return ft.ExpansionTile(
            expanded=getattr(self, "choices_open", False),
            on_change=toggled,
            title=ft.Text(f"Food choices ({len(rows)} set)"),
            subtitle=ft.Text("leave out, always include, min/max",
                             size=11),
            controls=[ft.Column([
                ft.Text("Pick a food to leave it out, always include it "
                        "(with a minimum) or cap it (maximum). Also used "
                        "by the other apps' generator.", size=11),
                ft.Row([pick, ft.FilledButton("Set…", on_click=open_pick)]),
            ] + (rows or [ft.Text("No food choices yet.", italic=True,
                                  size=12)]))])

    def _reset_food(self, e):
        set_food_setting(e.control.data)
        self.choices_open = True
        self.show()

    def edit_food(self, name):
        def saved():
            self.choices_open = True              # keep the list open
            self.show()
        open_dialog(self.page, name, saved)

    # ---- running
    def cancel(self, e=None):
        self.cancel_flag = True
        self.status.value = "Cancelling…"
        self.page.update()

    def run(self, e=None):
        if self.running:
            return
        opt = "opt" in self.mode.selected
        if opt and not self.recipe:
            self.toast("Add foods on the Recipe tab first.")
            return
        self.running, self.cancel_flag = True, False
        self.run_btn.disabled = True
        self.cancel_btn.visible = True
        self.bar.visible, self.bar.value = True, None   # moving until counted
        self.status.value = "Starting…"
        self.page.update()
        self.page.run_thread(self._work, opt)

    def _progress(self):
        last = [0.0]

        def prog(label, i, total):
            if self.cancel_flag:
                raise Cancelled()
            now = time.monotonic()
            if now - last[0] > 0.25 or total <= 1:  # do not flood the UI
                last[0] = now
                if total <= 1:                  # one step: no count to show
                    self.bar.value = None
                    self.status.value = f"{label}…"
                else:
                    self.bar.value = min(1.0, (i + 1) / total)
                    count = f"{i + 1}/{total}"
                    self.status.value = (label if count in label
                                         else f"{label} {count}")
                self.page.update()
        return prog

    def _work(self, opt):
        t0 = time.monotonic()
        try:
            if opt:
                self._run_opt()
            else:
                self._run_gen()
            self.status.value = f"Done in {time.monotonic() - t0:.0f} s."
        except Cancelled:
            self.status.value = "Cancelled."
        except Exception as ex:                   # keep the app alive
            self.status.value = f"Error: {ex}"
        finally:
            self.running = False
            self.run_btn.disabled = False
            self.cancel_btn.visible = False
            self.bar.visible = False
            self.page.update()

    def _run_opt(self):
        bw, factor, stage, ext, need, max_g = self.get_settings()
        ctx = context(stage, need, bw, ext, max_g=max_g)
        cands = opt_candidates(self.recipe, self.db, ext,
                               bool(self.o_full.value))
        locked = {n for n, cb in self.locks.items() if cb.value}
        current, opts = run_optimiser(
            [list(r) for r in self.recipe], self.db, ctx, cands,
            int(self.o_max.value), bool(self.o_add.value),
            bool(self.o_swap.value), bool(self.o_rem.value), locked,
            self._progress())
        cards = [self._card(
            "Now", current["change"], current["names"], current["grams"],
            current["score"], current["rating"], "", None, ctx)]
        for o in opts[:12]:
            cards.append(self._card(
                ("★ " if o["best"] else "") + o["kind"], o["change"],
                o["names"], o["grams"], o["score"], o["rating"], o["why"],
                f"Optimised: {o['kind'].lower()}", ctx))
        if not opts:
            cards.append(ft.Text("No better version found with these "
                                 "settings.", italic=True))
        self.results_for["opt"] = [ft.Text(
            "Options, best first (score 0 = every target met; rating "
            "0–100, higher = better):", size=12)] + cards
        self.results.controls = self.results_for["opt"]

    def _run_gen(self):
        bw, factor, stage, ext, need, max_g = self.get_settings()
        ctx = context(stage, need, bw, ext, bool(self.g_ign.value), max_g)
        fixed = [tuple(r) for r in self.recipe] if self.g_fixed.value else ()
        pool, forced, max_each = gen_inputs(self.db, ext,
                                            bool(self.g_full.value), fixed)
        vmin, vmax = int(self.g_vmin.value), int(self.g_vmax.value)
        if vmax < vmin:
            vmax = vmin
        prog = self._progress()
        res = rc.generate_recipes(
            self.db, pool, ctx, int(self.g_n.value), int(self.g_max.value),
            fixed, lambda text, i, total: prog(text, i, total),
            cancelled=lambda: self.cancel_flag, n_veg=vmin, veg_max=vmax,
            forced=forced, max_each=max_each)
        if self.cancel_flag:
            raise Cancelled()
        cards = [self._card(f"Recipe {i + 1}", "", names, grams, score,
                            summary(names, grams, self.db, ctx)["rating"],
                            "", f"Generated recipe {i + 1}", ctx,
                            list_foods=True)
                 for i, (names, grams, score, terms) in enumerate(res)]
        if not cards:
            cards = [ft.Text("No recipe found – allow more foods or "
                             "vegetables.", italic=True)]
        self.results_for["gen"] = cards
        self.results.controls = cards

    # ---- result cards
    def _card(self, title, change, names, grams, score, rating, why, label,
              ctx, list_foods=False):
        s = summary(names, grams, self.db, ctx)
        lines = [ft.Text(title, weight=ft.FontWeight.BOLD)]
        if change:
            lines.append(ft.Text(change, size=12))
        if list_foods:
            lines += [ft.Text(f"{n} – {g:.0f} g", size=12)
                      for n, g in zip(names, grams) if g >= 0.5]
        lines.append(ft.Text(
            f"Score {score:.3f} · rating {rating:.0f} · {s['g']:.0f} g, "
            f"{s['kcal']:.0f} kcal · P {s['p']:.0f} mg and protein "
            f"{s['protein']:.0f} g /1000 kcal", size=11))
        if why and why != "–":
            lines.append(ft.Text(f"Better: {why}", size=11, italic=True))
        if label:
            rows = [[n, round(g, 1)] for n, g in zip(names, grams)
                    if g >= 0.5]
            lines.append(ft.FilledButton(
                "Use this recipe" if list_foods else "Apply",
                on_click=lambda e, r=rows, lb=label: self.apply(r, lb)))
        return ft.Card(content=ft.Container(ft.Column(lines, spacing=4),
                                            padding=10))

    def apply(self, rows, label):
        if label.startswith("Optimised"):        # options were for the old
            self.results_for["opt"] = [ft.Text(  # recipe: run again
                "Applied. Press Find options again to improve the new "
                "recipe.", italic=True)]
        self.apply_cb(rows, label)
        self.toast(f"{label} applied – Undo is at the top of this tab.")

    def undo(self):
        if self.undo_cb():
            self.toast("Previous recipe restored.")
        else:
            self.toast("Nothing to undo.")
