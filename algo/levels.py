"""Collect every candidate level as of the start of trade day `D` (no peeking at D)."""
import numpy as np
import pandas as pd

from . import profile as P
from . import vwap as V

# type -> (label, category, timeframe)
TYPES = {
    "PD_POC": ("Prior-day POC", "profile", "D"), "PD_VAH": ("Prior-day VAH", "profile", "D"),
    "PD_VAL": ("Prior-day VAL", "profile", "D"), "PD_HVN": ("Prior-day HVN", "profile", "D"),
    "PD_LVN": ("Prior-day LVN", "lvn", "D"),
    "PW_POC": ("Prior-week POC", "profile", "W"), "PW_VAH": ("Prior-week VAH", "profile", "W"),
    "PW_VAL": ("Prior-week VAL", "profile", "W"), "PW_HVN": ("Prior-week HVN", "profile", "W"),
    "PW_LVN": ("Prior-week LVN", "lvn", "W"),
    "PM_POC": ("Prior-month POC", "profile", "M"), "PM_VAH": ("Prior-month VAH", "profile", "M"),
    "PM_VAL": ("Prior-month VAL", "profile", "M"),
    "NPOC": ("Naked POC", "profile", "D"),
    "PD_H": ("Prior-day high", "range", "D"), "PD_L": ("Prior-day low", "range", "D"),
    "PD_C": ("Prior-day close", "range", "D"),
    "PW_H": ("Prior-week high", "range", "W"), "PW_L": ("Prior-week low", "range", "W"),
    "PW_C": ("Prior-week close", "range", "W"),
    "PM_H": ("Prior-month high", "range", "M"), "PM_L": ("Prior-month low", "range", "M"),
    "PM_C": ("Prior-month close", "range", "M"),
    "POOR_H": ("Poor high", "amt", "D"), "POOR_L": ("Poor low", "amt", "D"),
    "SINGLE": ("Single prints", "amt", "D"),
    "PD_VWAP": ("Prior-day VWAP", "vwap", "D"), "PD_VWAP_1": ("Prior-day VWAP 1σ", "vwap", "D"),
    "PD_VWAP_2": ("Prior-day VWAP 2σ", "vwap", "D"),
    "PW_VWAP": ("Prior-week VWAP", "vwap", "W"), "PW_VWAP_1": ("Prior-week VWAP 1σ", "vwap", "W"),
    "PW_VWAP_2": ("Prior-week VWAP 2σ", "vwap", "W"),
    "PM_VWAP": ("Prior-month VWAP", "vwap", "M"), "PM_VWAP_2": ("Prior-month VWAP 2σ", "vwap", "M"),
    "W_VWAP": ("Weekly VWAP", "vwap", "W"), "W_VWAP_1": ("Weekly VWAP 1σ", "vwap", "W"),
    "W_VWAP_2": ("Weekly VWAP 2σ", "vwap", "W"),
    "M_VWAP": ("Monthly VWAP", "vwap", "M"), "M_VWAP_1": ("Monthly VWAP 1σ", "vwap", "M"),
    "M_VWAP_2": ("Monthly VWAP 2σ", "vwap", "M"),
    "OTE_D": ("Daily OTE 0.705", "ote", "D"), "OTE_W": ("Weekly OTE 0.705", "ote", "W"),
    "GEX_CALL": ("Call wall", "options", "O"), "GEX_PUT": ("Put wall", "options", "O"),
    "GAMMA_FLIP": ("Gamma flip", "options", "O"), "DEX_WALL": ("DEX wall", "options", "O"),
    "MAX_PAIN": ("Max pain", "options", "O"), "VOL_TRIGGER": ("Vol trigger", "options", "O"),
}


def _add(out, t, price, sfx="", zone=None):
    if price is None or not np.isfinite(price):
        return
    lab, cat, tf = TYPES[t]
    out.append({"type": t, "label": lab + sfx, "cat": cat, "tf": tf, "price": float(price), "zone": zone})


def _pivots(d1: pd.DataFrame, k: int):
    hs, ls = [], []
    h, l = d1.high.values, d1.low.values
    for i in range(k, len(d1) - k):
        if h[i] == max(h[i - k:i + k + 1]):
            hs.append((i, h[i]))
        if l[i] == min(l[i - k:i + k + 1]):
            ls.append((i, l[i]))
    return hs, ls


def ote(bars: pd.DataFrame, k: int):
    """Last swing leg -> 0.62-0.79 retrace zone. Returns (mid, lo, hi, side_hint)."""
    if bars is None or len(bars) < 2 * k + 3:
        return None
    hs, ls = _pivots(bars, k)
    if not hs or not ls:
        return None
    (hi_i, hi), (lo_i, lo) = hs[-1], ls[-1]
    rng = hi - lo
    if rng <= 0:
        return None
    if hi_i > lo_i:   # up leg -> buy zone below
        a, b = hi - 0.62 * rng, hi - 0.79 * rng
    else:             # down leg -> sell zone above
        a, b = lo + 0.62 * rng, lo + 0.79 * rng
    return (a + b) / 2, min(a, b), max(a, b)


def collect(m5: pd.DataFrame, d1: pd.DataFrame, D, day_prof: dict, options=None) -> list:
    out = []
    past = m5[m5.tdate < D]
    days = sorted(past.tdate.unique())
    if not days:
        return out
    pd_ = days[-1]
    pdb = past[past.tdate == pd_]
    prof = day_prof.get(pd_)
    if prof:
        _add(out, "PD_POC", prof["poc"]); _add(out, "PD_VAH", prof["vah"]); _add(out, "PD_VAL", prof["val"])
        for x in prof["hvn"][:2]:
            _add(out, "PD_HVN", x)
        for x in prof["lvn"][:2]:
            _add(out, "PD_LVN", x)
    _add(out, "PD_H", pdb.high.max()); _add(out, "PD_L", pdb.low.min()); _add(out, "PD_C", pdb.close.iloc[-1])

    amt = P.rth_structure(pdb)
    if amt.get("poor_high"):
        _add(out, "POOR_H", amt["poor_high"])
    if amt.get("poor_low"):
        _add(out, "POOR_L", amt["poor_low"])
    for a, b in amt.get("singles", [])[:2]:
        _add(out, "SINGLE", (a + b) / 2, f" {a:,.0f}-{b:,.0f}", zone=(a, b))

    for d, poc in P.naked_pocs(day_prof, m5, D)[-6:]:
        _add(out, "NPOC", poc, f" ({d:%m/%d})")

    # prior week
    wk = V.week_key(D)
    wkeys = past.tdate.map(V.week_key)
    prev_w = sorted({k for k in wkeys.unique() if k < wk})
    if prev_w:
        wb = past[wkeys == prev_w[-1]]
        if wb.tdate.nunique() >= 3:
            wp = P.build(wb)
            _add(out, "PW_POC", wp["poc"]); _add(out, "PW_VAH", wp["vah"]); _add(out, "PW_VAL", wp["val"])
            for x in wp["hvn"][:2]:
                _add(out, "PW_HVN", x)
            for x in wp["lvn"][:2]:
                _add(out, "PW_LVN", x)
            _add(out, "PW_H", wb.high.max()); _add(out, "PW_L", wb.low.min()); _add(out, "PW_C", wb.close.iloc[-1])

    # prior month profile (only if mostly inside the 60d window)
    mk = (D.year, D.month)
    mkeys = past.tdate.map(lambda d: (d.year, d.month))
    prev_m = sorted({k for k in mkeys.unique() if k < mk})
    if prev_m:
        mb = past[mkeys == prev_m[-1]]
        if mb.tdate.nunique() >= 15:
            mp = P.build(mb)
            _add(out, "PM_POC", mp["poc"]); _add(out, "PM_VAH", mp["vah"]); _add(out, "PM_VAL", mp["val"])

    # monthly H/L/C from daily bars (longer history)
    if d1 is not None and not d1.empty:
        dd = d1[d1.index.date < D]
        if len(dd):
            mo = dd.groupby([dd.index.year, dd.index.month]).agg(
                {"high": "max", "low": "min", "close": "last"})
            prev = [k for k in mo.index if k < mk]
            if prev:
                r = mo.loc[prev[-1]]
                _add(out, "PM_H", r.high); _add(out, "PM_L", r.low); _add(out, "PM_C", r.close)
            o = ote(dd.tail(120), 3)
            if o:
                _add(out, "OTE_D", o[0], zone=(o[1], o[2]))
            wkly = dd.resample("W-FRI").agg({"high": "max", "low": "min", "close": "last"}).dropna()
            o = ote(wkly.tail(80), 2)
            if o:
                _add(out, "OTE_W", o[0], zone=(o[1], o[2]))

    # VWAPs as of the start of D
    vw = V.all_vwaps(past, D)
    for key, base in (("prior_daily", "PD_VWAP"), ("prior_weekly", "PW_VWAP"), ("prior_monthly", "PM_VWAP"),
                      ("weekly", "W_VWAP"), ("monthly", "M_VWAP")):
        s = vw.get(key)
        if not s:
            continue
        _add(out, base, s["vwap"])
        for m in (1, 2):
            t = f"{base}_{m}"
            if t in TYPES and s["sd"] > 0:
                _add(out, t, s["vwap"] + m * s["sd"], " (+)")
                _add(out, t, s["vwap"] - m * s["sd"], " (−)")

    for o in options or []:
        _add(out, o["type"], o["price"], o.get("sfx", ""))
    return out
