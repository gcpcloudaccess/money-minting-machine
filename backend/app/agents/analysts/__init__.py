from app.agents.analysts.algo_signal import AlgoSignalAnalyst
from app.agents.analysts.astro import AstroAnalyst
from app.agents.analysts.catalyst import CatalystAnalyst
from app.agents.analysts.fundamental import FundamentalAnalyst
from app.agents.analysts.geopolitical import GeopoliticalAnalyst
from app.agents.analysts.iv_options import IVOptionsAnalyst
from app.agents.analysts.liquidity import LiquidityAnalyst
from app.agents.analysts.macro import MacroAnalyst
from app.agents.analysts.policy import PolicyAnalyst
from app.agents.analysts.relative_strength import RelativeStrengthAnalyst
from app.agents.analysts.risk import RiskAnalyst
from app.agents.analysts.sentiment import SentimentAnalyst
from app.agents.analysts.technical import TechnicalAnalyst
from app.agents.analysts.volatility_regime import VolatilityRegimeAnalyst

# Staged pipeline (see app/agents/debate_loop.py): each tier runs after the
# previous one completes, and later tiers receive earlier tiers' votes as
# context (AnalysisContext.prior_stage_votes) - top-down macro/sentiment/
# policy/astrology backdrop first, then company-specific drill-down informed
# by that backdrop, then the algo model + its critic as the final automated
# signal. AstroAnalyst sits in the macro tier since it reads a market-wide
# planetary backdrop, not anything symbol-specific in the fundamental sense -
# see its own docstring for why it's deliberately a low-weight nudge, not a
# primary signal.
MACRO_TIER = [MacroAnalyst, SentimentAnalyst, GeopoliticalAnalyst, PolicyAnalyst, AstroAnalyst]
DRILLDOWN_TIER = [FundamentalAnalyst, TechnicalAnalyst, RiskAnalyst]
ALGO_TIER = [AlgoSignalAnalyst]

# Positional-only tier (see app/agents/debate_loop.py run_positional_debate) -
# reads options-chain/IV/catalyst/relative-strength data that only
# app/orchestration/positional_scanner.py populates on AnalysisContext.
# Never runs as part of the intraday run_debate() pipeline, so it can't
# affect the existing intraday consensus/tests at all.
POSITIONAL_TIER = [RelativeStrengthAnalyst, CatalystAnalyst, VolatilityRegimeAnalyst, IVOptionsAnalyst, LiquidityAnalyst]

ALL_ANALYSTS = [*MACRO_TIER, *DRILLDOWN_TIER, *ALGO_TIER]
ALL_POSITIONAL_ANALYSTS = [*MACRO_TIER, *DRILLDOWN_TIER, *POSITIONAL_TIER, *ALGO_TIER]

__all__ = [
    "FundamentalAnalyst",
    "TechnicalAnalyst",
    "MacroAnalyst",
    "SentimentAnalyst",
    "GeopoliticalAnalyst",
    "PolicyAnalyst",
    "RiskAnalyst",
    "AlgoSignalAnalyst",
    "AstroAnalyst",
    "RelativeStrengthAnalyst",
    "CatalystAnalyst",
    "VolatilityRegimeAnalyst",
    "IVOptionsAnalyst",
    "LiquidityAnalyst",
    "MACRO_TIER",
    "DRILLDOWN_TIER",
    "ALGO_TIER",
    "POSITIONAL_TIER",
    "ALL_ANALYSTS",
    "ALL_POSITIONAL_ANALYSTS",
]
