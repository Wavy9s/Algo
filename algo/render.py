"""Graphite dashboard with NQ | ES tabs. One self-contained HTML file, auto-refreshes every 5 min."""
import html
import math

from .levels import TYPES

CSS = """
*{box-sizing:border-box}body{margin:0;background:#151515;color:#EDEDED;font:14px/1.5 -apple-system,Segoe UI,Inter,Arial,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:20px}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;gap:10px;flex-wrap:wrap}
.title{font-size:20px;font-weight:600;color:#F5F5F5}.pill{background:#1F1F1F;border:1px solid #333;color:#A3A3A3;padding:3px 12px;border-radius:999px;font-size:12px}
.tabs{display:flex;gap:6px}.tab{background:#1F1F1F;border:1px solid #333;color:#A3A3A3;border-radius:999px;padding:5px 18px;font-size:14px;font-weight:600;cursor:pointer}
.tab.on{background:#E5E5E5;color:#111;border-color:#E5E5E5}
.grid4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:12px}
.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
@media(max-width:760px){.grid4{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-columns:1fr}}
.card{background:#1F1F1F;border:1px solid #333;border-radius:12px;padding:14px 18px;margin-bottom:12px;overflow-x:auto}
.k{background:#1F1F1F;border:1px solid #333;border-radius:12px;padding:10px 14px}
.lab{font-size:12px;color:#A3A3A3;font-weight:600;margin:0 0 6px}.big{font-size:22px;font-weight:600;margin:0;color:#F5F5F5}
.sub{font-size:12px;color:#8A8A8A;margin:2px 0 0}
table{width:100%;border-collapse:collapse;font-size:13px}th{color:#A3A3A3;font-weight:600;text-align:left;font-size:12px;padding:6px 6px}
td{padding:7px 6px;border-top:1px solid #2A2A2A;vertical-align:top}.m{font-family:ui-monospace,Menlo,Consolas,monospace}
.g{display:inline-block;font-size:11px;padding:2px 9px;border-radius:999px;font-weight:600}
.gA\\+{background:#E5E5E5;color:#111}.gA{background:#3A3A3A;color:#F5F5F5}.gB{background:#262626;color:#A3A3A3}.gLVN{background:#262626;color:#6B6B6B}
.R{color:#F87171}.S{color:#4ADE80}.muted{color:#6B6B6B}
.st{font-size:11px;padding:2px 8px;border-radius:999px}.st-live{background:#2A2A2A;color:#D4D4D4}.st-held{background:#14321F;color:#86EFAC}
.st-broke{background:#3B1818;color:#FCA5A5}.st-testing{background:#3A2E12;color:#FCD34D}
.sev{font-size:11px;padding:2px 8px;border-radius:999px;font-weight:600;margin-right:6px}.High{background:#3B1818;color:#FCA5A5}
.Med{background:#3A2E12;color:#FCD34D}.Low{background:#2A2A2A;color:#D4D4D4}
.row{display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-top:1px solid #2A2A2A;font-size:13px}.row:first-of-type{border-top:none}
code.str{display:block;flex:1;font-size:12px;background:#151515;color:#D4D4D4;padding:9px;border-radius:8px;overflow-x:auto;white-space:nowrap;border:1px solid #2A2A2A}
button.cp{background:#E5E5E5;color:#111;border:0;border-radius:8px;padding:8px 16px;font-size:13px;font-weight:600;cursor:pointer}
details summary{cursor:pointer;color:#D4D4D4;font-weight:600}a{color:#D4D4D4}
.warn{background:#2A2312;color:#FCD34D;border:1px solid #4A3B14;border-radius:10px;padding:8px 12px;margin-bottom:12px;font-size:13px}
.hide{display:none}
"""

GREEN, RED, AMBER, GREY = "#4ADE80", "#F87171", "#FBBF24", "#A3A3A3"


def e(x):
    return html.escape(str(x))


def pct(x):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.0%}"


def num(x, d=0):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:,.{d}f}"


def _top(c, s, a):
    mc = {"Bull": GREEN, "Bear": RED}.get(c["macro_bias"], GREY)
    rc = {"High": RED, "Elevated": AMBER}.get(c["risk_level"], GREEN)
    for w in s["warnings"]:
        a(f"<div class='warn'>{e(w)}</div>")
    a("<div class='grid4'>")
    a(f"<div class='k'><p class='lab'>{s['name']} (yfinance, ~15m delay)</p><p class='big m'>{num(s['price'], 2)}</p>"
      f"<p class='sub'>picks locked {e(s['locked_at'])}</p></div>")
    a(f"<div class='k'><p class='lab'>Macro</p><p class='big' style='color:{mc}'>{e(c['macro_bias'])} {c['macro_total']:+d}</p></div>")
    a(f"<div class='k'><p class='lab'>Risk today</p><p class='big' style='color:{rc}'>{e(c['risk_level'])}</p></div>")
    a(f"<div class='k'><p class='lab'>Expected move (1σ day)</p><p class='big m'>±{num(s['sigma'], 1 if s['sigma'] < 100 else 0)}</p>"
      f"<p class='sub'>week ±{num(s['sigma'] * 5 ** .5, 1 if s['sigma'] < 100 else 0)} · {e(s['sigma_src'])}</p></div>")
    a("</div>")

    a(f"<div class='card'><p class='lab'>{s['name']} picked levels — locked at first run of the day</p><table>"
      "<tr><th>Price</th><th>Level</th><th>Touch</th><th>Hold</th><th>n</th><th>Bounce</th><th>EV</th><th>Grade</th><th>Status</th></tr>")
    for p in s["picks"]:
        notes = f"<div class='sub'>{e(', '.join(p['notes']))}</div>" if p.get("notes") else ""
        a(f"<tr><td class='m {p['side']}'>{num(p['price'], 2)}</td><td>{e(p['label'])}{notes}</td>"
          f"<td>{pct(p['touch'])}</td><td>{pct(p['hold'])}</td><td>{p['n']}</td><td>{num(p['bounce'])}</td>"
          f"<td>{num(p['ev'], 1)}</td><td><span class='g g{e(p['grade'])}'>{e(p['grade'])}</span></td>"
          f"<td><span class='st st-{p.get('status', 'live')}'>{e(p.get('status', 'live'))}</span></td></tr>")
    if not s["picks"]:
        a("<tr><td colspan='9' class='muted'>No levels passed the filters today.</td></tr>")
    a("</table></div>")

    a("<div class='grid2'>")
    o = s.get("options")
    a(f"<div class='card'><p class='lab'>Options (DataFirst → {s['name']})</p>")
    if o:
        env = o.get("gamma_env")
        gc = GREEN if env == "positive" else RED
        txt = "Positive — levels hold more" if env == "positive" else "Negative — moves run, levels break more" if env == "negative" else "—"
        a(f"<div class='row'><span>Gamma environment</span><b style='color:{gc}'>{e(txt)}</b></div>")
        a(f"<div class='row'><span>Gamma flip</span><span class='m'>{num(o.get('flip'), 2)}</span></div>")
        for lab, p in o["rows"]:
            a(f"<div class='row'><span>{e(lab)}</span><span class='m'>{num(p, 2)}</span></div>")
        if o.get("dex_note"):
            a(f"<div class='row'><span style='color:{AMBER}'>{e(o['dex_note'])}</span></div>")
        a(f"<p class='sub'>From {e(o['underlying'])}, converted to {s['name']}. Backtest has {o['hist_days']} days of GEX history.</p>")
    else:
        a("<p class='sub'>No options data this run.</p>")
    a("</div>")
    a(f"<div class='card'><p class='lab'>{s['name']} VWAPs (hlc3) and bands</p>")
    for k, lab in [("session", "Session (RTH)"), ("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly"),
                   ("prior_daily", "Prior-day close"), ("prior_weekly", "Prior-week close"), ("prior_monthly", "Prior-month close")]:
        v = s["vwaps"].get(k)
        if v:
            a(f"<div class='row'><span>{lab}</span><span class='m'>{num(v['vwap'], 2)} "
              f"<span class='muted'>±1σ {num(v['sd'], 1)} · ±2σ {num(2 * v['sd'], 1)}</span></span></div>")
    a("</div></div>")


def _bottom(s, a):
    sc = s.get("scorecard")
    a(f"<div class='card'><p class='lab'>{s['name']} scorecard — how past picks did</p>")
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

    sid = f"ls{s['name']}"
    a(f"<div class='card'><p class='lab'>{s['name']} level string (for LV in TradingView)</p><div style='display:flex;gap:8px;align-items:center'>"
      f"<code class='str' id='{sid}'>{e(s['level_string'])}</code><button class='cp' onclick=\"navigator.clipboard.writeText("
      f"document.getElementById('{sid}').innerText);this.innerText='Copied';setTimeout(()=>this.innerText='Copy',1500)\">Copy</button></div></div>")

    a(f"<div class='card'><details><summary>All {s['name']} levels today</summary><table><tr><th>Price</th><th>Level</th>"
      "<th>Touch</th><th>Hold</th><th>n</th><th>Stack</th><th>Grade</th></tr>")
    for x in sorted(s["scored"], key=lambda z: -z["price"]):
        a(f"<tr><td class='m {x['side']}'>{num(x['price'], 2)}</td><td>{e(x['label'])}</td><td>{pct(x['touch'])}</td>"
          f"<td>{pct(x['hold'])}</td><td>{x['n']}</td><td>{x['stack']}</td><td><span class='g g{e(x['grade'])}'>{e(x['grade'])}</span></td></tr>")
    a("</table></details></div>")

    L = s["learned"]
    a(f"<div class='card'><details><summary>{s['name']} level stats (backtest, {L['n']} touches, last ~60 days)</summary>"
      f"<p class='sub'>Overall hold {pct(L['overall'])} · stack bonus +{L['stack_bonus']:.0%} per extra level · "
      f"risk-day penalty −{L['risk_penalty']:.0%}. Small n = shrunk toward the category average.</p><table>"
      "<tr><th>Type</th><th>n</th><th>Hold</th><th>Sweep</th><th>Bounce</th><th>Break run</th><th>1st touch</th><th>Retest</th>"
      "<th>NY AM</th><th>Risk day</th></tr>")
    for t, st in sorted(L["types"].items(), key=lambda kv: -kv[1]["n"]):
        am = st["sess"].get("NY AM", (float("nan"), 0))
        a(f"<tr><td>{e(TYPES.get(t, (t,))[0])}</td><td>{st['n']}</td><td>{pct(st['hold'])}</td><td>{pct(st['sweep'])}</td>"
          f"<td>{num(st['bounce'])}</td><td>{num(st['run'])}</td><td>{pct(st['first'])} <span class='muted'>({st['n_first']})</span></td>"
          f"<td>{pct(st['retest'])} <span class='muted'>({st['n_retest']})</span></td><td>{pct(am[0])} <span class='muted'>({am[1]})</span></td>"
          f"<td>{pct(st['risk_day'])} <span class='muted'>({st['n_risk']})</span></td></tr>")
    a("</table></details></div>")


def _shared(c, a):
    a("<div class='grid2'>")
    a("<div class='card'><p class='lab'>Headline risk (last 24h, keyword-tagged)</p>")
    for h in c["headlines"][:8]:
        link = f"<a href='{e(h['url'])}' target='_blank' rel='noopener'>{e(h['headline'])}</a>" if h.get("url") else e(h["headline"])
        a(f"<div class='row'><span><span class='sev {h['sev']}'>{h['sev']}</span>{link}"
          f"<span class='sub'> · {e(h['cat'])}{' · ' + e(', '.join(h['symbols'])) if h['symbols'] else ''}</span></span></div>")
    if not c["headlines"]:
        a("<p class='sub'>No index-moving headlines flagged.</p>")
    a("</div>")
    a("<div class='card'><p class='lab'>Scheduled events (next 7 days, 8:30 ET unless FOMC 2:00 ET)</p>")
    for d, n in c["events"]:
        a(f"<div class='row'><span>{e(n)}</span><span>{d:%a %b %d}</span></div>")
    if not c["events"]:
        a("<p class='sub'>Nothing major scheduled.</p>")
    a("<p class='lab' style='margin-top:12px'>Macro score inputs</p>")
    for name, sc, v in c["macro_parts"]:
        col = GREEN if sc > 0 else RED if sc < 0 else GREY
        a(f"<div class='row'><span>{e(name)}</span><span>{e(v)} <b style='color:{col}'>{sc:+d}</b></span></div>")
    a("</div></div>")


def page(c: dict) -> str:
    P = []
    a = P.append
    secs = c["sections"]
    names = [s["name"] for s in secs]
    a("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
      f"<meta http-equiv='refresh' content='300'><title>Swing levels</title><style>{CSS}</style></head><body><div class='wrap'>")
    tabs = "".join(f"<button class='tab' data-t='{n}' onclick=\"sw('{n}')\">{n}</button>" for n in names)
    a(f"<div class='top'><div style='display:flex;align-items:center;gap:12px'><span class='title'>Swing levels</span>"
      f"<span class='tabs'>{tabs}</span></div><span class='pill'>Updated {e(c['updated'])}</span></div>")
    for w in c.get("warnings", []):
        a(f"<div class='warn'>{e(w)}</div>")
    for s in secs:
        a(f"<div class='sec' data-s='{s['name']}'>")
        _top(c, s, a)
        a("</div>")
    _shared(c, a)
    for s in secs:
        a(f"<div class='sec' data-s='{s['name']}'>")
        _bottom(s, a)
        a("</div>")
    a("<p class='sub'>Data: yfinance (futures, ~15m delayed), Alpaca (ETFs, Benzinga headlines), FRED (yields, VIX, VXN, "
      "release dates), DataFirst (options, when connected). Not financial advice.</p></div>")
    a("<script>function sw(t){document.querySelectorAll('.sec').forEach(x=>x.classList.toggle('hide',x.dataset.s!==t));"
      "document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x.dataset.t===t));"
      "try{localStorage.setItem('lv_tab',t)}catch(e){}}"
      f"let t0='{names[0] if names else ''}';try{{const s=localStorage.getItem('lv_tab');"
      "if(s&&document.querySelector(`.tab[data-t='${s}']`))t0=s}catch(e){}sw(t0);</script></body></html>")
    return "".join(P)
