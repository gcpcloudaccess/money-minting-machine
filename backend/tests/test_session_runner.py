"""Unit tests for SessionRunner's multi-exchange eligibility logic (app/
orchestration/session_runner.py) - proves NSE keeps its existing session-hours
gating while CRYPTO_INDIA is always eligible, independent of the clock or
NSE's own state. No network, no LLM key, no DB required."""

import datetime as dt
from zoneinfo import ZoneInfo

from app.orchestration.session_runner import SessionRunner

IST = ZoneInfo("Asia/Kolkata")


def _runner(data_mode: str, replay_exchange: str = "NSE") -> SessionRunner:
    runner = SessionRunner()
    # Mutate the already-constructed Settings instance directly rather than
    # fighting get_settings()'s process-wide lru_cache - safe here since
    # each test builds its own SessionRunner (and therefore reads
    # self.settings fresh each time via get_settings(), which returns the
    # same cached object every test run touches).
    runner.settings.data_mode = data_mode
    runner.settings.replay_exchange = replay_exchange
    return runner


def test_live_mode_both_eligible_during_nse_hours():
    runner = _runner("live")
    weekday_during_nse_hours = dt.datetime(2026, 7, 8, 10, 0, tzinfo=IST)  # Wednesday
    codes = [e.code for e in runner._eligible_exchanges(weekday_during_nse_hours)]
    assert codes == ["NSE", "CRYPTO_INDIA"]


def test_live_mode_only_crypto_eligible_on_weekend():
    runner = _runner("live")
    saturday = dt.datetime(2026, 7, 11, 12, 0, tzinfo=IST)
    codes = [e.code for e in runner._eligible_exchanges(saturday)]
    assert codes == ["CRYPTO_INDIA"]


def test_live_mode_only_crypto_eligible_after_nse_close():
    runner = _runner("live")
    weekday_evening = dt.datetime(2026, 7, 8, 20, 0, tzinfo=IST)
    codes = [e.code for e in runner._eligible_exchanges(weekday_evening)]
    assert codes == ["CRYPTO_INDIA"]


def test_replay_mode_both_eligible_regardless_of_clock():
    runner = _runner("replay", replay_exchange="NSE")
    saturday = dt.datetime(2026, 7, 11, 3, 0, tzinfo=IST)
    codes = [e.code for e in runner._eligible_exchanges(saturday)]
    assert codes == ["NSE", "CRYPTO_INDIA"]


def test_no_duplicate_when_replay_exchange_is_crypto():
    runner = _runner("replay", replay_exchange="CRYPTO_INDIA")
    codes = [e.code for e in runner._eligible_exchanges()]
    assert codes == ["CRYPTO_INDIA"]  # not duplicated


def test_crypto_session_never_ends():
    runner = _runner("live")
    from app.data import exchanges
    assert runner._session_should_end(exchanges.CRYPTO_INDIA, list(exchanges.CRYPTO_INDIA.watchlist)) is False


def test_planners_are_independent_per_exchange():
    runner = _runner("replay")
    from app.data import exchanges
    nse_planner = runner._planner_for(exchanges.NSE)
    crypto_planner = runner._planner_for(exchanges.CRYPTO_INDIA)
    assert nse_planner is not crypto_planner
    assert runner._planner_for(exchanges.NSE) is nse_planner  # stable across calls
