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

import renal_diet_calc as rc

st.set_page_config(page_title="Renal Diet Calculator", page_icon="🐕",
                   layout="wide")

# full-width tables on old and new Streamlit versions
_ver = tuple(int(x) for x in st.__version__.split(".")[:2])
FULL = {"width": "stretch"} if _ver >= (1, 49) else {"use_container_width": True}

# ---------------------------------------------------------------- state
ss = st.session_state
if "db" not in ss:
    ss.db = rc.load_db()
for key, val in {"recipe": [], "rec_ver": 0, "recipe_note": "",
                 "applied": None, "score_ctx": None, "opt_result": None,
                 "gen_result": None, "bw": 6.0, "factor": 1.6,
                 "stage": "Stage 2", "lib_ver": 0}.items():
    ss.setdefault(key, val)
db = ss.db

TAG_COLOUR = {"ok": "color: #1b7a1b", "warn": "color: #b36b00",
              "bad": "color: #c0392b; font-weight: 600", "": ""}


def need_now():
    return rc.mer(ss.bw, ss.factor)


def score_context(kcal=None):
    """Last optimiser/generator settings for this stage, else defaults."""
    sc = ss.score_ctx or {}
    same = sc.get("stage") == ss.stage
    return {"kcal_target": kcal or sc.get("kcal_override") or need_now(),
            "renal": rc.STAGES[ss.stage][0],
            "weights": {**rc.OPT_WEIGHTS, **sc.get("weights", {})},
            "aims": (dict(sc["aims"]) if same and "aims" in sc
                     else dict(rc.AIMS[ss.stage]))}


def set_recipe(recipe):
    ss.recipe = [[n, float(g)] for n, g in recipe]
    ss.rec_ver += 1                      # rebuild the editor widget


def apply_recipe(names, g, score, label, ctx):
    set_recipe([(n, a) for n, a in zip(names, g) if a >= 0.1])
    ss.score_ctx = {"stage": ss.stage, "weights": dict(ctx["weights"]),
                    "aims": dict(ctx["aims"])}
    if abs(ctx["kcal_target"] - need_now()) > 1:
        ss.score_ctx["kcal_override"] = ctx["kcal_target"]
    ss.recipe_note = (f"{label} – score {score:.3f} "
                      f"({ctx['kcal_target']:.0f} kcal/day, {ss.stage})")
    ss.applied = [list(r) for r in ss.recipe]
    st.toast("Recipe applied – open the Recipe tab")


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
    st.selectbox("IRIS stage", list(rc.STAGES), key="stage")
    st.metric("Daily energy need (MER)", f"{need_now():.0f} kcal")
    st.caption(rc.STAGES[ss.stage][1])
    st.divider()
    st.caption("Approximate tool – not veterinary advice. A home-made renal "
               "diet should be balanced by a vet nutritionist.")

tab_rec, tab_opt, tab_gen, tab_lib, tab_about = st.tabs(
    ["🍲 Recipe & analysis", "⚙️ Optimise", "✨ Generate recipes",
     "📚 Ingredient library", "ℹ️ About"])

names_all = sorted(db, key=str.lower)

# ================================================================ RECIPE
with tab_rec:
    if ss.recipe_note:
        edited = ss.recipe != ss.applied
        st.success(ss.recipe_note + ("   (edited since)" if edited else ""))

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
                    width="large"),
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
            m = st.columns(5)
            m[0].metric("Score (0 = all met)",
                        f"{a['score']:.3f}" if a["score"] is not None
                        else "–")
            m[1].metric("Energy", f"{t['kcal']:.0f} kcal",
                        f"{t['kcal'] - need_now():+.0f} vs need")
            m[2].metric("Protein", f"{t['protein'] * k1000:.0f} g/1000kcal")
            m[3].metric("Phosphorus (net)",
                        f"{rc.net_p(t) * k1000:.0f} mg/1000kcal")
            m[4].metric("Ca : P",
                        f"{t['ca'] / t['p']:.2f}" if t["p"] else "–")
            st.subheader("Assessment")
            st.markdown("\n".join(
                ("- " + ln[2:]) if ln.startswith("• ") else
                (ln + "\n" if ln else "") for ln in a["notes"].splitlines()))

    if a["mass"] > 0:
        st.divider()
        ct, bt = st.tabs(["Composition", "Ingredient breakdown"])
        with ct:
            sm = pd.DataFrame(a["summary"],
                              columns=["Summary", "Unit", "Value", "Note"])
            st.dataframe(sm, hide_index=True, **FULL)
            cols = ["Nutrient", "Unit", "Recipe total", "/100 g fed",
                    "/100 g DM", "/1000 kcal", "Per day", "Renal range",
                    "AAFCO min", "Status"]
            comp = pd.DataFrame([v for v, _ in a["rows"]], columns=cols)
            tags = [tg for _, tg in a["rows"]]
            styled = comp.style.apply(
                lambda r: [TAG_COLOUR.get(tags[r.name], "")] * len(r),
                axis=1)
            st.dataframe(styled, hide_index=True, **FULL,
                         height=35 * (len(comp) + 1) + 3)
        with bt:
            bcols = [c for _, c, _ in rc.App.BRK_COLS]
            st.dataframe(pd.DataFrame(a["breakdown"], columns=bcols),
                         hide_index=True, **FULL)
            st.caption("'?' = value unknown for that ingredient.")

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
                                 key="o_kcal",
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
                    step=0.5, key=f"w_{k}")
            aims = {}
            if ctx0["renal"]:
                ac = st.columns(2)
                for i, k in enumerate(("protein", "p")):
                    lo, hi = rc.RENAL[k]
                    aims[k] = ac[i].number_input(
                        f"Aim {rc.LABEL[k]} ({rc.UNIT[k]}/1000 kcal), range "
                        f"{lo}–{hi}", 0.0, 5000.0,
                        float(ctx0["aims"].get(k, (lo + hi) / 2)),
                        key=f"aim_{k}")
            st.caption("Aims are this app's editable defaults inside the "
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
            ctx = {"kcal_target": o_kcal, "renal": ctx0["renal"],
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
                    stt, _ = rc.status_for(k, per[k], ctx["renal"])
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
                st.dataframe(tb.drop(columns=[""]), hide_index=True,
                             **FULL)
                st.button("Apply optimised amounts", type="primary",
                          key="o_apply",
                          on_click=apply_recipe,
                          args=(r["names"], g, s, "Optimised recipe", ctx))
            with oc2:
                st.dataframe(key_values(r["names"], g), hide_index=True,
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
                cc[0].dataframe(recipe_table(cn, cg, added), hide_index=True,
                                **FULL)
                cc[1].dataframe(key_values(cn, cg), hide_index=True,
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
    gmax = g3.slider("Max. ingredients each", 3, 9, 6, key="g_max")
    v1, v2, v3 = st.columns(3)
    gveg = v1.slider("Vegetables per recipe", 0, 4, 2, key="g_veg")
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
    st.caption("Untick anything you do not want used (e.g. animal "
               "products). Roles are assigned automatically.")
    gdf = st.data_editor(
        pd.DataFrame({"Use": True,
                      "Role": [rc.ingredient_role(db[n]) for n in gnames],
                      "Ingredient": gnames}),
        hide_index=True, **FULL, height=300,
        disabled=["Role", "Ingredient"], key=f"g_pool_{ss.lib_ver}")

    if st.button("Generate", type="primary", key="g_run"):
        ctx = score_context(gk)
        if ign:
            ctx["weights"]["vitamins"] = 0.0
        pool = list(gdf.loc[gdf["Use"], "Ingredient"])
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
                prog, n_veg=gveg, veg_max_uses=guse, veg_min_g=gmin)
            bar.empty()
            ss.gen_result = {"ctx": ctx, "res": res,
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
                cc[0].dataframe(pd.DataFrame({
                    "Ingredient": names,
                    "Role": [rc.ingredient_role(db[n]) for n in names],
                    "g/day": [round(x, 1) for x in g],
                    "kcal": [fmt_kcal(n, x) for n, x in zip(names, g)],
                    "": ["fixed" if j < gr["n_fixed"] else ""
                         for j in range(len(names))]}),
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
    lib_rows = []
    for n in names_all:
        it = db[n]
        row = {"name": n, "category": it["category"],
               "note": it.get("note", "")}
        row.update({k: it["per100g"][k] for k in rc.KEYS})
        lib_rows.append(row)
    ldf = pd.DataFrame(lib_rows)
    cfg = {"category": st.column_config.SelectboxColumn(
        "category", options=["food", "supplement", "binder",
                             "commercial food", "imported"])}
    cfg.update({k: st.column_config.NumberColumn(
        f"{rc.LABEL[k]} ({rc.UNIT[k]})", format="%g") for k in rc.KEYS})
    led = st.data_editor(ldf, key=f"lib_{ss.lib_ver}", num_rows="dynamic",
                         hide_index=True, **FULL,
                         height=420, column_config=cfg)
    lc = st.columns(3)
    if lc[0].button("💾 Save library changes", type="primary"):
        new_db = {}
        for _, rw in led.iterrows():
            nm = str(rw["name"]).strip() if pd.notna(rw["name"]) else ""
            if not nm:
                continue
            new_db[nm] = rc.normalise({
                "name": nm, "category": rw["category"] or "food",
                "note": rw["note"] if pd.notna(rw["note"]) else "",
                "per100g": {k: (None if pd.isna(rw[k]) else float(rw[k]))
                            for k in rc.KEYS}})
        ss.db = new_db
        rc.save_db(new_db)
        ss.lib_ver += 1
        st.success(f"Saved {len(new_db)} ingredients.")
        st.rerun()
    out = io.StringIO()
    ldf.to_csv(out, index=False)
    lc[1].download_button("⬇️ Export library (.csv)", out.getvalue(),
                          file_name="ingredient_library.csv",
                          mime="text/csv")
    tmpl = io.StringIO()
    wt = csv.writer(tmpl)
    wt.writerow(["name", "category", "note"] + rc.KEYS)
    wt.writerow(["# units per 100 g ->", "", ""] +
                [rc.UNIT[k] for k in rc.KEYS])
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
                                  "per100g": per})
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
acid load (indicative) and calories vs the dog's daily need.

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
