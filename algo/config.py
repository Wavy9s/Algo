"""All settings in one place. Change numbers here, not in the code."""

# --- Instruments -------------------------------------------------------------
NQ = "NQ=F"            # yfinance continuous NQ
ES = "ES=F"            # yfinance continuous ES (for NQ/ES ratio)
ETFS = ["QQQ", "SPY", "SOXX"]   # Alpaca (stocks/ETFs)

# Mega-caps that move NQ — headlines on these count more
NQ_HEAVY = ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "NFLX", "COST"]

# --- Volume profile ----------------------------------------------------------
BUCKET = 5.0           # NQ points per profile bucket
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
STACK_TOL_MIN = 10.0   # ...but never tighter than 10 pts

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
