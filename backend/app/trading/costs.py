"""Realistic Indian discount-broker intraday equity cost model.

Rates approximate a typical discount broker (e.g. Zerodha-style) intraday
equity delivery-vs-intraday charge schedule. Used so "net profit after all
trading costs" is a real, defensible number rather than a stub.
"""

from __future__ import annotations

BROKERAGE_RATE = 0.0003  # 0.03%
BROKERAGE_CAP = 20.0  # flat Rs 20 cap per executed order
STT_SELL_RATE = 0.00025  # 0.025% on sell-side turnover, intraday equity
EXCHANGE_TXN_RATE = 0.0000297  # NSE exchange transaction charge
SEBI_CHARGE_RATE = 0.0000001  # Rs 10 per crore
STAMP_DUTY_BUY_RATE = 0.00003  # 0.003%, buy-side only
GST_RATE = 0.18


def compute_costs(action: str, quantity: float, price: float) -> dict:
    turnover = quantity * price

    brokerage = min(turnover * BROKERAGE_RATE, BROKERAGE_CAP)
    stt = turnover * STT_SELL_RATE if action == "SELL" else 0.0
    exchange_charges = turnover * EXCHANGE_TXN_RATE
    sebi_charges = turnover * SEBI_CHARGE_RATE
    stamp_duty = turnover * STAMP_DUTY_BUY_RATE if action == "BUY" else 0.0
    gst = GST_RATE * (brokerage + exchange_charges + sebi_charges)

    total = brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst

    return {
        "turnover": round(turnover, 2),
        "brokerage": round(brokerage, 2),
        "stt": round(stt, 2),
        "exchange_charges": round(exchange_charges, 4),
        "sebi_charges": round(sebi_charges, 4),
        "stamp_duty": round(stamp_duty, 2),
        "gst": round(gst, 2),
        "total": round(total, 2),
    }
