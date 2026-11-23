"""Run the swing-levels algo once: pull data, learn stats, pick levels, write the page."""
import datetime as dt
import json
import os
import sys

import numpy as np

from algo import config as C
from algo import data, levels, logbook, options, pick, profile, render, risk, stats
from algo.data import NY

OUT = os.path.join(os.path.dirname(__file__), "site")


def main():
    now = dt.datetime.now(NY)
    warnings = []

    fut = data.futures()
    m1, m5, d1, es = fut["m1"], fut["m5"], fut["d1"], fut["es_d1"]
    if m5.empty:
        print("No NQ data from yfinance — stopping without changes.")
        sys.exit(0)
    for d, g in fut.get("rolls", []):
        warnings.append(f"Contract roll detected {d:%b %d}: older bars shifted {g:+.0f} pts so profiles don't mix contracts.")
    today = data.trade_date(m5.index[-1])
    price = float((m1 if not m1.empty else m5).close.iloc[-1])

    # macro / risk inputs
    fred = {s: data.fred_series(s) for s in ("DGS2", "DGS10", "VIXCLS", "VXVCLS", "VXNCLS")}
    if not os.getenv("FRED_API_KEY"):
        warnings.append("FRED_API_KEY missing — macro score, VXN and event dates are off.")
    if not os.getenv("ALPACA_KEY_ID"):
        warnings.append("Alpaca keys missing — headlines and ETF inputs are off.")
    etf = data.alpaca_daily(C.ETFS)
    upcoming, risk_days, fomc_stale = risk.events(today)
    if fomc_stale:
        warnings.append("FOMC dates in config.py are out of date — add next year's dates.")
    news = data.alpaca_news(hours=24) + data.alpaca_news(hours=24, symbols=C.NQ_HEAVY + ["QQQ", "SPY"])
    tagged = risk.tag_headlines(news)
    risk_level, risk_day = risk.day_risk(today, upcoming, tagged)
    m_total, m_bias, m_parts = risk.macro_score(fred, etf, d1, es)

    # options
    opt = options.fetch()
    opt_levels = options.to_levels(opt, price) if opt else []

    # volatility
    vxn = fred["VXNCLS"]
    vx = float(vxn.iloc[-1]) if len(vxn) else None
    sigma, sigma_src = stats.sigma_points(price, d1[d1.index.date < today], vx)
    if opt and opt.get("gamma_env") == "negative":
        sigma *= C.GAMMA_NEG_EM
        sigma_src += " ×neg-gamma"
    close_et = now.replace(hour=17, minute=0, second=0, microsecond=0)
    frac = max(0.15, min(1.0, (close_et - now).total_seconds() / (23 * 3600))) if now < close_et else 1.0
    sigma_rem = sigma * np.sqrt(frac)

    # learn from history (daily profiles use 1m where available for accuracy)
    day_prof = profile.by_day(m5)
    for d, g in m1.groupby("tdate") if not m1.empty else []:
        if d < today and len(g) > 300:
            day_prof[d] = profile.build(g)
    bt = stats.backtest(m5, d1, day_prof, vxn if len(vxn) else None, risk_days)
    learned = stats.learn(bt)

    # today's levels
    lv = levels.collect(m5, d1, today, day_prof, opt_levels)
    ctx = {"risk_day": risk_day, "macro_bias": m_bias,
           "gamma_env": (opt or {}).get("gamma_env"),
           "dex_sign": int(np.sign((opt or {}).get("net_dex") or 0))}
    scored = pick.score(lv, price, sigma, sigma_rem, learned, ctx)

    # lock picks at the first run of the day, then only update status
    logbook.finalize(m5, today)
    rec = logbook.load_locked(today)
    if rec is None:
        rec = logbook.lock(today, pick.choose(scored, sigma), sigma, price, now)
    picks = logbook.live_status(rec, m5[m5.tdate == today])

    opt_view = None
    if opt:
        r = price / opt["spot"]
        opt_view = {"gamma_env": opt.get("gamma_env"), "flip_nq": (opt.get("gamma_flip") or 0) * r or None,
                    "net_dex": opt.get("net_dex"),
                    "walls_nq": [{"label": f"{w['kind'].title()} wall {w.get('dte', '')}", "price": w["strike"] * r}
                                 for w in opt.get("walls", []) if w.get("strike")]}

    from algo import vwap
    page_ctx = {
        "updated": now.strftime("%a %b %d %I:%M %p ET"), "locked_at": rec["locked_at"][11:16] + " ET",
        "price": price, "sigma": sigma, "sigma_src": sigma_src,
        "macro_total": m_total, "macro_bias": m_bias, "macro_parts": m_parts,
        "risk_level": risk_level, "events": upcoming, "headlines": tagged,
        "picks": picks, "scored": scored, "learned": learned, "options": opt_view,
        "vwaps": vwap.all_vwaps(m5, today), "scorecard": logbook.scorecard(),
        "level_string": pick.level_string(picks), "warnings": warnings,
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "index.html"), "w") as f:
        f.write(render.page(page_ctx))
    with open(os.path.join(OUT, "levels.json"), "w") as f:
        json.dump({"date": today.isoformat(), "updated": now.isoformat(), "price": price, "sigma": sigma,
                   "risk": risk_level, "macro": m_total, "picks": picks,
                   "level_string": page_ctx["level_string"]}, f, indent=1, default=str)
    print(f"OK {today} price={price:.2f} sigma={sigma:.0f} picks={len(picks)} touches={learned['n']}")


if __name__ == "__main__":
    main()
