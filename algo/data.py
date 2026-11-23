"""Data pulls: yfinance (futures), Alpaca (ETFs + news), FRED (macro + release dates)."""
import os
import time
import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

NY = ZoneInfo("America/New_York")
FRED_URL = "https://api.stlouisfed.org/fred"
ALPACA_DATA = "https://data.alpaca.markets"


# ---------------------------------------------------------------- helpers
def trade_date(ts: pd.Timestamp) -> dt.date:
    """CME day runs 18:00 ET -> 17:00 ET. Bars after 18:00 belong to the next day."""
    return (ts + pd.Timedelta(hours=6)).date()


def session_of(ts: pd.Timestamp) -> str:
    h = ts.hour + ts.minute / 60
    if h >= 18 or h < 2:
        return "Asia"
    if h < 9.5:
        return "London"
    if h < 12:
        return "NY AM"
    return "NY PM"


def tag(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["tdate"] = [trade_date(t) for t in df.index]
    df["sess"] = [session_of(t) for t in df.index]
    hm = df.index.hour * 60 + df.index.minute
    df["rth"] = (hm >= 570) & (hm < 960)
    return df


# ---------------------------------------------------------------- yfinance
def yf_bars(ticker: str, period: str, interval: str, tries: int = 3) -> pd.DataFrame:
    import yfinance as yf
    for i in range(tries):
        try:
            df = yf.Ticker(ticker).history(period=period, interval=interval,
                                           auto_adjust=False, prepost=True)
            if df is not None and len(df):
                df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
                df.columns = ["open", "high", "low", "close", "volume"]
                idx = df.index
                df.index = idx.tz_convert(NY) if idx.tz is not None else idx.tz_localize(NY)
                df = df[(df.high > 0) & (df.low > 0)].dropna()
                return df
        except Exception as e:  # rate limits happen on shared runners
            print(f"[yf] {ticker} {interval} try {i+1}: {e}")
        time.sleep(5 * (i + 1))
    return pd.DataFrame()


def expiries(years):
    """Third Friday of Mar/Jun/Sep/Dec = equity index futures expiry."""
    out = []
    for y in years:
        for m in (3, 6, 9, 12):
            d = dt.date(y, m, 15)
            out.append(d + dt.timedelta(days=(4 - d.weekday()) % 7))
    return out


def find_roll(m5: pd.DataFrame):
    """yfinance's NQ=F jumps to the next contract near expiry. Find that jump:
    the biggest session-open gap inside each roll window (8 days before expiry -> expiry)."""
    if m5.empty:
        return []
    rolls = []
    days = sorted(m5.tdate.unique())
    first = m5.groupby("tdate").open.first()
    last = m5.groupby("tdate").close.last()
    for ex in expiries({days[0].year, days[-1].year}):
        win = [d for d in days[1:] if ex - dt.timedelta(days=8) <= d <= ex + dt.timedelta(days=1)]
        if not win:
            continue
        gaps = {d: first[d] - last[days[days.index(d) - 1]] for d in win}
        d, g = max(gaps.items(), key=lambda kv: abs(kv[1]))
        if 0.002 <= abs(g) / last[d] <= 0.02:
            rolls.append((d, float(g)))
    return rolls


def back_adjust(df, rolls, intraday=True):
    """Shift bars before each roll by the gap so profiles/levels don't mix two contracts."""
    if df.empty:
        return df
    df = df.copy()
    keys = df.tdate if intraday else pd.Series(df.index.date, index=df.index)
    for d, g in rolls:
        mask = (keys < d).values
        for c in ("open", "high", "low", "close"):
            df.loc[mask, c] += g
    return df


def futures():
    """1m (7d), 5m (60d), 1d (2y) for NQ; daily ES for the ratio. Back-adjusted for rolls."""
    m1 = tag(yf_bars("NQ=F", "7d", "1m"))
    m5 = tag(yf_bars("NQ=F", "60d", "5m"))
    d1 = yf_bars("NQ=F", "2y", "1d")
    rolls = find_roll(m5)
    return {
        "m1": back_adjust(m1, rolls), "m5": back_adjust(m5, rolls),
        "d1": back_adjust(d1, rolls, intraday=False),
        "es_d1": yf_bars("ES=F", "6mo", "1d"), "rolls": rolls,
    }


# ---------------------------------------------------------------- Alpaca
def _alpaca_headers():
    k, s = os.getenv("ALPACA_KEY_ID"), os.getenv("ALPACA_SECRET")
    if not k or not s:
        return None
    return {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s}


def alpaca_daily(symbols, days=60) -> dict:
    h = _alpaca_headers()
    if not h:
        return {}
    start = (dt.datetime.utcnow() - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    out = {}
    try:
        r = requests.get(f"{ALPACA_DATA}/v2/stocks/bars", headers=h, timeout=20, params={
            "symbols": ",".join(symbols), "timeframe": "1Day", "start": start,
            "feed": "iex", "limit": 10000, "adjustment": "all"})
        r.raise_for_status()
        for sym, rows in (r.json().get("bars") or {}).items():
            df = pd.DataFrame(rows)
            if df.empty:
                continue
            df["t"] = pd.to_datetime(df["t"])
            out[sym] = df.set_index("t")["c"].astype(float)
    except Exception as e:
        print(f"[alpaca bars] {e}")
    return out


def alpaca_news(hours=24, symbols=None, max_items=300) -> list:
    h = _alpaca_headers()
    if not h:
        return []
    start = (dt.datetime.utcnow() - dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    items, token = [], None
    params = {"start": start, "limit": 50, "sort": "desc", "include_content": "false"}
    if symbols:
        params["symbols"] = ",".join(symbols)
    try:
        while len(items) < max_items:
            if token:
                params["page_token"] = token
            r = requests.get(f"{ALPACA_DATA}/v1beta1/news", headers=h, params=params, timeout=20)
            r.raise_for_status()
            js = r.json()
            items += js.get("news", [])
            token = js.get("next_page_token")
            if not token:
                break
    except Exception as e:
        print(f"[alpaca news] {e}")
    return items


# ---------------------------------------------------------------- FRED
def fred_series(series_id: str, days=400) -> pd.Series:
    key = os.getenv("FRED_API_KEY")
    if not key:
        return pd.Series(dtype=float)
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    try:
        r = requests.get(f"{FRED_URL}/series/observations", timeout=20, params={
            "series_id": series_id, "api_key": key, "file_type": "json",
            "observation_start": start})
        r.raise_for_status()
        obs = r.json().get("observations", [])
        s = pd.Series({pd.Timestamp(o["date"]).date(): (np.nan if o["value"] == "." else float(o["value"]))
                       for o in obs})
        return s.dropna()
    except Exception as e:
        print(f"[fred {series_id}] {e}")
        return pd.Series(dtype=float)


def fred_release_dates(release_id: int, days_back=120, days_fwd=45) -> list:
    key = os.getenv("FRED_API_KEY")
    if not key:
        return []
    start = (dt.date.today() - dt.timedelta(days=days_back)).isoformat()
    try:
        r = requests.get(f"{FRED_URL}/release/dates", timeout=20, params={
            "release_id": release_id, "api_key": key, "file_type": "json",
            "realtime_start": start, "include_release_dates_with_no_data": "true",
            "sort_order": "asc", "limit": 1000})
        r.raise_for_status()
        end = dt.date.today() + dt.timedelta(days=days_fwd)
        ds = [dt.date.fromisoformat(x["date"]) for x in r.json().get("release_dates", [])]
        return sorted({d for d in ds if d <= end})
    except Exception as e:
        print(f"[fred release {release_id}] {e}")
        return []
