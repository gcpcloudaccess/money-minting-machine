"""Session Runner: the market-hours (or replay) tick loop.

Ticks every currently-eligible exchange independently, each with its own
persistent active Portfolio (see app/trading/execution_engine.py's
get_active_portfolio, which is now exchange-scoped) and its own lifecycle:

- NSE: eligible only during its own session hours in live mode (or always in
  replay mode, governed by its own cached replay data running out) - unchanged
  from before this module supported more than one exchange.
- CRYPTO_INDIA: ALWAYS eligible, live or replay, weekday or weekend, NSE open
  or closed - the whole point of adding it (see app/data/exchanges.py). Its
  session never force-closes on its own; it just keeps compounding
  indefinitely, same as a real always-open market. In replay mode its replay
  cursor wraps around instead of exhausting (see market_data.py's advance()).

There is no longer a single global "the active session" that rolls over
between exchanges - each exchange keeps its own portfolio the whole time,
which is what actually lets crypto trade continuously while NSE separately
opens, closes, and reports each trading day."""

from __future__ import annotations

import datetime as dt
import logging

from app.agents.planner import InvestmentPlanner
from app.config import get_settings
from app.data import exchanges
from app.data.exchanges import Exchange
from app.data.market_data import MarketDataProvider
from app.db.models import Position, utcnow
from app.db.session import SessionLocal
from app.orchestration import supervisor
from app.reporting import audit_log, pdf_export
from app.trading import execution_engine

logger = logging.getLogger("session_runner")


class SessionRunner:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.provider = MarketDataProvider(self.settings.data_mode)
        # One InvestmentPlanner per exchange, not shared - each tracks its own
        # rotation cursor over its own watchlist (see agents/planner.py); a
        # single shared planner would scramble NSE's 3-symbol rotation against
        # crypto's 1-symbol watchlist every tick.
        self._planners: dict[str, InvestmentPlanner] = {}

    def _planner_for(self, exchange: Exchange) -> InvestmentPlanner:
        if exchange.code not in self._planners:
            self._planners[exchange.code] = InvestmentPlanner(max_symbols_per_tick=self.settings.max_symbols_per_tick)
        return self._planners[exchange.code]

    def _eligible_exchanges(self, now: dt.datetime | None = None) -> list[Exchange]:
        """`now` is injectable purely for deterministic testing (see
        tests/test_session_runner.py) - production calls always use the real
        clock via the default None."""
        eligible: list[Exchange] = []
        if self.settings.data_mode == "live":
            if exchanges.NSE.is_open(now):
                eligible.append(exchanges.NSE)
        else:
            eligible.append(exchanges.get_exchange(self.settings.replay_exchange))

        # Crypto is always additionally eligible, regardless of mode or NSE's
        # state - dedup guards the (unusual) case where replay_exchange is
        # itself configured to CRYPTO_INDIA.
        if exchanges.CRYPTO_INDIA not in eligible:
            eligible.append(exchanges.CRYPTO_INDIA)
        return eligible

    def run_tick(self) -> None:
        db = SessionLocal()
        try:
            for exchange in self._eligible_exchanges():
                try:
                    self._tick_exchange(db, exchange)
                except Exception:
                    logger.exception("Tick failed for exchange %s", exchange.code)
                    audit_log.log_event(db, "tick_error", {"exchange": exchange.code, "error": "tick_exchange raised - see backend logs"})
        finally:
            db.close()

    def _tick_exchange(self, db, exchange: Exchange) -> None:
        portfolio = execution_engine.get_active_portfolio(db, exchange=exchange.code)
        if portfolio.status != "active":
            return

        watchlist = list(exchange.watchlist)
        open_symbols = [p.symbol for p in db.query(Position).filter_by(portfolio_id=portfolio.id, status="open").all()]
        symbols = self._planner_for(exchange).plan_tick(watchlist, open_symbols)

        for sym in symbols:
            try:
                supervisor.run_committee_for_symbol(db, self.provider, sym, watchlist, execute=True, exchange=exchange)
            except Exception as exc:
                logger.exception("Committee run failed for %s (%s)", sym, exchange.code)
                audit_log.log_event(db, "tick_error", {"symbol": sym, "exchange": exchange.code, "error": str(exc)})

        self.provider.advance_all(watchlist)

        if self._session_should_end(exchange, watchlist):
            self._close_session(db, portfolio, watchlist)

    def _session_should_end(self, exchange: Exchange, watchlist: list[str]) -> bool:
        if exchange.code == "CRYPTO_INDIA":
            return False  # 24/7 - never auto-closes, see class docstring
        if self.settings.data_mode == "live":
            return exchange.minutes_to_close() <= self.settings.tick_minutes
        return all(self.provider.is_session_exhausted(s) for s in watchlist)

    def close_now(self, exchange: str = "NSE") -> None:
        """Force-close the given exchange's active session immediately
        (manual override, e.g. from the API). Defaults to NSE, matching the
        pre-multi-exchange behavior of every existing caller."""
        db = SessionLocal()
        try:
            portfolio = execution_engine.get_active_portfolio(db, exchange=exchange)
            if portfolio.status == "active":
                watchlist = list(exchanges.get_exchange(portfolio.exchange).watchlist)
                self._close_session(db, portfolio, watchlist)
        finally:
            db.close()

    def _close_session(self, db, portfolio, watchlist: list[str]) -> None:
        # Both exchanges are already INR-native - get_latest_price() needs no conversion either way.
        price_lookup = {}
        for s in watchlist:
            try:
                price_lookup[s] = self.provider.get_latest_price(s)
            except Exception:
                continue

        execution_engine.force_close_all(db, portfolio, price_lookup)
        portfolio.status = "closed"
        portfolio.session_end = utcnow()
        db.add(portfolio)
        db.commit()

        report_path = pdf_export.generate_session_report(db, portfolio)
        audit_log.log_event(db, "session_closed", {"portfolio_id": portfolio.id, "exchange": portfolio.exchange, "report_path": report_path})
        logger.info("Session closed (%s). Report at %s", portfolio.exchange, report_path)
