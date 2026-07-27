"""Delivery/positional cost model, per exchange.

NSE rates approximate Zerodha's published DELIVERY equity charge schedule
(zerodha.com/charges) - not an authoritative fee schedule, but realistic
enough that net profit after costs is a real, defensible number, not a stub.
Delivery rates specifically (not intraday) because positions are now held
across days/weeks (see app/orchestration/session_runner.py's positional-mode
docstring), and Indian equity delivery has a genuinely different, higher cost
structure than intraday - zero brokerage but STT on BOTH buy and sell sides
at 0.1% each (vs intraday's 0.025% sell-side-only), 5x the stamp duty
(0.015% vs 0.003%, still buy-side only), and a flat per-scrip DP
(Depository Participant) charge on the sell side that intraday trades never
incur at all (nothing ever actually enters a demat holding intraday).

CRYPTO_INDIA rates approximate CoinDCX's published retail spot fee schedule
(0.2% maker/taker) plus two India-wide charges that apply to every domestic
crypto trade regardless of exchange: 18% GST on the trading fee itself, and
1% TDS on the SELL-side trade value under Income Tax Act Section 194S
(effective since July 2022, deducted at source by the exchange on every
transfer of a virtual digital asset) - a real, material cost that a "should I
hold intraday or positionally" decision for crypto needs to account for, not
a securities-market charge that happens to not apply here.

Percentage-based rates are applied directly against price_inr * quantity
(the caller has already converted the local-currency price to INR-equivalent
- see app/data/fx.py; always a 1.0 no-op for both exchanges here since both
are already INR-denominated). Flat local-currency fees (NSE's Rs 20
brokerage cap) are converted to INR via fx_rate_to_inr at call time.
"""

from __future__ import annotations

# Rates are percentages of turnover (currency-agnostic) plus a flat component
# expressed in the exchange's own local currency (INR, for both exchanges here).
COST_PROFILES = {
    "NSE": {  # Zerodha delivery equity charge schedule (zero-brokerage delivery, not intraday/F&O)
        "brokerage_rate": 0.0, "brokerage_cap_local": None,
        "stt_buy_rate": 0.001, "stt_sell_rate": 0.001,  # 0.1% BOTH sides for delivery (intraday: sell-side only, 0.025%)
        "exchange_txn_rate": 0.0000297,
        "sebi_rate": 0.0000001, "stamp_duty_buy_rate": 0.00015,  # delivery: 0.015% (intraday: 0.003%)
        "dp_charge_flat_local": 15.34,  # DP charge, sell-side only - only charged when selling out of a demat holding
        "gst_rate": 0.18,
    },
    "CRYPTO_INDIA": {  # CoinDCX retail spot fee schedule + India-wide GST/TDS
        "trading_fee_rate": 0.002,  # 0.2% maker/taker, retail (non-VIP) tier
        "gst_rate": 0.18,           # GST on the trading fee, not on turnover
        "tds_rate": 0.01,           # Section 194S TDS on SELL-side turnover only
    },
}


def _compute_crypto_costs(action: str, turnover: float, profile: dict) -> dict:
    trading_fee = turnover * profile["trading_fee_rate"]
    gst = trading_fee * profile["gst_rate"]
    tds = turnover * profile["tds_rate"] if action == "SELL" else 0.0
    total = trading_fee + gst + tds
    return {
        "turnover": round(turnover, 2),
        "trading_fee": round(trading_fee, 2),
        "gst": round(gst, 2),
        "tds": round(tds, 2),
        "total": round(total, 2),
    }


def _compute_nse_costs(action: str, turnover: float, profile: dict, fx_rate_to_inr: float) -> dict:
    brokerage = turnover * profile["brokerage_rate"]
    if profile.get("brokerage_cap_local") is not None:
        brokerage = min(brokerage, profile["brokerage_cap_local"] * fx_rate_to_inr)
    brokerage += profile.get("brokerage_flat_local", 0.0) * fx_rate_to_inr

    # Delivery STT applies on both sides (unlike intraday's sell-only) - see module docstring.
    stt_rate = profile["stt_buy_rate"] if action == "BUY" else profile["stt_sell_rate"]
    stt = turnover * stt_rate
    exchange_charges = turnover * profile["exchange_txn_rate"]
    sebi_charges = turnover * profile["sebi_rate"]
    stamp_duty = turnover * profile["stamp_duty_buy_rate"] if action == "BUY" else 0.0
    # DP charge: flat per-scrip fee only incurred when selling shares that actually sat in a
    # demat holding (i.e. delivery, never intraday) - not turnover-based, so applied post-GST.
    dp_charge = profile.get("dp_charge_flat_local", 0.0) * fx_rate_to_inr if action == "SELL" else 0.0
    gst = profile["gst_rate"] * (brokerage + exchange_charges + sebi_charges)

    total = brokerage + stt + exchange_charges + sebi_charges + stamp_duty + dp_charge + gst

    return {
        "turnover": round(turnover, 2),
        "brokerage": round(brokerage, 2),
        "stt": round(stt, 2),
        "exchange_charges": round(exchange_charges, 4),
        "sebi_charges": round(sebi_charges, 4),
        "stamp_duty": round(stamp_duty, 2),
        "dp_charge": round(dp_charge, 2),
        "gst": round(gst, 2),
        "total": round(total, 2),
    }


def compute_costs(action: str, quantity: float, price_inr: float, exchange: str = "NSE", fx_rate_to_inr: float = 1.0) -> dict:
    profile = COST_PROFILES.get(exchange, COST_PROFILES["NSE"])
    turnover = quantity * price_inr

    if exchange == "CRYPTO_INDIA":
        return _compute_crypto_costs(action, turnover, profile)
    return _compute_nse_costs(action, turnover, profile, fx_rate_to_inr)
