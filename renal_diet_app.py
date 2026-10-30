"""
renal_diet_app.py - Streamlit version of the Renal Diet Composition Calculator.

Run:   streamlit run renal_diet_app.py
Needs: renal_diet_calc.py in the same folder (shared calculation engine and
       the same ingredient library file, renal_ingredients.json), plus
       streamlit and pandas. scipy is optional (faster optimiser).

Approximate tool - not veterinary advice. Check any diet with your vet.
"""
import csv
import io
import json
import os

import pandas as pd
import streamlit as st

import importlib
import inspect

import renal_diet_calc as rc
try:                                   # browser storage for preferences
    from streamlit_js_eval import streamlit_js_eval
except ImportError:                    # app still works (file only)
    streamlit_js_eval = None

# Streamlit keeps imported modules in memory between reruns, so after an
# update the new app script can meet the old engine. Reload it if stale.
ENGINE_VERSION = "2026.10.30i"
if getattr(rc, "ENGINE_VERSION", None) != ENGINE_VERSION:
    rc = importlib.reload(rc)

st.set_page_config(page_title="Renal Diet Calculator", page_icon="🐕",
                   layout="wide", initial_sidebar_state="auto")

# full-width tables on old and new Streamlit versions
_ver = tuple(int(x) for x in st.__version__.split(".")[:2])
FULL = {"width": "stretch"} if _ver >= (1, 49) else {"use_container_width": True}

# ---------------------------------------------------------------- layout
# Phone vs desktop is decided by screen width in CSS (no JavaScript):
# content in st.container(key="mob_...") shows on narrow screens only,
# key="desk_..." on wide screens only. Keyed containers need Streamlit
# >= 1.39; older versions just show the desktop layout.
KEYED = "key" in inspect.signature(st.container).parameters
PHONE_MAX = 700          # px; below this width the phone layout is used

_PHONE_CSS = """
[data-testid="stMainBlockContainer"], .block-container {
  padding: 3.6rem 0.6rem 3rem !important; }
h1 { font-size: 1.45rem !important; } h2 { font-size: 1.25rem !important; }
h3 { font-size: 1.1rem !important; }
[data-testid="stHorizontalBlock"] { flex-wrap: wrap !important;
  gap: 0.5rem !important; }
[data-testid="stColumn"], [data-testid="column"] {
  min-width: 100% !important; flex: 1 1 100% !important; }
[class*="st-key-metrics"] [data-testid="stColumn"] {
  min-width: 45% !important; flex: 1 1 45% !important; }
[data-testid="stMetricValue"] { font-size: 1.25rem !important; }
[data-testid="stMetricLabel"] p { font-size: 0.8rem !important; }
.stTabs [role="tablist"], .stTabs [data-baseweb="tab-list"] {
  gap: 0.6rem !important; overflow-x: auto; flex-wrap: nowrap; }
.stTabs [role="tab"], .stTabs [data-baseweb="tab"] {
  padding-left: 0.1rem !important; padding-right: 0.1rem !important;
  white-space: nowrap; }
.stTabs [role="tab"] p, .stTabs [data-baseweb="tab"] p {
  font-size: 0.85rem !important; }
.stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button {
  width: 100%; min-height: 2.75rem; }
input, select, textarea { font-size: 16px !important; }
[class*="st-key-desk_"] { display: none !important; }
"""
_DESK_CSS = '[class*="st-key-mob_"] { display: none !important; }'


# Always-visible scroll bars on tables (the grid's own thin overlay bars
# hide until you scroll, so wide tables look cut off). Chrome only honours
# ::-webkit-scrollbar when scrollbar-width/-color are left at 'auto'.
_TABLE_CSS = """
[data-testid="stDataFrame"] .dvn-scroller,
[data-testid="stDataEditor"] .dvn-scroller {
  scrollbar-width: auto !important; scrollbar-color: auto !important; }
[data-testid="stDataFrame"] .dvn-scroller::-webkit-scrollbar,
[data-testid="stDataEditor"] .dvn-scroller::-webkit-scrollbar {
  height: 12px; width: 12px; background: #eef1f5; }
[data-testid="stDataFrame"] .dvn-scroller::-webkit-scrollbar-thumb,
[data-testid="stDataEditor"] .dvn-scroller::-webkit-scrollbar-thumb {
  background: #9aa4b2; border-radius: 6px; border: 3px solid #eef1f5; }
[data-testid="stDataFrame"] .dvn-scroller::-webkit-scrollbar-thumb:hover,
[data-testid="stDataEditor"] .dvn-scroller::-webkit-scrollbar-thumb:hover {
  background: #6b7685; }
[data-testid="stDataFrame"] .dvn-scroller::-webkit-scrollbar-corner,
[data-testid="stDataEditor"] .dvn-scroller::-webkit-scrollbar-corner {
  background: #eef1f5; }
"""


ROW_H, SCROLL_H = 35, 14


def show_df(where, data, **kw):
    """st.dataframe with room for the always-visible horizontal scroll bar
    (otherwise it covers the last row)."""
    df_ = data if isinstance(data, pd.DataFrame) else getattr(data, "data",
                                                               data)  # Styler
    if kw.get("height") is None:
        kw["height"] = min(len(df_) + 1, 11) * ROW_H + 3   # Streamlit default
    kw["height"] += SCROLL_H
    return where.dataframe(data, **kw)


def layout_css(mode):
    if mode == "Phone":
        css = _PHONE_CSS
    elif mode == "Desktop":
        css = _DESK_CSS
    else:                                   # Auto: by screen width
        css = (f"@media (max-width: {PHONE_MAX}px) {{ {_PHONE_CSS} }}\n"
               f"@media (min-width: {PHONE_MAX + 1}px) {{ {_DESK_CSS} }}")
    st.markdown(f"<style>{_TABLE_CSS}\n{css}</style>",
                unsafe_allow_html=True)


_SHORT = [("above NRC safe upper limit", "↑ max"), ("above renal range", "↑"),
          ("below renal range", "↓"), ("in renal range", "✓"),
          ("above AAFCO max", "↑ max"), ("below AAFCO min", "↓ min"),
          ("≥ AAFCO min", "✓")]


def short_status(s):
    out = s
    for long_, short in _SHORT:
        out = out.replace(long_, short)
    return out.replace("; data missing", " ?").replace("data missing", "?")


def with_unit(v, u):
    """'75.1  (26% of weight)' + 'g' -> '75.1 g (26% of weight)'."""
    if not u:
        return v
    head, _, rest = str(v).partition(" ")
    if rest.lstrip().startswith("/"):            # '20 / 25 / 55' + '% ME'
        return f"{v} {u}"
    try:
        float(head.replace(",", ""))
    except ValueError:
        return v
    return f"{head} {u}" + (f" {rest.strip()}" if rest.strip() else "")


_W = (lambda px, word: px) if _ver >= (1, 45) else (lambda px, word: word)
PHONE_COMP_CFG = {"Nutrient": st.column_config.TextColumn(width=_W(165, "medium")),
                  "/1000 kcal": st.column_config.TextColumn(width=_W(72, "small")),
                  "Target": st.column_config.TextColumn(width=_W(80, "small")),
                  "": st.column_config.TextColumn(width=_W(48, "small"))}


def view(kind, name):
    """Container shown only on phones (kind='mob') or only on wider screens
    (kind='desk'). Without keyed containers: desktop only."""
    if KEYED:
        return st.container(key=f"{kind}_{name}")
    return st.container() if kind == "desk" else None


def keyed(name):
    return st.container(key=name) if KEYED else st.container()

# ---------------------------------------------------------------- state
ss = st.session_state
if "db" not in ss:
    ss.db = rc.load_db()
for key, val in {"recipe": [], "rec_ver": 0, "recipe_note": "",
                 "applied": None, "score_ctx": None, "opt_result": None,
                 "gen_result": None, "bw": 6.0, "factor": 1.6,
                 "stage": "Stage 2", "lib_ver": 0, "tgt_ver": 0,
                 "blood_eval": None, "ext": False, "max_g": 0.0,
                 "meals": 2}.items():
    ss.setdefault(key, val)
db = ss.db

# ---- excluded foods (generator pool / optimiser additions), remembered in
#      this browser (localStorage) and in renal_prefs.json next to the app
LS_KEY = "renalfood_excluded"
if "excluded" not in ss:
    ss.excluded = rc.load_excluded()
    ss.ex_loaded = streamlit_js_eval is None
    ss.gen_ex_ver = ss.opt_ex_ver = 0
    ss.gen_ex_base = ss.opt_ex_base = set(ss.excluded)
if not ss.ex_loaded:
    raw = streamlit_js_eval(
        js_expressions=f"localStorage.getItem('{LS_KEY}') || 'null'",
        key="ls_get_excluded")
    if raw is not None:                # None = browser not answered yet
        ss.ex_loaded = True
        try:
            got = json.loads(raw)
        except (TypeError, ValueError):
            got = None
        if isinstance(got, list):      # browser copy wins over the file
            ss.excluded = set(got)
            ss.gen_ex_base = ss.opt_ex_base = set(got)
            if "gen_set" in ss:
                ss.gen_set_base = ss.gen_set
            ss.gen_ex_ver += 1
            ss.opt_ex_ver += 1


# ---- generator settings per ingredient (Always include, Min g, Max g),
#      remembered the same way
LS_GEN = "renalfood_gen"
if "gen_set" not in ss:
    ss.gen_set = rc.load_gen_settings()
    ss.gen_set_base = ss.gen_set
    ss.gen_loaded = streamlit_js_eval is None
if not ss.gen_loaded:
    raw = streamlit_js_eval(
        js_expressions=f"localStorage.getItem('{LS_GEN}') || 'null'",
        key="ls_get_gen")
    if raw is not None:
        ss.gen_loaded = True
        try:
            got = json.loads(raw)
        except (TypeError, ValueError):
            got = None
        if isinstance(got, dict):
            ss.gen_set = ss.gen_set_base = rc.clean_gen_settings(got)
            ss.gen_ex_base = set(ss.excluded)
            ss.gen_ex_ver += 1


def set_gen_settings(new):
    new = rc.clean_gen_settings(new)
    if new != ss.gen_set:
        ss.gen_set = new
        rc.save_gen_settings(new)


def set_excluded(new, source):
    """Store a changed exclusion list; reset the OTHER list's editor so it
    shows the change."""
    if new == ss.excluded:
        return
    ss.excluded = set(new)
    rc.save_excluded(ss.excluded)
    if source == "gen":
        ss.opt_ex_base = set(new)
        ss.opt_ex_ver += 1
    else:
        ss.gen_ex_base = set(new)
        ss.gen_set_base = ss.gen_set      # editor is rebuilt: keep settings
        ss.gen_ex_ver += 1


def store_excluded_in_browser():
    if streamlit_js_eval is None or not ss.ex_loaded:
        return
    val = json.dumps(sorted(ss.excluded, key=str.lower), ensure_ascii=False)
    streamlit_js_eval(
        js_expressions=f"localStorage.setItem('{LS_KEY}', {json.dumps(val)})"
                       " || 1",
        key=f"ls_set_excluded_{abs(hash(val))}")
    if ss.gen_loaded:
        val = json.dumps(ss.gen_set, ensure_ascii=False, sort_keys=True)
        streamlit_js_eval(
            js_expressions=f"localStorage.setItem('{LS_GEN}', "
                           f"{json.dumps(val)}) || 1",
            key=f"ls_set_gen_{abs(hash(val))}")


LIGHT_CSS = {"g": "background-color: #dcf2dc; color: #1b5e20",
             "a": "background-color: #fdecc4; color: #7a4f00",
             "r": "background-color: #f8cfc8; color: #8e1b10; "
                  "font-weight: 600"}
LIGHT_LEGEND = ("🟢 fine, or a good source of a needed nutrient · 🟡 rich in "
                "a nutrient to limit, or partly meets a need · 🔴 a cause of "
                "a problem in this recipe (total too high and this ingredient "
                "supplies ≥10 % of it) · blank = no target or not a "
                "meaningful source. Each cell is judged on that ingredient's "
                "density per 1000 kcal against the targets; the TOTAL row "
                "shows the recipe's own status. % of P: red when its share "
                "of phosphorus is over 1.5× its share of calories. Oxalate: judged per "
                "100 g of the food – 🟢 <25 mg, 🟡 25–99 mg, 🔴 ≥100 mg "
                "(high-oxalate food).")
TAG_COLOUR = {"ok": "color: #1b7a1b", "warn": "color: #b36b00",
              "bad": "color: #c0392b; font-weight: 600", "": ""}


def need_now():
    return rc.mer(ss.bw, ss.factor)


def score_context(kcal=None):
    """Last optimiser/generator settings or blood adaptation for this stage,
    else defaults."""
    ctx = rc.build_score_context(ss.score_ctx, ss.stage, need_now(), ss.bw,
                                 ss.ext, ss.max_g or None)
    if kcal:
        ctx["kcal_target"] = kcal
    return ctx


def set_recipe(recipe):
    ss.recipe = [[n, float(g)] for n, g in recipe]
    ss.rec_ver += 1                      # rebuild the editor widget


# ---- undo / redo of recipe changes (this session)
HIST_MAX = 50
ss.setdefault("hist", [])
ss.setdefault("hist_pos", -1)


def _snap():
    return {"recipe": [list(r) for r in ss.recipe], "note": ss.recipe_note,
            "applied": ss.applied}


def record_history():
    """Remember the recipe if it changed since the current history point."""
    h, p = ss.hist, ss.hist_pos
    if p >= 0 and h[p]["recipe"] == ss.recipe:
        return
    del h[p + 1:]                         # a new change drops the redo part
    h.append(_snap())
    if len(h) > HIST_MAX:
        del h[0]
    ss.hist_pos = len(h) - 1


def _restore(pos):
    snap = ss.hist[pos]
    ss.hist_pos = pos
    set_recipe(snap["recipe"])
    ss.recipe_note = snap["note"]
    ss.applied = snap["applied"]


def undo():
    if ss.hist_pos > 0:
        _restore(ss.hist_pos - 1)


def redo():
    if ss.hist_pos < len(ss.hist) - 1:
        _restore(ss.hist_pos + 1)


def apply_recipe(names, g, score, label, ctx):
    set_recipe([(n, a) for n, a in zip(names, g) if a >= 0.1])
    ss.score_ctx = rc.store_score_context(ss.score_ctx, ctx, ss.stage,
                                          need_now())
    ss.recipe_note = (f"{label} – score {score:.3f} "
                      f"({ctx['kcal_target']:.0f} kcal/day, {ss.stage})")
    ss.applied = [list(r) for r in ss.recipe]
    st.toast("Recipe applied – open the Recipe tab")


def blood_values():
    d = {"date": str(ss.get("bl_date") or ""),
         "weight_trend": ss.get("bl_trend", "stable")}
    for k, *_ in rc.BLOOD_FIELDS:
        d[k] = ss.get(f"bl_{k}")
    return d


def apply_bloods_cb():
    ev = ss.blood_eval
    if not ev:
        return
    a, b = ev["adapt"], ev["bloods"]
    ss.stage = a["stage"]
    ss.score_ctx = rc.blood_score_context(a, b)
    if ss.get("bl_mer", True) and a["mer_delta"]:
        ss.factor = round(min(3.0, max(0.8, ss.factor + a["mer_delta"])), 1)
    ss.tgt_ver += 1                      # refresh optimiser inputs
    ss.blood_msg = f"Applied: {a['stage']}. " + a["note"]


def reset_targets_cb():
    ss.score_ctx = None
    ss.tgt_ver += 1
    ss.blood_msg = "Targets reset to the defaults for the current stage."


def load_recipe_cb():
    """Runs before the page is redrawn, so it may change sidebar widgets."""
    up = ss.get("rec_up")
    if up is None:
        return
    d = json.load(up)
    missing = [n for n, _ in d.get("items", []) if n not in db]
    set_recipe([(n, float(g)) for n, g in d.get("items", []) if n in db])
    try:
        ss.bw = float(d.get("bw", ss.bw))
        ss.max_g = float(d.get("max_g") or 0.0)
        ss.meals = int(d.get("meals") or ss.meals)
        ss.factor = float(d.get("factor", ss.factor))
    except ValueError:
        pass
    if d.get("stage") in rc.STAGES:
        ss.stage = d["stage"]
    ss.score_ctx = d.get("optimiser")
    ss.recipe_note = f"Loaded {up.name}" + (
        f" – {d['note']}" if d.get("note") else "")
    ss.applied = [list(r) for r in ss.recipe]
    if missing:
        ss.load_msg = "Not in library (skipped): " + ", ".join(missing)


def fmt_kcal(n, g):
    k = db[n]["per100g"]["kcal"] if n in db else None
    return None if k is None else round(k * g / 100)


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("🐕 Dog")
    st.number_input("Body weight (kg)", 0.5, 100.0, step=0.1, key="bw",
                    help="Use ideal weight if she is over- or underweight.")
    st.number_input("MER factor (× 70·BW^0.75)", 0.8, 3.0, step=0.1,
                    key="factor",
                    help="≈1.6 neutered adult, 1.8 intact, 1.2–1.4 less "
                         "active / weight-gain prone. Adjust to keep weight "
                         "stable.")
    st.number_input("Max food per day (g, 0 = no limit)", 0.0, 5000.0,
                    step=10.0, key="max_g",
                    help="For a small appetite: the optimiser and generator "
                         "then prefer energy-dense recipes that fit in this "
                         "amount.")
    st.number_input("Meals per day", 1, 6, step=1, key="meals",
                    help="Recipes stay daily totals; per-meal amounts are "
                         "the daily amounts divided by this number "
                         "(nutrient balance per 1000 kcal is the same).")
    st.selectbox("IRIS stage", list(rc.STAGES), key="stage")
    st.metric("Daily energy need (MER)", f"{need_now():.0f} kcal")
    st.caption(rc.STAGES[ss.stage][1])
    st.toggle("Extended nutrients", key="ext",
              help="Also show and check essential amino acids, linoleic "
                   "acid and trace minerals (Fe, Cu, Mn, Zn, I, Se) against "
                   "AAFCO adult minimums. Needs these values in the "
                   "ingredient library.")
    st.divider()
    st.radio("Layout", ["Auto", "Phone", "Desktop"], key="layout",
             horizontal=True, help="Auto picks by screen width.")
    st.caption("Approximate tool – not veterinary advice. A home-made renal "
               "diet should be balanced by a vet nutritionist.")
layout_css(ss.get("layout", "Auto"))

tab_rec, tab_blood, tab_opt, tab_gen, tab_lib, tab_about = st.tabs(
    ["🍲 Recipe & analysis", "🩸 Blood results", "⚙️ Optimise",
     "✨ Generate recipes", "📚 Ingredient library", "ℹ️ About"])

names_all = sorted(db, key=str.lower)

# ================================================================ RECIPE
with tab_rec:
    _m = view("mob", "dog")
    if _m:
        with _m:
            st.caption(f"🐕 {ss.bw:g} kg · {ss.stage} · {need_now():.0f} "
                       "kcal/day — change in the sidebar (› top left)")
    if ss.recipe_note:
        edited = ss.recipe != ss.applied
        st.success(ss.recipe_note + ("   (edited since)" if edited else ""))
    _bn = score_context().get("blood_note")
    if _bn:
        st.info("🩸 " + _bn)

    left, right = st.columns([2, 3], gap="large")
    with left:
        st.subheader("Recipe (grams per day)")
        # The editor's input must stay the same between reruns, otherwise
        # Streamlit drops edits in progress (e.g. a new row with no grams
        # yet). It is rebuilt only when the recipe is set by the app
        # (apply, undo, load, scale... all bump rec_ver).
        if ss.get("rec_base_ver") != ss.rec_ver:
            ss.rec_base = [list(r) for r in ss.recipe]
            ss.rec_base_ver = ss.rec_ver
        df = pd.DataFrame(ss.rec_base or [], columns=["Ingredient", "g"])
        df["Ingredient"] = df["Ingredient"].astype("object")
        df["g"] = df["g"].astype("float")
        ed = st.data_editor(
            df, key=f"rec_{ss.rec_ver}", num_rows="dynamic",
            **FULL, hide_index=True,
            column_config={
                "Ingredient": st.column_config.SelectboxColumn(
                    "Ingredient", options=names_all, required=True,
                    width="medium"),
                "g": st.column_config.NumberColumn(
                    "g/day", min_value=0.0, step=0.5, format="%.1f",
                    required=True)})
        ss.recipe = [[r.Ingredient, float(r.g)] for r in ed.itertuples()
                     if isinstance(r.Ingredient, str) and r.Ingredient in db
                     and pd.notna(r.g)]
        record_history()
        uc = st.columns([1, 1, 3])
        uc[0].button("↶ Undo", key="undo", on_click=undo,
                     disabled=ss.hist_pos <= 0, **FULL,
                     help="Undo the last recipe change (applied results, "
                          "edits, scaling, loading).")
        uc[1].button("↷ Redo", key="redo", on_click=redo,
                     disabled=ss.hist_pos >= len(ss.hist) - 1, **FULL)
        st.caption("Add a row at the bottom of the table; select rows and "
                   "press Delete to remove them.")
        if ss.meals > 1 and ss.recipe:
            pm = pd.DataFrame({
                "Ingredient": [n for n, _ in ss.recipe],
                "g per meal": [round(g / ss.meals, 1) for _, g in ss.recipe],
                "kcal per meal": [fmt_kcal(n, g / ss.meals)
                                  for n, g in ss.recipe]})
            with st.expander(f"Per meal ({ss.meals} meals/day)",
                             expanded=True):
                show_df(st, pm, hide_index=True, **FULL)
                st.caption("Daily amounts ÷ meals. If one meal is different "
                           "(e.g. kibble at breakfast), split by hand – the "
                           "daily totals are what count.")

        with st.expander("⚖️ Scale amounts to body weight"):
            st.write(f"Daily need {need_now():.0f} kcal "
                     f"({ss.bw:g} kg × {ss.factor:g}).")
            tgt = st.number_input("Target kcal/day", 1.0, 10000.0,
                                  value=float(round(need_now())), key="sc_t")
            binders = [n for n, _ in ss.recipe
                       if db[n]["category"] == "binder"]
            fixed = st.multiselect(
                "Keep fixed (e.g. breakfast kibble; binders always fixed)",
                [n for n, _ in ss.recipe], default=binders, key="sc_fix")
            if st.button("Scale", key="sc_go", disabled=not ss.recipe):
                try:
                    new, s = rc.scale_to_target(ss.recipe, db, tgt,
                                                set(fixed) | set(binders))
                    set_recipe(new)
                    st.toast(f"Scaled ×{s:.2f} to {tgt:.0f} kcal/day")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

        if ss.recipe:
            st.download_button(
                "🖨️ Printable recipe", rc.recipe_print_html(
                    ss.recipe, db, need_now(), ss.stage, score_context(),
                    ss.meals, ss.recipe_note, ss.bw, ss.factor),
                file_name="recipe_print.html", mime="text/html",
                key="print_recipe", **FULL,
                help="Downloads an A4 page with ingredients (per day and per "
                     "meal), key nutrients vs targets, assessment and "
                     "feeding notes. Open it and press Print (or Ctrl+P / "
                     "Share → Print on a phone).")
        with st.expander("💾 Save / load recipe"):
            payload = {"items": ss.recipe, "bw": str(ss.bw),
                       "max_g": str(ss.max_g), "meals": ss.meals,
                       "factor": str(ss.factor), "stage": ss.stage,
                       "note": ss.recipe_note}
            if ss.score_ctx:
                payload["optimiser"] = ss.score_ctx
            st.download_button("Download recipe (.json)",
                               json.dumps(payload, indent=1,
                                          ensure_ascii=False),
                               file_name="recipe.json",
                               mime="application/json",
                               disabled=not ss.recipe)
            up = st.file_uploader("Load a recipe .json", type=["json"],
                                  key="rec_up")
            st.button("Load", key="rec_load", disabled=up is None,
                      on_click=load_recipe_cb)
            if ss.get("load_msg"):
                st.warning(ss.pop("load_msg"))

    a = rc.analyse_recipe(ss.recipe, db, need_now(), ss.stage,
                          score_context(), ss.meals)
    with right:
        if a["mass"] <= 0:
            st.info("Add ingredients to the recipe – or use **Generate "
                    "recipes** to build one automatically.")
        else:
            t = a["totals"]
            k1000 = 1000 / t["kcal"] if t["kcal"] else 0
            with keyed("metrics"):
                m = st.columns(5)
            m[0].metric("Score", f"{a['score']:.3f}" if a["score"]
                        is not None else "–", help="0 = all targets met")
            if a.get("rating") is not None:
                st.caption(f"**Rating {a['rating']:.0f}/100** (tie-breaker "
                           "for equal scores; higher = better) – " +
                           " · ".join(f"{rc.RATING_LABELS[k]} "
                                      f"{a['rating_parts'][k] * 100:.0f}%"
                                      for k in rc.RATING_W))
            m[1].metric("kcal/day", f"{t['kcal']:.0f}",
                        f"{t['kcal'] - need_now():+.0f} vs need")
            m[2].metric("Protein g", f"{t['protein'] * k1000:.0f}",
                        help="per 1000 kcal")
            m[3].metric("P mg (net)", f"{rc.net_p(t) * k1000:.0f}",
                        help="phosphorus per 1000 kcal, net of any binder")
            m[4].metric("Ca : P",
                        f"{t['ca'] / t['p']:.2f}" if t["p"] else "–")
            st.subheader("Assessment")
            st.markdown("\n".join(
                ("- " + ln[2:]) if ln.startswith("• ") else
                (ln + "\n" if ln else "") for ln in a["notes"].splitlines()))

    if a["mass"] > 0:
        st.divider()
        ct, bt = st.tabs(["Composition", "Ingredient breakdown"])
        cols = ["Nutrient", "Unit", "Recipe total", "/100 g fed",
                "/100 g DM", "/1000 kcal", "Per day", "Per meal",
                "Renal range", "AAFCO min", "Status"]
        comp = pd.DataFrame([v for v, _ in a["rows"]], columns=cols)
        if ss.meals <= 1:
            comp = comp.drop(columns=["Per meal"])
            cols = [c for c in cols if c != "Per meal"]
            a["rows"] = [(tuple(x for j, x in enumerate(v) if j != 7), tg)
                         for v, tg in a["rows"]]
        tags = [tg for _, tg in a["rows"]]
        bcols = [c for _, c, _ in a.get("breakdown_cols", rc.BRK_COLS)]
        brk = pd.DataFrame(a["breakdown"], columns=bcols)
        h_comp = 35 * (len(comp) + 1) + 3

        def colour(df_):
            return df_.style.apply(
                lambda r: [TAG_COLOUR.get(tags[r.name], "")] * len(r),
                axis=1)

        lights = a.get("breakdown_lights") or []

        def traffic(df_, idx=None):
            """Cell colours from the engine's traffic lights; idx = column
            positions kept in df_ (phone subset)."""
            if len(lights) != len(df_):
                return df_
            L = [[row[i] for i in idx] if idx else row for row in lights]
            css = pd.DataFrame([[LIGHT_CSS.get(x, "") for x in r] for r in L],
                               index=df_.index, columns=df_.columns)
            css.iloc[-1] = [c + "; border-top: 2px solid #9aa4b2" if c else
                            "border-top: 2px solid #9aa4b2"
                            for c in css.iloc[-1]]
            return df_.style.apply(lambda _: css, axis=None)
        with ct:
            sm = pd.DataFrame(a["summary"],
                              columns=["Summary", "Unit", "Value", "Note"])
            with view("desk", "comp"):
                show_df(st, sm, hide_index=True, **FULL)
                show_df(st, colour(comp), hide_index=True, **FULL,
                             height=h_comp)
            _m = view("mob", "comp")
            if _m:
                with _m:
                    show_df(st, pd.DataFrame({
                        "Summary": sm["Summary"],
                        "Value": [with_unit(v, u) + (f" · {n}" if n else "")
                                  for v, u, n in zip(sm["Value"], sm["Unit"],
                                                     sm["Note"])]}),
                        hide_index=True, **FULL)
                    rng = [r or (f"≥{m_}" if m_ else "")
                           for r, m_ in zip(comp["Renal range"],
                                            comp["AAFCO min"])]
                    show_df(st, colour(pd.DataFrame({
                        "Nutrient": [f"{n} ({u})" if u else n for n, u in
                                     zip(comp["Nutrient"], comp["Unit"])],
                        "/1000 kcal": comp["/1000 kcal"], "Target": rng,
                        "": [short_status(s_) for s_ in comp["Status"]]})),
                        hide_index=True, **FULL, height=h_comp,
                        column_config=PHONE_COMP_CFG)
                    st.caption("Values per 1000 kcal. ✓ ok · ↓ low · ↑ high "
                               "· ? data missing. Per-day amounts: Layout → "
                               "Desktop (sidebar).")
            refs = rc.load_references()
            if not refs:
                st.caption("No reference diets loaded – import one on the "
                           "Ingredient library tab to compare.")
            if refs:
                with st.expander("Compare with a reference diet"):
                    rname = st.selectbox("Reference", [r_["name"]
                                                       for r_ in refs],
                                         key="ref_pick")
                    ref = next(r_ for r_ in refs if r_["name"] == rname)
                    rdf = pd.DataFrame(
                        rc.reference_rows(t, ref, a["missing"], ss.ext),
                        columns=["Nutrient", "Unit", "Recipe /1000 kcal",
                                 "Reference /1000 kcal", "Difference"])
                    rsc, rterms, rg = rc.reference_score(ref,
                                                         score_context())
                    if rsc is not None:
                        sc_c = st.columns(2)
                        sc_c[0].metric(
                            "Reference score", f"{rsc:.3f}",
                            help="The reference fed alone at your energy "
                                 f"target ({rg:.0f} g/day), scored with the "
                                 "same criteria as your recipe (stage, "
                                 "blood adaptation, priorities). 0 = every "
                                 "target met.")
                        sc_c[1].metric("This recipe", f"{a['score']:.3f}"
                                       if a["score"] is not None else "–")
                        rg_ = [f"{k} ({v:.3f})" for k, v in
                               sorted(rterms.items(), key=lambda kv: -kv[1])
                               if v > 1e-3][:5]
                        st.caption("Reference gaps: " + (", ".join(rg_) or
                                   "none") + ". Undeclared EPA+DHA counts "
                                   "as 0 (as for any complete food); "
                                   "undeclared Na/K/Mg and trace minerals "
                                   "at the AAFCO minimum.")
                    show_df(st, rdf, hide_index=True, **FULL,
                            height=35 * (len(rdf) + 1) + 3)
                    st.caption("For comparison only – not an ingredient. "
                               "'≥' = lower bound (label gives only added "
                               "amounts, or an ingredient's value is "
                               "unknown); no difference is shown then. "
                               + ref.get("note", ""))
                    if ref.get("source"):
                        st.caption(f"Source: {ref['source']}")
        with bt:
            with view("desk", "brk"):
                show_df(st, traffic(brk), hide_index=True, **FULL)
            _m = view("mob", "brk")
            if _m:
                with _m:
                    keep = ["Ingredient", "g", "kcal", "P mg", "% of P"]
                    show_df(st, traffic(brk[keep],
                                        [list(brk.columns).index(c)
                                         for c in keep]),
                            hide_index=True, **FULL)
            st.caption(LIGHT_LEGEND)
            st.caption("'?' = value unknown for that ingredient"
                       + ("; '≈' = AAFCO minimum assumed (complete food). "
                          "All nutrients shown – scroll sideways."
                          if ss.ext else "."))

        buf = io.StringIO()
        w = csv.writer(buf)
        if ss.recipe_note:
            w.writerow([ss.recipe_note])
        w.writerow(["Recipe", "g/day"])
        w.writerows(ss.recipe)
        w.writerow([])
        w.writerow(bcols)
        w.writerows(a["breakdown"])
        w.writerow([])
        w.writerows([list(r) for r in a["summary"]])
        w.writerow(cols)
        w.writerows([list(v) for v, _ in a["rows"]])
        w.writerow([])
        w.writerows([[ln] for ln in a["notes"].splitlines()])
        st.download_button("⬇️ Export results (.csv)", buf.getvalue(),
                           file_name="diet_results.csv", mime="text/csv")

# ================================================================ BLOODS
with tab_blood:
    st.subheader("Blood results → adapted targets")
    st.caption("Enter what was tested (leave the rest blank). The app "
               "suggests the IRIS stage and tightens or relaxes the nutrient "
               "ranges, aims and priorities; the optimiser and generator then "
               "use them. Reference ranges are typical canine values – your "
               "lab's own ranges take precedence. Adjustment sizes are this "
               "app's rules of thumb, for discussion with your vet.")
    prev = (ss.score_ctx or {}).get("bloods") or {}
    for k, *_ in rc.BLOOD_FIELDS:            # prefill once from saved
        if f"bl_{k}" not in ss:
            ss[f"bl_{k}"] = (None if prev.get(k) is None
                             else float(prev[k]))
    ss.setdefault("bl_trend", prev.get("weight_trend", "stable"))
    ss.setdefault("bl_date", prev.get("date", ""))
    h = st.columns(3)
    h[0].text_input("Test date", key="bl_date", placeholder="e.g. 2026-11-03")
    h[1].selectbox("Weight trend", ["stable", "losing", "gaining"],
                   key="bl_trend")
    for i, (k, lab, unit, refr) in enumerate(rc.BLOOD_FIELDS):
        if i % 3 == 0:
            cols = st.columns(3)
        cols[i % 3].number_input(f"{lab}" + (f" ({unit})" if unit else ""),
                                 min_value=0.0, format="%g",
                                 key=f"bl_{k}", help=refr)
    b = st.columns([1, 1, 2])
    if b[0].button("Evaluate", type="primary", key="bl_eval"):
        bv = blood_values()
        ss.blood_eval = {"bloods": bv,
                         "adapt": rc.adapt_from_bloods(bv, ss.stage)}
    if ss.get("blood_msg"):
        st.success(ss.pop("blood_msg"))
    ev = ss.blood_eval
    if ev:
        a = ev["adapt"]
        st.markdown(f"**Suggested stage: {a['stage']}**"
                    + ("  · renal ranges applied because of high phosphate"
                       if a["renal_force"] else ""))
        if a["findings"]:
            with view("desk", "findings"):
                show_df(st, pd.DataFrame(a["findings"], columns=[
                    "Test", "Value", "Reference / target", "Finding",
                    "Change to targets"]), hide_index=True, **FULL)
            _m = view("mob", "findings")
            if _m:
                with _m:
                    st.markdown("\n".join(
                        f"- **{t_}** {v_} — {f_}"
                        + (f"  \n  → {c_}" if c_ else "")
                        for t_, v_, r_, f_, c_ in a["findings"]))
        else:
            st.info("No results entered.")
        ch = pd.DataFrame(a["changes"], columns=["Target (per 1000 kcal)",
                                                 "Default", "Adapted"])
        changed = [r1 != r2 for r1, r2 in zip(ch["Default"], ch["Adapted"])]
        with view("desk", "changes"):
            show_df(st, ch.style.apply(
                lambda r: ["font-weight: 600; color: #b36b00"
                           if changed[r.name] else ""] * len(r), axis=1),
                hide_index=True, **FULL)
        _m = view("mob", "changes")
        if _m:
            with _m:
                st.markdown("**Target changes (per 1000 kcal)**\n" + (
                    "\n".join(f"- {t_}: {d0} → **{d1}**" for (t_, d0, d1), c_
                              in zip(a["changes"], changed) if c_)
                    or "- none"))
        c = st.columns([1, 1, 2])
        c[0].checkbox("Also adjust MER factor", True, key="bl_mer",
                      disabled=not a["mer_delta"])
        c[1].button("Apply to targets", type="primary", key="bl_apply",
                    on_click=apply_bloods_cb)
        c[2].button("Reset targets to defaults", key="bl_reset",
                    on_click=reset_targets_cb)
        st.caption("Recheck phosphate and calcium 4–6 weeks after a change, "
                   "then every 12 weeks (IRIS). Change one thing at a time.")
    elif (ss.score_ctx or {}).get("blood_note"):
        st.button("Reset targets to defaults", key="bl_reset0",
                  on_click=reset_targets_cb)

# ================================================================ OPTIMISE
with tab_opt:
    st.subheader("Optimise amounts & suggest additions")
    if not ss.recipe:
        st.info("Add the ingredients you want to use on the Recipe tab "
                "first (or use Generate recipes).")
    else:
        ctx0 = score_context()
        c1, c2 = st.columns([1, 2])
        o_kcal = c1.number_input("Target energy (kcal/day)", 1.0, 10000.0,
                                 value=float(round(ctx0["kcal_target"])),
                                 key=f"o_kcal_{ss.tgt_ver}",
                                 help="Covers the whole day – lock breakfast "
                                      "kibble if it is in the recipe.")
        rows = []
        for n, g in ss.recipe:
            lo, hi = rc.default_bounds(db[n], o_kcal)
            rows.append({"Ingredient": n, "Current g": g, "Min g": lo,
                         "Max g": max(hi, g),
                         "Lock": db[n]["category"] == "binder"})
        bdf = st.data_editor(
            pd.DataFrame(rows), hide_index=True, **FULL,
            key=f"o_bounds_{ss.rec_ver}_"
                f"{abs(hash(tuple(n for n, _ in ss.recipe)))}",
            disabled=["Ingredient", "Current g"],
            column_config={"Lock": st.column_config.CheckboxColumn(
                "Lock at current", help="Binders are always locked.")})

        refs_o = rc.load_references()
        OBJ = ["Renal targets", "Match a reference diet",
               "Renal targets + reference diet"]
        oc = st.columns([1, 2])
        obj = oc[0].selectbox(
            "Objective", OBJ if refs_o else OBJ[:1], key="o_obj",
            help="'Match a reference diet' changes amounts (and suggests "
                 "additions/substitutions) to get as close as possible to "
                 "the reference per 1000 kcal, keeping the energy target. "
                 "'+ reference' keeps the renal targets and adds closeness "
                 "to the reference.")
        o_ref = None
        if obj != OBJ[0]:
            rn = oc[1].selectbox("Reference diet",
                                 [r_["name"] for r_ in refs_o], key="o_ref")
            o_ref = next(r_ for r_ in refs_o if r_["name"] == rn)
            oc[1].caption("Closeness is weighted most for protein and "
                          "phosphorus, then fat, calcium, sodium and "
                          "potassium. Label values given only as 'added' "
                          "count as minimums.")

        with st.expander("Priorities and aims"):
            wc = st.columns(5)
            weights = {}
            for i, (k, v) in enumerate(ctx0["weights"].items()):
                weights[k] = wc[i % 5].number_input(
                    rc.WEIGHT_LABELS.get(k, k), 0.0, 100.0, float(v),
                    step=0.5, key=f"w_{k}_{ss.tgt_ver}")
            aims = {}
            if ctx0["renal"]:
                ac = st.columns(2)
                for i, k in enumerate(("protein", "p")):
                    lo, hi = rc.get_ranges(ctx0)[k]
                    aims[k] = ac[i].number_input(
                        f"Aim {rc.LABEL[k]} ({rc.UNIT[k]}/1000 kcal), range "
                        f"{lo:g}–{hi:g}", 0.0, 5000.0,
                        float(ctx0["aims"].get(k, (lo + hi) / 2)),
                        key=f"aim_{k}_{ss.tgt_ver}")
            st.caption("Aims and ranges adapted from blood results."
                       if ctx0.get("ranges") else
                       "Aims are this app's editable defaults inside the "
                       "ACVN range, not published targets.")

        do_sug = st.checkbox("Test additions from the library", True,
                             key="o_sug")
        do_subs = st.checkbox("Test substitutions (swap each ingredient for "
                              "another of the same type)", True,
                              key="o_subs",
                              help="Each unlocked ingredient is replaced in "
                                   "turn by every library food of the same "
                                   "role (protein, starch, vegetable, oil, "
                                   "supplement…) and all amounts are "
                                   "re-optimised. Unticked foods below are "
                                   "not used.")
        do_rem = st.checkbox("Test removals (leave each ingredient out in "
                             "turn)", True, key="o_rem",
                             help="Lists ingredients the recipe does not "
                                  "need: taking them out (all other amounts "
                                  "re-optimised) improves the score or costs "
                                  "under 1 %.")
        o_full = st.checkbox(
            "Suggest only ingredients with complete data (missing choline "
            "allowed)", False, key="o_full",
            help="Additions and substitutions use only foods without unknown "
                 "values among the nutrients checked (all of them with "
                 "Extended nutrients on).")
        max_add = st.slider("Max. additions to combine", 1, 6, 3,
                            key="o_max")
        cand_names = [n for n in names_all
                      if n not in dict(ss.recipe)
                      and db[n]["category"] != "binder"
                      and db[n]["per100g"]["kcal"] is not None]
        cdf = st.data_editor(
            pd.DataFrame({"Use": [n not in ss.opt_ex_base
                                  for n in cand_names],
                          "Role": [rc.ingredient_role(db[n])
                                   for n in cand_names],
                          "Ingredient": cand_names}),
            hide_index=True, **FULL, height=250,
            disabled=["Role", "Ingredient"],
            key=f"o_cand_{ss.rec_ver}_{ss.opt_ex_ver}") \
            if do_sug else None
        if cdf is not None:
            set_excluded(rc.merge_excluded(
                ss.excluded, cand_names,
                cdf.loc[~cdf["Use"], "Ingredient"]), "opt")
            st.caption("Unticked foods are remembered in this browser and "
                       "also left out of the recipe generator.")

        st.caption("With all tests on this can take up to a minute or two "
                   "on the hosted app – leave the page alone until the "
                   "results appear (clicking anything restarts the run).")
        if st.button("Run optimisation", type="primary", key="o_run"):
            ctx = {"kcal_target": o_kcal, "bw": ctx0.get("bw"),
                   "extended": ctx0.get("extended", False),
                   "max_g": ctx0.get("max_g"),
                   "renal": ctx0["renal"],
                   "ranges": dict(ctx0.get("ranges", {})),
                   "weights": weights, "aims": {k: v for k, v in
                                                aims.items() if v}}
            if o_ref is not None:
                ctx = rc.reference_context(
                    ctx, o_ref, "match" if obj == OBJ[1] else "both")
            names = list(bdf["Ingredient"])
            x0 = list(bdf["Current g"].astype(float))
            bounds = [(float(r["Min g"]), float(r["Max g"]),
                       bool(r["Lock"]) or db[r["Ingredient"]]["category"]
                       == "binder") for _, r in bdf.iterrows()]
            if any(lo > hi for lo, hi, _ in bounds):
                st.error("A minimum is larger than its maximum.")
            else:
                vecs = [rc._vec(db[n]) for n in names]
                before = rc.score_amounts(x0, vecs, ctx)
                if do_sug:
                    cands = list(cdf.loc[cdf["Use"], "Ingredient"])
                    if o_full:
                        cands = rc.complete_only(cands, db, ss.ext)
                    bar = st.progress(0.0, text="Testing additions…")

                    def prog(i, total, name):
                        bar.progress(min(1.0, (i + 1) / max(1, total)),
                                     text=f"Step 1/3 – additions "
                                          f"{i + 1}/{total}: {name}")
                    base, singles, combo = rc.suggest_additions(
                        names, db, bounds, x0, ctx, cands, max_add, prog)
                    bar.empty()
                else:
                    with st.spinner("Optimising…"):
                        base = rc.optimise(names, db, bounds, x0, ctx)
                    singles, combo = [], None
                subs = []
                if do_subs:
                    pool_s = (list(cdf.loc[cdf["Use"], "Ingredient"]) if do_sug
                              else [n for n in names_all
                                    if n not in ss.excluded])
                    if o_full:
                        pool_s = rc.complete_only(pool_s, db, ss.ext)
                    bar = st.progress(0.0, text="Testing substitutions…")

                    def prog_s(i, total, name):
                        bar.progress(min(1.0, (i + 1) / max(1, total)),
                                     text=f"Step 2/3 – substitutions "
                                          f"{i + 1}/{total}: {name}")
                    subs = rc.suggest_substitutions(names, db, bounds, base,
                                                    ctx, pool_s, prog_s)
                    bar.empty()
                rems = []
                if do_rem:
                    with st.spinner("Step 3/3 – testing removals…"):
                        rems = rc.suggest_removals(names, db, bounds, base,
                                                   ctx)
                ss.opt_result = {"ctx": ctx, "names": names, "x0": x0,
                                 "before": before[0], "base": base,
                                 "singles": singles, "combo": combo,
                                 "bounds": bounds, "manual": None,
                                 "subs": subs, "rems": rems}

        r = ss.opt_result
        if r:
            ctx = r["ctx"]
            g, s, terms = r["base"]
            st.divider()
            _c0 = {k: v for k, v in ctx.items() if k != "ref_match"}
            rt_o = rc.recipe_rating(r["names"], g, db, _c0)[0]
            rm_ = ctx.get("ref_match")
            st.markdown(f"**Score:** current {r['before']:.3f} → optimised "
                        f"**{s:.3f}**  " + (
                            f"(0 = same as {rm_['name']} per 1000 kcal"
                            + (")" if rm_["only"] else
                               " and every renal target met)")
                            if rm_ else "(0 = every target met)")
                        + f" · rating **{rt_o:.0f}**/100")
            if rm_:
                ref_o = next((r_ for r_ in rc.load_references()
                              if r_["name"] == rm_["name"]), None)
                if ref_o:
                    with st.expander(f"Optimised recipe vs {rm_['name']}",
                                     expanded=True):
                        _, tot_o, miss_o = rc.compute(
                            list(zip(r["names"], g)), db)[:3]
                        show_df(st, pd.DataFrame(
                            rc.reference_rows(tot_o, ref_o, miss_o, ss.ext),
                            columns=["Nutrient", "Unit", "Recipe /1000 kcal",
                                     "Reference /1000 kcal", "Difference"]),
                            hide_index=True, **FULL)
                        _rs = rc.reference_score(ref_o, ctx)[0]
                        _os = rc.score_amounts(
                            g, [rc._vec(db[n]) for n in r["names"]],
                            {k: v for k, v in ctx.items()
                             if k != "ref_match"})[0]
                        st.caption(f"Usual score (renal targets): reference "
                                   f"{_rs:.3f} · this optimised recipe "
                                   f"{_os:.3f}")
                        if rm_["only"]:
                            st.caption("Matching the reference only: renal "
                                       "targets are not checked here – see "
                                       "the status column and the Recipe "
                                       "tab after applying.")

            def recipe_table(names, grams, new=()):
                d_ = {"Ingredient": names,
                      "g/day": [round(x, 1) for x in grams]}
                if ss.meals > 1:
                    d_["g/meal"] = [round(x / ss.meals, 1) for x in grams]
                d_["kcal"] = [fmt_kcal(n, x) for n, x in zip(names, grams)]
                d_[""] = ["new" if n in new else "" for n in names]
                return pd.DataFrame(d_)

            def key_values(names, grams):
                vecs = [rc._vec(db[n]) for n in names]
                kcal, per, _ = rc.per1000_from(grams, vecs)
                out = []
                for k in ("protein", "p", "na", "k", "ca", "epa_dha"):
                    stt, _ = rc.status_for(k, per[k], ctx["renal"],
                                           rc.get_ranges(ctx))
                    out.append({"Per 1000 kcal": rc.LABEL[k],
                                "Value": f"{per[k]:.1f} {rc.UNIT[k]}",
                                "Status": stt})
                if per["p"]:
                    out.append({"Per 1000 kcal": "Ca:P ratio",
                                "Value": f"{per['ca'] / per['p']:.2f}",
                                "Status": "target 1–2"})
                return pd.DataFrame(out)

            def gaps(tt):
                items = [(k, round(v, 3)) for k, v in
                         sorted(tt.items(), key=lambda kv: -kv[1])
                         if v > 1e-4][:8]
                return ", ".join(f"{k} ({v})" for k, v in items) or \
                    "none – all targets met"

            oc1, oc2 = st.columns(2)
            with oc1:
                st.markdown("**Optimised daily amounts**")
                tb = recipe_table(r["names"], g)
                tb.insert(1, "was g", [round(x, 1) for x in r["x0"]])
                show_df(st, tb.drop(columns=[""]), hide_index=True,
                             **FULL)
                st.button("Apply optimised amounts", type="primary",
                          key="o_apply",
                          on_click=apply_recipe,
                          args=(r["names"], g, s, "Optimised recipe", ctx))
            with oc2:
                show_df(st, key_values(r["names"], g), hide_index=True,
                             **FULL)
                st.caption("Remaining gaps: " + gaps(terms))

            if r["singles"]:
                st.markdown("**Suggested additions** – each tested alone, "
                            "all amounts re-optimised")
                for i, (c, gg, ss_, tt) in enumerate(r["singles"][:10]):
                    pct = (1 - ss_ / s) * 100 if s > 0 else 0
                    why = ", ".join(rc.improvement_reasons(terms, tt)) or "–"
                    cc = st.columns([5, 1])
                    rt_s = rc.recipe_rating(r["names"] + [c], gg, db, _c0)[0]
                    cc[0].write(f"{i + 1}. **+ {gg[-1]:.1f} g {c}** → score "
                                f"{ss_:.3f} {rc.score_change(ss_, s)} · rating "
                                f"{rt_s:.0f} (was {rt_o:.0f}) · improves: "
                                f"{why}")
                    cc[1].button("Apply", key=f"o_s_{i}",
                                 on_click=apply_recipe,
                                 args=(r["names"] + [c], gg, ss_,
                                       f"Optimised + {c}", ctx))
            elif r["combo"] is not None:
                st.info("No single library ingredient improved the score by "
                        "≥2%.")
            if r.get("rems"):
                st.markdown("**Suggested removals** – the recipe does as well "
                            "or better without these (other amounts "
                            "re-optimised)")
                for i, (rm_n, rn, rg, rs, rt) in enumerate(r["rems"][:10]):
                    ch = (rs / s - 1) * 100 if s > 0 else 0
                    cc = st.columns([5, 1])
                    cc[0].write(f"{i + 1}. **− {rm_n}** → score {rs:.3f} "
                                f"({ch:+.0f}%) · rating "
                                f"{rc.recipe_rating(rn, rg, db, _c0)[0]:.0f}")
                    cc[1].button("Apply", key=f"o_rem_{i}",
                                 on_click=apply_recipe,
                                 args=(rn, rg, rs, f"Optimised − {rm_n}",
                                       ctx))
            elif r.get("rems") is not None and st.session_state.get("o_rem"):
                st.caption("Every ingredient is needed: removing any of them "
                           "makes the score >1 % worse.")
            if r.get("subs"):
                st.markdown("**Suggested substitutions** – one ingredient "
                            "swapped for another of the same type, all "
                            "amounts re-optimised")
                for i, (old_, new_, sn, sg, ss_, tt) in \
                        enumerate(r["subs"][:10]):
                    pct = (1 - ss_ / s) * 100 if s > 0 else 0
                    why = ", ".join(rc.improvement_reasons(terms, tt)) or "–"
                    gi = sn.index(new_)
                    cc = st.columns([5, 1])
                    rt_s = rc.recipe_rating(sn, sg, db, _c0)[0]
                    cc[0].write(f"{i + 1}. **{old_} → {sg[gi]:.1f} g "
                                f"{new_}** → score {ss_:.3f} "
                                f"{rc.score_change(ss_, s)} · rating "
                                f"{rt_s:.0f} (was {rt_o:.0f}) · improves: "
                                f"{why}")
                    cc[1].button("Apply", key=f"o_sub_{i}",
                                 on_click=apply_recipe,
                                 args=(sn, sg, ss_,
                                       f"Optimised, {old_} → {new_}", ctx))
            elif r.get("subs") is not None and st.session_state.get("o_subs"):
                st.caption("No substitution improved the score by ≥2%.")
            if r["combo"] and r["combo"][4]:
                cn, cg, cs, ct_, added = r["combo"]
                st.markdown(f"**Best combination** (adds {', '.join(added)})"
                            f" → score **{cs:.3f}** · rating "
                            f"{rc.recipe_rating(cn, cg, db, _c0)[0]:.0f}")
                cc = st.columns(2)
                show_df(cc[0], recipe_table(cn, cg, added), hide_index=True,
                                **FULL)
                show_df(cc[1], key_values(cn, cg), hide_index=True,
                                **FULL)
                cc[1].caption("Remaining gaps: " + gaps(ct_))
                st.button("Apply best combination", key="o_combo",
                          on_click=apply_recipe,
                          args=(cn, cg, cs, "Optimised + " + ", ".join(added),
                                ctx))

            # ---- user's own additions
            if r.get("bounds") is not None:
                st.markdown("**Add or remove ingredients yourself** – any "
                            "library ingredient; everything is re-optimised")
                has_combo = bool(r["combo"] and r["combo"][4])
                start = st.radio("Start from", ["Optimised recipe",
                                                "Best combination"],
                                 horizontal=True, key="o_man_start") \
                    if has_combo else "Optimised recipe"
                if start == "Best combination":
                    base_n, base_g, base_s = (r["combo"][0], r["combo"][1],
                                              r["combo"][2])
                else:
                    base_n, base_g, base_s = r["names"], g, s
                opts = [n for n in names_all if n not in base_n
                        and db[n]["per100g"]["kcal"] is not None]
                rem_sel = st.multiselect("Ingredients to remove",
                                         [n for n in base_n],
                                         key="o_man_rem")
                sel = st.multiselect("Ingredients to add", opts,
                                     key="o_man_sel")
                med = None
                if sel:
                    med = st.data_editor(
                        pd.DataFrame({
                            "Ingredient": sel,
                            "Min g": pd.Series([None] * len(sel),
                                               dtype="float"),
                            "Max g": pd.Series([None] * len(sel),
                                               dtype="float")}),
                        hide_index=True, **FULL, disabled=["Ingredient"],
                        key="o_man_ed_" + str(abs(hash(tuple(sel)))),
                        column_config={
                            "Min g": st.column_config.NumberColumn(
                                "Min g", min_value=0.0, format="%g",
                                help="Blank = 0. Min = Max fixes the "
                                     "amount."),
                            "Max g": st.column_config.NumberColumn(
                                "Max g", min_value=0.0, format="%g",
                                help="Blank = default limit")})
                    st.caption("Leave both blank to let the optimiser choose "
                               "the amount (it may choose 0 g if the "
                               "ingredient does not help). Set Min g to make "
                               "sure it is included; Min = Max for an exact "
                               "amount.")
                if (sel or rem_sel) and st.button("Re-optimise with these",
                                                  key="o_man_run"):
                        adds = [(rw["Ingredient"],
                                 None if pd.isna(rw["Min g"])
                                 else float(rw["Min g"]),
                                 None if pd.isna(rw["Max g"])
                                 else float(rw["Max g"]))
                                for _, rw in med.iterrows()] \
                            if med is not None else []
                        bad = [a for a, lo, hi in adds if lo is not None
                               and hi is not None and lo > hi]
                        if bad:
                            st.error("Min g is larger than Max g for: "
                                     + ", ".join(bad))
                        else:
                            bb = list(r["bounds"]) + [
                                (*rc.default_bounds(db[n],
                                                    ctx["kcal_target"]),
                                 False) for n in base_n[len(r["names"]):]]
                            if len(rem_sel) >= len(base_n) and not adds:
                                st.error("That would remove everything.")
                            else:
                                with st.spinner("Optimising…"):
                                    r["manual"] = (base_s,) + \
                                        rc.remove_and_add(base_n, db, bb,
                                                          base_g, ctx,
                                                          rem_sel, adds)
                man = r.get("manual")
                if man:
                    ms0, mn, mg, ms, mt = man
                    new = [n for n in mn if n not in r["names"]]
                    gone = [n for n in r["names"] if n not in mn]
                    st.markdown(f"**With your changes** → score "
                                f"**{ms:.3f}** (was {ms0:.3f})"
                                + (f" · removed: {', '.join(gone)}"
                                   if gone else ""))
                    cc = st.columns(2)
                    show_df(cc[0], recipe_table(mn, mg, new), hide_index=True,
                            **FULL)
                    show_df(cc[1], key_values(mn, mg), hide_index=True,
                            **FULL)
                    cc[1].caption("Remaining gaps: " + gaps(mt))
                    st.button("Apply this recipe", key="o_man_apply",
                              type="primary", on_click=apply_recipe,
                              args=(mn, mg, ms, "Optimised + own changes",
                                    ctx))

# ================================================================ GENERATE
with tab_gen:
    st.subheader("Generate balanced recipes from the library")
    ctx0 = score_context()
    g1, g2, g3 = st.columns(3)
    gk = g1.number_input("Target kcal/day", 1.0, 10000.0,
                         float(round(ctx0["kcal_target"])), key="g_kcal")
    gn = g2.slider("Recipes", 1, 10, 5, key="g_n")
    gmax = g3.slider("Max. foods each", 3, 9, 6, key="g_max",
                     help="Salt, supplements and oils are extra (up to 3).")
    v1, v2, v3 = st.columns(3)
    gveg_lo, gveg_hi = v1.slider(
                     "Vegetables per recipe (min – max)", 0, 6, (1, 3),
                     key="g_veg_rng",
                     help="Non-starchy vegetables (incl. mushrooms and "
                          "low-calorie fruit such as apple): at least the "
                          "minimum, more up to the maximum only if they "
                          "improve the recipe. "
                          "Potato, sweet potato and banana count as starch; "
                          "peas and chickpeas as 'other' – see the Role "
                          "column in the results.")
    guse = v2.slider("Same vegetable in max. … recipes", 1, 10, 2,
                     key="g_use")
    gmin = v3.number_input("Min. g per vegetable", 0.0, 500.0,
                           float(round(0.04 * gk)), key="g_min")
    fixed_base = st.checkbox(
        "Keep the current recipe items as a fixed base (e.g. breakfast "
        "kibble): " + (", ".join(f"{n} {g:g} g" for n, g in ss.recipe)
                       or "recipe is empty"),
        False, key="g_fixed", disabled=not ss.recipe)
    ign = st.checkbox("Ignore vitamin minimums (A, B vitamins, folate, "
                      "choline, D, E) – I will add a vitamin supplement",
                      True, key="g_ign",
                      help="Whole eggs are the only B12 source in the "
                           "library, so without this every recipe is pushed "
                           "towards egg yolk. Fat, Ca and Mg minimums still "
                           "apply.")
    gnames = sorted((n for n in db if db[n]["per100g"]["kcal"] is not None
                     and rc.ingredient_role(db[n]) != "binder"),
                    key=lambda n: (rc.ROLES.index(rc.ingredient_role(db[n])),
                                   n.lower()))
    fc = st.columns([3, 2])
    g_full = fc[0].checkbox(
        "Only ingredients with complete data", False, key="g_full",
        help="Leaves out foods with any unknown value among the nutrients "
             "checked (all nutrients with Extended nutrients on). Values "
             "assumed at the AAFCO minimum for complete foods count as "
             "unknown. Always-include and fixed-base items are kept.")
    g_full_ch = fc[1].checkbox(
        "…but allow missing choline", True, key="g_full_ch",
        disabled=not g_full,
        help="Choline is not in the food tables used, so most foods lack "
             "it; untick to require it too.")
    _allow = ("choline",) if g_full_ch else ()
    _miss = {n: rc.missing_data(db[n], ss.ext, _allow) for n in gnames}
    if g_full:
        st.caption(f"{sum(1 for n in gnames if not _miss[n])} of "
                   f"{len(gnames)} ingredients have complete data"
                   + (" (extended nutrients)" if ss.ext else "") + ".")
    st.caption("Untick **Use** for anything you do not want (e.g. animal "
               "products). Tick **Always include** to force an ingredient "
               "into every recipe – its amount is optimised but never below "
               "**Min g** (blank = 5 g, 0.5 g for oils/supplements). **Max g** "
               "caps an ingredient whenever it is used. A forced "
               "protein, starch or vegetable fills that role. Roles are "
               "assigned automatically.")
    _gkey = (f"g_pool_{ss.lib_ver}_{ss.gen_ex_ver}_{int(ss.ext)}_"
             f"{int(g_full_ch)}")
    if ss.get("gen_key_last") != _gkey:      # fresh editor: current settings
        ss.gen_key_last = _gkey
        ss.gen_set_base = ss.gen_set
        ss.gen_ex_base = set(ss.excluded)
    gdf = st.data_editor(
        pd.DataFrame({"Use": [n not in ss.gen_ex_base for n in gnames],
                      "Always include": [n in ss.gen_set_base["forced"]
                                         for n in gnames],
                      "Min g": pd.Series([ss.gen_set_base["min"].get(n)
                                          for n in gnames], dtype="float"),
                      "Max g": pd.Series([ss.gen_set_base["max"].get(n)
                                          for n in gnames], dtype="float"),
                      "Role": [rc.ingredient_role(db[n]) for n in gnames],
                      "Ingredient": gnames,
                      "Missing data": [", ".join(_miss[n][:6]) +
                                       ("…" if len(_miss[n]) > 6 else "")
                                       for n in gnames]}),
        hide_index=True, **FULL, height=300,
        disabled=["Role", "Ingredient", "Missing data"],
        key=_gkey,
        column_config={"Min g": st.column_config.NumberColumn(
            "Min g", min_value=0.0, step=1.0, format="%g"),
            "Max g": st.column_config.NumberColumn(
            "Max g", min_value=0.0, step=1.0, format="%g",
            help="Upper limit (g/day) whenever this ingredient is used; "
                 "blank = no limit")})
    set_excluded(rc.merge_excluded(ss.excluded, gnames,
                                   gdf.loc[~gdf["Use"], "Ingredient"]), "gen")
    _shown = set(gnames)
    _old = ss.gen_set
    set_gen_settings({
        "forced": [n for n in _old["forced"] if n not in _shown]
        + list(gdf.loc[gdf["Always include"], "Ingredient"]),
        "min": {**{n: v for n, v in _old["min"].items() if n not in _shown},
                **{rw["Ingredient"]: float(rw["Min g"])
                   for _, rw in gdf.iterrows() if pd.notna(rw["Min g"])}},
        "max": {**{n: v for n, v in _old["max"].items() if n not in _shown},
                **{rw["Ingredient"]: float(rw["Max g"])
                   for _, rw in gdf.iterrows() if pd.notna(rw["Max g"])}}})
    st.caption("Your ticks and Min/Max values are remembered in this "
               "browser; unticked foods are also left out of the optimiser's "
               "suggested additions.")

    if st.button("Generate", type="primary", key="g_run"):
        ctx = score_context(gk)
        if ign:
            ctx["weights"]["vitamins"] = 0.0
        frows = gdf[gdf["Always include"]]
        forced = {rw["Ingredient"]: (None if pd.isna(rw["Min g"])
                                     else float(rw["Min g"]))
                  for _, rw in frows.iterrows()}
        pool = list(gdf.loc[gdf["Use"] | gdf["Always include"],
                            "Ingredient"])
        if g_full:
            pool = rc.complete_only(
                pool, db, ss.ext, g_full_ch,
                keep=set(forced) | ({n for n, _ in ss.recipe}
                                    if fixed_base else set()))
        max_each = {rw["Ingredient"]: float(rw["Max g"])
                    for _, rw in gdf.iterrows() if pd.notna(rw["Max g"])}
        clash = [n for n, m in forced.items()
                 if m is not None and n in max_each and m > max_each[n]]
        if clash:
            st.error("Min g is larger than Max g for: " + ", ".join(clash))
        elif len(pool) < 2:
            st.error("Select more ingredients.")
        else:
            bar = st.progress(0.0, text="Starting…")

            def prog(text, i, total):
                bar.progress(min(1.0, i / max(1, total)),
                             text=f"{text} ({i}/{total})")
            res = rc.generate_recipes(
                db, pool, ctx, gn, gmax,
                [tuple(x) for x in ss.recipe] if fixed_base else (),
                prog, n_veg=gveg_lo, veg_max=gveg_hi, veg_max_uses=guse,
                veg_min_g=gmin,
                forced=forced, max_each=max_each)
            bar.empty()
            ss.gen_result = {"ctx": ctx, "res": res, "forced": list(forced),
                             "n_fixed": len(ss.recipe) if fixed_base else 0}

    gr = ss.gen_result
    if gr:
        ctx = gr["ctx"]
        if not gr["res"]:
            st.warning("No recipes found – select more ingredients.")
        if ctx["weights"].get("vitamins", 1) == 0:
            st.warning("Vitamin minimums were ignored – add a vitamin "
                       "supplement (B-complex incl. B12; vitamin A only if "
                       "your vet agrees).")
        for i, (names, g, s, terms) in enumerate(gr["res"]):
            vecs = [rc._vec(db[n]) for n in names]
            kcal, per, _ = rc.per1000_from(g, vecs)
            rt_, rparts = rc.recipe_rating(names, g, db, ctx)
            title = (f"Recipe {i + 1} · score {s:.3f} · rating {rt_:.0f} · "
                     f"{sum(g):.0f} g/day · "
                     + ", ".join(n.split(",")[0] for n, a in zip(names, g)
                                 if rc.ingredient_role(db[n]) in
                                 ("protein", "starch", "veg")))
            with st.expander(title, expanded=(i == 0)):
                st.caption("Rating " + f"{rt_:.0f}/100 – " + " · ".join(
                    f"{rc.RATING_LABELS[k]} {rparts[k] * 100:.0f}%"
                    for k in rc.RATING_W))
                cc = st.columns([3, 2])
                show_df(cc[0], pd.DataFrame({
                    "Ingredient": names,
                    "Role": [rc.ingredient_role(db[n]) for n in names],
                    "g/day": [round(x, 1) for x in g],
                    **({"g/meal": [round(x / ss.meals, 1) for x in g]}
                       if ss.meals > 1 else {}),
                    "kcal": [fmt_kcal(n, x) for n, x in zip(names, g)],
                    "": ["fixed" if j < gr["n_fixed"] else
                         "forced" if n in gr.get("forced", []) else ""
                         for j, n in enumerate(names)]}),
                    hide_index=True, **FULL)
                capr = per["ca"] / per["p"] if per["p"] else 0
                cc[1].markdown(
                    f"Per 1000 kcal: protein **{per['protein']:.0f} g**, "
                    f"P **{max(0, per['p'] - per['p_bind']):.0f} mg**, "
                    f"Na {per['na']:.0f} mg, K {per['k']:.0f} mg, "
                    f"Ca:P **{capr:.2f}**, EPA+DHA {per['epa_dha']:.0f} mg")
                gaps_ = [f"{k} {v:.3f}" for k, v in
                         sorted(terms.items(), key=lambda kv: -kv[1])[:4]
                         if v > 1e-3]
                cc[1].caption("Remaining gaps: " + (", ".join(gaps_)
                                                    or "none"))
                cc[1].button("Use this recipe", key=f"g_apply_{i}",
                             type="primary", on_click=apply_recipe,
                             args=(names, g, s, f"Generated recipe #{i + 1}",
                                   ctx))

# ================================================================ LIBRARY
with tab_lib:
    st.subheader("Ingredient library")
    st.caption(f"{len(db)} ingredients · values per 100 g · blank = unknown "
               f"· shared with the desktop app ({os.path.basename(rc.DB_PATH)})")
    lib_keys = rc.visible_keys(ss.ext)
    lib_rows = []
    for n in names_all:
        it = db[n]
        row = {"name": n, "category": it["category"],
               "note": it.get("note", "")}
        row.update({k: it["per100g"][k] for k in rc.KEYS})
        row["assume_aafco"] = bool(it.get("assume_aafco"))
        lib_rows.append(row)
    full_df = pd.DataFrame(lib_rows)        # all columns, for export
    flag_col = ["assume_aafco"] if ss.ext else []   # extended mode only
    ldf = full_df[["name", "category", "note"] + flag_col + lib_keys]
    cfg = {"category": st.column_config.SelectboxColumn(
        "category", options=["food", "supplement", "binder",
                             "commercial food", "imported"])}
    cfg.update({k: st.column_config.NumberColumn(
        f"{rc.LABEL[k]} ({rc.UNIT[k]})", format="%g") for k in lib_keys})
    cfg["assume_aafco"] = st.column_config.CheckboxColumn(
        "Complete food (assume AAFCO)",
        help="Missing extended nutrients are assumed to be at the AAFCO "
             "adult minimum (complete commercial foods only).")
    _m = view("mob", "libnote")
    if _m:
        with _m:
            st.caption("📱 This table is wide – swipe sideways, or edit on a "
                       "larger screen.")
    led = st.data_editor(ldf, key=f"lib_{ss.lib_ver}", num_rows="dynamic",
                         hide_index=True, **FULL,
                         height=420, column_config=cfg)
    lc = st.columns(3)
    if lc[0].button("💾 Save library changes", type="primary"):
        new_db = {}
        for idx, rw in led.iterrows():
            nm = str(rw["name"]).strip() if pd.notna(rw["name"]) else ""
            if not nm:
                continue
            # hidden (extended) columns keep their stored values
            try:
                orig = db.get(names_all[int(idx)])
            except (TypeError, ValueError, IndexError):
                orig = None
            orig = orig or db.get(nm)
            per = {k: (orig["per100g"].get(k) if orig else None)
                   for k in rc.KEYS}
            per.update({k: (None if pd.isna(rw[k]) else float(rw[k]))
                        for k in lib_keys})
            flag = (rw["assume_aafco"] if "assume_aafco" in rw
                    else bool(orig and orig.get("assume_aafco")))
            new_db[nm] = rc.normalise({
                "name": nm, "category": rw["category"] or "food",
                "note": rw["note"] if pd.notna(rw["note"]) else "",
                "per100g": per, "assume_aafco": flag,
                "role": orig.get("role") if orig else None})
        ss.db = new_db
        rc.save_db(new_db)
        ss.lib_ver += 1
        st.success(f"Saved {len(new_db)} ingredients.")
        st.rerun()
    out = io.StringIO()
    full_df.to_csv(out, index=False)
    lc[1].download_button("⬇️ Export library (.csv)", out.getvalue(),
                          file_name="ingredient_library.csv",
                          mime="text/csv")
    tmpl = io.StringIO()
    wt = csv.writer(tmpl)
    wt.writerow(["name", "category", "note"] + rc.KEYS + ["assume_aafco"])
    wt.writerow(["# units per 100 g ->", "", ""] +
                [rc.UNIT[k] for k in rc.KEYS] + ["1 = complete food"])
    lc[2].download_button("⬇️ CSV template", tmpl.getvalue(),
                          file_name="ingredients_template.csv",
                          mime="text/csv")

    st.markdown("#### Import ingredients (CSV or JSON)")
    imp = st.file_uploader("Same formats as the desktop app; same-name "
                           "entries are overwritten.", type=["csv", "json"],
                           key="lib_imp")
    if imp is not None and st.button("Import", key="lib_imp_go"):
        try:
            items = []
            if imp.name.lower().endswith(".json"):
                data = json.load(imp)
                items = data if isinstance(data, list) else [data]
            else:
                text = imp.getvalue().decode("utf-8-sig")
                for row in csv.DictReader(io.StringIO(text)):
                    row = {(k or "").strip().lower(): v for k, v in
                           row.items()}
                    nm = (row.get("name") or "").strip()
                    if not nm or nm.startswith("#"):
                        continue
                    per = {k: (0.0 if (k in rc.OPTIONAL_ZERO and k not in row)
                               else rc.to_float(row.get(k, "") or ""))
                           for k in rc.KEYS}
                    items.append({"name": nm, "category":
                                  (row.get("category") or "imported").strip(),
                                  "note": (row.get("note") or "").strip(),
                                  "per100g": per,
                                  "assume_aafco": row.get("assume_aafco", "")})
            new = sum(1 for i in items if i["name"] not in db)
            for i in items:
                db[str(i["name"]).strip()] = rc.normalise(i)
            rc.save_db(db)
            ss.lib_ver += 1
            st.success(f"Imported {len(items)} ({new} new, "
                       f"{len(items) - new} updated).")
            st.rerun()
        except (ValueError, KeyError) as e:
            st.error(f"Import failed: {e}")

    st.markdown("#### Add from a pet-food label")
    with st.form("label_form", clear_on_submit=True):
        lname = st.text_input("Name (e.g. Bonza vegan kibble)")
        fc = st.columns(4)
        vals = {}
        for i, (k, lab) in enumerate(rc.LABEL_FIELDS):
            vals[k] = fc[i % 4].text_input(lab, key=f"lab_{k}")
        st.caption("As-fed values from the label. Blank = unknown. Without "
                   "kcal/kg, energy is estimated (modified Atwater).")
        if st.form_submit_button("Add to library"):
            try:
                v = {k: rc.to_float(x) for k, x in vals.items()}
            except ValueError:
                st.error("Invalid number.")
                v = None
            if v is not None:
                if not lname.strip():
                    st.error("Name is required.")
                else:
                    db[lname.strip()] = rc.normalise({
                        "name": lname.strip(), "category": "commercial food",
                        "note": "From label (as fed).",
                        "per100g": rc.per100g_from_label(v)})
                    rc.save_db(db)
                    ss.lib_ver += 1
                    st.success(f"Added {lname.strip()}.")
                    st.rerun()

    # ---- reference diets (comparison only, not ingredients)
    st.markdown("#### Reference diets (for comparison, not ingredients)")
    refs_all = rc.load_references()
    st.caption("Shown on the Recipe tab → Composition → *Compare with a "
               "reference diet*. Loaded: " +
               (", ".join(r_["name"] for r_ in refs_all) or "none") + ".")
    rc1, rc2 = st.columns(2)
    rt = io.StringIO()
    csv.writer(rt).writerows(rc.reference_template_rows())
    rc1.download_button("⬇️ Reference CSV template", rt.getvalue(),
                        file_name="reference_template.csv", mime="text/csv")
    rc2.download_button("⬇️ Export reference diets",
                        json.dumps(refs_all, indent=1, ensure_ascii=False),
                        file_name="renal_references.json",
                        mime="application/json", disabled=not refs_all)
    rimp = st.file_uploader("Import reference diets (CSV template or JSON; an "
                            "ingredient JSON also works). Same-name entries "
                            "are replaced. Blank kcal is estimated from "
                            "protein, fat, fibre, ash and moisture.",
                            type=["csv", "json"], key="ref_imp")
    if rimp is not None and st.button("Import reference diets",
                                      key="ref_imp_go"):
        try:
            items = rc.parse_references(rimp.name, rimp.getvalue())
            n_new, n_upd = rc.import_references(items)
            st.success(f"Imported {len(items)} ({n_new} new, {n_upd} "
                       "updated).")
            st.rerun()
        except (ValueError, KeyError, TypeError) as e:
            st.error(f"Import failed: {e}")
    if refs_all:
        dc1, dc2 = st.columns([3, 1])
        rdel = dc1.selectbox("Delete a reference diet",
                             [r_["name"] for r_ in refs_all], key="ref_del")
        if dc2.button("Delete", key="ref_del_go"):
            rc.delete_reference(rdel)
            st.rerun()

# ================================================================ ABOUT
with tab_about:
    st.markdown("""
**What it checks** – protein, phosphorus (net of any binder), calcium and
Ca:P, sodium, potassium, magnesium, fat and energy density, vitamins A, B1,
B2, B3, B5, B6, B12, folate, choline, D (min and max), E, C, EPA+DHA,
acid load (indicative) and calories vs the dog's daily need. With
*Extended nutrients* on (sidebar): essential amino acids, linoleic acid and
trace minerals (Fe, Cu, Mn, Zn, I, Se) vs AAFCO adult minimums; fill these
values with `fdc_fill.py`.

**Targets** – ACVN Nutrition Notes renal-diet ranges for dogs (per 1000
kcal), AAFCO adult maintenance minimums/maximums, IRIS serum phosphate
targets by stage. Ingredient values approximate USDA FoodData Central.

**Score** – weighted sum of squared relative deviations outside each target
(0 = all met). Weights are this app's judgement calls, editable on the
Optimise tab.

**Oxalate** – dietary oxalate can form calcium-oxalate crystals, which
are to be avoided in dogs with reduced kidney function or stone history
(high-oxalate foods such as spinach, Swiss chard, sweet potato, peanuts,
buckwheat and chia). There is no canine numeric limit: this app penalises
oxalate above 50 mg/1000 kcal (its own judgement, scaled from human
low-oxalate diets; weight editable on the Optimise tab) and flags foods
≥100 mg/100 g. Values: Oxalosis & Hyperoxaluria Foundation food list
(2024), approximate – plant oxalate varies with variety and cooking.
[Cook & Atiee, Today's Veterinary Practice 2026]
(https://todaysveterinarypractice.com/urology-renal-medicine/understanding-and-addressing-canine-calcium-oxalate-urolithiasis/)
· [OHF oxalate list](https://ohf.org/wp-content/uploads/2024/02/Oxalate-List-022724.pdf)

**Not checked** – trace minerals (Zn, Cu, Fe, I, Se), vitamin K, biotin,
essential fatty-acid balance, amino-acid balance. A home-made renal diet
needs a balancing supplement and should be checked by a vet nutritionist.
Never force-feed (food aversion). Binders and vitamin D only as prescribed.

Sources: [UC Davis – Nutritional Management of Chronic Renal Disease]
(https://www.vetmed.ucdavis.edu/hospital/animal-health-topics/chronic-renal-disease)
· [ACVN Nutrition Notes – CKD]
(https://todaysveterinarypractice.com/wp-content/uploads/sites/4/2016/05/2016-0304_ACVN-Nutrition.pdf)
· [IRIS](https://www.iris-kidney.com/iris-guidelines-1)
""")

store_excluded_in_browser()
