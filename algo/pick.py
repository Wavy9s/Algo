"""Score today's levels, cluster stacks, adjust for risk/macro/gamma, grade, and pick."""
import numpy as np

from . import config as C
from . import stats as S


def score(lv, price, sigma, sigma_rem, learned, ctx):
    """ctx: risk_day, macro_bias ('Bull'/'Bear'/'Neutral'), gamma_env, dex_sign."""
    T, cats, overall = learned["types"], learned["cats"], learned["overall"]
    tgt_def = C.HOLD_TARGET * sigma
    for x in lv:
        st = T.get(x["type"])
        if st:
            hold, n = st["hold"], st["n"]
            bounce = st["bounce"] if np.isfinite(st.get("bounce", np.nan)) else tgt_def
        else:  # no history for this type yet -> category / overall average
            hold, n, bounce = cats.get(x["cat"], overall), 0, tgt_def
        x["side"] = "R" if x["price"] > price else "S"
        x["dist"] = x["price"] - price
        x["touch"] = S.touch_odds(x["dist"], sigma_rem)
        x["hold_base"], x["n"], x["bounce"] = float(hold), int(n), float(bounce)
        x["stats"] = st or {}

    tol = max(C.STACK_TOL_MIN, C.STACK_TOL_SIGMA * sigma)
    clusters = []
    for x in sorted(lv, key=lambda z: z["price"]):
        if clusters and abs(x["price"] - clusters[-1][-1]["price"]) <= tol:
            clusters[-1].append(x)
        else:
            clusters.append([x])

    out = []
    for cl in clusters:
        lead = max(cl, key=lambda z: (z["cat"] != "lvn", z["hold_base"], z["n"]))
        lvn_only = all(z["cat"] == "lvn" for z in cl)
        k = len({z["type"] for z in cl})
        hold = lead["hold_base"] + learned["stack_bonus"] * min(k - 1, 2)
        notes = []
        if ctx.get("risk_day"):
            hold -= learned["risk_penalty"] or 0.03
            notes.append("risk day")
        against = (ctx.get("macro_bias") == "Bull" and lead["side"] == "R") or \
                  (ctx.get("macro_bias") == "Bear" and lead["side"] == "S")
        if against:
            hold += C.AGAINST_MACRO_HOLD
            notes.append("against macro")
        g = ctx.get("gamma_env")
        if g == "negative":
            hold += C.GAMMA_NEG_HOLD
            notes.append("neg gamma")
        elif g == "positive":
            hold += C.GAMMA_POS_HOLD
        dex = ctx.get("dex_sign", 0)
        if (dex > 0 and lead["side"] == "S") or (dex < 0 and lead["side"] == "R"):
            notes.append("against dealers")
            hold -= 0.02
        hold = float(np.clip(hold, 0.05, 0.95))
        stop = C.BREAK_STOP * sigma
        ev = lead["touch"] * (hold * lead["bounce"] - (1 - hold) * stop)
        if lvn_only:
            grade = "LVN"
        elif hold >= C.APLUS_HOLD and lead["n"] >= C.MIN_N_APLUS and ev > 0 and k >= 2:
            grade = "A+"
        elif hold >= C.A_HOLD and ev > 0:
            grade = "A"
        else:
            grade = "B"
        if against and grade in ("A+", "A"):
            grade = {"A+": "A", "A": "B"}[grade]
        price_c = lead["price"]
        out.append({
            "price": round(price_c, 2), "side": lead["side"], "dist": round(lead["dist"], 2),
            "label": " + ".join(dict.fromkeys(z["label"] for z in sorted(cl, key=lambda z: -z["hold_base"]))),
            "types": sorted({z["type"] for z in cl}), "stack": k,
            "touch": round(lead["touch"], 3), "hold": round(hold, 3), "n": lead["n"],
            "bounce": round(lead["bounce"], 1), "ev": round(ev, 1), "grade": grade,
            "notes": notes, "zone": lead.get("zone"), "lvn": lvn_only,
            "sweep": lead["stats"].get("sweep"), "run": lead["stats"].get("run"),
        })
    return out


def choose(scored, sigma):
    picks = []
    for side in ("R", "S"):
        c = [x for x in scored if x["side"] == side and not x["lvn"] and x["grade"] in ("A+", "A", "B")
             and x["touch"] >= C.MIN_TOUCH and abs(x["dist"]) >= C.MIN_DIST_SIGMA * sigma]
        rank = {"A+": 2, "A": 1, "B": 0}
        c.sort(key=lambda x: (rank[x["grade"]], x["ev"]), reverse=True)
        picks += c[:C.N_SIDE]
    return sorted(picks, key=lambda x: -x["price"])


def level_string(picks):
    return ",".join(f"{p['price']:.2f}:{p['grade']}:{p['side']}" for p in picks)
