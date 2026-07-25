# Money Minting Machine — Positional Options Enhancement Plan

Reviewed the current codebase (9 analysts + 4 critics, trust-weighted consensus, single-page Streamlit dashboard) against the goal: reliable "best positional options pick" recommendations. Below is the gap analysis, the specific agents and dashboard changes needed, and a prioritized build order.

## Why current output feels inefficient

Three structural reasons, not a tuning problem:

1. **Wrong time horizon end-to-end.** The system is built for a 4–6 hour intraday session with 10-minute ticks and a single BUY/SELL/HOLD/WAIT/SWITCH verdict per tick. A positional options thesis plays out over days to weeks — daily bars, not 10-minute bars, and a thesis that should be re-evaluated once a day, not every 10 minutes.
2. **Universe too small to ever produce a "best pick."** `watchlist` is 3 symbols (`^NSEI`, `GOLDBEES.NS`, `SILVERBEES.NS`), and `max_symbols_per_tick=1` means the committee only fully evaluates one symbol per tick. There's no ranking across candidates because there's rarely more than one candidate in play at a time.
3. **Consensus is tuned to fight intraday noise, not surface conviction.** The decisive threshold in `trust_weighted_consensus.py` has already been lowered twice (30% → 18% → 14%) because HOLD kept winning by vote count even when 1–2 agents had real conviction. That's the right instinct for a noisy 10-minute tape, but it's a band-aid — the actual fix is giving directional agents more room to lead when the underlying signal (daily trend, IV skew, catalyst) is genuinely strong, which requires new agents and a horizon-aware weighting table, not a lower bar.

Also confirmed: there is currently **zero options infrastructure** — no chain data, no IV, no greeks, no strike/expiry selection anywhere in `app/data/` or `app/tools/`. This is the single biggest blocker and should be phase 1.

## New analyst agents needed

Add these to `app/agents/analysts/`, each following the existing `AgentVote` pattern in `app/agents/base.py`:

**IV & Options Chain Analyst.** IV rank/percentile vs. 1-year history, IV skew (put vs call), put-call OI ratio, max pain, OI buildup by strike. This is what tells you whether to buy premium or sell it — a strong directional view with IV rank at 80th percentile calls for a spread, not a naked long option.

**Volatility Regime Analyst.** Historical (realized) vol vs. implied vol spread, vol term structure across expiries. Feeds the Strategy Architect below and flags IV-crush risk (e.g., pre-earnings IV that will collapse the day after the print regardless of direction being right).

**Catalyst & Events Analyst.** Earnings dates, RBI MPC meeting dates, F&O monthly expiry, corporate actions, index rebalancing. Positional options theses live or die on what happens between entry and expiry — this agent is what prevents the system from recommending a 3-week call right before an earnings IV crush.

**Strategy Architect Agent.** Not a directional voter — a translator. Takes the consensus direction + conviction + IV regime and outputs the actual structure: long call/put, debit spread, credit spread, or calendar, plus suggested strike and expiry, max loss, breakeven, and a payoff curve. This is the agent that turns "BUY, 62% confidence" into an actual placeable options trade.

**Liquidity/OI Analyst.** Bid-ask spread and open interest depth per strike. Filters out picks where the options market itself is too illiquid to trade the size implied by position sizing — necessary before "best pick" reaches the dashboard, otherwise you'll rank an untradeable contract as #1.

**Relative Strength / Sector Analyst.** Only needed once the watchlist widens (see below) — ranks candidates against sector and index to help the Planner decide which symbols are even worth full committee time each cycle.

Existing agents that need horizon changes, not replacement:

- **Technical Analyst** — currently intraday RSI/MACD blended with a daily-chart overlay. For positional picks, flip the primary signal to daily/weekly (trend structure, support/resistance, higher-timeframe momentum) and demote the intraday read to a timing nudge only.
- **Risk Assessment Analyst** — add options-specific risk: theta decay curve over the hold period, vega exposure, assignment risk on any short leg, max loss as % of allocated capital.
- **Fundamental / Macro / Geopolitical / Policy Analysts** — these are currently down-weighted (`EXPERTISE_RELEVANCE` 0.45–0.55) because they're too slow-moving to matter in a 4-hour session. For a multi-week options position they matter much more and need a **separate expertise-relevance table for "positional" mode** (see below) — don't just raise their global weight, since that would also change intraday behavior.

## Consensus engine changes

`trust_weighted_consensus.py` needs a `mode: "intraday" | "positional"` parameter that selects between two `EXPERTISE_RELEVANCE` tables, since the right weighting genuinely differs by horizon (technical dominates intraday; fundamentals/macro/catalysts matter more positionally). Don't overwrite the existing table — intraday mode should keep working as-is.

Move from "one symbol decided per tick" to a **ranking pass**: each cycle (daily, not every 10 minutes), run the full committee across the whole candidate universe, and output a ranked list by `directional_confidence × risk-adjusted expected move`, not a single verdict. This is what actually produces a "best pick" instead of a single yes/no on whatever symbol happened to be up next in the rotation.

Recalibrate the decisive threshold from scratch for positional mode using backtested daily data rather than reusing 14% (that number was tuned specifically for 10-minute-tick noise and has no reason to transfer).

## Data layer

This is the real blocker, so sequence it first:

1. **NSE options chain feed** — yfinance has no Indian options data. Look at `nsepython` or the NSE India option-chain endpoint directly for live chain snapshots (strikes, OI, IV, LTP per leg); budget for a paid vendor (e.g., Sensibull, Kite Connect if you're on Zerodha, or ICICI Breeze) if you need reliable historical IV for backtesting.
2. **Daily/weekly OHLC history** — needed for the Technical Analyst's positional read; yfinance covers this fine even though it doesn't have options.
3. **Economic/earnings calendar** — free sources exist (NSE corporate announcements, Moneycontrol earnings calendar) for the Catalyst Analyst.
4. **Widen the universe** — at minimum the Nifty 50 constituents, so there's something to actually rank. 3 symbols cannot produce a "best pick."

## Dashboard changes

The current `frontend/Home.py` is a single flat page built around one live intraday session. For positional picks, add:

**Positional Picks tab** — the main new surface. A ranked, sortable/filterable table: symbol, direction, conviction %, suggested structure (from the Strategy Architect), expiry, strike, max loss, risk/reward, IV rank, days to next catalyst. This is the actual deliverable the user is asking for.

**Per-pick drill-down** — agent-by-agent vote breakdown (the explainability pattern already exists for intraday verdicts in the reasoning/report layer — extend it here), plus a payoff diagram (P&L vs. underlying price at expiry) and the upcoming catalyst timeline for that symbol.

**Universe screener / heatmap** — conviction score across the full watchlist so it's visually obvious what's a real signal vs. noise, instead of only ever seeing one symbol's verdict at a time.

**Conviction trend chart per candidate** — how the consensus score moved day over day leading into the pick. A positional entry is much stronger evidence when conviction has been building for 3 days than when it just crossed the threshold once.

**Options-aware portfolio view** — mark-to-market accounting for IV changes and theta decay, days-to-expiry countdown, and roll/adjust alerts, replacing the current cash-equity-only P&L view.

**Event calendar strip** — upcoming earnings/expiry/macro dates for anything held or shortlisted, surfaced at the top of the dashboard, not buried in a tab.

## Suggested build order

1. **Data unlock** — NSE options chain integration, daily bar history, expand universe to Nifty 50, earnings/expiry calendar feed. Nothing else is useful until this exists.
2. **New agents** — IV & Options Chain Analyst, Catalyst Analyst, Strategy Architect, Liquidity Analyst; add the positional `EXPERTISE_RELEVANCE` table; retune Technical and Risk agents for daily horizon.
3. **Consensus** — universe-wide ranking pass (replacing single-symbol-per-tick), positional mode switch, threshold recalibration via backtest on daily data.
4. **Dashboard** — Positional Picks tab, screener heatmap, payoff diagrams, event calendar strip, options-aware portfolio view.
5. **Track record** — extend `reliability_tracker.py` to score positional calls against realized multi-day outcomes (separate from the intraday trust scores, since they're measuring different things), and feed that into a positional trust score. This is what makes agent weighting actually improve over time instead of staying fixed at hand-picked numbers.

Phases 1–2 are the load-bearing ones — everything downstream (ranking, dashboard, track record) is only as good as having real options/IV/catalyst data and the agents that read it. Worth doing those before touching the dashboard, even though the dashboard is the more visible ask.
