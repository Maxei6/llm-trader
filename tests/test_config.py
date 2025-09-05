"""
Tests for configuration management.
"""

import pytest
import os
from unittest.mock import patch

from llm_trader.config import Settings, AgentConfig
from llm_trader.models import LLMConfig, StrategyConfig, AlpacaConfig, SearchConfig


class TestSettings:
    """Test Settings configuration."""
    
    def test_default_values(self):
        """Test default configuration values."""
        with patch.dict(os.environ, {}, clear=True):
            # Set required values
            os.environ.update({
                "OPENROUTER_API_KEY": "test_key",
                "ALPACA_API_KEY": "test_alpaca_key",
                "ALPACA_SECRET_KEY": "test_alpaca_secret"
            })
            
            settings = Settings()
            
            assert settings.llm_model == "anthropic/claude-3-haiku"
            assert settings.llm_temperature == 0.1
            assert settings.risk_per_position_pct == 0.75
            assert settings.max_positions == 6
            assert settings.loop_interval_seconds == 300
            assert settings.timezone == "America/New_York"
    
    def test_environment_override(self):
        """Test environment variable override."""
        with patch.dict(os.environ, {
            "OPENROUTER_API_KEY": "test_key",
            "ALPACA_API_KEY": "test_alpaca_key", 
            "ALPACA_SECRET_KEY": "test_alpaca_secret",
            "LLM_MODEL": "openai/gpt-4",
            "RISK_PER_POSITION_PCT": "1.0",
            "MAX_POSITIONS": "10",
            "TIMEZONE": "UTC"
        }):
            settings = Settings()
            
            assert settings.llm_model == "openai/gpt-4"
            assert settings.risk_per_position_pct == 1.0
            assert settings.max_positions == 10
            assert settings.timezone == "UTC"
    
    def test_llm_config_property(self):
        """Test LLM config property."""
        with patch.dict(os.environ, {
            "OPENROUTER_API_KEY": "test_key",
            "ALPACA_API_KEY": "test_alpaca_key",
            "ALPACA_SECRET_KEY": "test_alpaca_secret",
            "LLM_MODEL": "test-model",
            "LLM_TEMPERATURE": "0.5",
            "LLM_MAX_TOKENS": "2000",
            "LLM_FALLBACK_MODELS": "model1,model2"
        }):
            settings = Settings()
            llm_config = settings.llm_config
            
            assert isinstance(llm_config, LLMConfig)
            assert llm_config.model == "test-model"
            assert llm_config.temperature == 0.5
            assert llm_config.max_tokens == 2000
            assert llm_config.fallback_models == ["model1", "model2"]
    
    def test_strategy_config_property(self):
        """Test strategy config property."""
        with patch.dict(os.environ, {
            "OPENROUTER_API_KEY": "test_key",
            "ALPACA_API_KEY": "test_alpaca_key",
            "ALPACA_SECRET_KEY": "test_alpaca_secret",
            "RISK_PER_POSITION_PCT": "1.5",
            "MAX_POSITIONS": "8",
            "HYPE_THRESHOLD_LONG": "0.8",
            "MIN_PRICE_USD": "10.0"
        }):
            settings = Settings()
            strategy_config = settings.strategy_config
            
            assert isinstance(strategy_config, StrategyConfig)
            assert strategy_config.risk_per_position_pct == 1.5
            assert strategy_config.max_positions == 8
            assert strategy_config.hype_threshold_long == 0.8
            assert strategy_config.min_price_usd == 10.0
    
    def test_alpaca_config_property(self):
        """Test Alpaca config property."""
        with patch.dict(os.environ, {
            "OPENROUTER_API_KEY": "test_key",
            "ALPACA_API_KEY": "test_alpaca_key",
            "ALPACA_SECRET_KEY": "test_alpaca_secret",
            "ALPACA_BASE_URL": "https://api.alpaca.markets",
            "ALPACA_MODE": "live"
        }):
            settings = Settings()
            alpaca_config = settings.alpaca_config
            
            assert isinstance(alpaca_config, AlpacaConfig)
            assert alpaca_config.api_key == "test_alpaca_key"
            assert alpaca_config.secret_key == "test_alpaca_secret"
            assert alpaca_config.base_url == "https://api.alpaca.markets"
            assert alpaca_config.mode == "live"
    
    def test_search_config_property(self):
        """Test search config property."""
        with patch.dict(os.environ, {
            "OPENROUTER_API_KEY": "test_key",
            "ALPACA_API_KEY": "test_alpaca_key",
            "ALPACA_SECRET_KEY": "test_alpaca_secret",
            "SEARCH_RECENCY_DAYS": "14",
            "ALLOWED_PUBLISHERS": "reuters.com,bloomberg.com",
            "BLOCKED_PUBLISHERS": "reddit.com,twitter.com"
        }):
            settings = Settings()
            search_config = settings.search_config
            
            assert isinstance(search_config, SearchConfig)
            assert search_config.recency_days == 14
            assert search_config.allowed_publishers == ["reuters.com", "bloomberg.com"]
            assert search_config.blocked_publishers == ["reddit.com", "twitter.com"]


class TestAgentConfig:
    """Test AgentConfig prompts and templates."""
    
    def test_system_prompt_exists(self):
        """Test system prompt is defined."""
        prompt = AgentConfig.get_system_prompt()
        
        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert "momentum" in prompt.lower()
        assert "strategy" in prompt.lower()
    
    def test_run_template_exists(self):
        """Test run template is defined."""
        template = AgentConfig.get_run_template()
        
        assert isinstance(template, str)
        assert "{timezone}" in template
        assert "{timestamp_local}" in template
        assert "{cash_estimate}" in template
        assert "{focus_tickers}" in template
    
    def test_repair_prompt_exists(self):
        """Test repair prompt is defined."""
        prompt = AgentConfig.get_repair_prompt()
        
        assert isinstance(prompt, str)
        assert "{errors}" in prompt
        assert "{original_json}" in prompt
    
    def test_format_run_prompt(self):
        """Test run prompt formatting."""
        formatted = AgentConfig.format_run_prompt(
            timezone="America/New_York",
            timestamp_local="2024-01-15 10:30:00",
            cash_estimate="$50,000",
            notable_exposures=["TECH"],
            num_positions=2,
            max_positions=6,
            focus_tickers=["AAPL", "MSFT"],
            risk_per_position_pct=0.75,
            hype_threshold_long=0.70,
            hype_threshold_short=0.30,
            confidence_threshold=0.65,
            min_price_usd=5.0,
            min_daily_volume=1000000,
            max_bid_ask_spread_pct=1.0,
            earnings_lockout_days=2
        )
        
        assert "America/New_York" in formatted
        assert "2024-01-15 10:30:00" in formatted
        assert "$50,000" in formatted
        assert "AAPL, MSFT" in formatted
        assert "0.75%" in formatted
        assert "2/6" in formatted


class TestConfigValidation:
    """Test configuration validation."""
    
    def test_valid_risk_parameters(self):
        """Test valid risk parameter ranges."""
        with patch.dict(os.environ, {
            "OPENROUTER_API_KEY": "test_key",
            "ALPACA_API_KEY": "test_alpaca_key",
            "ALPACA_SECRET_KEY": "test_alpaca_secret",
            "RISK_PER_POSITION_PCT": "0.5"
        }):
            settings = Settings()
            strategy_config = settings.strategy_config
            
            assert 0.1 <= strategy_config.risk_per_position_pct <= 2.0
    
    def test_valid_hype_thresholds(self):
        """Test valid hype threshold ranges."""
        with patch.dict(os.environ, {
            "OPENROUTER_API_KEY": "test_key",
            "ALPACA_API_KEY": "test_alpaca_key",
            "ALPACA_SECRET_KEY": "test_alpaca_secret",
            "HYPE_THRESHOLD_LONG": "0.75",
            "HYPE_THRESHOLD_SHORT": "0.25"
        }):
            settings = Settings()
            strategy_config = settings.strategy_config
            
            assert 0.5 <= strategy_config.hype_threshold_long <= 1.0
            assert 0.0 <= strategy_config.hype_threshold_short <= 0.5
    
    def test_valid_llm_parameters(self):
        """Test valid LLM parameter ranges."""
        with patch.dict(os.environ, {
            "OPENROUTER_API_KEY": "test_key",
            "ALPACA_API_KEY": "test_alpaca_key",
            "ALPACA_SECRET_KEY": "test_alpaca_secret",
            "LLM_TEMPERATURE": "0.2",
            "LLM_MAX_TOKENS": "3000"
        }):
            settings = Settings()
            llm_config = settings.llm_config
            
            assert 0.0 <= llm_config.temperature <= 2.0
            assert 100 <= llm_config.max_tokens <= 8000


class TestConfigIntegration:
    """Test configuration integration."""
    
    def test_config_consistency(self):
        """Test configuration consistency across modules."""
        with patch.dict(os.environ, {
            "OPENROUTER_API_KEY": "test_key",
            "ALPACA_API_KEY": "test_alpaca_key",
            "ALPACA_SECRET_KEY": "test_alpaca_secret"
        }):
            from llm_trader.config import settings, llm_config, strategy_config
            
            # Test that global configs match settings properties
            assert llm_config.model == settings.llm_model
            assert strategy_config.risk_per_position_pct == settings.risk_per_position_pct
    
    def test_missing_required_keys(self):
        """Test behavior with missing required API keys."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(Exception):  # Should fail validation
                Settings()


if __name__ == "__main__":
    pytest.main([__file__])

