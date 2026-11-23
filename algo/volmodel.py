"""5-day realized-vol forecast (ridge), checked walk-forward against VXN/VIX and HAR.

Target:   y_t = sqrt(252/5 * sum(r_{t+1..t+5}^2))   (annualized RV of the next 5 sessions)
Features: implied vol (VXN for NQ / VIX for ES), VIX, rv1, rv5, rv10, rv21, VIX 5d-avg minus 21d-avg
Model:    ridge on standardized features, intercept not penalized, alpha picked walk-forward.
The model is only used if it beats both baselines out of sample. Otherwise the best baseline is used.
"""
import datetime as dt

import numpy as np
import pandas as pd

from . import data

ALPHAS = (0.1, 1.0, 3.0, 10.0, 30.0, 100.0)
H = 5                 # forecast horizon (sessions)
MIN_TRAIN = 250
STEP = 20
EDGE = 0.98           # model must be >=2% better than the best baseline


def _returns(d1: pd.DataFrame) -> pd.Series:
    """Daily log returns, with quarterly contract-roll gaps removed (roll day uses open->close)."""
    d = d1.copy()
    d.index = pd.Index([t.date() for t in d.index])
    r = np.log(d.close / d.close.shift(1))
    gap = np.log(d.open / d.close.shift(1))
    days = list(d.index)
    for ex in data.expiries({days[0].year, days[-1].year}):
        win = [x for x in days[1:] if ex - dt.timedelta(days=8) <= x <= ex + dt.timedelta(days=1)]
        if not win:
            continue
        x = max(win, key=lambda k: abs(gap[k]))
        if 0.002 <= abs(gap[x]) <= 0.02:
            r[x] = np.log(d.close[x] / d.open[x])
    return r.dropna()


def build_frame(d1, iv: pd.Series, vix: pd.Series):
    r = _returns(d1)
    idx = r.index
    s = lambda x: pd.Series(x.values, index=pd.Index(x.index)).reindex(idx, method="ffill") if x is not None and len(x) else None
    ivs, vx = s(iv), s(vix)
    if ivs is None or vx is None:
        return None
    f = pd.DataFrame(index=idx)
    f["iv"] = ivs / 100
    f["vix"] = vx / 100
    r2 = r ** 2
    f["rv1"] = r.abs() * np.sqrt(252)
    for n in (5, 10, 21):
        f[f"rv{n}"] = np.sqrt(252 * r2.rolling(n).mean())
    f["vix_d521"] = (vx.rolling(5).mean() - vx.rolling(21).mean()) / 100
    fwd = sum(r2.shift(-k) for k in range(1, H + 1))
    f["y"] = np.sqrt(252 / H * fwd)
    return f


FEATS = ["iv", "vix", "rv1", "rv5", "rv10", "rv21", "vix_d521"]
HAR = ["rv1", "rv5", "rv21"]


def _fit(X, y, alpha):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    Z = (X - mu) / sd
    ym = y.mean()
    beta = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (y - ym))
    return lambda Xn: ym + ((Xn - mu) / sd) @ beta


def _walk(f, cols, alpha):
    """Walk-forward: expanding train, purge H rows so targets don't overlap the test block."""
    rows = f.dropna(subset=cols + ["y"])
    X, y, idx = rows[cols].values, rows["y"].values, rows.index
    preds = {}
    for start in range(MIN_TRAIN, len(rows), STEP):
        tr = slice(0, max(start - H, 1))
        te = slice(start, min(start + STEP, len(rows)))
        m = _fit(X[tr], y[tr], alpha)
        for k, p in zip(idx[te], m(X[te])):
            preds[k] = max(float(p), 0.02)
    return pd.Series(preds)


def _rmse(pred, f):
    j = pred.index.intersection(f.dropna(subset=["y"]).index)
    return float(np.sqrt(((pred[j] - f.loc[j, "y"]) ** 2).mean())) if len(j) else np.inf


def forecast(d1, iv, vix):
    """Returns dict: chosen, fc (annualized), iv, rmse{...}, alpha, regime, oos (date->pred of chosen), ratio."""
    f = build_frame(d1, iv, vix)
    if f is None or f.dropna().shape[0] < MIN_TRAIN + 40:
        return None
    # pick alpha walk-forward
    best = None
    for a in ALPHAS:
        p = _walk(f, FEATS, a)
        e = _rmse(p, f)
        if best is None or e < best[1]:
            best = (a, e, p)
    alpha, e_ridge, p_ridge = best
    p_har = _walk(f, HAR, 1e-6)
    p_iv = f["iv"].reindex(p_ridge.index)
    err = {"ridge": e_ridge, "HAR": _rmse(p_har, f), "implied": _rmse(p_iv, f)}
    base = min(("HAR", "implied"), key=lambda k: err[k])
    chosen = "ridge" if e_ridge < EDGE * err[base] else base

    last = f.dropna(subset=FEATS).iloc[-1]
    train = f.dropna(subset=FEATS + ["y"])
    if chosen == "ridge":
        fc = float(_fit(train[FEATS].values, train["y"].values, alpha)(last[FEATS].values[None, :])[0])
        oos = p_ridge
    elif chosen == "HAR":
        fc = float(_fit(train[HAR].values, train["y"].values, 1e-6)(last[HAR].values[None, :])[0])
        oos = p_har
    else:
        fc = float(last["iv"])
        oos = p_iv
    fc = max(fc, 0.02)
    ratio = fc / float(last["iv"]) if last["iv"] else 1.0
    regime = "chop" if ratio < 0.85 else "expansion" if ratio > 1.10 else "normal"
    # regime per past day (for the backtest): chosen model's out-of-sample forecast vs implied that day
    ivh = f["iv"].reindex(oos.index)
    reg_hist = {}
    for k in oos.index:
        q = oos[k] / ivh[k] if ivh[k] else 1.0
        reg_hist[k] = "chop" if q < 0.85 else "expansion" if q > 1.10 else "normal"
    return {"chosen": chosen, "fc": fc, "iv": float(last["iv"]), "rmse": err, "alpha": alpha,
            "regime": regime, "ratio": ratio, "oos": oos.to_dict(), "reg_hist": reg_hist,
            "asof": str(f.dropna(subset=FEATS).index[-1])}


def realized(d1, start_date, n=H):
    """Annualized RV of the n sessions after start_date (None if not complete yet)."""
    r = _returns(d1)
    after = r[r.index > start_date]
    if len(after) < n:
        return None
    return float(np.sqrt(252 / n * (after.iloc[:n] ** 2).sum()))
