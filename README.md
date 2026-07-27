# Autonomous Multi-Agent Investment Committee

Autonomous multi-agent committee that paper-trades NSE **positionally** (positions held across days/weeks, not force-closed same-day - see [Positional trading mode](#positional-trading-mode) below): an India-only universe (Nifty 50 spot index `^NSEI` — yfinance has no NSE Nifty futures data, so this is a synthetic paper-only position, not a real placeable order — plus MCX gold/silver via their NSE-listed ETF proxies `GOLDBEES.NS`/`SILVERBEES.NS`, with a COMEX gold/silver futures fallback for the analysis feed only while NSE is closed, see `app/data/market_data.py`), **plus BTC via CoinDCX (an Indian crypto exchange, not a global one) trading 24/7 — weekends and NSE's off-hours included** (see [Crypto (BTC)](#crypto-btc) below). Starts with ₹1,00,000 virtual capital per exchange, cash-only (no margin), and autonomously decides BUY / SELL / HOLD / WAIT / SWITCH per symbol using a **trust-weighted, directional-confidence-aware consensus** across 9 analyst agents and a 4-critic debate loop — never simple majority voting or plain confidence averaging.

This build targets a **hackathon-friendly, zero-Docker setup**: everything runs with just a Python virtualenv (Python 3.14 verified) and two local processes (FastAPI backend + Streamlit frontend). See [Architecture mapping](#architecture-mapping-diagram--this-build) for how each diagrammed component was implemented.

## Quick start

```bash
# 1. Create venv & install deps (from the investment-committee/ root)
python -m venv .venv
./.venv/Scripts/pip install -r backend/requirements.txt -r frontend/requirements.txt

# 2. Configure secrets
cp backend/.env.example backend/.env
# edit backend/.env: set ANTHROPIC_API_KEY (or OPENAI_API_KEY + LLM_PROVIDER=openai)

# 3. Run the backend (from investment-committee/ root — this chdir's into backend/ itself)
./.venv/Scripts/python run_backend.py
# -> http://127.0.0.1:8000  (docs at /docs)

# 4. In a second terminal, run the frontend
./.venv/Scripts/python -m streamlit run frontend/Home.py
# -> http://localhost:8501
```

**Without an LLM key**, the app still runs fully — all indicator math, the consensus algorithm, position sizing, execution, and costs are pure Python and key-independent. Only the natural-language reasoning text degrades to a deterministic templated summary instead of an LLM-generated narrative. The Dashboard surfaces a warning banner if no key is configured.
**Local LLM** We are using local LLMs using Ollama using the class app/llm/local_llm.py, just need to replace it with the live LLMs using the function get_local_llm_client along with the model name.

### Data mode

- `DATA_MODE=replay` (default): downloads a window of recent historical intraday bars per symbol once (cached under `data_cache/`) and replays them tick-by-tick. Works at any time of day — good for demos.
- `DATA_MODE=live`: pulls live/delayed quotes from yfinance. Only meaningful during NSE hours (09:15–15:30 IST, Mon–Fri).

### Running a session

- The backend auto-ticks every `TICK_MINUTES` (default 5) via APScheduler once started.
- For a live demo, use the Dashboard's **"Run Tick"** button to trigger a tick on demand instead of waiting.
- Positions are never auto-closed on a clock or when replay data runs out (see [Positional trading mode](#positional-trading-mode)) - a portfolio only closes via the manual `POST /session/close` override (force-closes all positions + generates the PDF trade log), which the dashboard no longer exposes as a button by default since it's not part of the normal positional flow.

## Positional trading mode

Every exchange (NSE and CRYPTO_INDIA) runs positionally: a committee tick still only runs during
that exchange's own trading hours (NSE: 09:15-15:30 IST Mon-Fri; crypto: always), but an opened
position is no longer force-closed at end of day - it's held across ticks, days, and weeks until
a real exit condition fires. This replaced the earlier intraday design where NSE's portfolio
force-closed everything at 15:30 IST and started fresh the next session.

Two independent exit mechanisms, both automatic:

- **Reversal exit** (`app/portfolio/portfolio_manager.py`): every open position's symbol is
  re-run through the full committee on every tick regardless of the per-tick symbol budget (see
  `app/agents/planner.py`) - if the consensus verdict flips to SELL/SWITCH, the position closes.
- **Stop-loss / target exit** (`app/trading/execution_engine.py::check_stop_loss_target`): a
  pure price check, no LLM call, run every tick before the committee loop. Stop-loss/target
  levels are set once at entry (`app/portfolio/portfolio_manager.py::_stop_loss_target`) based on
  the Risk Assessment Analyst's `risk_level` for that trade, at a consistent 1:2 risk-reward
  ratio (LOW 4%/8%, MEDIUM 6%/12%, HIGH 9%/18%, EXTREME 12%/24%) - wider than a typical intraday
  stop, since a positional trade is expected to ride out ordinary day-to-day noise over its
  holding period rather than get shaken out by a single bad hour.

Because positions are now held for days rather than hours, `app/trading/costs.py`'s NSE cost
profile switched from intraday to **delivery** rates to stay realistic: zero brokerage, STT on
both buy and sell (0.1% each, vs intraday's 0.025% sell-only), 5x the stamp duty (0.015% vs
0.003%, still buy-side only), and a new flat DP (Depository Participant) charge on the sell side
that intraday trades never incur.

### Tests

```bash
cd backend && ../.venv/Scripts/python -m pytest tests/ -v
```

Covers the mandatory consensus algorithm (proves it is *not* majority voting / plain averaging) and the trading/cost engine, independent of any LLM or live network call.

## Architecture mapping (diagram → this build)

| Diagram layer | This build |
|---|---|
| Data Sources | `app/data/market_data.py` (yfinance, NSE `.NS` symbols), `app/data/news_data.py` (free RSS: Google News, Moneycontrol, Economic Times; NewsAPI optional), `app/data/fundamentals.py` (yfinance fundamentals) |
| Data Ingestion (Airflow/Kafka) | In-process APScheduler tick loop (`app/orchestration/session_runner.py`) — no external ingestion infra needed for a single-process hackathon deployment |
| Multi-Agent Orchestration (LangGraph) | Custom Python orchestrator (`app/orchestration/supervisor.py`, `app/agents/`) — avoided both LangGraph and CrewAI: these agents are deterministic Python/ML with a thin LLM narration call, not LLM-driven tool-use loops, so a framework built around agentic reasoning chains wouldn't fit. `app/agents/debate_loop.py` runs all analysts (then all critics) concurrently via a bounded `ThreadPoolExecutor` (`settings.max_parallel_agents`, default 4) instead of sequentially — full unbounded parallelism was tried first and tripped Anthropic rate limits, so concurrency is capped rather than open-ended |
| Specialized Analyst Agents | 9 agents in `app/agents/analysts/`: Fundamental, Technical, Macroeconomic, Sentiment, Geopolitical, Government Policy, Risk Assessment, Algo Signal, Astrological — each wraps a custom-built tool in `app/tools/`. Several are blended with teammate-contributed engines (vendored unmodified under `backend/`): Risk Assessment blends our per-bar volatility read with `risk_agent/` (beta, Sharpe/Sortino, VaR/CVaR, liquidity/concentration/sector-exposure risk, on daily bars); Technical blends our intraday RSI/MACD with `technical_analyst_agent/` (daily-chart trend overlay); Sentiment fully replaces our lexicon with `sentiment_analyst.py` (emotion/credibility/risk-scored polarity); Algo Signal is new capability wrapping `algo_agent/` (a freshly-trained logistic regression model per tick, validated out-of-sample) reviewed by `critic_agent/` (a dedicated schema/consistency critic for that model's output); Astrological is a traditional Vedic/Jyotish planetary-position heuristic (`app/tools/planetary_positions.py` + `app/tools/astro_signals.py`, own pure-Python low-precision ephemeris, no external service) — explicitly not empirically validated, so it's capped at low confidence and given the lowest expertise weight in the consensus (`app/consensus/trust_weighted_consensus.py`) so it can only nudge, never drive, the verdict |
| Debate & Consensus Layer | `app/agents/debate_agent.py` (Debate Agent — surfaces the strongest contradicting analyst views before critique) → 4 critics in `app/agents/critics.py` (Risk, Profit, Macro, Opportunity) → `app/consensus/trust_weighted_consensus.py` (the mandatory directional confidence-aware algorithm, combining Confidence Scoring + Directional Consensus into one weighted engine) + `app/consensus/reliability_tracker.py` (persisted Beta-updated historical reliability). Evidence Fusion is implicit in how consensus aggregates each agent's evidence list, rather than a separate agent. |
| Portfolio Decision Layer | `app/portfolio/` — portfolio_manager, position_sizing (respects ₹1,00,000 cash-only cap, no margin), scenario_analysis, execution_advisor |
| Reporting & Output | `app/reporting/` — report_agent (LLM "why" narrative), visualization (Plotly equity curve), alert_agent, audit_log, pdf_export (end-of-session explainable trade log PDF) |
| Memory & Knowledge (PostgreSQL/PGVector/Redis) | SQLite via SQLAlchemy by default (`DATABASE_URL` swappable for Postgres), or Firestore as an alternate backend (`FIRESTORE_PROJECT_ID` - see Persistence section below); decision/vote history queried directly (no vector store dependency); no separate cache layer (single process) |
| Monitoring & Governance (Prometheus/Grafana/LangSmith/Auth0) | Structured logging + `AuditLog` DB table only — not built; noted here as the production upgrade path |
| External Integrations (Broker APIs) | Simulated execution engine (`app/trading/execution_engine.py`) with a realistic Indian delivery cost model (`app/trading/costs.py`: brokerage, STT, exchange charges, SEBI charges, stamp duty, DP charge, GST — see [Positional trading mode](#positional-trading-mode)) — no live broker, this is paper trading |
| User Interface | Streamlit, single consolidated dashboard (`frontend/Home.py`) — a top Market Status strip (NSE/CoinDCX open-closed + tick-scheduler health), NSE (Nifty/Gold/Silver) and BTC panels side by side (live price, Algo Recommendation, portfolio value/P&L, open positions), a candlestick Price Chart panel with a symbol selector, and a compact side panel (auto-trading toggle, positional calls scan) |

### The mandatory consensus algorithm

`app/consensus/trust_weighted_consensus.py` computes, per agent, per tick:

```
weight = confidence × expertise_relevance(context) × trust_score(persisted history) × agreement_adjustment(this tick)
```

`agreement_adjustment` discounts agents that just agree with the room (redundant signal) and amplifies agents that disagree with the room *and* have a strong track record (the "reliable contrarian" case from the spec). The final `directional_confidence` blends the winning action's *dominance* (share of trust-weighted influence) with the *conviction* of the agents backing it (their own confidence × trust) — see `backend/tests/test_consensus.py` for the proofs that this diverges from both majority voting and plain confidence averaging.

## Persistence: SQLite (default) vs Firestore

By default this app stores everything (portfolios, positions, decisions, trades, agent
reliability scores) in a local SQLite file via SQLAlchemy - zero setup, works out of the box.

**This is a real problem on Cloud Run (or any host with an ephemeral local disk) if you
don't set `min-instances` ≥ 1**: the container's local filesystem is wiped every time it
scales to zero and a fresh one spins up, or on every redeploy - so the SQLite file, and every
decision/trade it holds, resets to empty. If your session's `session_start` keeps showing a
recent timestamp instead of holding steady across days, this is why.

Two ways to actually fix it:

- **Pin `min-instances` = `max-instances` = 1** on the Cloud Run service (Console → your
  backend service → Edit & Deploy New Revision → Autoscaling). Keeps one container alive
  permanently so the local disk survives idle periods - cheap and needs no code change, but
  a redeploy still resets it (new revision = new container = new empty disk), and it costs
  continuous compute instead of scale-to-zero.
- **Switch to Firestore** (`app/db/firestore_session.py`, `app/db/models_firestore.py`): set
  `FIRESTORE_PROJECT_ID` in `.env` (or as a Cloud Run env var) to your GCP project id. Real
  persistence that survives both idle scaling and redeploys, and Firestore's free tier (50K
  reads / 20K writes / 1GB storage per day) comfortably covers this app's volume - a decision
  every few minutes is nowhere near that ceiling. Requires: the Firestore API enabled and a
  Firestore database (Native mode) created in that GCP project, and the running service's
  account having the Cloud Datastore User role (the default Compute Engine service account
  Cloud Run uses already has this in most projects). No code changes needed beyond the env
  var - `app/db/models.py` and `app/db/session.py` both branch on whether `FIRESTORE_PROJECT_ID`
  is set and route every existing call site (`main.py`, `execution_engine.py`,
  `session_runner.py`, etc.) to the right backend transparently.

**Design note on the Firestore adapter**: `app/db/firestore_session.py` is deliberately a
narrow shim, not a general ORM - it implements exactly the query patterns this codebase's
~12 database call sites actually use (`filter_by`, `.filter(col.in_(...))`, `order_by(.desc()/
.asc())`, `limit`, `first`/`all`/`one_or_none`, `add`/`flush`/`commit`/`refresh`/`get`), found
by grepping every `db.query()`/`db.add()` call before writing it. Auto-increment integer ids
are preserved (via a per-collection counter document) rather than switching to Firestore's
native string document ids, so API paths like `GET /decisions/{decision_id}` didn't need to
change. **Verified offline against an in-memory fake of `google.cloud.firestore`** (this
sandbox has no network access to a real Firestore project) covering create/fetch/filter/
order/limit/relationship-traversal/`.in_()` - one real bug (filtering by `.id` didn't match
anything, since the id was only used as the document key, not stored in the document body
too) was caught and fixed this way. What that fake stub *can't* catch: real network/auth
behavior, Firestore's actual query index requirements (composite queries sometimes need an
index created via a link Firestore gives you the first time you run them), and real
concurrent-write behavior. **Test this against your real GCP project before trusting it with
anything that matters** - watch the Cloud Run logs on first deploy for a
`FailedPrecondition: query requires an index` error, which just means clicking the link
Firestore prints to auto-create it.

## Backtesting (read before considering live trading)

Before connecting this to a real broker/exchange account (e.g. Delta Exchange for crypto derivatives), run a real backtest - the consensus thresholds in this build were tuned to make the demo actually produce trades, not validated for real-money edge, and no historical accuracy number exists anywhere in this repo until you generate one.

```bash
# 1. Fetch real historical candles from CoinDCX (needs real internet access - won't work from a network-sandboxed environment)
cd backend && python scripts/fetch_backtest_data.py --market BTCINR --interval 5m --days 90

# 2. Run the backtest
cd .. && python run_backtest.py --csv backend/data_cache/backtest_BTCINR_5m.csv
```

This replays historical bars through the **real production pipeline** (`TechnicalAnalyst`, `RiskAnalyst`, `AlgoSignalAnalyst`, the Debate Agent, all 4 critics, and the actual `trust_weighted_consensus` math - not a reimplementation), simulates a portfolio against it with the real `CRYPTO_INDIA` cost model, and reports total return, CAGR, win rate, Sharpe ratio, max drawdown, and — critically — **return vs simply buying and holding the asset over the same window**. If alpha vs buy-and-hold is negative, the algorithm did worse than doing nothing.

**Read `app/backtest/engine.py`'s module docstring before trusting the output.** Two honest limitations baked into every run:

- **Macro/Sentiment/Geopolitical/Government Policy/Fundamental/Astrological analysts are excluded.** Each either needs LIVE news/company-financials context that can't be validly reconstructed for a historical bar (feeding today's headlines into a bar from 3 months ago isn't a neutral simulation), or doesn't meaningfully apply to a cryptocurrency (financial statements, planetary positions). The backtest measures the price/risk/model-driven core of the committee, not the full intraday roster.
- **Reliability trust scores are held at the neutral 0.5 prior throughout.** There's no historical trust data to bootstrap from, so live behavior will diverge from this backtest as the system builds a real track record (see `app/consensus/reliability_tracker.py`).

## Crypto (BTC)

A second, fully independent trading exchange alongside NSE — added specifically so trades keep executing on weekends and outside NSE's 09:15–15:30 IST session, which a single India-equities-only build otherwise has no way to do.

- **Exchange**: `CRYPTO_INDIA` in `app/data/exchanges.py` — open 7 days a week, 00:00–23:59:59, so `is_open()` is always `True`. Watchlist is `("BTCINR",)` only.
- **Data source**: `app/data/crypto_data.py` — CoinDCX's public REST API (`api.coindcx.com` / `public.coindcx.com`), chosen deliberately over yfinance's crypto tickers because it's an *Indian* exchange's own INR order book, matching the same "Indian exchange only" stance the rest of this app already takes for equities and options. No API key needed for market data.
- **PI (Pi Network) deliberately excluded**: as of this build it isn't listed on any major/vetted Indian exchange (CoinDCX, WazirX, Bitbns, ZebPay) — the only Indian venue found was Flitpay, a much smaller, less-established platform not worth depending on for trading data yet.
- **Concurrent, independent portfolios**: `execution_engine.get_active_portfolio()` is exchange-scoped, and `session_runner.SessionRunner` ticks every currently-eligible exchange each cycle — NSE only during its own session hours (live mode) or its own replay window (replay mode), CRYPTO_INDIA always, regardless of the other's state. There's no single global "active session" anymore; NSE and crypto each keep compounding independently. Crypto's session never force-closes on a schedule the way NSE's does — in replay mode its cached candle history loops instead of running out (see `market_data.py`'s `advance()`), so it never reports "session exhausted".
- **Cost model**: `app/trading/costs.py`'s `CRYPTO_INDIA` profile — CoinDCX's 0.2% retail spot fee, 18% GST on that fee, and 1% TDS on sell-side turnover under Income Tax Act Section 194S (a real, material cost for Indian crypto trades, not a securities-market charge that happens not to apply).
- **Dashboard**: BTC has its own panel side by side with the Nifty 50 panel in the single consolidated `frontend/Home.py` dashboard (live price, Algo Recommendation, session P&L) — not a separate page.
- **API**: every relevant endpoint (`/portfolio`, `/watchlist`, `/planner/allocation-plan`, `/session/close`) takes an `exchange` query param (default `NSE`, so every existing caller is unaffected); `/market/chart/{symbol}` and `/analyze/{symbol}` resolve a symbol's exchange automatically.

Not yet done: PI coin (see above), a crypto-specific track record in the reliability tracker (currently shares trust scores with NSE).

## Positional calls (options + directional)

A second, separate pipeline alongside the intraday session above — screens Nifty 50, Bank Nifty, Gold, Silver, and BTC (`POSITIONAL_UNIVERSE=^NSEI,^NSEBANK,GOLDBEES.NS,SILVERBEES.NS,BTCINR` in `.env`, not the 3-symbol intraday `WATCHLIST`) for multi-day/week positional trades, and ranks candidates instead of producing one verdict at a time. Originally built around a 20-stock large-cap universe; narrowed to index-only since individual-stock trading wasn't the actual use case, then widened again to add Gold/Silver/BTC once it became clear those were. See `docs/POSITIONAL_OPTIONS_ENHANCEMENT_PLAN.md` for the full design rationale (written before either narrowing/widening pass).

Only Nifty 50 and Bank Nifty get a real **options structure** (long call/put, debit or credit spread with strikes/expiry/max loss/profit) — they're the only two symbols in the universe with a listed NSE options chain this app can fetch. Gold/Silver (ETF proxies, no listed equity options) and BTC (CoinDCX is spot-only, no listed options chain) still run the full committee and get a **directional positional call** (BUY/SELL/HOLD/WAIT + conviction %, no structure) — `app/agents/strategy_architect.py`'s `build_strategy_for_verdict()` already returns `None` gracefully whenever there's no options chain to build real strikes/premiums from, so this needed no new fallback logic, just widening the universe.

- **5 new analyst agents** (`app/agents/analysts/`): IV & Options Chain Analyst (IV rank, put-call OI ratio, max pain), Volatility Regime Analyst (implied vs realized vol, term structure), Catalyst & Events Analyst (earnings/expiry/RBI MPC dates), Liquidity Analyst (bid-ask spread/OI depth as a tradability gate), Relative Strength Analyst (vs the Nifty 50 benchmark) — run in `POSITIONAL_TIER`, only as part of a positional scan, never the intraday tick loop.
- **Options chain data** (`app/data/options_data.py`): live NSE option-chain fetch (strikes, OI, IV, LTP) — not available via yfinance, so this talks to NSE's own JSON API directly. Degrades to `None` (agents fall back to a clearly-labeled low-confidence read, and the Strategy Architect skips structuring) for any symbol NSE doesn't have listed options for, or if NSE is unreachable/rate-limits.
- **Catalyst calendar** (`app/data/calendar_data.py`): the F&O-expiry catalyst event is only emitted for `^NSEI`/`^NSEBANK` — fabricating a monthly "expiry" date for Gold/Silver/BTC (none of which have one) would be a fake event, so it's just omitted for those rather than guessed.
- **News query** (`app/data/news_data.py`'s `symbol_news_query()`): BTCINR/GOLDBEES.NS/SILVERBEES.NS have no yfinance company profile to pull a search term from, so these three have an explicit override (`SYMBOL_NEWS_QUERY_OVERRIDES` - "Bitcoin", "gold price India", "silver price India") instead of searching the literal ticker string. Shared by both the intraday flow and the positional scanner, since Gold/Silver/BTC are on the intraday watchlists too.
- **Positional consensus mode**: `compute_consensus(..., mode="positional")` in `app/consensus/trust_weighted_consensus.py` uses a separate `POSITIONAL_EXPERTISE_RELEVANCE` weighting table (fundamentals/macro weighted up, the intraday-only Algo Signal weighted down) and higher, not-yet-backtested decisive thresholds (`POSITIONAL_DECISIVE_THRESHOLD`) — intraday behavior (`mode` omitted) is completely unchanged.
- **API**: `POST /positional/scan` runs the full committee across the universe (a few minutes — ~19 agents × 5 symbols); `GET /positional/picks` returns the latest ranked scan without re-running it; `GET /positional/picks/{symbol}` is the per-symbol drill-down (agent votes, structure if any, conviction trend across past scans) — not surfaced in the UI, but queryable directly.
- **Dashboard**: surfaced as a single compact line per symbol under its panel in `frontend/Home.py` — an options-pick line (direction, structure, expiry, max loss/profit) for Nifty/Bank Nifty, or a directional-call line (direction, conviction %) for Gold/Silver/BTC — triggered via the "Scan Positional Calls" button in the side panel. The full ranked table, payoff diagram, conviction trend, and per-agent vote breakdown were dropped from the UI in favor of an essentials-only single dashboard; they're still available via the API endpoints above.

Not yet done (see the enhancement plan's phased roadmap): a once-daily automatic schedule for the scan (currently on-demand only), backtesting the positional decisive threshold against real scan history, and a separate positional-specific trust score in the reliability tracker (currently shares the intraday one).

## What's not built (explicitly out of scope for this hackathon build)

Airflow, Kafka, Kubernetes/Terraform, PGVector, Redis, Prometheus/Grafana, LangSmith/Op