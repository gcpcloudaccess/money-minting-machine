"""Intraday cost model for NSE (the only exchange this build trades).

Rates approximate a typical Zerodha-style Indian discount-broker charge
schedule - not an authoritative fee schedule, but realistic enough that net
profit after costs is a real, defensible number, not a stub.

Percentage-based rates are applied directly against price_inr * quantity
(the caller has already converted the local-currency price to INR-equivalent
- see app/data/fx.py; for NSE that conversion is always a 1.0 no-op since the
exchange's currency is already INR). Flat local-currency fees (NSE's Rs 20
brokerage cap) are converted to INR via fx_rate_to_inr at call time, which is
always 1.0 here for the same reason.
"""

from __future__ import annotations

# Rates are percentages of turnover (currency-agnostic) plus a flat component
# expressed in the exchange's own local currency (INR, for NSE).
COST_PROFILES = {
    "NSE": {  # Zerodha-style Indian discount broker
        "brokerage_rate": 0.0003, "brokerage_cap_local": 20.0,
        "stt_sell_rate": 0.00025, "exchange_txn_rate": 0.0000297,
        "sebi_rate": 0.0000001, "stamp_duty_buy_rate": 0.00003, "gst_rate": 0.18,
    },
}


def compute_costs(action: str, quantity: float, price_inr: float, exchange: str = "NSE", fx_rate_to_inr: float = 1.0) -> dict:
    profile = COST_PROFILES.get(exchange, COST_PROFILES["NSE"])
    turnover = quantity * price_inr

    brokerage = turnover * profile["brokerage_rate"]
    if profile.get("brokerage_cap_local") is not None:
        brokerage = min(brokerage, profile["brokerage_cap_local"] * fx_rate_to_inr)
    brokerage += profile.get("brokerage_flat_local", 0.0) * fx_rate_to_inr

    stt = turnover * profile["stt_sell_rate"] if action == "SELL" else 0.0
    exchange_charges = turnover * profile["exchange_txn_rate"]
    sebi_charges = turnover * profile["sebi_rate"]
    stamp_duty = turnover * profile["stamp_duty_buy_rate"] if action == "BUY" else 0.0
    gst = profile["gst_rate"] * (brokerage + exchange_charges + sebi_charges)

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
