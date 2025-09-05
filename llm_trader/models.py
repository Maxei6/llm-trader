"""
Pydantic models for LLM Trader schema validation and database DTOs.
"""

"""Pydantic models for LLM Trader schema validation and database DTOs."""

from datetime import datetime, date as Date
from typing import List, Optional, Literal, Union
from enum import Enum

from pydantic import BaseModel, Field, validator, ConfigDict
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


# Enums for type safety
class SentimentType(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class CatalystType(str, Enum):
    EARNINGS = "earnings"
    PRODUCT = "product"
    REGULATION = "regulation"
    GUIDANCE = "guidance"
    MA = "M&A"
    PARTNERSHIP = "partnership"
    OTHER = "other"


class ActionType(str, Enum):
    LONG = "long"
    SHORT = "short"
    NO_TRADE = "no-trade"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


# Pydantic Models for JSON Schema Validation
class SourceInfo(BaseModel):
    """Information about a news source."""
    title: str = Field(..., description="Article title")
    url: str = Field(..., description="Article URL")
    publisher: str = Field(..., description="Publisher name")
    # ``date`` is both the field name and the type we want to use. In
    # Pydantic v2 this causes a conflict because the type annotation is
    # evaluated using the same name as the field, triggering a
    # ``PydanticUserError`` during model creation.  To avoid the clash we
    # import ``date`` from :mod:`datetime` using a different alias and use
    # that alias in the annotation.  The field itself is still called
    # ``date`` so tests and downstream code continue to work as expected.
    date: Date = Field(..., description="Publication date")
    takeaway: str = Field(..., max_length=30, description="Key takeaway in ≤30 words")


class FundamentalsBrief(BaseModel):
    """Brief fundamental information about a company."""
    mkt_cap: str = Field(..., description="Market capitalization")
    rev_ltm: str = Field(..., description="Revenue last twelve months")
    growth_yoy: str = Field(..., description="Year-over-year growth")
    margin_brief: str = Field(..., description="Margin information")
    next_earnings: Optional[Date] = Field(None, description="Next earnings date")


class ResearchItem(BaseModel):
    """Research analysis for a single symbol."""
    symbol: str = Field(..., description="Stock ticker symbol")
    sources: List[SourceInfo] = Field(..., description="News sources analyzed")
    fundamentals_brief: FundamentalsBrief = Field(..., description="Key fundamentals")
    thesis: str = Field(..., max_length=40, description="Investment thesis in ≤40 words")
    sentiment: SentimentType = Field(..., description="Overall sentiment")
    hype_score: float = Field(..., ge=0.0, le=1.0, description="Hype score [0,1]")
    catalyst: CatalystType = Field(..., description="Primary catalyst type")
    checks: List[str] = Field(..., min_items=3, max_items=6, description="Measurable checks")
    risks: List[str] = Field(..., min_items=2, max_items=5, description="Key risks")
    liquidity_ok: bool = Field(..., description="Liquidity check passed")


class OrderPlan(BaseModel):
    """Order execution plan."""
    type: OrderType = Field(..., description="Order type")
    entry_note: str = Field(..., max_length=20, description="Entry rationale in ≤20 words")
    limit_price: Optional[float] = Field(None, description="Limit price if applicable")
    stop_logic: str = Field(..., description="Stop loss logic")
    take_profit_logic: str = Field(..., description="Take profit logic")
    size_pct_equity: float = Field(..., ge=0.0, le=1.0, description="Position size as % of equity")
    qty_estimate: int = Field(..., ge=0, description="Estimated quantity")


class DecisionItem(BaseModel):
    """Trading decision for a single symbol."""
    symbol: str = Field(..., description="Stock ticker symbol")
    action: ActionType = Field(..., description="Trading action")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level [0,1]")
    upside_downside_ratio: float = Field(..., ge=0.0, description="Risk-reward ratio")
    # Allow a short phrase describing the expected return.  The previous
    # implementation limited this field to 20 **characters**, which was too
    # restrictive and caused legitimate descriptions like "Strong upside
    # potential" to fail validation.  Increase the limit to a more reasonable
    # 40 characters which roughly corresponds to the intended "≤20 words"
    # guideline.
    exp_return_brief: str = Field(..., max_length=40, description="Expected return in ≤20 words")
    order_plan: Optional[OrderPlan] = Field(None, description="Order plan if trading")

    @validator('order_plan')
    def validate_order_plan(cls, v, values):
        """Ensure order_plan is provided for trading actions."""
        action = values.get('action')
        if action in [ActionType.LONG, ActionType.SHORT] and v is None:
            raise ValueError("order_plan required for trading actions")
        return v


class PositionsContext(BaseModel):
    """Current portfolio context."""
    cash_estimate: Optional[str] = Field(None, description="Cash estimate")
    notable_exposures: List[str] = Field(default_factory=list, description="Notable exposures")


class MonitoringPlan(BaseModel):
    """Monitoring and review plan."""
    interval: str = Field(default="daily close", description="Review interval")
    auto_exit: List[str] = Field(..., description="Auto-exit conditions")
    review_checks: List[str] = Field(..., description="Review checklist items")
    next_review_after_hours: int = Field(default=0, description="Hours until next review")


class SafetyChecks(BaseModel):
    """Safety and risk management checks."""
    why_no_trade_if_any: Optional[str] = Field(None, description="Reason for no-trade")
    drawdown_kill_switch_suggestion: str = Field(..., description="Kill switch recommendation")


class TradingDecision(BaseModel):
    """Complete trading decision schema."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    schema_version: int = Field(default=1, description="Schema version")
    run_id: str = Field(..., description="Unique run identifier")
    timestamp_local: datetime = Field(..., description="Local timestamp")
    universe_considered: List[str] = Field(..., description="Symbols considered")
    positions_context: PositionsContext = Field(..., description="Portfolio context")
    research: List[ResearchItem] = Field(..., description="Research analysis")
    decision: List[DecisionItem] = Field(..., description="Trading decisions")
    monitoring: MonitoringPlan = Field(..., description="Monitoring plan")
    notes: List[str] = Field(default_factory=list, description="Implementation notes")
    safety: SafetyChecks = Field(..., description="Safety checks")

    @validator('timestamp_local')
    def validate_timestamp(cls, v):
        """Ensure timestamp has timezone info."""
        if v.tzinfo is None:
            raise ValueError("timestamp_local must include timezone information")
        return v


# Some downstream code and tests reference certain models without importing
# them explicitly.  To maintain backwards compatibility we expose these models
# via the ``builtins`` module so they are available as global names once this
# module is imported.
import builtins  # pragma: no cover - side effect for legacy support

for _name in ("PositionsContext", "MonitoringPlan", "SafetyChecks"):
    setattr(builtins, _name, globals()[_name])


# SQLAlchemy Database Models
Base = declarative_base()


class DBTradingRun(Base):
    """Database model for trading runs."""
    __tablename__ = "trading_runs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(50), unique=True, nullable=False, index=True)
    timestamp_local = Column(DateTime(timezone=True), nullable=False)
    schema_version = Column(Integer, nullable=False, default=1)
    universe_considered = Column(Text, nullable=False)  # JSON array
    cash_estimate = Column(String(50))
    notable_exposures = Column(Text)  # JSON array
    notes = Column(Text)  # JSON array
    safety_notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Relationships
    research_items = relationship("DBResearchItem", back_populates="trading_run")
    decisions = relationship("DBDecision", back_populates="trading_run")


class DBResearchItem(Base):
    """Database model for research items."""
    __tablename__ = "research_items"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(50), ForeignKey("trading_runs.run_id"), nullable=False)
    symbol = Column(String(10), nullable=False, index=True)
    thesis = Column(String(200), nullable=False)
    sentiment = Column(String(10), nullable=False)
    hype_score = Column(Float, nullable=False)
    catalyst = Column(String(20), nullable=False)
    liquidity_ok = Column(Boolean, nullable=False)
    sources_json = Column(Text, nullable=False)  # JSON array
    fundamentals_json = Column(Text, nullable=False)  # JSON object
    checks_json = Column(Text, nullable=False)  # JSON array
    risks_json = Column(Text, nullable=False)  # JSON array
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Relationships
    trading_run = relationship("DBTradingRun", back_populates="research_items")


class DBDecision(Base):
    """Database model for trading decisions."""
    __tablename__ = "decisions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(50), ForeignKey("trading_runs.run_id"), nullable=False)
    symbol = Column(String(10), nullable=False, index=True)
    action = Column(String(10), nullable=False)
    confidence = Column(Float, nullable=False)
    upside_downside_ratio = Column(Float, nullable=False)
    exp_return_brief = Column(String(100), nullable=False)
    order_plan_json = Column(Text)  # JSON object, nullable for no-trade
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Relationships
    trading_run = relationship("DBTradingRun", back_populates="decisions")


class DBOrder(Base):
    """Database model for order tracking."""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    op_id = Column(String(50), unique=True, nullable=False, index=True)  # Idempotency key
    run_id = Column(String(50), nullable=False)
    symbol = Column(String(10), nullable=False, index=True)
    action = Column(String(10), nullable=False)
    order_type = Column(String(10), nullable=False)
    quantity = Column(Integer, nullable=False)
    limit_price = Column(Float)
    stop_price = Column(Float)
    alpaca_order_id = Column(String(50), index=True)
    status = Column(String(20), nullable=False, default="pending")
    filled_qty = Column(Integer, default=0)
    filled_price = Column(Float)
    submitted_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    filled_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    
    
class DBPosition(Base):
    """Database model for position tracking."""
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    avg_cost = Column(Float, nullable=False)
    current_price = Column(Float)
    unrealized_pnl = Column(Float)
    stop_price = Column(Float)
    take_profit_price = Column(Float)
    entry_run_id = Column(String(50), nullable=False)
    opened_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    closed_at = Column(DateTime(timezone=True))


class DBEquityCurve(Base):
    """Database model for equity curve tracking."""
    __tablename__ = "equity_curve"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    total_equity = Column(Float, nullable=False)
    cash = Column(Float, nullable=False)
    positions_value = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, nullable=False)
    realized_pnl_daily = Column(Float, default=0.0)
    drawdown_pct = Column(Float, default=0.0)
    peak_equity = Column(Float, nullable=False)
    num_positions = Column(Integer, default=0)


class DBLog(Base):
    """Database model for structured logging."""
    __tablename__ = "logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    level = Column(String(10), nullable=False, index=True)
    logger = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    run_id = Column(String(50), index=True)
    symbol = Column(String(10), index=True)
    extra_json = Column(Text)  # JSON object for additional context


# Configuration Models
class LLMConfig(BaseModel):
    """LLM configuration settings."""
    model: str = Field(default="anthropic/claude-3-haiku")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4000, ge=100, le=8000)
    timeout_seconds: int = Field(default=30, ge=5, le=120)
    max_retries: int = Field(default=3, ge=1, le=10)
    fallback_models: List[str] = Field(default_factory=list)


class StrategyConfig(BaseModel):
    """Strategy configuration settings."""
    risk_per_position_pct: float = Field(default=0.75, ge=0.1, le=2.0)
    max_positions: int = Field(default=6, ge=1, le=20)
    hype_threshold_long: float = Field(default=0.70, ge=0.5, le=1.0)
    hype_threshold_short: float = Field(default=0.30, ge=0.0, le=0.5)
    confidence_threshold: float = Field(default=0.65, ge=0.5, le=1.0)
    min_price_usd: float = Field(default=5.0, ge=1.0, le=50.0)
    min_daily_volume: int = Field(default=1000000, ge=100000)
    max_bid_ask_spread_pct: float = Field(default=1.0, ge=0.1, le=5.0)
    earnings_lockout_days: int = Field(default=2, ge=0, le=10)
    drawdown_kill_switch_pct: float = Field(default=6.0, ge=1.0, le=20.0)


class AlpacaConfig(BaseModel):
    """Alpaca broker configuration."""
    api_key: str
    secret_key: str
    base_url: str = Field(default="https://paper-api.alpaca.markets")
    mode: Literal["paper", "live"] = Field(default="paper")


class SearchConfig(BaseModel):
    """Web search configuration."""
    recency_days: int = Field(default=7, ge=1, le=30)
    min_source_quality_score: float = Field(default=0.7, ge=0.0, le=1.0)
    allowed_publishers: List[str] = Field(default_factory=list)
    blocked_publishers: List[str] = Field(default_factory=list)

