"""
LLM Trader - Autonomous LLM-driven equities trader.

A production-ready Python trading system implementing Hype & Event Momentum strategy
with strict quantitative gates and comprehensive risk management.
"""

__version__ = "0.1.0"
__author__ = "LLM Trader Team"
__email__ = "trader@example.com"

from .config import settings, llm_config, strategy_config, alpaca_config, search_config, agent_config
from .models import (
    TradingDecision,
    ResearchItem,
    DecisionItem,
    SentimentType,
    CatalystType,
    ActionType,
    OrderType
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
    "OrderType"
]

