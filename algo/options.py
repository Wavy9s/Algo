"""DataFirst options adapter (GEX, gamma environment, DEX, 0DTE/7DTE walls).

NOT WIRED YET: the endpoint paths and field names below are placeholders until
we have DataFirst's docs. Everything else in the algo already accepts the
normalized output of fetch(), so wiring = filling in _pull() only.

Normalized output:
{
  "underlying": "NDX" | "QQQ",
  "spot": float,                       # underlying price at fetch time
  "gamma_env": "positive" | "negative",
  "gamma_flip": float,                 # underlying price
  "net_dex": float,                    # + dealers long delta, - short
  "walls": [{"kind": "call"|"put"|"dex", "dte": "0DTE"|"7DTE", "strike": float}, ...]
}
"""
import os


def _pull(key: str, base: str):
    # TODO(datafirst): replace with real endpoints + field mapping from the docs.
    return None


def fetch():
    key = os.getenv("DATAFIRST_API_KEY")
    base = os.getenv("DATAFIRST_BASE_URL")
    if not key or not base:
        return None
    try:
        return _pull(key, base)
    except Exception as e:
        print(f"[datafirst] {e}")
        return None


def to_levels(opt: dict, nq_price: float) -> list:
    """Convert underlying strikes to NQ prices with today's NQ/underlying ratio."""
    if not opt or not opt.get("spot"):
        return []
    r = nq_price / opt["spot"]
    out = []
    if opt.get("gamma_flip"):
        out.append({"type": "GAMMA_FLIP", "price": opt["gamma_flip"] * r})
    kinds = {"call": "GEX_CALL", "put": "GEX_PUT", "dex": "DEX_WALL"}
    for w in opt.get("walls", []):
        t = kinds.get(w.get("kind"))
        if t and w.get("strike"):
            out.append({"type": t, "price": w["strike"] * r, "sfx": f" {w.get('dte', '')}".rstrip()})
    return out
