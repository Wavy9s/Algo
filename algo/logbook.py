"""Lock picks at the first run of the day, track them live, score them after the day ends.
Files are encrypted with PAGE_PASSWORD (the repo is public)."""
import os

import pandas as pd

from . import secure
from . import stats as S

ROOT = secure.ROOT
PICKS = os.path.join(ROOT, "picks")
RESULTS = os.path.join(ROOT, "results.json")


def _path(d):
    return os.path.join(PICKS, f"{d.isoformat()}.json")


def load_locked(d):
    return secure.load(_path(d))


def lock(d, picks, sigma, price, now):
    rec = {"date": d.isoformat(), "locked_at": now.isoformat(), "sigma": sigma, "price": price, "picks": picks}
    secure.save(_path(d), rec)
    return rec


def _after_lock(rec, bars):
    if bars is None or bars.empty:
        return bars
    return bars[bars.index >= pd.Timestamp(rec["locked_at"])]


def _first_outcome(p, bars, sigma):
    recs = S.simulate(p["price"], p["side"], bars, sigma, max_touches=1)
    if not recs:
        return False, "untouched"
    return True, recs[0]["outcome"]


def live_status(rec, m5_today):
    bars = _after_lock(rec, m5_today)
    out = []
    for p in rec["picks"]:
        if bars is None or bars.empty:
            out.append({**p, "status": "live"})
            continue
        _, oc = _first_outcome(p, bars, rec["sigma"])
        out.append({**p, "status": {"untouched": "live", "open": "testing", "held": "held", "broke": "broke"}[oc]})
    return out


def _results():
    return secure.load(RESULTS) or []


def finalize(m5, today):
    if not os.path.isdir(PICKS):
        return
    rows = _results()
    done = {r["date"] for r in rows}
    new = []
    for fn in sorted(os.listdir(PICKS)):
        ds = fn[:-5]
        try:
            d = pd.Timestamp(ds).date()
        except Exception:
            continue
        if d >= today or ds in done:
            continue
        bars = m5[m5.tdate == d]
        rec = secure.load(os.path.join(PICKS, fn))
        if bars.empty or not rec:
            continue
        bars = _after_lock(rec, bars)
        for p in rec["picks"]:
            touched, oc = _first_outcome(p, bars, rec["sigma"])
            new.append({"date": ds, "price": p["price"], "side": p["side"], "grade": p["grade"],
                        "label": p["label"], "touch_pred": p["touch"], "hold_pred": p["hold"],
                        "touched": bool(touched), "outcome": oc})
    if new:
        secure.save(RESULTS, rows + new)


def scorecard(days=30):
    rows = _results()
    if not rows:
        return None
    df = pd.DataFrame(rows)
    keep = sorted(df.date.unique())[-days:]
    df = df[df.date.isin(keep)]
    res = df[df.outcome.isin(["held", "broke"])]
    by_grade = {g: (float((x.outcome == "held").mean()), int(len(x))) for g, x in res.groupby("grade")}
    last = df[df.date == keep[-1]]
    lr = last[last.outcome.isin(["held", "broke"])]
    return {
        "days": len(keep), "by_grade": by_grade,
        "touch_pred": float(df.touch_pred.mean()), "touch_real": float(df.touched.astype(bool).mean()),
        "hold_pred": float(res.hold_pred.mean()) if len(res) else None,
        "hold_real": float((res.outcome == "held").mean()) if len(res) else None,
        "last_date": keep[-1], "last_held": int((lr.outcome == "held").sum()), "last_n": int(len(lr)),
        "last_picks": int(len(last)),
    }


# ---------------------------------------------------------------- options cache
def load_opt_cache():
    return secure.load(os.path.join(ROOT, "options.json")) or {}


def save_opt_cache(obj):
    secure.save(os.path.join(ROOT, "options.json"), obj)
