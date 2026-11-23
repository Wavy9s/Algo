"""Volume profile from candles: POC, VAH, VAL, HVN, LVN, naked POCs, poor highs/lows, single prints."""
import numpy as np
import pandas as pd

from . import config as C


def build(bars: pd.DataFrame, bucket: float = None):
    """Spread each candle's volume evenly over the buckets it traded through."""
    bucket = bucket or C.BUCKET
    if bars is None or bars.empty:
        return None
    lo = np.floor(bars.low.min() / bucket) * bucket
    hi = np.floor(bars.high.max() / bucket) * bucket
    n = int(round((hi - lo) / bucket)) + 1
    vol = np.zeros(n)
    v_all = bars.volume.values.astype(float)
    if v_all.sum() <= 0:
        v_all = np.ones_like(v_all)
    i0s = np.floor((bars.low.values - lo) / bucket + 1e-9).astype(int)
    i1s = np.floor((bars.high.values - lo) / bucket + 1e-9).astype(int)
    for i0, i1, v in zip(i0s, i1s, v_all):
        i0, i1 = max(i0, 0), min(i1, n - 1)
        vol[i0:i1 + 1] += v / (i1 - i0 + 1)
    edges = lo + bucket * np.arange(n)
    return _read(edges, vol, bucket, float(bars.high.max()), float(bars.low.min()))


def _read(edges, vol, bucket, high, low):
    n = len(vol)
    mid = edges + bucket / 2
    poc_i = int(np.argmax(vol))
    # value area: grow from POC two buckets at a time toward the heavier side
    target = vol.sum() * C.VALUE_AREA
    lo_i = hi_i = poc_i
    acc = vol[poc_i]
    while acc < target and (lo_i > 0 or hi_i < n - 1):
        up = vol[hi_i + 1:hi_i + 3].sum() if hi_i < n - 1 else -1
        dn = vol[max(lo_i - 2, 0):lo_i].sum() if lo_i > 0 else -1
        if up >= dn:
            step = min(2, n - 1 - hi_i)
            acc += vol[hi_i + 1:hi_i + 1 + step].sum()
            hi_i += step
        else:
            step = min(2, lo_i)
            acc += vol[lo_i - step:lo_i].sum()
            lo_i -= step
    hvn, lvn = _nodes(mid, vol, poc_i)
    return {"poc": float(mid[poc_i]), "vah": float(edges[hi_i] + bucket), "val": float(edges[lo_i]),
            "hvn": hvn, "lvn": lvn, "high": high, "low": low,
            "mid": mid, "vol": vol}


def _nodes(mid, vol, poc_i):
    n = len(vol)
    if n < 7:
        return [], []
    w = max(2, n // 40)
    k = np.concatenate([np.arange(1, w + 2), np.arange(w, 0, -1)]).astype(float)
    sm = np.convolve(vol, k / k.sum(), mode="same")
    avg = sm[sm > 0].mean()
    sep = max(3, n // 15)
    peaks = [i for i in range(1, n - 1)
             if sm[i] >= sm[i - 1] and sm[i] >= sm[i + 1] and sm[i] > C.HVN_MULT * avg]
    peaks.sort(key=lambda i: -sm[i])
    keep = []
    for i in peaks:
        if all(abs(i - j) >= sep for j in keep) and abs(i - poc_i) >= sep:
            keep.append(i)
    keep_all = sorted(keep + [poc_i])
    lv = []
    for a, b in zip(keep_all[:-1], keep_all[1:]):
        if b - a < 3:
            continue
        j = a + 1 + int(np.argmin(sm[a + 1:b]))
        if sm[j] < C.LVN_MULT * avg:
            lv.append(j)
    return [float(mid[i]) for i in sorted(keep)[:4]], [float(mid[i]) for i in lv[:4]]


def by_day(m5: pd.DataFrame) -> dict:
    return {d: build(g) for d, g in m5.groupby("tdate")}


def naked_pocs(day_profiles: dict, m5: pd.DataFrame, today, exclude_last=True) -> list:
    """Old daily POCs that no later bar has traded through (as of `today`'s start)."""
    days = sorted(d for d in day_profiles if d < today and day_profiles[d])
    if exclude_last and days:
        days = days[:-1]  # yesterday's POC is already the prior-day POC
    days = days[-C.NAKED_LOOKBACK:]
    out = []
    for d in days:
        poc = day_profiles[d]["poc"]
        later = m5[(m5.tdate > d) & (m5.tdate < today)]
        if later.empty or not ((later.low <= poc) & (later.high >= poc)).any():
            out.append((d, poc))
    return out


def rth_structure(day_bars: pd.DataFrame, bucket: float = None, tol: float = None):
    """AMT read of one RTH session: poor high/low and single-print zones (30m TPOs)."""
    bucket = bucket or C.BUCKET
    tol = tol if tol is not None else C.POOR_TOL
    rth = day_bars[day_bars.rth]
    if len(rth) < 6:
        return {}
    tpo = rth.resample("30min").agg({"high": "max", "low": "min"}).dropna()
    hi, lo = tpo.high.max(), tpo.low.min()
    poor_high = int((tpo.high >= hi - tol).sum()) >= 2
    poor_low = int((tpo.low <= lo + tol).sum()) >= 2
    b0 = np.floor(lo / bucket) * bucket
    n = int(np.floor((hi - b0) / bucket)) + 1
    cnt = np.zeros(n, int)
    for h, l in zip(tpo.high, tpo.low):
        cnt[int((l - b0) // bucket): int((h - b0) // bucket) + 1] += 1
    singles, i = [], 0
    while i < n:
        if cnt[i] == 1:
            j = i
            while j + 1 < n and cnt[j + 1] == 1:
                j += 1
            if i > 0 and j < n - 1 and (j - i + 1) >= 3:  # inside the range, not a tail
                singles.append((float(b0 + i * bucket), float(b0 + (j + 1) * bucket)))
            i = j + 1
        else:
            i += 1
    return {"poor_high": hi if poor_high else None, "poor_low": lo if poor_low else None,
            "singles": singles}
