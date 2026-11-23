"""Session, daily, weekly, monthly VWAP with +-1/2 sigma bands (hlc3, volume weighted)."""
import numpy as np
import pandas as pd


def stats(bars: pd.DataFrame):
    if bars is None or bars.empty:
        return None
    tp = (bars.high + bars.low + bars.close) / 3
    v = bars.volume.astype(float)
    if v.sum() <= 0:
        v = pd.Series(1.0, index=bars.index)
    vw = float((tp * v).sum() / v.sum())
    sd = float(np.sqrt((v * (tp - vw) ** 2).sum() / v.sum()))
    return {"vwap": vw, "sd": sd}


def week_key(d):
    iso = d.isocalendar()
    return (iso[0], iso[1])


def all_vwaps(m5: pd.DataFrame, today):
    """Current (live) and prior closing VWAPs for each anchor."""
    out = {}
    cur = m5[m5.tdate == today]
    out["session"] = stats(cur[cur.rth])
    out["daily"] = stats(cur)
    past_days = sorted(d for d in m5.tdate.unique() if d < today)
    if past_days:
        out["prior_daily"] = stats(m5[m5.tdate == past_days[-1]])

    wk = week_key(today)
    wkeys = m5.tdate.map(week_key)
    out["weekly"] = stats(m5[wkeys == wk])
    prev_w = sorted({k for k in wkeys.unique() if k < wk})
    if prev_w:
        out["prior_weekly"] = stats(m5[wkeys == prev_w[-1]])

    mkey = (today.year, today.month)
    mkeys = m5.tdate.map(lambda d: (d.year, d.month))
    out["monthly"] = stats(m5[mkeys == mkey])
    prev_m = sorted({k for k in mkeys.unique() if k < mkey})
    if prev_m:
        out["prior_monthly"] = stats(m5[mkeys == prev_m[-1]])
    return {k: v for k, v in out.items() if v}
