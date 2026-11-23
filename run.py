"""Run the swing-levels algo once for NQ and ES: pull data, learn stats, pick levels, write the page."""
import datetime as dt
import os
import sys

import numpy as np

from algo import config as C
from algo import data, levels, logbook, options, pick, profile, render, risk, secure, stats, volmodel, vwap
from algo.data import NY

OUT = os.path.join(os.path.dirname(__file__), "site")


def run_instrument(name, fut, now, shared, fred, pw):
    """Everything that's specific to one contract. Returns the page section for it."""
    C.use(name)
    cfg = C.INSTRUMENTS[name]
    warns = []
    m1, m5, d1 = fut["m1"], fut["m5"], fut["d1"]
    for d, g in fut.get("rolls", []):
        warns.append(f"{name} contract roll {d:%b %d}: older bars shifted {g:+.0f} pts so profiles don't mix contracts.")
    today = data.trade_date(m5.index[-1])
    price = float((m1 if not m1.empty else m5).close.iloc[-1])

    # options (DataFirst) — only if the page is password-locked
    opt = options.fetch(cfg["opt"]) if pw else None
    if os.getenv("DATAFIRST_API_KEY") and not opt:
        warns.append(f"DataFirst didn't return {name} options this run — check the Run algo log for [datafirst] lines."
                     if pw else "DataFirst is connected but PAGE_PASSWORD is missing — options are hidden.")
    opt_levels = options.to_levels(opt, price) if opt else []
    cache = logbook.load_opt_cache(name) if pw else {}
    if pw and options._key() and cache.get("hist_date") != today.isoformat():
        h = options.fetch_history(30, cfg["opt"])
        if h:
            cache["hist"] = h
            cache["hist_date"] = today.isoformat()
    opt_hist = options.history_to_levels(cache.get("hist", {}), m5) if cache.get("hist") else {}
    dex_note = None
    if opt and opt.get("net_dex") is not None:
        base = cache.get("dex")
        if base and base.get("date") == today.isoformat() and base.get("v"):
            ch = (opt["net_dex"] - base["v"]) / abs(base["v"])
            if abs(ch) >= 0.25:
                dex_note = f"DEX shifted {ch:+.0%} since {base['time']}"
        else:
            cache["dex"] = {"date": today.isoformat(), "v": opt["net_dex"], "time": now.strftime("%I:%M %p ET")}
    if pw:
        logbook.save_opt_cache(cache, name)

    # volatility: 5-day RV forecast (ridge vs HAR vs implied, best out-of-sample wins)
    ivs = fred.get(cfg["vol"])
    iv = float(ivs.iloc[-1]) if ivs is not None and len(ivs) else None
    iv_name = "VIX" if cfg["vol"] == "VIXCLS" else "VXN"
    d1_closed = d1[d1.index.date < today]
    sigma_iv, iv_src = stats.sigma_points(price, d1_closed, iv)
    vm = None
    try:
        vm = volmodel.forecast(d1_closed, ivs, fred.get("VIXCLS"))
    except Exception as e:
        print(f"[volmodel {name}] {type(e).__name__}: {e}")
    if vm:
        sigma = price * vm["fc"] / np.sqrt(252)
        sigma_src = {"ridge": "vol model", "HAR": "HAR model", "implied": iv_name}[vm["chosen"]]
    else:
        sigma, sigma_src = sigma_iv, iv_src.replace("VXN", iv_name)
    vol_view = None
    if vm:
        vol_view = {"chosen": vm["chosen"], "sigma_iv": sigma_iv, "iv_name": iv_name, "regime": vm["regime"],
                    "ratio": vm["ratio"], "rmse": vm["rmse"], "alpha": vm["alpha"],
                    "track": logbook.vol_log(name, today, vm, d1_closed)}
    if opt and opt.get("gamma_env") == "negative":
        sigma *= C.GAMMA_NEG_EM
        sigma_src += " ×neg-gamma"
    close_et = now.replace(hour=17, minute=0, second=0, microsecond=0)
    frac = max(0.15, min(1.0, (close_et - now).total_seconds() / (23 * 3600))) if now < close_et else 1.0
    sigma_rem = sigma * np.sqrt(frac)

    # learn from history (daily profiles use 1m where available)
    day_prof = profile.by_day(m5)
    if not m1.empty:
        for d, g in m1.groupby("tdate"):
            if d < today and len(g) > 300:
                day_prof[d] = profile.build(g)
    bt = stats.backtest(m5, d1, day_prof, ivs if ivs is not None and len(ivs) else None,
                        shared["risk_days"], opt_hist,
                        fc_hist=(vm or {}).get("oos"), reg_hist=(vm or {}).get("reg_hist"))
    learned = stats.learn(bt)

    lv = levels.collect(m5, d1, today, day_prof, opt_levels)
    ctx = {"risk_day": shared["risk_day"], "macro_bias": shared["macro_bias"],
           "gamma_env": (opt or {}).get("gamma_env"), "dex_sign": 0,
           "vol_regime": (vm or {}).get("regime")}
    scored = pick.score(lv, price, sigma, sigma_rem, learned, ctx)

    logbook.finalize(m5, today, name)
    rec = logbook.load_locked(today, name)
    if rec is None:
        rec = logbook.lock(today, pick.choose(scored, sigma), sigma, price, now, name)
    picks = logbook.live_status(rec, m5[m5.tdate == today])

    opt_view = None
    if opt:
        r = price / opt["spot"]
        rows = []
        for tag, v in (("0DTE", opt["near"]), ("weekly", opt["week"])):
            for lab, k in (("Call wall", "call_wall"), ("Put wall", "put_wall")):
                if v.get(k):
                    rows.append((f"{lab} {tag}", v[k] * r))
        for lab, k in (("Max pain (weekly)", "max_pain"), ("Vol trigger", "vol_trigger"), ("Zero gamma", "zero")):
            if opt["week"].get(k):
                rows.append((lab, opt["week"][k] * r))
        for i, k in enumerate(opt.get("dex_walls", [])):
            rows.append((f"DEX wall {i + 1}", k * r))
        opt_view = {"underlying": opt["underlying"], "gamma_env": opt.get("gamma_env"),
                    "flip": (opt.get("gamma_flip") or 0) * r or None, "rows": rows,
                    "dex_note": dex_note, "hist_days": len(opt_hist)}

    print(f"OK {name} {today} picks={len(picks)} touches={learned['n']} options={'on' if opt else 'off'} "
          f"options_history_days={len(opt_hist)}")
    return {
        "name": name, "price": price, "sigma": sigma, "sigma_src": sigma_src,
        "locked_at": rec["locked_at"][11:16] + " ET", "picks": picks, "scored": scored,
        "learned": learned, "options": opt_view, "vwaps": vwap.all_vwaps(m5, today),
        "scorecard": logbook.scorecard(inst=name), "level_string": pick.level_string(picks),
        "warnings": warns, "vol": vol_view,
    }


def main():
    now = dt.datetime.now(NY)
    warnings = []
    pw = secure.password()
    if not pw:
        warnings.append("PAGE_PASSWORD missing — this page is public and options are off.")
    if not os.getenv("FRED_API_KEY"):
        warnings.append("FRED_API_KEY missing — macro score, VIX/VXN and event dates are off.")
    if not os.getenv("ALPACA_KEY_ID"):
        warnings.append("Alpaca keys missing — headlines and ETF inputs are off.")

    futs = {n: data.futures(c["yf"]) for n, c in C.INSTRUMENTS.items()}
    if all(f["m5"].empty for f in futs.values()):
        print("No futures data from yfinance — stopping without changes.")
        sys.exit(0)
    today = data.trade_date(next(f["m5"] for f in futs.values() if not f["m5"].empty).index[-1])

    # shared: macro, events, headlines
    fred = {s: data.fred_series(s, days=800) for s in ("DGS2", "DGS10", "VIXCLS", "VXVCLS", "VXNCLS")}
    etf = data.alpaca_daily(C.ETFS)
    upcoming, risk_days, fomc_stale = risk.events(today)
    if fomc_stale:
        warnings.append("FOMC dates in config.py are out of date — add next year's dates.")
    news = data.alpaca_news(hours=24) + data.alpaca_news(hours=24, symbols=C.NQ_HEAVY + ["QQQ", "SPY"])
    tagged = risk.tag_headlines(news)
    risk_level, risk_day = risk.day_risk(today, upcoming, tagged)
    m_total, m_bias, m_parts = risk.macro_score(fred, etf, futs["NQ"]["d1"], futs["ES"]["d1"])
    shared = {"risk_days": risk_days, "risk_day": risk_day, "macro_bias": m_bias}

    sections = []
    for name in C.INSTRUMENTS:
        if futs[name]["m5"].empty:
            warnings.append(f"No {name} data from yfinance this run.")
            continue
        try:
            sections.append(run_instrument(name, futs[name], now, shared, fred, pw))
        except Exception as e:  # one instrument failing shouldn't take the page down
            print(f"[{name}] failed: {type(e).__name__}: {e}")
            warnings.append(f"{name} failed this run ({type(e).__name__}) — check the Run algo log.")
    C.use("NQ")

    page_ctx = {
        "updated": now.strftime("%a %b %d %I:%M %p ET"), "warnings": warnings,
        "macro_total": m_total, "macro_bias": m_bias, "macro_parts": m_parts,
        "risk_level": risk_level, "events": upcoming, "headlines": tagged, "sections": sections,
    }
    os.makedirs(OUT, exist_ok=True)
    html = render.page(page_ctx)
    if pw:
        html = secure.lock_page(html, pw)
    with open(os.path.join(OUT, "index.html"), "w") as f:
        f.write(html)
    old = os.path.join(OUT, "levels.json")
    if os.path.exists(old):
        os.remove(old)
    print(f"OK page sections={[s['name'] for s in sections]} locked={'yes' if pw else 'NO'}")


if __name__ == "__main__":
    main()
