from __future__ import annotations

import csv
import math
import random
import urllib.parse
import urllib.request
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
                raise ValueError(f"Invalid numeric value in row: {raw}") from exc

    rows.sort(key=lambda bar: bar.date)
    if len(rows) < 80:
        raise ValueError("Need at least 80 price bars to train a useful model.")
    return rows


def load_stooq(symbol: str) -> list[PriceBar]:
    query = urllib.parse.urlencode({"s": symbol.lower(), "i": "d"})
    url = f"https://stooq.com/q/d/l/?{query}"
    with urllib.request.urlopen(url, timeout=20) as response:
        content = response.read().decode("utf-8")

    temp_path = Path(".stooq_download.csv")
    temp_path.write_text(content, encoding="utf-8")
    try:
        return load_csv(temp_path)
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass


def generate_demo_prices(days: int = 420, seed: int = 42) -> list[PriceBar]:
    rng = random.Random(seed)
    bars: list[PriceBar] = []
    current = 100.0
    start = date.today() - timedelta(days=days * 1.45)

    day_index = 0
    calendar_day = start
    while len(bars) < days:
        calendar_day += timedelta(days=1)
        if calendar_day.weekday() >= 5:
            continue

        cycle = math.sin(day_index / 27.0) * 0.003
        drift = 0.00045 + cycle
        shock = rng.gauss(0.0, 0.012)
        previous = current
        current = max(5.0, current * (1.0 + drift + shock))
        high = max(previous, current) * (1.0 + abs(rng.gauss(0.003, 0.004)))
        low = min(previous, current) * (1.0 - abs(rng.gauss(0.003, 0.004)))
        volume = 1_000_000 + rng.randint(-250_000, 350_000)
        bars.append(
            PriceBar(
                date=calendar_day.isoformat(),
                open=round(previous, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(current, 2),
                volume=float(volume),
            )
        )
        day_index += 1

    return bars
