"""Intraday equity cost models, one per supported exchange (NSE/SGX/LSE/NYSE).

Rates approximate a typical discount-broker charge schedule for each market
- not authoritative fee schedules, same spirit as the original NSE-only model
("realistic enough that net profit after costs is a real, defensible number,
not a stub"). All 7 output fields are kept across every exchange for a stable
schema even though what each field represents shifts per market (e.g. NYSE's
near-zero commission has nothing in "stamp_duty", LSE's does).

Percentage-based rates are applied directly against price_inr * quantity
(the caller has already converted the local-currency price to INR-equivalent
- see app/data/fx.py), since a percentage of turnover is currency-agnostic.
Flat local-currency fees (e.g. NSE's Rs 20 brokerage cap, LSE's flat GBP
commission) are converted to INR via fx_rate_to_inr at call time.
"""

from __future__ import annotations

# Each profile's rates are percentages of turnover (currency-agnostic) plus
# any flat component expressed in the EXCHANGE's own local currency.
COST_PROFILES = {
    "NSE": {  # Zerodha-style Indian discount broker
        "brokerage_rate": 0.0003, "brokerage_cap_local": 20.0,
        "stt_sell_rate": 0.00025, "exchange_txn_rate": 0.0000297,
        "sebi_rate": 0.0000001, "stamp_duty_buy_rate": 0.00003, "gst_rate": 0.18,
    },
    "SGX": {  # SGX clearing + trading fee, Singapore GST on the fees (not turnover)
        "brokerage_rate": 0.0, "brokerage_cap_local": None,
        "stt_sell_rate": 0.0, "exchange_txn_rate": 0.0004,
        "sebi_rate": 0.0, "stamp_duty_buy_rate": 0.0, "gst_rate": 0.09,
    },
    "LSE": {  # flat commission + UK Stamp Duty Reserve Tax (buy-side only)
        "brokerage_rate": 0.0, "brokerage_cap_local": None, "brokerage_flat_local": 3.0,
        "stt_sell_rate": 0.0, "exchange_txn_rate": 0.0,
        "sebi_rate": 0.0, "stamp_duty_buy_rate": 0.005, "gst_rate": 0.0,
    },
    "NYSE": {  # commission-free like modern US brokers, tiny SEC/FINRA sell-side fees
        "brokerage_rate": 0.0, "brokerage_cap_local": None,
        "stt_sell_rate": 0.0000278, "exchange_txn_rate": 0.0,
        "sebi_rate": 0.0, "stamp_duty_buy_rate": 0.0, "gst_rate": 0.0,
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
