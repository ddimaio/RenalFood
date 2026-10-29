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

# Streamlit keeps imported modules in memory between reruns, so after an
# update the new app script can meet the old engine. Reload it if stale.
ENGINE_VERSION = "2026.10.29i"
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
                 "blood_eval": None, "ext": False, "max_g": 0.0}.items():
    ss.setdefault(key, val)
db = ss.db

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
                "of phosphorus is over 1.5× its share of calories.")
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
        df = pd.DataFrame(ss.recipe or [], columns=["Ingredient", "g"])
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
        st.caption("Add a row at the bottom of the table; select rows and "
                   "press Delete to remove them.")

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

        with st.expander("💾 Save / load recipe"):
            payload = {"items": ss.recipe, "bw": str(ss.bw),
                       "max_g": str(ss.max_g),
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
                          score_context())
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
                "/100 g DM", "/1000 kcal", "Per day", "Renal range",
                "AAFCO min", "Status"]
        comp = pd.DataFrame([v for v, _ in a["rows"]], columns=cols)
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
        max_add = st.slider("Max. additions to combine", 1, 6, 3,
                            key="o_max")
        cand_names = [n for n in names_all
                      if n not in dict(ss.recipe)
                      and db[n]["category"] != "binder"
                      and db[n]["per100g"]["kcal"] is not None]
        cdf = st.data_editor(
            pd.DataFrame({"Use": True, "Role": [rc.ingredient_role(db[n])
                                                 for n in cand_names],
                          "Ingredient": cand_names}),
            hide_index=True, **FULL, height=250,
            disabled=["Role", "Ingredient"], key=f"o_cand_{ss.rec_ver}") \
            if do_sug else None

        if st.button("Run optimisation", type="primary", key="o_run"):
            ctx = {"kcal_target": o_kcal, "bw": ctx0.get("bw"),
                   "extended": ctx0.get("extended", False),
                   "max_g": ctx0.get("max_g"),
                   "renal": ctx0["renal"],
                   "ranges": dict(ctx0.get("ranges", {})),
                   "weights": weights, "aims": {k: v for k, v in
                                                aims.items() if v}}
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
                    bar = st.progress(0.0, text="Testing additions…")

                    def prog(i, total, name):
                        bar.progress(min(1.0, (i + 1) / max(1, total)),
                                     text=f"Testing {i + 1}/{total}: {name}")
                    base, singles, combo = rc.suggest_additions(
                        names, db, bounds, x0, ctx, cands, max_add, prog)
                    bar.empty()
                else:
                    with st.spinner("Optimising…"):
                        base = rc.optimise(names, db, bounds, x0, ctx)
                    singles, combo = [], None
                ss.opt_result = {"ctx": ctx, "names": names, "x0": x0,
                                 "before": before[0], "base": base,
                                 "singles": singles, "combo": combo}

        r = ss.opt_result
        if r:
            ctx = r["ctx"]
            g, s, terms = r["base"]
            st.divider()
            st.markdown(f"**Score:** current {r['before']:.3f} → optimised "
                        f"**{s:.3f}**  (0 = every target met)")

            def recipe_table(names, grams, new=()):
                return pd.DataFrame({
                    "Ingredient": names, "g/day": [round(x, 1) for x in grams],
                    "kcal": [fmt_kcal(n, x) for n, x in zip(names, grams)],
                    "": ["new" if n in new else "" for n in names]})

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
                    cc[0].write(f"{i + 1}. **+ {gg[-1]:.1f} g {c}** → score "
                                f"{ss_:.3f} (−{pct:.0f}%) · improves: {why}")
                    cc[1].button("Apply", key=f"o_s_{i}",
                                 on_click=apply_recipe,
                                 args=(r["names"] + [c], gg, ss_,
                                       f"Optimised + {c}", ctx))
            elif r["combo"] is not None:
                st.info("No single library ingredient improved the score by "
                        "≥2%.")
            if r["combo"] and r["combo"][4]:
                cn, cg, cs, ct_, added = r["combo"]
                st.markdown(f"**Best combination** (adds {', '.join(added)})"
                            f" → score **{cs:.3f}**")
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
    gveg = v1.slider("Vegetables per recipe", 0, 4, 2, key="g_veg",
                     help="Exact number of non-starchy vegetables (incl. "
                          "mushrooms and low-calorie fruit such as apple). "
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
    st.caption("Untick **Use** for anything you do not want (e.g. animal "
               "products). Tick **Always include** to force an ingredient "
               "into every recipe – its amount is optimised but never below "
               "**Min g** (blank = 5 g, 0.5 g for oils/supplements). A forced "
               "protein, starch or vegetable fills that role. Roles are "
               "assigned automatically.")
    gdf = st.data_editor(
        pd.DataFrame({"Use": True, "Always include": False,
                      "Min g": pd.Series([None] * len(gnames),
                                         dtype="float"),
                      "Role": [rc.ingredient_role(db[n]) for n in gnames],
                      "Ingredient": gnames}),
        hide_index=True, **FULL, height=300,
        disabled=["Role", "Ingredient"], key=f"g_pool_{ss.lib_ver}",
        column_config={"Min g": st.column_config.NumberColumn(
            "Min g", min_value=0.0, step=1.0, format="%g")})

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
        if len(pool) < 2:
            st.error("Select more ingredients.")
        else:
            bar = st.progress(0.0, text="Starting…")

            def prog(text, i, total):
                bar.progress(min(1.0, i / max(1, total)),
                             text=f"{text} ({i}/{total})")
            res = rc.generate_recipes(
                db, pool, ctx, gn, gmax,
                [tuple(x) for x in ss.recipe] if fixed_base else (),
                prog, n_veg=gveg, veg_max_uses=guse, veg_min_g=gmin,
                forced=forced)
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
            title = (f"Recipe {i + 1} · score {s:.3f} · {sum(g):.0f} g/day · "
                     + ", ".join(n.split(",")[0] for n, a in zip(names, g)
                                 if rc.ingredient_role(db[n]) in
                                 ("protein", "starch", "veg")))
            with st.expander(title, expanded=(i == 0)):
                cc = st.columns([3, 2])
                show_df(cc[0], pd.DataFrame({
                    "Ingredient": names,
                    "Role": [rc.ingredient_role(db[n]) for n in names],
                    "g/day": [round(x, 1) for x in g],
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
                "per100g": per, "assume_aafco": flag})
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
