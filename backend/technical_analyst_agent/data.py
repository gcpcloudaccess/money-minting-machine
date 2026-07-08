from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


@dataclass(frozen=True)
class PriceBar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def load_csv(path: str | Path) -> list[PriceBar]:
    rows: list[PriceBar] = []
    with Path(path).open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row.")
        normalized = {name.lower().strip(): name for name in reader.fieldnames}
        required = ["date", "open", "high", "low", "close", "volume"]
        missing = [name for name in required if name not in normalized]
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")

        for raw in reader:
            try:
                rows.append(
                    PriceBar(
                        date=str(raw[normalized["date"]]).strip(),
                        open=float(raw[normalized["open"]]),
                        high=float(raw[normalized["high"]]),
                        low=float(raw[normalized["low"]]),
                        close=float(raw[normalized["close"]]),
                        volume=float(raw[normalized["volume"]]),
                    )
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid OHLCV row: {raw}") from exc

    rows.sort(key=lambda bar: bar.date)
    if len(rows) < 80:
        raise ValueError("Need at least 80 price bars for reliable technical analysis.")
    return rows


def generate_demo_prices(days: int = 260, seed: int = 17) -> list[PriceBar]:
    rng = random.Random(seed)
    bars: list[PriceBar] = []
    current = 100.0
    calendar_day = date.today() - timedelta(days=days * 1.45)

    while len(bars) < days:
        calendar_day += timedelta(days=1)
        if calendar_day.weekday() >= 5:
            continue

        index = len(bars)
        trend = 0.00055
        cycle = math.sin(index / 21.0) * 0.0028
        shock = rng.gauss(0.0, 0.010)
        previous = current
        current = max(2.0, current * (1.0 + trend + cycle + shock))
        intraday_width = abs(rng.gauss(0.006, 0.004))
        high = max(previous, current) * (1.0 + intraday_width)
        low = min(previous, current) * (1.0 - intraday_width)
        volume_cycle = 1.0 + max(0.0, math.sin(index / 13.0)) * 0.35
        volume = (1_100_000 + rng.randint(-250_000, 450_000)) * volume_cycle

        bars.append(
            PriceBar(
                date=calendar_day.isoformat(),
                open=round(previous, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(current, 2),
                volume=round(volume, 0),
            )
        )

    return bars
