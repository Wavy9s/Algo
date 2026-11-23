"""Lock picks at the first run of the day, track them live, score them after the day ends.
Files are encrypted with PAGE_PASSWORD (the repo is public)."""
import os

import numpy as np
import pandas as pd

from . import secure
from . import stats as S

ROOT = secure.ROOT


def _sfx(inst):
    return "" if inst == "NQ" else f"_{inst}"   # NQ keeps the original file names


def _picks_dir(inst):
    return os.path.join(ROOT, "picks" + _sfx(inst))


def _results_path(inst):
    return os.path.join(ROOT, f"results{_sfx(inst)}.json")


def _path(d, inst):
    return os.path.join(_picks_dir(inst), f"{d.isoformat()}.json")


def load_locked(d, inst="NQ"):
    return secure.load(_path(d, inst))


def lock(d, picks, sigma, price, now, inst="NQ"):
    rec = {"date": d.isoformat(), "locked_at": now.isoformat(), "sigma": sigma, "price": price, "picks": picks}
    secure.save(_path(d, inst), rec)
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


def _results(inst):
    return secure.load(_results_path(inst)) or []


def finalize(m5, today, inst="NQ"):
    PICKS = _picks_dir(inst)
    if not os.path.isdir(PICKS):
        return
    rows = _results(inst)
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
        secure.save(_results_path(inst), rows + new)


def scorecard(days=30, inst="NQ"):
    rows = _results(inst)
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
def load_opt_cache(inst="NQ"):
    return secure.load(os.path.join(ROOT, f"options{_sfx(inst)}.json")) or {}


def save_opt_cache(obj, inst="NQ"):
    secure.save(os.path.join(ROOT, f"options{_sfx(inst)}.json"), obj)


# ---------------------------------------------------------------- vol forecast log
def vol_log(inst, today, vm, d1):
    """Save today's forecast once, score old ones once 5 sessions have passed."""
    from . import volmodel
    path = os.path.join(ROOT, f"vol{_sfx(inst)}.json")
    rows = secure.load(path) or []
    if vm and not any(r["date"] == today.isoformat() for r in rows):
        rows.append({"date": today.isoformat(), "asof": vm["asof"], "fc": vm["fc"], "iv": vm["iv"], "chosen": vm["chosen"]})
    for r in rows:
        if r.get("real") is None and r.get("asof"):
            r["real"] = volmodel.realized(d1, pd.Timestamp(r["asof"]).date())
    secure.save(path, rows)
    done = [r for r in rows if r.get("real")][-20:]
    if not done:
        return None
    err = lambda k: float(np.mean([abs(r[k] - r["real"]) for r in done]))
    return {"n": len(done), "model_err": err("fc"), "iv_err": err("iv")}
