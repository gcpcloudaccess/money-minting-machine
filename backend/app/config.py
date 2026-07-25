from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    newsapi_key: str = ""

    data_mode: str = "replay"  # live | replay

    database_url: str = "sqlite:///./investment_committee.db"

    starting_capital_inr: float = 100_000.0  # ₹1 lac paper capital
    leverage: float = 1.0  # no margin - cash-only paper trading
    session_hours: float = 4.0
    tick_minutes: int = 10
    # Scoped to an India-only, single-exchange universe: the Nifty 50 index
    # directly (^NSEI - yfinance has no NSE Nifty futures data, so this is a
    # synthetic paper-only position, not a real placeable order) plus MCX
    # gold/silver via their NSE-listed ETF proxies (GOLDBEES.NS / SILVERBEES.NS)
    # - see app/data/exchanges.py for the full rationale on both.
    watchlist: str = "^NSEI,GOLDBEES.NS,SILVERBEES.NS"

    # This build only supports NSE (see app/data/exchanges.py) - kept as a
    # setting rather than hardcoded so the session runner's live/replay branch
    # doesn't need special-casing.
    replay_exchange: str = "NSE"

    # Drives the Investment Planner's asset-allocation caps and profit/loss goals
    # (see agents/allocation_planner.py) - conservative | moderate | aggressive.
    risk_tolerance: str = "moderate"

    backend_host: str = "127.0.0.1"
    backend_port: int = 8000

    # Caps concurrent LLM calls when running agents in parallel. Keep conservative -
    # most API tiers rate-limit on concurrent/burst requests, and firing all 8+
    # analysts at once can trigger retries that cost more time than sequential
    # execution would have. Raise this if your API tier comfortably supports it.
    max_parallel_agents: int = 4

    # How many symbols the Investment Planner analyzes per tick (see agents/planner.py).
    # Each symbol runs the full 14-agent committee (~30-90s wall-clock), so this is the
    # main lever on how fast a decision lands, not TICK_MINUTES - a tick can't finish
    # faster than max_symbols_per_tick x (time per symbol), regardless of how often the
    # scheduler fires. Lower = faster individual decisions, less breadth per tick (the
    # watchlist still rotates fully over time, just in smaller batches).
    max_symbols_per_tick: int = 1

    # Optional India macro inputs for the Macroeconomist Analyst's regime model
    # (GDP growth, CPI inflation, RBI repo rate). No free live feed for these is
    # wired up, so rather than fabricate numbers this is left unset by default -
    # the agent falls back to its news-sentiment-only reading until you fill
    # these in from RBI/MOSPI bulletins (update periodically; they move slowly).
    macro_gdp_growth_pct: float | None = None
    macro_inflation_pct: float | None = None
    macro_policy_rate_pct: float | None = None
    macro_data_as_of: str = ""  # ISO date, e.g. "2026-06-30"

    # ---------------------------------------------------------------- positional options
    # Index options only - Nifty 50 (^NSEI) and Bank Nifty (^NSEBANK), NOT
    # individual stocks. This was originally a 20-stock large-cap universe, but
    # the user doesn't trade individual stocks, only index and BTC positions -
    # and index options are the most liquid F&O instruments on NSE anyway, so
    # narrowing to just these two loses nothing for this use case.
    # app/data/options_data.py's _INDEX_SYMBOL_MAP and app/data/calendar_data.py's
    # is_index check already special-case both of these for the NSE index option
    # chain endpoint and weekly (not monthly) expiry cadence.
    positional_universe: str = "^NSEI,^NSEBANK"

    # NSE has changed the weekday for index weekly options expiry more than
    # once (Thursday -> Tuesday as of this build) - see app/data/calendar_data.py.
    # 0=Monday ... 6=Sunday.
    options_expiry_weekday: int = 1  # Tuesday

    min_days_to_expiry_positional: int = 7    # avoid picks that decay/expire too soon to hold a positional thesis
    max_days_to_expiry_positional: int = 45   # avoid tying up premium in an expiry far beyond the thesis horizon

    # No free live feed for RBI MPC meeting dates (published on rbi.org.in well
    # in advance) - comma-separated ISO dates, update periodically. Empty by
    # default rather than fabricated.
    rbi_mpc_dates: str = ""

    @property
    def watchlist_symbols(self) -> list[str]:
        return [s.strip() for s in self.watchlist.split(",") if s.strip()]

    @property
    def positional_universe_symbols(self) -> list[str]:
        return [s.strip() for s in self.positional_universe.split(",") if s.strip()]

    @property
    def max_exposure_inr(self) -> float:
        return self.starting_capital_inr * self.leverage

    @property
    def llm_key_configured(self) -> bool:
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
