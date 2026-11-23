"""Volatility, touch odds, and the backtest that learns hold % per level type and situation."""
import math

import numpy as np
import pandas as pd

from . import config as C
from . import levels as L


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def yang_zhang(d1: pd.DataFrame, n: int = 20):
    d = d1.tail(n + 1)
    if len(d) < 10:
        return None
    o = np.log(d.open / d.close.shift(1)).dropna()
    c = np.log(d.close / d.open).iloc[1:]
    rs = (np.log(d.high / d.close) * np.log(d.high / d.open)
          + np.log(d.low / d.close) * np.log(d.low / d.open)).iloc[1:]
    m = len(o)
    k = 0.34 / (1.34 + (m + 1) / (m - 1))
    var = o.var() + k * c.var() + (1 - k) * rs.mean()
    return float(math.sqrt(max(var, 1e-10)))


def sigma_points(price, d1, vxn=None):
    """Daily 1-sigma move in NQ points. VXN (implied) first, Yang-Zhang (realized) fallback."""
    if vxn and vxn > 0:
        return price * vxn / 100 / math.sqrt(252), "VXN"
    yz = yang_zhang(d1) if d1 is not None else None
    if yz:
        return price * yz, "Yang-Zhang"
    return price * 0.013, "default"


def touch_odds(dist, sigma_rem):
    if sigma_rem <= 0:
        return 0.0
    return float(min(1.0, 2 * (1 - phi(abs(dist) / sigma_rem))))


def stack_counts(lv: list, tol: float):
    ps = np.array([x["price"] for x in lv])
    return [int((np.abs(ps - p) <= tol).sum()) for p in ps]


# ----------------------------------------------------------------------------- simulation
def simulate(level, side, bars: pd.DataFrame, sigma, max_touches=C.MAX_TOUCHES):
    """Walk bars forward. side 'R' = level above price (expect rejection down), 'S' = below.
    Returns a list of touch records."""
    tgt, stop, sweep = C.HOLD_TARGET * sigma, C.BREAK_STOP * sigma, C.SWEEP_MIN * sigma
    hi, lo, ts = bars.high.values, bars.low.values, bars.index
    sess = bars.sess.values if "sess" in bars else [""] * len(bars)
    sgn = 1 if side == "R" else -1          # +1: level above
    recs, i, n, armed = [], 0, len(bars), True
    while i < n and len(recs) < max_touches:
        touched = (hi[i] >= level) if sgn > 0 else (lo[i] <= level)
        if not (touched and armed):
            # re-arm after price moved a full target away
            if not armed and ((sgn > 0 and hi[i] <= level - tgt) or (sgn < 0 and lo[i] >= level + tgt)):
                armed = True
            i += 1
            continue
        rec = {"time": ts[i], "sess": sess[i], "first": len(recs) == 0, "outcome": "open",
               "sweep": False, "bounce": 0.0, "run": 0.0}
        worst = best = 0.0
        for j in range(i, min(n, i + C.HORIZON_BARS)):
            thru = (hi[j] - level) if sgn > 0 else (level - lo[j])      # adverse (through level)
            away = (level - lo[j]) if sgn > 0 else (hi[j] - level)       # favorable (bounce)
            worst, best = max(worst, thru), max(best, away)
            if thru >= stop:
                rec["outcome"] = "broke"
                break
            if j > i and away >= tgt:
                rec["outcome"] = "held"
                rec["sweep"] = worst >= sweep
                break
        k_end = min(n, j + C.HORIZON_BARS)
        if rec["outcome"] == "held":
            seg = bars.iloc[i:k_end]
            rec["bounce"] = float((level - seg.low.min()) if sgn > 0 else (seg.high.max() - level))
        elif rec["outcome"] == "broke":
            seg = bars.iloc[j:k_end]
            rec["run"] = float((seg.high.max() - level) if sgn > 0 else (level - seg.low.min()))
        recs.append(rec)
        if rec["outcome"] == "broke":
            break
        armed = False
        i = j + 1
    return recs


def _asof(d: dict, D):
    """Value for the last key before date D."""
    if not d:
        return None
    ks = [k for k in d if k < D]
    return d[max(ks)] if ks else None


def backtest(m5, d1, day_prof, vxn_hist=None, risk_days=frozenset(), opt_hist=None, fc_hist=None, reg_hist=None):
    """Rebuild levels each past day using only prior data, then score every touch."""
    rows = []
    days = sorted(m5.tdate.unique())
    for D in days[6:]:
        bars = m5[m5.tdate == D]
        if len(bars) < 50:
            continue
        prev_close = m5[m5.tdate < D].close.iloc[-1]
        vx = None
        if vxn_hist is not None and len(vxn_hist):
            prior = vxn_hist[vxn_hist.index < D]
            vx = float(prior.iloc[-1]) if len(prior) else None
        dd = d1[d1.index.date < D] if d1 is not None else None
        fc = _asof(fc_hist, D)
        if fc:
            sigma = prev_close * fc / math.sqrt(252)   # vol model's out-of-sample forecast
        else:
            sigma, _ = sigma_points(prev_close, dd, vx)
        reg = _asof(reg_hist, D) or "normal"
        lv = L.collect(m5, d1, D, day_prof, (opt_hist or {}).get(D))
        if not lv:
            continue
        tol = max(C.STACK_TOL_MIN, C.STACK_TOL_SIGMA * sigma)
        stacks = stack_counts(lv, tol)
        o = bars.open.iloc[0]
        hm = bars.index.hour * 60 + bars.index.minute
        rth_bars = bars[(hm >= 570) & (hm < 1020)]
        for x, stk in zip(lv, stacks):
            # options levels are known from 9:30 ET, so only test them from then on
            b = rth_bars if x["cat"] in ("options", "on") else bars
            if b.empty:
                continue
            side = "R" if x["price"] > b.open.iloc[0] else "S"
            for r in simulate(x["price"], side, b, sigma):
                if r["outcome"] == "open":
                    continue
                rows.append({"date": D, "type": x["type"], "cat": x["cat"], "side": side,
                             "stack": stk, "risk": D in risk_days, "sigma": sigma, "regime": reg, **r})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- aggregation
def _rate(s):
    return s.mean() if len(s) else np.nan


def learn(bt: pd.DataFrame):
    """Hold % per type with shrinkage: type -> category -> overall."""
    if bt is None or bt.empty:
        return {"overall": 0.5, "types": {}, "cats": {}, "stack_bonus": 0.0, "risk_penalty": 0.0, "n": 0,
                "regime_adj": {}, "regime_n": {}}
    bt = bt.copy()
    bt["held"] = (bt.outcome == "held").astype(float)
    K = C.SHRINK_K
    overall = bt.held.mean()
    cats = {}
    for c, g in bt.groupby("cat"):
        cats[c] = (g.held.sum() + K * overall) / (len(g) + K)
    types = {}
    for t, g in bt.groupby("type"):
        prior = cats.get(g.cat.iloc[0], overall)
        held = g[g.outcome == "held"]
        broke = g[g.outcome == "broke"]
        first, retest = g[g["first"]], g[~g["first"]]
        types[t] = {
            "n": int(len(g)),
            "hold": float((g.held.sum() + K * prior) / (len(g) + K)),
            "raw": float(g.held.mean()),
            "sweep": float(held.sweep.mean()) if len(held) else np.nan,
            "bounce": float(held.bounce.mean()) if len(held) else np.nan,
            "run": float(broke.run.mean()) if len(broke) else np.nan,
            "first": float(_rate(first.held)), "n_first": int(len(first)),
            "retest": float(_rate(retest.held)), "n_retest": int(len(retest)),
            "sess": {s: (float(_rate(x.held)), int(len(x))) for s, x in g.groupby("sess")},
            "risk_day": float(_rate(g[g.risk].held)), "n_risk": int(g.risk.sum()),
        }
    single, stacked = bt[bt["stack"] <= 1].held.mean(), bt[bt["stack"] >= 2].held.mean()
    bonus = float(np.clip((stacked - single) if np.isfinite(stacked - single) else 0, 0, 0.08))
    rp = 0.0
    if bt.risk.sum() >= 20:
        rp = float(np.clip(bt[~bt.risk].held.mean() - bt[bt.risk].held.mean(), 0, 0.15))
    reg_adj, reg_n = {}, {}
    if "regime" in bt:
        for g, x in bt.groupby("regime"):
            reg_n[g] = int(len(x))
            reg_adj[g] = float(np.clip(x.held.mean() - overall, -0.08, 0.08)) if len(x) >= 30 else 0.0
    return {"overall": float(overall), "types": types, "cats": cats, "stack_bonus": bonus,
            "risk_penalty": rp, "n": int(len(bt)), "regime_adj": reg_adj, "regime_n": reg_n,
            "bounce_all": float(bt[bt.outcome == "held"].bounce.mean() or 0)}
