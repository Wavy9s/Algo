# Algo — NQ swing levels

Picks the best NQ swing levels each day from volume profile, VWAPs, ranges, AMT structure and OTE. It learns hold % from the last ~60 days and adjusts for macro and headline/event risk. It runs on GitHub Actions every 30 min during the session.

## Files
- `run.py`: runs everything once
- `algo/config.py`: all settings (bucket size, grades, FOMC dates and so on)
- `algo/data.py`: yfinance (NQ), Alpaca (ETFs + headlines), FRED (macro + release dates), contract-roll fix
- `algo/profile.py`: POC/VAH/VAL/HVN/LVN, naked POCs, poor highs/lows, single prints
- `algo/vwap.py`: session/daily/weekly/monthly VWAP + bands
- `algo/levels.py`: collects every level as of the day's start
- `algo/stats.py`: volatility, touch odds, backtest, hold % per type and situation
- `algo/risk.py`: headline keyword tagging, events, macro score
- `algo/options.py`: DataFirst slot (not wired until we have their docs)
- `algo/pick.py`: stacking, adjustments, EV, grades, picks
- `algo/logbook.py`: locks picks, tracks them live, scores them the next day
- `algo/render.py`: the light blue page
- `state/`: picks log + results (committed by the bot)
- `site/`: the generated page

## Secrets (Settings → Secrets and variables → Actions)
- `ALPACA_KEY_ID`, `ALPACA_SECRET`, `FRED_API_KEY`: required
- `PAGES_TOKEN`: publishes the page to `sentiment2343/levels/`
- `DATAFIRST_API_KEY`: used once the options adapter is wired

## Grades
A "hold" means a 0.25σ bounce happens before a 0.12σ break. Pure chance gives about 32%, so A = 38%+ and A+ = 45%+ with 15+ samples and 2+ stacked levels.

## Yearly chore
Add next year's FOMC dates in `algo/config.py`. The page warns you when they run out.
