"""Session Runner: the market-hours (or replay) tick loop. Each tick, the
Investment Planner picks which symbols to run, the supervisor runs the full
committee pipeline per symbol, and positions are force-closed once the
session ends (real market close, or replay data exhausted)."""

from __future__ import annotations

import logging

from app.agents.planner import InvestmentPlanner
from app.config import get_settings
from app.data import market_data
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
        self.planner = InvestmentPlanner()

    def run_tick(self) -> None:
        db = SessionLocal()
        try:
            portfolio = execution_engine.get_active_portfolio(db)
            if portfolio.status != "active":
                return

            if self.settings.data_mode == "live" and not market_data.is_market_open():
                audit_log.log_event(db, "tick_skipped", {"reason": "market closed", "mode": "live"})
                return

            watchlist = self.settings.watchlist_symbols
            open_symbols = [p.symbol for p in db.query(Position).filter_by(portfolio_id=portfolio.id, status="open").all()]
            symbols = self.planner.plan_tick(watchlist, open_symbols)

            for sym in symbols:
                try:
                    supervisor.run_committee_for_symbol(db, self.provider, sym, watchlist, execute=True)
                except Exception as exc:
                    logger.exception("Committee run failed for %s", sym)
                    audit_log.log_event(db, "tick_error", {"symbol": sym, "error": str(exc)})

            self.provider.advance_all(watchlist)

            if self._session_should_end(watchlist):
                self._close_session(db, portfolio, watchlist)
        finally:
            db.close()

    def _session_should_end(self, watchlist: list[str]) -> bool:
        if self.settings.data_mode == "live":
            return market_data.minutes_to_close() <= self.settings.tick_minutes
        return all(self.provider.is_session_exhausted(s) for s in watchlist)

    def close_now(self) -> None:
        """Force-close the active session immediately (manual override, e.g. from the API)."""
        db = SessionLocal()
        try:
            portfolio = execution_engine.get_active_portfolio(db)
            if portfolio.status == "active":
                self._close_session(db, portfolio, self.settings.watchlist_symbols)
        finally:
            db.close()

    def _close_session(self, db, portfolio, watchlist: list[str]) -> None:
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
        audit_log.log_event(db, "session_closed", {"portfolio_id": portfolio.id, "report_path": report_path})
        logger.info("Session closed. Report at %s", report_path)
