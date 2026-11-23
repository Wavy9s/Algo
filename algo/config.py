"""All settings in one place. Change numbers here, not in the code."""

# --- Instruments -------------------------------------------------------------
NQ = "NQ=F"            # yfinance continuous NQ
ES = "ES=F"            # yfinance continuous ES (for NQ/ES ratio)
ETFS = ["QQQ", "SPY", "SOXX"]   # Alpaca (stocks/ETFs)

# Mega-caps that move NQ — headlines on these count more
NQ_HEAVY = ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "NFLX", "COST"]

# --- Instruments on the page --------------------------------------------------
# bucket = profile bucket size in points, stack_min = tightest stack tolerance,
# poor_tol = how close two 30m highs/lows must be to call it a poor high/low,
# vol = FRED implied-vol series for the expected move, opt = DataFirst symbols (first that works)
INSTRUMENTS = {
    "NQ": {"yf": "NQ=F", "bucket": 5.0, "stack_min": 10.0, "poor_tol": 2.0, "vol": "VXNCLS", "opt": ("NDX", "QQQ")},
    "ES": {"yf": "ES=F", "bucket": 1.0, "stack_min": 2.5, "poor_tol": 0.5, "vol": "VIXCLS", "opt": ("SPX", "SPY")},
}

# --- Volume profile ----------------------------------------------------------
BUCKET = 5.0           # points per profile bucket (set per instrument by use())
POOR_TOL = 2.0
VALUE_AREA = 0.70      # 70% value area
HVN_MULT = 1.5         # HVN = node above 1.5x avg volume
LVN_MULT = 0.5         # LVN = valley below 0.5x avg volume
NAKED_LOOKBACK = 20    # trade days back to look for naked POCs
MAX_NAKED = 6

# --- Picks -------------------------------------------------------------------
N_SIDE = 2             # picks above + below
MIN_TOUCH = 0.15       # skip levels with <15% touch odds
MIN_DIST_SIGMA = 0.08  # skip levels sitting right on price (x daily sigma)
STACK_TOL_SIGMA = 0.04 # levels this close (x daily sigma) count as stacked
STACK_TOL_MIN = 10.0   # ...but never tighter than this (set per instrument by use())

# --- Outcome rules (x daily sigma) --------------------------------------------
HOLD_TARGET = 0.25     # bounce this far = held
BREAK_STOP = 0.12      # close this far through = broke
SWEEP_MIN = 0.03       # poke through by this much then hold = sweep
HORIZON_BARS = 36      # 5m bars (3h) to resolve a touch
MAX_TOUCHES = 3        # per level per day

# --- Stats -------------------------------------------------------------------
SHRINK_K = 15          # shrink small samples toward the category average
MIN_N_APLUS = 15       # A+ needs at least this many past touches
# A "hold" needs a 0.25σ bounce before a 0.12σ break, so pure chance is ~32%.
# Grades are set vs that baseline, not vs 50%.
APLUS_HOLD = 0.45
A_HOLD = 0.38

# --- Risk --------------------------------------------------------------------
# FRED release ids: CPI=10, Employment Situation (NFP)=50, GDP=53, PCE=54
FRED_RELEASES = {10: "CPI", 50: "Jobs report (NFP)", 53: "GDP", 54: "PCE"}

# FOMC statement days. UPDATE EACH YEAR from federalreserve.gov
FOMC_DATES = [
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]

# Gamma priors until the log has enough data to learn them
GAMMA_NEG_HOLD = -0.05
GAMMA_POS_HOLD = +0.03
GAMMA_NEG_EM = 1.15
AGAINST_MACRO_HOLD = -0.03

# --- Brief repo (page publishing) --------------------------------------------
PAGE_REPO = "Wavy9s/sentiment2343"
PAGE_DIR = "levels"


def use(name):
    """Switch the per-instrument settings above to `name` (NQ or ES)."""
    global BUCKET, STACK_TOL_MIN, POOR_TOL
    i = INSTRUMENTS[name]
    BUCKET, STACK_TOL_MIN, POOR_TOL = i["bucket"], i["stack_min"], i["poor_tol"]
