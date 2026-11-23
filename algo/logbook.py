"""Lock picks at the first run of the day, track them live, score them after the day ends."""
import json
import os

import pandas as pd

from . import stats as S

ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state")
PICKS = os.path.join(ROOT, "picks")
RESULTS = os.path.join(ROOT, "results.csv")


def _path(d):
    return os.path.join(PICKS, f"{d.isoformat()}.json")


def load_locked(d):
    p = _path(d)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return None


def lock(d, picks, sigma, price, now):
    os.makedirs(PICKS, exist_ok=True)
    rec = {"date": d.isoformat(), "locked_at": now.isoformat(), "sigma": sigma, "price": price, "picks": picks}
    with open(_path(d), "w") as f:
        json.dump(rec, f, indent=1, default=str)
    return rec


def _first_outcome(p, bars, sigma):
    recs = S.simulate(p["price"], p["side"], bars, sigma, max_touches=1)
    if not recs:
        return False, "untouched"
    return True, recs[0]["outcome"]


def _after_lock(rec, bars):
    t = pd.Timestamp(rec["locked_at"])
    return bars[bars.index >= t] if bars is not None and not bars.empty else bars


def live_status(rec, m5_today):
    m5_today = _after_lock(rec, m5_today)
    out = []
    for p in rec["picks"]:
        if m5_today is None or m5_today.empty:
            out.append({**p, "status": "live"})
            continue
        touched, oc = _first_outcome(p, m5_today, rec["sigma"])
        status = {"untouched": "live", "open": "testing", "held": "held", "broke": "broke"}[oc]
        out.append({**p, "status": status})
    return out


def finalize(m5, today):
    """Score every locked day before today that isn't in results.csv yet."""
    if not os.path.isdir(PICKS):
        return
    done = set()
    if os.path.exists(RESULTS):
        done = set(pd.read_csv(RESULTS, usecols=["date"]).date.astype(str))
    rows = []
    for fn in sorted(os.listdir(PICKS)):
        ds = fn[:-5]
        d = pd.Timestamp(ds).date()
        if d >= today or ds in done:
            continue
        bars = m5[m5.tdate == d]
        if bars.empty:
            continue
        with open(os.path.join(PICKS, fn)) as f:
            rec = json.load(f)
        bars = _after_lock(rec, bars)
        for p in rec["picks"]:
            touched, oc = _first_outcome(p, bars, rec["sigma"])
            rows.append({"date": ds, "price": p["price"], "side": p["side"], "grade": p["grade"],
                         "label": p["label"], "touch_pred": p["touch"], "hold_pred": p["hold"],
                         "touched": touched, "outcome": oc})
    if rows:
        df = pd.DataFrame(rows)
        df.to_csv(RESULTS, mode="a", header=not os.path.exists(RESULTS), index=False)


def scorecard(days=30):
    if not os.path.exists(RESULTS):
        return None
    df = pd.read_csv(RESULTS)
    if df.empty:
        return None
    keep = sorted(df.date.unique())[-days:]
    df = df[df.date.isin(keep)]
    res = df[df.outcome.isin(["held", "broke"])]
    by_grade = {}
    for g, x in res.groupby("grade"):
        by_grade[g] = (float((x.outcome == "held").mean()), int(len(x)))
    last = df[df.date == keep[-1]]
    lr = last[last.outcome.isin(["held", "broke"])]
    return {
        "days": len(keep),
        "by_grade": by_grade,
        "touch_pred": float(df.touch_pred.mean()),
        "touch_real": float(df.touched.astype(bool).mean()),
        "hold_pred": float(res.hold_pred.mean()) if len(res) else None,
        "hold_real": float((res.outcome == "held").mean()) if len(res) else None,
        "last_date": keep[-1], "last_held": int((lr.outcome == "held").sum()), "last_n": int(len(lr)),
        "last_picks": int(len(last)),
    }
