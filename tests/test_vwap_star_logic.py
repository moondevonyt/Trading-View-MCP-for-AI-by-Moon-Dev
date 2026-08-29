"""
🌙 Moon Dev's signal check for the VWAP Triangle + Volume Star script.

Reimplements the EXACT Pine logic in pandas and runs it over real 5m bars, so
we know how often each mark fires before we ever look at a chart. Real data
only — no synthetic bars.

    triangle -> ta.crossover / ta.crossunder of close vs session VWAP
    star     -> volume >= volume[1] * mult

Run:
    python tests/test_vwap_star_logic.py [csv ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
DEFAULT_FILES = [
    REPO / "data/hyperliquid_midcap_5m/SPX_5m_hl.csv",
    REPO / "data/hyperliquid_midcap_5m/FARTCOIN_5m_hl.csv",
    REPO / "data/ASTER_5m_20250926_125300_historical.csv",
]
VOL_MULT = 3.0


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """ta.vwap(hlc3) — cumulative, reset at each new session (calendar day). 🌙"""
    hlc3 = (df["High"] + df["Low"] + df["Close"]) / 3.0
    day = df["Datetime"].dt.date
    pv = (hlc3 * df["Volume"]).groupby(day).cumsum()
    vv = df["Volume"].groupby(day).cumsum()
    return pv / vv


def run(path: Path) -> dict:
    df = pd.read_csv(path)
    # Files across this repo disagree on casing (Open/open, Volume/volume). 🌙
    df.columns = [c.strip().capitalize() for c in df.columns]
    tcol = "Datetime" if "Datetime" in df.columns else df.columns[0]
    df["Datetime"] = pd.to_datetime(df[tcol])
    df = df.sort_values("Datetime").reset_index(drop=True)

    vwap = session_vwap(df)
    above = df["Close"] > vwap
    # ta.crossover: was at/below on the prior bar, above now.
    cross_up = above & ~above.shift(1).fillna(above.iloc[0])
    cross_dn = ~above & above.shift(1).fillna(above.iloc[0])

    prev_vol = df["Volume"].shift(1)
    star = (df["Volume"] >= prev_vol * VOL_MULT) & (prev_vol > 0)

    bars = len(df)
    return {
        "file": path.name,
        "bars": bars,
        "span": f"{df['Datetime'].iloc[0]:%Y-%m-%d} to {df['Datetime'].iloc[-1]:%Y-%m-%d}",
        "tri_up": int(cross_up.sum()),
        "tri_dn": int(cross_dn.sum()),
        "stars": int(star.sum()),
        "star_pct": 100.0 * star.sum() / bars,
        "biggest_star": float((df["Volume"] / prev_vol)[star].max()) if star.any() else 0.0,
        "both_same_bar": int((star & (cross_up | cross_dn)).sum()),
    }


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv[1:]] or DEFAULT_FILES
    # 🌙 DEFAULT_FILES live in Moon Dev's trading-bots repo. When this MCP is
    # split out on its own, that data is not there — skip instead of failing,
    # and let anyone point it at their own OHLCV CSVs.
    if not argv[1:] and not any(f.exists() for f in files):
        print("🌙 Moon Dev: no OHLCV data found (this test reads CSVs from the "
              "trading-bots repo). Pass your own files:\n"
              "    python tests/test_vwap_star_logic.py path/to/ohlcv.csv ...\n"
              "Columns needed: datetime, Open, High, Low, Close, Volume")
        return 0
    print(f"🌙 Moon Dev VWAP+Star signal check — volume spike = {VOL_MULT}x the LAST bar\n")
    hdr = f"{'file':<34}{'bars':>6}{'▲':>6}{'▼':>6}{'★':>7}{'★ %':>8}{'max x':>9}{'both':>6}"
    print(hdr)
    print("-" * len(hdr))
    rows = []
    for f in files:
        if not f.exists():
            print(f"{f.name:<34}  MISSING")
            continue
        r = run(f)
        rows.append(r)
        print(f"{r['file']:<34}{r['bars']:>6}{r['tri_up']:>6}{r['tri_dn']:>6}"
              f"{r['stars']:>7}{r['star_pct']:>7.1f}%{r['biggest_star']:>9.1f}{r['both_same_bar']:>6}")

    print()
    for r in rows:
        print(f"  {r['file']}: {r['span']}")

    ok = bool(rows) and all(r["tri_up"] > 0 and r["tri_dn"] > 0 and r["stars"] > 0 for r in rows)
    print(f"\n🌙 every mark fires on every file: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
