"""
Centralized configuration for LLM Trader with Pydantic Settings.
All prompts, model configs, and thresholds are managed here.
"""

from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_core import ValidationError

from .models import LLMConfig, StrategyConfig, AlpacaConfig, SearchConfig


class Settings(BaseSettings):
    """Main application settings with environment variable support."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # OpenRouter Configuration
    openrouter_api_key: str = Field(..., description="OpenRouter API key")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter base URL"
    )
    
    # Alpaca Configuration
    alpaca_api_key: str = Field(..., description="Alpaca API key")
    alpaca_secret_key: str = Field(..., description="Alpaca secret key")
    alpaca_base_url: str = Field(
        default="https://paper-api.alpaca.markets",
        description="Alpaca base URL"
    )
    alpaca_mode: str = Field(default="paper", description="Trading mode")
    
    # Database Configuration
    database_url: str = Field(
        default="sqlite:///./llm_trader.db",
        description="Database connection URL"
    )
    database_wal_mode: bool = Field(default=True, description="Enable WAL mode")
    
    # Strategy Configuration
    risk_per_position_pct: float = Field(default=0.75, description="Risk per position %")
    max_positions: int = Field(default=6, description="Maximum positions")
    hype_threshold_long: float = Field(default=0.70, description="Long hype threshold")
    hype_threshold_short: float = Field(default=0.30, description="Short hype threshold")
    confidence_threshold: float = Field(default=0.65, description="Confidence threshold")
    min_price_usd: float = Field(default=5.0, description="Minimum price USD")
    min_daily_volume: int = Field(default=1000000, description="Minimum daily volume")
    max_bid_ask_spread_pct: float = Field(default=1.0, description="Max bid-ask spread %")
    earnings_lockout_days: int = Field(default=2, description="Earnings lockout days")
    drawdown_kill_switch_pct: float = Field(default=6.0, description="Drawdown kill switch %")
    
    # LLM Configuration
    llm_model: str = Field(default="anthropic/claude-3-haiku", description="LLM model")
    llm_temperature: float = Field(default=0.1, description="LLM temperature")
    llm_max_tokens: int = Field(default=4000, description="LLM max tokens")
    llm_timeout_seconds: int = Field(default=30, description="LLM timeout")
    llm_max_retries: int = Field(default=3, description="LLM max retries")
    llm_fallback_models: str = Field(
        default="openai/gpt-3.5-turbo,meta-llama/llama-2-70b-chat",
        description="Comma-separated fallback models"
    )
    
    # Loop Configuration
    loop_interval_seconds: int = Field(default=300, description="Loop interval seconds")
    dashboard_refresh_seconds: int = Field(default=5, description="Dashboard refresh")
    market_hours_only: bool = Field(default=True, description="Trade only in market hours")
    timezone: str = Field(default="America/New_York", description="Trading timezone")
    
    # Search Configuration
    search_recency_days: int = Field(default=7, description="Search recency days")
    min_source_quality_score: float = Field(default=0.7, description="Min source quality")
    allowed_publishers: str = Field(
        default="reuters.com,bloomberg.com,wsj.com,cnbc.com,marketwatch.com,yahoo.com,sec.gov",
        description="Comma-separated allowed publishers"
    )
    blocked_publishers: str = Field(
        default="reddit.com,twitter.com,stocktwits.com",
        description="Comma-separated blocked publishers"
    )
    
    # Logging Configuration
    log_level: str = Field(default="INFO", description="Log level")
    log_file: str = Field(default="llm_trader.log", description="Log file path")
    log_rotation: str = Field(default="10 MB", description="Log rotation size")
    log_retention: str = Field(default="30 days", description="Log retention period")
    
    # Development Configuration
    debug: bool = Field(default=False, description="Debug mode")
    enable_metrics: bool = Field(default=True, description="Enable metrics")
    enable_backtesting: bool = Field(default=False, description="Enable backtesting")
    
    @property
    def llm_config(self) -> LLMConfig:
        """Get LLM configuration object."""
        return LLMConfig(
            model=self.llm_model,
            temperature=self.llm_temperature,
            max_tokens=self.llm_max_tokens,
            timeout_seconds=self.llm_timeout_seconds,
            max_retries=self.llm_max_retries,
            fallback_models=self.llm_fallback_models.split(",") if self.llm_fallback_models else []
        )
    
    @property
    def strategy_config(self) -> StrategyConfig:
        """Get strategy configuration object."""
        return StrategyConfig(
            risk_per_position_pct=self.risk_per_position_pct,
            max_positions=self.max_positions,
            hype_threshold_long=self.hype_threshold_long,
            hype_threshold_short=self.hype_threshold_short,
            confidence_threshold=self.confidence_threshold,
            min_price_usd=self.min_price_usd,
            min_daily_volume=self.min_daily_volume,
            max_bid_ask_spread_pct=self.max_bid_ask_spread_pct,
            earnings_lockout_days=self.earnings_lockout_days,
            drawdown_kill_switch_pct=self.drawdown_kill_switch_pct
        )
    
    @property
    def alpaca_config(self) -> AlpacaConfig:
        """Get Alpaca configuration object."""
        return AlpacaConfig(
            api_key=self.alpaca_api_key,
            secret_key=self.alpaca_secret_key,
            base_url=self.alpaca_base_url,
            mode=self.alpaca_mode
        )
    
    @property
    def search_config(self) -> SearchConfig:
        """Get search configuration object."""
        return SearchConfig(
            recency_days=self.search_recency_days,
            min_source_quality_score=self.min_source_quality_score,
            allowed_publishers=self.allowed_publishers.split(",") if self.allowed_publishers else [],
            blocked_publishers=self.blocked_publishers.split(",") if self.blocked_publishers else []
        )


class AgentConfig:
    """LLM Agent configuration with prompts and templates."""
    
    SYSTEM_PROMPT = """You are an expert financial analyst and quantitative trader specializing in momentum and event-driven strategies.

Your role is to analyze market news, sentiment, and company events to identify high-conviction trading opportunities with strict risk management.

STRATEGY: Hype & Event Momentum
- Focus on stocks with significant news catalysts and momentum
- Long positions when sentiment is positive with high hype scores (≥0.70)
- Short positions when sentiment is negative with low hype scores (≤0.30)
- No trade otherwise

ANALYSIS REQUIREMENTS:
1. Scan recent credible news sources for each symbol
2. Identify the primary catalyst driving momentum
3. Assess sentiment and calculate hype score based on volume and tone
4. Verify all quantitative gates are met
5. Provide evidence with specific sources and dates

QUANTITATIVE GATES (ALL MUST PASS):
- Price ≥ $5 USD (no penny stocks)
- Average daily volume ≥ 1,000,000 shares
- Bid-ask spread ≤ 1%
- Not within 2 trading days of earnings (unless earnings is the catalyst)
- Sufficient liquidity for position size

RISK MANAGEMENT:
- Risk per position: 0.5-0.75% of equity
- Initial stop: 2× ATR(14) from entry
- Take profit: 1.5-2.0× risk or trailing ATR
- Maximum 6 positions
- Kill switch if drawdown > 6%

OUTPUT FORMAT:
You MUST return ONLY valid JSON following the exact schema provided. No additional text, explanations, or markdown formatting.

If any quantitative gate fails or evidence is insufficient, return no-trade with a brief reason in the safety section.

Be conservative and thorough. Quality over quantity. Only trade when you have high confidence."""

    RUN_TEMPLATE = """TRADING ANALYSIS REQUEST

Server Timezone: {timezone}
Current Time: {timestamp_local}

PORTFOLIO CONTEXT:
Cash Estimate: {cash_estimate}
Notable Exposures: {notable_exposures}
Current Positions: {num_positions}/{max_positions}

UNIVERSE TO ANALYZE:
{focus_tickers}

RISK PARAMETERS:
- Risk per position: {risk_per_position_pct}% of equity
- Max positions: {max_positions}
- Hype threshold (long): {hype_threshold_long}
- Hype threshold (short): {hype_threshold_short}
- Confidence threshold: {confidence_threshold}
- Min price: ${min_price_usd}
- Min daily volume: {min_daily_volume:,} shares
- Max spread: {max_bid_ask_spread_pct}%
- Earnings lockout: {earnings_lockout_days} days

INSTRUCTIONS:
1. Research each symbol for recent news and catalysts
2. Apply all quantitative gates strictly
3. Calculate sentiment and hype scores
4. Make trading decisions based on strategy rules
5. Return ONLY valid JSON - no other text

Focus on quality analysis with credible sources. Be conservative with position sizing and risk management."""

    REPAIR_PROMPT = """The JSON you provided has validation errors. Please fix the following issues and return ONLY the corrected JSON:

ERRORS:
{errors}

ORIGINAL JSON:
{original_json}

Return the corrected JSON with no additional text or formatting."""

    @classmethod
    def get_system_prompt(cls) -> str:
        """Get the system prompt for the LLM agent."""
        return cls.SYSTEM_PROMPT
    
    @classmethod
    def get_run_template(cls) -> str:
        """Get the run template for formatting requests."""
        return cls.RUN_TEMPLATE
    
    @classmethod
    def get_repair_prompt(cls) -> str:
        """Get the repair prompt for JSON validation errors."""
        return cls.REPAIR_PROMPT
    
    @classmethod
    def format_run_prompt(
        cls,
        timezone: str,
        timestamp_local: str,
        cash_estimate: str,
        notable_exposures: List[str],
        num_positions: int,
        max_positions: int,
        focus_tickers: List[str],
        risk_per_position_pct: float,
        hype_threshold_long: float,
        hype_threshold_short: float,
        confidence_threshold: float,
        min_price_usd: float,
        min_daily_volume: int,
        max_bid_ask_spread_pct: float,
        earnings_lockout_days: int
    ) -> str:
        """Format the run prompt with current context."""
        focus_str = ", ".join(focus_tickers) if focus_tickers else "Market scan (top movers, news-driven stocks)"
        exposures_str = ", ".join(notable_exposures) if notable_exposures else "None"
        
        return cls.RUN_TEMPLATE.format(
            timezone=timezone,
            timestamp_local=timestamp_local,
            cash_estimate=cash_estimate,
            notable_exposures=exposures_str,
            num_positions=num_positions,
            max_positions=max_positions,
            focus_tickers=focus_str,
            risk_per_position_pct=risk_per_position_pct,
            hype_threshold_long=hype_threshold_long,
            hype_threshold_short=hype_threshold_short,
            confidence_threshold=confidence_threshold,
            min_price_usd=min_price_usd,
            min_daily_volume=min_daily_volume,
            max_bid_ask_spread_pct=max_bid_ask_spread_pct,
            earnings_lockout_days=earnings_lockout_days
        )


# Global settings instance
#
# Importing :class:`Settings` at module import time previously raised a
# ``ValidationError`` when the required environment variables (API keys) were
# absent, which happens in the test environment.  To make the module robust we
# attempt to create the settings and fall back to a dummy configuration when the
# real credentials are not supplied.  This keeps downstream imports simple while
# still allowing tests to provide their own environment via `Settings()`.
try:  # pragma: no cover - exercised indirectly
    settings = Settings()
except ValidationError:  # pragma: no cover - missing env vars
    settings = Settings(
        openrouter_api_key="test",
        alpaca_api_key="test",
        alpaca_secret_key="test",
    )

# Export commonly used configs derived from the settings instance
llm_config = settings.llm_config
strategy_config = settings.strategy_config
alpaca_config = settings.alpaca_config
search_config = settings.search_config
agent_config = AgentConfig()

