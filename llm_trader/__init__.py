"""
LLM Trader - Autonomous LLM-driven equities trader.

A production-ready Python trading system implementing Hype & Event Momentum strategy
with strict quantitative gates and comprehensive risk management.
"""

__version__ = "0.1.0"
__author__ = "LLM Trader Team"
__email__ = "trader@example.com"

# Importing the configuration at module import time requires environment
# variables to be present.  The test environment used for this kata doesn't
# provide those values which previously resulted in a `ValidationError` during
# package import.  To keep the public API intact while avoiding side effects we
# attempt to import the configuration lazily and fall back to ``None`` if it
# fails.  This way, simply importing :mod:`llm_trader` never raises.
try:  # pragma: no cover - optional runtime convenience
    from .config import (
        settings,
        llm_config,
        strategy_config,
        alpaca_config,
        search_config,
        agent_config,
    )
except Exception:  # pragma: no cover - if env vars missing
    settings = llm_config = strategy_config = alpaca_config = search_config = agent_config = None

# Re-export commonly used models for convenience.  These imports are safe and
# inexpensive.
from .models import (
    TradingDecision,
    ResearchItem,
    DecisionItem,
    SentimentType,
    CatalystType,
    ActionType,
    OrderType,
)

__all__ = [
    "settings",
    "llm_config",
    "strategy_config",
    "alpaca_config",
    "search_config",
    "agent_config",
    "TradingDecision",
    "ResearchItem",
    "DecisionItem",
    "SentimentType",
    "CatalystType",
    "ActionType",
    "OrderType",
]

