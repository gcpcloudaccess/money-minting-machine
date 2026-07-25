#!/usr/bin/env python3
"""Fetches real historical BTCINR candles from CoinDCX (paginated beyond its
1000-candles-per-request cap) and saves them to a CSV ready for
run_backtest.py. Run from the `backend/` directory:

    python scripts/fetch_backtest_data.py --interval 5m --days 90
    python scripts/fetch_backtest_data.py --interval 1h --days 365

This has to run somewhere with real internet access to CoinDCX - it will not
work from a network-sandboxed environment (see app/data/crypto_data.py's
module docstring: every function degrades to None on a failed request rather
than raising, so a network-blocked run just produces an empty/short CSV
instead of a traceback - check the row count this script prints before
trusting the output).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `import app...` works run from anywhere

import pandas as pd

from app.data import crypto_data

MS_PER_INTERVAL = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000, "8h": 28_800_000,
    "1d": 86_400_000, "3d": 259_200_000, "1w": 604_800_000,
}


def fetch_history(market: str, interval: str, days: int, pause_seconds: float = 0.3) -> pd.DataFrame:
    if interval not in MS_PER_INTERVAL:
        raise ValueError(f"Unknown interval {interval!r} - expected one of {sorted(MS_PER_INTERVAL)}")

    end_ms = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    start_target_ms = end_ms - days * 86_400_000
    chunk_span_ms = MS_PER_INTERVAL[interval] * 1000  # 1000 candles per request (CoinDCX's max)

    frames: list[pd.DataFrame] = []
    cursor_end = end_ms
    while cursor_end > start_target_ms:
        cursor_start = max(start_target_ms, cursor_end - chunk_span_ms)
        df = crypto_data.get_candles(market, interval=interval, limit=1000, start_time_ms=cursor_start, end_time_ms=cursor_end)
        if df is None or df.empty:
            print(f"  (no data for window ending {dt.datetime.fromtimestamp(cursor_end / 1000, tz=dt.timezone.utc)} - stopping)")
            break
        frames.append(df)
        print(f"  fetched {len(df)} candles, window {df.index.min()} .. {df.index.max()}")
        cursor_end = cursor_start - 1
        time.sleep(pause_seconds)  # be polite to CoinDCX's public endpoint

    if not frames:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    combined = pd.concat(frames)
    combined = combined[~combined.index.duplicated(keep="first")].sort_index()
    return combined


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", default="BTCINR")
    parser.add_argument("--interval", default="5m", choices=sorted(MS_PER_INTERVAL))
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--out", default=None, help="Output CSV path (default: data_cache/backtest_<market>_<interval>.csv)")
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else Path(__file__).resolve().parents[1] / "data_cache" / f"backtest_{args.market}_{args.interval}.csv"
    out_path.parent.mkdir(exist_ok=True)

    print(f"Fetching {args.days}d of {args.interval} candles for {args.market} from CoinDCX...")
    df = fetch_history(args.market, args.interval, args.days)

    if df.empty:
        print("Got zero rows back - CoinDCX unreachable, market not listed, or every request failed. Nothing written.")
        raise SystemExit(1)

    df.to_csv(out_path)
    print(f"Wrote {len(df)} rows ({df.index.min()} .. {df.index.max()}) to {out_path}")


if __name__ == "__main__":
    main()
