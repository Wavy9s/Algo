"""Light blue + white dashboard. One self-contained HTML file, auto-refreshes every 5 min."""
import html
import math

from .levels import TYPES

CSS = """
*{box-sizing:border-box}body{margin:0;background:#E6F1FB;color:#042C53;font:14px/1.5 -apple-system,Segoe UI,Inter,Arial,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:20px}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;gap:8px;flex-wrap:wrap}
.title{font-size:20px;font-weight:600;color:#0C447C}.pill{background:#fff;border:1px solid #B5D4F4;color:#185FA5;padding:3px 12px;border-radius:999px;font-size:12px}
.grid4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:12px}
.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
@media(max-width:760px){.grid4{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-columns:1fr}}
.card{background:#fff;border:1px solid #B5D4F4;border-radius:12px;padding:14px 18px;margin-bottom:12px;overflow-x:auto}
.k{background:#fff;border:1px solid #B5D4F4;border-radius:12px;padding:10px 14px}
.lab{font-size:12px;color:#378ADD;font-weight:600;margin:0 0 6px}.big{font-size:22px;font-weight:600;margin:0}
.sub{font-size:12px;color:#5d84ad;margin:2px 0 0}
table{width:100%;border-collapse:collapse;font-size:13px}th{color:#378ADD;font-weight:600;text-align:left;font-size:12px;padding:6px 6px}
td{padding:7px 6px;border-top:1px solid #E6F1FB;vertical-align:top}.m{font-family:ui-monospace,Menlo,Consolas,monospace}
.g{display:inline-block;font-size:11px;padding:2px 9px;border-radius:999px;font-weight:600}
.gA\\+{background:#185FA5;color:#fff}.gA{background:#B5D4F4;color:#0C447C}.gB{background:#EEF4FA;color:#5d84ad}.gLVN{background:#F1EFE8;color:#5F5E5A}
.R{color:#A32D2D}.S{color:#0F6E56}.muted{color:#85B7EB}
.st{font-size:11px;padding:2px 8px;border-radius:999px}.st-live{background:#E6F1FB;color:#185FA5}.st-held{background:#EAF3DE;color:#27500A}
.st-broke{background:#FCEBEB;color:#791F1F}.st-testing{background:#FAEEDA;color:#633806}
.sev{font-size:11px;padding:2px 8px;border-radius:999px;font-weight:600;margin-right:6px}.High{background:#FCEBEB;color:#A32D2D}
.Med{background:#FAEEDA;color:#854F0B}.Low{background:#E6F1FB;color:#185FA5}
.row{display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-top:1px solid #E6F1FB;font-size:13px}.row:first-of-type{border-top:none}
code.str{display:block;flex:1;font-size:12px;background:#E6F1FB;color:#0C447C;padding:9px;border-radius:8px;overflow-x:auto;white-space:nowrap}
button{background:#378ADD;color:#fff;border:0;border-radius:8px;padding:8px 16px;font-size:13px;cursor:pointer}
details summary{cursor:pointer;color:#185FA5;font-weight:600}a{color:#185FA5}
.warn{background:#FAEEDA;color:#633806;border:1px solid #FAC775;border-radius:10px;padding:8px 12px;margin-bottom:12px;font-size:13px}
"""


def e(x):
    return html.escape(str(x))


def pct(x):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.0%}"


def num(x, d=0):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:,.{d}f}"


def page(ctx: dict) -> str:
    c = ctx
    P = []
    a = P.append
    a(f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
      f"<meta http-equiv='refresh' content='300'><title>Swing levels · NQ</title><style>{CSS}</style></head><body><div class='wrap'>")
    a(f"<div class='top'><span class='title'>Swing levels · NQ</span><span class='pill'>Updated {e(c['updated'])} · "
      f"locked {e(c['locked_at'])}</span></div>")
    for w in c.get("warnings", []):
        a(f"<div class='warn'>{e(w)}</div>")

    mc = {"Bull": "#0F6E56", "Bear": "#A32D2D"}.get(c["macro_bias"], "#185FA5")
    rc = {"High": "#A32D2D", "Elevated": "#BA7517"}.get(c["risk_level"], "#0F6E56")
    a("<div class='grid4'>")
    a(f"<div class='k'><p class='lab'>NQ (yfinance, ~15m delay)</p><p class='big m'>{num(c['price'], 2)}</p></div>")
    a(f"<div class='k'><p class='lab'>Macro</p><p class='big' style='color:{mc}'>{e(c['macro_bias'])} {c['macro_total']:+d}</p></div>")
    a(f"<div class='k'><p class='lab'>Risk today</p><p class='big' style='color:{rc}'>{e(c['risk_level'])}</p></div>")
    a(f"<div class='k'><p class='lab'>Expected move (1σ day)</p><p class='big m'>±{num(c['sigma'])}</p>"
      f"<p class='sub'>week ±{num(c['sigma'] * 5 ** .5)} · {e(c['sigma_src'])}</p></div>")
    a("</div>")

    # picks
    a("<div class='card'><p class='lab'>Picked levels — locked at first run of the day</p><table>"
      "<tr><th>Price</th><th>Level</th><th>Touch</th><th>Hold</th><th>n</th><th>Bounce</th><th>EV</th><th>Grade</th><th>Status</th></tr>")
    for p in c["picks"]:
        notes = f"<div class='sub'>{e(', '.join(p['notes']))}</div>" if p.get("notes") else ""
        a(f"<tr><td class='m {p['side']}'>{num(p['price'], 2)}</td><td>{e(p['label'])}{notes}</td>"
          f"<td>{pct(p['touch'])}</td><td>{pct(p['hold'])}</td><td>{p['n']}</td><td>{num(p['bounce'])}</td>"
          f"<td>{num(p['ev'], 1)}</td><td><span class='g g{e(p['grade'])}'>{e(p['grade'])}</span></td>"
          f"<td><span class='st st-{p.get('status', 'live')}'>{e(p.get('status', 'live'))}</span></td></tr>")
    if not c["picks"]:
        a("<tr><td colspan='9' class='muted'>No levels passed the filters today.</td></tr>")
    a("</table></div>")

    a("<div class='grid2'>")
    # options
    o = c.get("options")
    a("<div class='card'><p class='lab'>Options (DataFirst)</p>")
    if o:
        gc = "#0F6E56" if o.get("gamma_env") == "positive" else "#A32D2D"
        a(f"<div class='row'><span>Gamma environment</span><b style='color:{gc}'>{e(o.get('gamma_env', '—'))}</b></div>")
        a(f"<div class='row'><span>Gamma flip (NQ)</span><span class='m'>{num(o.get('flip_nq'), 2)}</span></div>")
        d = o.get("net_dex")
        a(f"<div class='row'><span>Net DEX</span><span>{'▲ dealers long' if (d or 0) > 0 else '▼ dealers short' if (d or 0) < 0 else '—'}</span></div>")
        for w in o.get("walls_nq", []):
            a(f"<div class='row'><span>{e(w['label'])}</span><span class='m'>{num(w['price'], 2)}</span></div>")
    else:
        a("<p class='sub'>Not connected yet. GEX, gamma flip, DEX and 0DTE/7DTE walls show here once the DataFirst endpoints are wired.</p>")
    a("</div>")

    # vwaps
    a("<div class='card'><p class='lab'>VWAPs (hlc3) and bands</p>")
    names = [("session", "Session (RTH)"), ("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly"),
             ("prior_daily", "Prior-day close"), ("prior_weekly", "Prior-week close"), ("prior_monthly", "Prior-month close")]
    for k, lab in names:
        v = c["vwaps"].get(k)
        if v:
            a(f"<div class='row'><span>{lab}</span><span class='m'>{num(v['vwap'], 2)} "
              f"<span class='muted'>±1σ {num(v['sd'])} · ±2σ {num(2 * v['sd'])}</span></span></div>")
    a("</div>")

    # headlines
    a("<div class='card'><p class='lab'>Headline risk (last 24h, keyword-tagged)</p>")
    for h in c["headlines"][:8]:
        link = f"<a href='{e(h['url'])}' target='_blank' rel='noopener'>{e(h['headline'])}</a>" if h.get("url") else e(h["headline"])
        a(f"<div class='row'><span><span class='sev {h['sev']}'>{h['sev']}</span>{link}"
          f"<span class='sub'> · {e(h['cat'])}{' · ' + e(', '.join(h['symbols'])) if h['symbols'] else ''}</span></span></div>")
    if not c["headlines"]:
        a("<p class='sub'>No NQ-relevant headlines flagged.</p>")
    a("</div>")

    # events + macro
    a("<div class='card'><p class='lab'>Scheduled events (next 7 days, 8:30 ET unless FOMC 2:00 ET)</p>")
    for d, n in c["events"]:
        a(f"<div class='row'><span>{e(n)}</span><span>{d:%a %b %d}</span></div>")
    if not c["events"]:
        a("<p class='sub'>Nothing major scheduled.</p>")
    a("<p class='lab' style='margin-top:12px'>Macro score inputs</p>")
    for name, s, v in c["macro_parts"]:
        col = "#0F6E56" if s > 0 else "#A32D2D" if s < 0 else "#5d84ad"
        a(f"<div class='row'><span>{e(name)}</span><span>{e(v)} <b style='color:{col}'>{s:+d}</b></span></div>")
    a("</div>")
    a("</div>")  # grid2

    # scorecard
    sc = c.get("scorecard")
    a("<div class='card'><p class='lab'>Scorecard — how past picks did</p>")
    if sc:
        g = " · ".join(f"{k} held {pct(v[0])} (n={v[1]})" for k, v in sorted(sc["by_grade"].items()))
        a(f"<div class='row'><span>Last {sc['days']} days by grade</span><span>{e(g) or '—'}</span></div>")
        a(f"<div class='row'><span>Touch odds: predicted vs real</span><span>{pct(sc['touch_pred'])} vs {pct(sc['touch_real'])}</span></div>")
        a(f"<div class='row'><span>Hold %: predicted vs real</span><span>{pct(sc['hold_pred'])} vs {pct(sc['hold_real'])}</span></div>")
        a(f"<div class='row'><span>Last day ({e(sc['last_date'])})</span><span>{sc['last_held']} of {sc['last_n']} touched picks held "
          f"({sc['last_picks']} picks)</span></div>")
    else:
        a("<p class='sub'>Starts filling in after the first full day of picks.</p>")
    a("</div>")

    # level string
    a("<div class='card'><p class='lab'>Level string (for LV in TradingView)</p><div style='display:flex;gap:8px;align-items:center'>"
      f"<code class='str' id='ls'>{e(c['level_string'])}</code><button onclick=\"navigator.clipboard.writeText(document.getElementById('ls').innerText);"
      "this.innerText='Copied';setTimeout(()=>this.innerText='Copy',1500)\">Copy</button></div></div>")

    # all levels
    a("<div class='card'><details><summary>All levels today</summary><table><tr><th>Price</th><th>Level</th><th>Touch</th>"
      "<th>Hold</th><th>n</th><th>Stack</th><th>Grade</th></tr>")
    for x in sorted(c["scored"], key=lambda z: -z["price"]):
        a(f"<tr><td class='m {x['side']}'>{num(x['price'], 2)}</td><td>{e(x['label'])}</td><td>{pct(x['touch'])}</td>"
          f"<td>{pct(x['hold'])}</td><td>{x['n']}</td><td>{x['stack']}</td><td><span class='g g{e(x['grade'])}'>{e(x['grade'])}</span></td></tr>")
    a("</table></details></div>")

    # stats
    L = c["learned"]
    a(f"<div class='card'><details><summary>Level stats (backtest, {L['n']} touches, last ~60 days)</summary>"
      f"<p class='sub'>Overall hold {pct(L['overall'])} · stack bonus +{L['stack_bonus']:.0%} per extra level · "
      f"risk-day penalty −{L['risk_penalty']:.0%}. Small n = shrunk toward the category average.</p><table>"
      "<tr><th>Type</th><th>n</th><th>Hold</th><th>Sweep</th><th>Bounce</th><th>Break run</th><th>1st touch</th><th>Retest</th>"
      "<th>NY AM</th><th>Risk day</th></tr>")
    for t, s in sorted(L["types"].items(), key=lambda kv: -kv[1]["n"]):
        am = s["sess"].get("NY AM", (float("nan"), 0))
        a(f"<tr><td>{e(TYPES.get(t, (t,))[0])}</td><td>{s['n']}</td><td>{pct(s['hold'])}</td><td>{pct(s['sweep'])}</td>"
          f"<td>{num(s['bounce'])}</td><td>{num(s['run'])}</td><td>{pct(s['first'])} <span class='muted'>({s['n_first']})</span></td>"
          f"<td>{pct(s['retest'])} <span class='muted'>({s['n_retest']})</span></td><td>{pct(am[0])} <span class='muted'>({am[1]})</span></td>"
          f"<td>{pct(s['risk_day'])} <span class='muted'>({s['n_risk']})</span></td></tr>")
    a("</table></details></div>")

    a("<p class='sub'>Data: yfinance (NQ, ~15m delayed), Alpaca (ETFs, Benzinga headlines), FRED (yields, VIX, VXN, release dates). "
      "Not financial advice.</p></div></body></html>")
    return "".join(P)
