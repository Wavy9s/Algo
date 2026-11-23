"""Scheduled events (FRED + FOMC), headline risk tagging (keywords), macro score."""
import datetime as dt
import re

import numpy as np

from . import config as C
from . import data

# category -> keywords. Order matters: first match wins the label.
RULES = [
    ("Geopolitics", 3, r"\b(war|missile|invasion|invade|airstrike|military strike|attack on|nuclear|"
                       r"escalat\w*|ceasefire|sanction\w*|taiwan|strait of hormuz)\b"),
    ("Fed", 3, r"\b(fomc|powell|fed chair|rate hike|rate cut|emergency cut|fed minutes|"
               r"federal reserve|dot plot|balance sheet runoff)\b"),
    ("Trade/tariffs", 3, r"\b(tariff\w*|export control\w*|chip ban|trade war|retaliat\w*|"
                         r"entity list|section 301)\b"),
    ("Macro data", 2, r"\b(cpi|inflation|payrolls?|jobs report|unemployment rate|pce|gdp|"
                      r"retail sales|ism|jobless claims|ppi)\b"),
    ("Earnings", 2, r"\b(earnings|guidance|eps|revenue|quarterly results|beats|misses|"
                    r"raises outlook|cuts outlook|reports after|reports before)\b"),
    ("Systemic", 3, r"\b(bank failure|default|downgrad\w* (?:of )?(?:the )?u\.?s\.?|"
                    r"government shutdown|debt ceiling|liquidity crisis|circuit breaker)\b"),
]
SHOCK = r"\b(surprise\w*|unexpected\w*|emergency|plunge\w*|crash\w*|soar\w*|halt\w*|shock\w*)\b"
CALM = r"\b(as expected|in line|steady|unchanged)\b"


def tag_headlines(items: list) -> list:
    out, seen = [], set()
    heavy = set(C.NQ_HEAVY)
    for it in items:
        h = (it.get("headline") or "").strip()
        if not h or h.lower() in seen:
            continue
        seen.add(h.lower())
        low = h.lower()
        syms = set(it.get("symbols") or [])
        cat, score = None, 0
        for name, w, pat in RULES:
            if re.search(pat, low):
                cat, score = name, w
                break
        if not cat:
            continue
        if cat == "Earnings" and not (syms & heavy):
            continue                              # small-cap earnings don't move NQ
        if syms & heavy:
            score += 1
        if re.search(SHOCK, low):
            score += 1
        if re.search(CALM, low):
            score -= 1
        sev = "High" if score >= 4 else "Med" if score >= 3 else "Low"
        out.append({"headline": h, "cat": cat, "sev": sev, "score": score,
                    "symbols": sorted(syms)[:4], "time": it.get("created_at", ""),
                    "url": it.get("url", "")})
    out.sort(key=lambda x: x["time"], reverse=True)   # newest first...
    out.sort(key=lambda x: -x["score"])               # ...then most severe first
    return out


def events(today: dt.date):
    """Scheduled macro events in the next 7 days + set of past risk days (for the backtest)."""
    fomc = {dt.date.fromisoformat(d) for d in C.FOMC_DATES}
    allr = {d: "FOMC" for d in fomc}
    for rid, name in C.FRED_RELEASES.items():
        for d in data.fred_release_dates(rid):
            allr.setdefault(d, name)
    upcoming = sorted((d, n) for d, n in allr.items() if today <= d <= today + dt.timedelta(days=7))
    stale = max(dt.date.fromisoformat(d) for d in C.FOMC_DATES) < today
    return upcoming, frozenset(allr), stale


def day_risk(today, upcoming, tagged):
    pts = 0
    today_ev = [n for d, n in upcoming if d == today]
    pts += 3 * len([n for n in today_ev if n in ("FOMC", "CPI", "Jobs report (NFP)")])
    pts += len([n for n in today_ev if n not in ("FOMC", "CPI", "Jobs report (NFP)")])
    pts += 2 * sum(1 for x in tagged if x["sev"] == "High")
    pts += 0.5 * sum(1 for x in tagged if x["sev"] == "Med")
    lvl = "High" if pts >= 5 else "Elevated" if pts >= 2.5 else "Normal" if pts >= 1 else "Low"
    return lvl, bool(today_ev) or lvl in ("High", "Elevated")


def macro_score(fred: dict, etf: dict, nq_d1, es_d1):
    """+ = supportive for NQ, - = headwind. Each input is +1 / 0 / -1."""
    parts = []

    def chg(s, n=5):
        s = s.dropna() if s is not None else s
        return float(s.iloc[-1] - s.iloc[-1 - n]) if s is not None and len(s) > n else None

    d2 = chg(fred.get("DGS2"))
    if d2 is not None:
        parts.append(("2Y yield 5d", -1 if d2 > 0.10 else 1 if d2 < -0.10 else 0, f"{d2:+.2f}%"))
    d10 = chg(fred.get("DGS10"))
    if d10 is not None:
        parts.append(("10Y yield 5d", -1 if d10 > 0.10 else 1 if d10 < -0.10 else 0, f"{d10:+.2f}%"))
    vix, v3m = fred.get("VIXCLS"), fred.get("VXVCLS")
    if vix is not None and v3m is not None and len(vix) and len(v3m):
        r = float(vix.iloc[-1] / v3m.iloc[-1])
        parts.append(("VIX/VIX3M", -1 if r > 1.0 else 1 if r < 0.9 else 0, f"{r:.2f}"))

    def rel(a, b, n=5):
        if a is None or b is None or len(a) <= n or len(b) <= n:
            return None
        x = (a / b).dropna()
        return float(x.iloc[-1] / x.iloc[-1 - n] - 1) if len(x) > n else None

    s = rel(etf.get("SOXX"), etf.get("QQQ"))
    if s is not None:
        parts.append(("SOXX/QQQ 5d", 1 if s > 0.01 else -1 if s < -0.01 else 0, f"{s:+.1%}"))
    if nq_d1 is not None and es_d1 is not None and len(nq_d1) > 6 and len(es_d1) > 6:
        a = nq_d1.close.copy(); a.index = a.index.date
        b = es_d1.close.copy(); b.index = b.index.date
        s = rel(a, b)
        if s is not None:
            parts.append(("NQ/ES 5d", 1 if s > 0.005 else -1 if s < -0.005 else 0, f"{s:+.1%}"))
    total = int(sum(p[1] for p in parts))
    bias = "Bull" if total >= 2 else "Bear" if total <= -2 else "Neutral"
    return total, bias, parts
