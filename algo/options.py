"""DataFirst options: GEX levels, gamma regime, walls (nearest expiry + weekly), DEX walls, GEX history.

Docs: https://www.datafirsttrading.com/api/docs  (Bearer key, base https://api.datafirsttrading.com)
DataFirst data can't be redistributed — nothing here prints values to the (public) Actions log.
"""
import datetime as dt
import os

import pandas as pd
import requests

BASE = "https://api.datafirsttrading.com"
SYMS = ("NDX", "QQQ")          # NDX first (cleanest to NQ), QQQ as backup
NUM_KEYS = ("strike", "price", "value", "level", "center", "spot", "last")
TIME_KEYS = ("time", "timestamp", "ts", "t", "at", "minute", "datetime")


def _key():
    return (os.getenv("DATAFIRST_API_KEY") or "").strip() or None


HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0 Safari/537.36 swing-levels/1.0",
}


def _why(r):
    """DataFirst's own error reason (RFC 9457 title/detail) — text only, no market data."""
    try:
        js = r.json()
        parts = [str(js.get(k)) for k in ("title", "detail", "code", "error", "message") if js.get(k)]
        if parts:
            return " | ".join(parts)[:200]
    except Exception:
        pass
    server = r.headers.get("server", "")
    if "cloudflare" in server.lower() or "cf-ray" in {k.lower() for k in r.headers}:
        return "blocked by Cloudflare (bot filter), not by DataFirst's API"
    return (r.text or "")[:120].replace("\n", " ")


def _get(path, key, params=None):
    r = requests.get(BASE + path, headers={**HEADERS, "Authorization": f"Bearer {key}"},
                     params=params or {}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"{path} HTTP {r.status_code} — {_why(r)}")
    js = r.json()
    if isinstance(js, dict) and isinstance(js.get("data"), (dict, list)):
        js = js["data"]
    return js


def _num(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, dict):
        for k in NUM_KEYS:
            v = x.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
        return None
    try:
        return float(x)
    except Exception:
        return None


def _shape(d):
    """Key names only (never values) for debugging in a public log."""
    return sorted(d.keys())[:25] if isinstance(d, dict) else type(d).__name__


def _spot(d):
    if not isinstance(d, dict):
        return None
    for k in ("spot", "underlying_price", "price", "last", "underlying"):
        v = _num(d.get(k))
        if v:
            return v
    return None


def _parse(d):
    kl = d.get("key_levels") or {}
    walls = d.get("walls") or {}
    tot = d.get("totals") or {}
    de = d.get("dealer_extremes") or {}
    calls = [_num(x) for x in (walls.get("calls") or [])[:3]]
    puts = [_num(x) for x in (walls.get("puts") or [])[:3]]
    return {
        "flip": _num(kl.get("gamma_flip")), "zero": _num(kl.get("zero_gamma")),
        "call_wall": _num(kl.get("call_wall")), "put_wall": _num(kl.get("put_wall")),
        "max_pain": _num(kl.get("max_pain")), "vol_trigger": _num(kl.get("vol_trigger")),
        "calls": [c for c in calls if c], "puts": [p for p in puts if p],
        "net_gex": _num(tot.get("net_gex")), "gex_ratio": _num(tot.get("gex_ratio")),
        "dex": _num(tot.get("delta_exposure")),
        "regime": de.get("regime") if isinstance(de, dict) else None,
    }


def _regime(*views):
    for v in views:
        r = (v.get("regime") or "").upper()
        if "LONG" in r:
            return "positive"
        if "SHORT" in r:
            return "negative"
    for v in views:
        if v.get("net_gex") is not None:
            return "positive" if v["net_gex"] > 0 else "negative"
    return None


def fetch():
    key = _key()
    if not key:
        return None
    for sym in SYMS:
        try:
            near = _get(f"/v1/symbols/{sym}/levels", key, {"expirations": 1})
            week = _get(f"/v1/symbols/{sym}/levels", key, {"expirations": 5})
        except Exception as e:
            print(f"[datafirst] {sym} levels: {e}")
            continue
        if not isinstance(near, dict) or not isinstance(week, dict):
            print(f"[datafirst] {sym} unexpected shape: {type(near).__name__}")
            continue
        spot = _spot(near) or _spot(week)
        if not spot:
            try:
                spot = _spot(_get(f"/v1/symbols/{sym}/spot", key))
            except Exception as e:
                print(f"[datafirst] {sym} spot: {e}")
        if not spot:
            print(f"[datafirst] {sym}: no spot field. levels keys = {_shape(near)}")
            continue
        n, w = _parse(near), _parse(week)
        if not any([n["call_wall"], n["put_wall"], w["call_wall"], w["flip"]]):
            print(f"[datafirst] {sym}: no key levels found. keys = {_shape(near)}, key_levels = {_shape(near.get('key_levels'))}")
            continue
        out = {"underlying": sym, "spot": spot, "near": n, "week": w,
               "gamma_env": _regime(w, n), "gamma_flip": w["flip"] or n["flip"],
               "dex_walls": [], "net_dex": w["dex"]}
        try:
            st = _get(f"/v1/symbols/{sym}/strikes", key, {"expirations": 5, "strikes": 40})
            rows = st.get("strikes") if isinstance(st, dict) else st
            pts = []
            for r in rows or []:
                k = _num(r.get("strike"))
                d = _num((r.get("exposures") or {}).get("delta"))
                if k and d is not None:
                    pts.append((abs(d), k))
            out["dex_walls"] = [k for _, k in sorted(pts, reverse=True)[:2]]
        except Exception as e:
            print(f"[datafirst] {sym} strikes: {e}")
        return out
    return None


def to_levels(opt, nq_price):
    """Underlying strikes -> NQ prices using today's NQ / underlying ratio."""
    if not opt or not opt.get("spot"):
        return []
    r = nq_price / opt["spot"]
    out = []

    def add(t, v, sfx=""):
        if v:
            out.append({"type": t, "price": v * r, "sfx": sfx})

    add("GAMMA_FLIP", opt.get("gamma_flip"))
    for tag, v in (("0DTE", opt["near"]), ("weekly", opt["week"])):
        add("GEX_CALL", v.get("call_wall"), f" {tag}")
        add("GEX_PUT", v.get("put_wall"), f" {tag}")
    add("MAX_PAIN", opt["week"].get("max_pain"), " weekly")
    add("VOL_TRIGGER", opt["week"].get("vol_trigger"))
    for k in opt.get("dex_walls", []):
        add("DEX_WALL", k)
    return out


# ---------------------------------------------------------------- history (for the backtest)
def _walk(obj, parent_time=None):
    """Yield (time, level-dict) for every dict that looks like a key-levels snapshot."""
    if isinstance(obj, dict):
        t = next((obj[k] for k in TIME_KEYS if k in obj and isinstance(obj[k], (str, int, float))), parent_time)
        if "date" in obj and t is None:
            t = obj["date"]
        kl = obj.get("key_levels") if isinstance(obj.get("key_levels"), dict) else None
        if kl or any(k in obj for k in ("gamma_flip", "call_wall", "put_wall")):
            yield t, obj
            return  # don't double-count the nested key_levels dict
        for v in obj.values():
            if isinstance(v, (dict, list)):
                yield from _walk(v, t)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v, parent_time)


def fetch_history(days=30):
    """{date: {"spot": x, "levels": [(type, underlying_price, sfx)]}} using the snapshot nearest 9:30 ET."""
    key = _key()
    if not key:
        return {}
    to = dt.date.today()
    frm = to - dt.timedelta(days=int(days * 1.5))
    for sym in SYMS:
        try:
            js = _get(f"/v1/symbols/{sym}/history/levels", key,
                      {"from": frm.isoformat(), "to": to.isoformat(), "interval": 30})
        except Exception as e:
            print(f"[datafirst] {sym} history: {e}")
            continue
        snaps = {}
        for t, rec in _walk(js):
            try:
                if t is None:
                    continue
                ts = pd.Timestamp(t, unit="s") if isinstance(t, (int, float)) else pd.Timestamp(t)
                if pd.isna(ts):
                    continue
                ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts
                ts = ts.tz_convert("America/New_York")
            except Exception:
                continue
            mins = ts.hour * 60 + ts.minute
            if mins < 570:
                continue
            d = ts.date()
            if d not in snaps or mins < snaps[d][0]:
                snaps[d] = (mins, rec)
        out = {}
        for d, (_, rec) in snaps.items():
            kl = rec.get("key_levels") if isinstance(rec.get("key_levels"), dict) else rec
            spot = _spot(rec)
            lv = []
            for t, k in (("GAMMA_FLIP", "gamma_flip"), ("GEX_CALL", "call_wall"),
                         ("GEX_PUT", "put_wall"), ("MAX_PAIN", "max_pain"), ("VOL_TRIGGER", "vol_trigger")):
                v = _num(kl.get(k))
                if v:
                    lv.append((t, v, ""))
            if lv:
                out[d.isoformat()] = {"spot": spot, "levels": lv}
        if out:
            return {"sym": sym, "days": out}
        print(f"[datafirst] {sym} history: no snapshots parsed. top keys = {_shape(js)}")
    return {}


def history_to_levels(hist, m5):
    """Convert each day's underlying levels to NQ with that morning's NQ / underlying ratio."""
    res = {}
    for ds, rec in (hist.get("days") or {}).items():
        d = dt.date.fromisoformat(ds)
        bars = m5[(m5.tdate == d) & m5.rth]
        if bars.empty:
            continue
        nq_open = float(bars.open.iloc[0])
        spot = rec.get("spot")
        # no spot in the snapshot -> skip the day rather than guess a ratio
        if not spot:
            continue
        r = nq_open / spot
        res[d] = [{"type": t, "price": v * r, "sfx": s} for t, v, s in rec["levels"]]
    return res
