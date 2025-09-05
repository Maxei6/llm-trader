"""
Tests for Pydantic models and schema validation.
"""

import pytest
from datetime import datetime, date
from pydantic import ValidationError

from llm_trader.models import (
    TradingDecision, ResearchItem, DecisionItem, SourceInfo,
    FundamentalsBrief, OrderPlan, PositionsContext, MonitoringPlan,
    SafetyChecks, SentimentType, CatalystType, ActionType, OrderType
)


class TestSourceInfo:
    """Test SourceInfo model."""
    
    def test_valid_source_info(self):
        """Test valid source info creation."""
        source = SourceInfo(
            title="Test Article",
            url="https://example.com/article",
            publisher="example.com",
            date=date(2024, 1, 15),
            takeaway="Key insight from article"
        )
        
        assert source.title == "Test Article"
        assert source.publisher == "example.com"
        assert source.takeaway == "Key insight from article"
    
    def test_takeaway_length_validation(self):
        """Test takeaway length validation."""
        with pytest.raises(ValidationError):
            SourceInfo(
                title="Test",
                url="https://example.com",
                publisher="example.com",
                date=date(2024, 1, 15),
                takeaway="This takeaway is way too long and exceeds the 30 character limit"
            )


class TestFundamentalsBrief:
    """Test FundamentalsBrief model."""
    
    def test_valid_fundamentals(self):
        """Test valid fundamentals creation."""
        fundamentals = FundamentalsBrief(
            mkt_cap="$10.5B",
            rev_ltm="$2.1B",
            growth_yoy="15.2%",
            margin_brief="Op: 12.5%",
            next_earnings=date(2024, 2, 15)
        )
        
        assert fundamentals.mkt_cap == "$10.5B"
        assert fundamentals.next_earnings == date(2024, 2, 15)
    
    def test_optional_fields(self):
        """Test optional fields."""
        fundamentals = FundamentalsBrief(
            mkt_cap="$10.5B",
            rev_ltm="$2.1B",
            growth_yoy="15.2%",
            margin_brief="Op: 12.5%"
        )
        
        assert fundamentals.next_earnings is None


class TestResearchItem:
    """Test ResearchItem model."""
    
    def test_valid_research_item(self):
        """Test valid research item creation."""
        sources = [
            SourceInfo(
                title="Test Article",
                url="https://example.com/1",
                publisher="example.com",
                date=date(2024, 1, 15),
                takeaway="Positive news"
            )
        ]
        
        fundamentals = FundamentalsBrief(
            mkt_cap="$10.5B",
            rev_ltm="$2.1B",
            growth_yoy="15.2%",
            margin_brief="Op: 12.5%"
        )
        
        research = ResearchItem(
            symbol="AAPL",
            sources=sources,
            fundamentals_brief=fundamentals,
            thesis="Strong momentum on product launch",
            sentiment=SentimentType.POSITIVE,
            hype_score=0.85,
            catalyst=CatalystType.PRODUCT,
            checks=["Volume spike", "Price breakout", "Analyst upgrades"],
            risks=["Market volatility", "Competition"],
            liquidity_ok=True
        )
        
        assert research.symbol == "AAPL"
        assert research.sentiment == SentimentType.POSITIVE
        assert research.hype_score == 0.85
        assert len(research.checks) == 3
        assert len(research.risks) == 2
    
    def test_hype_score_validation(self):
        """Test hype score range validation."""
        with pytest.raises(ValidationError):
            ResearchItem(
                symbol="AAPL",
                sources=[],
                fundamentals_brief=FundamentalsBrief(
                    mkt_cap="$10B", rev_ltm="$2B", 
                    growth_yoy="15%", margin_brief="Op: 12%"
                ),
                thesis="Test thesis",
                sentiment=SentimentType.POSITIVE,
                hype_score=1.5,  # Invalid: > 1.0
                catalyst=CatalystType.PRODUCT,
                checks=["Check 1", "Check 2", "Check 3"],
                risks=["Risk 1", "Risk 2"],
                liquidity_ok=True
            )
    
    def test_checks_count_validation(self):
        """Test checks count validation."""
        with pytest.raises(ValidationError):
            ResearchItem(
                symbol="AAPL",
                sources=[],
                fundamentals_brief=FundamentalsBrief(
                    mkt_cap="$10B", rev_ltm="$2B",
                    growth_yoy="15%", margin_brief="Op: 12%"
                ),
                thesis="Test thesis",
                sentiment=SentimentType.POSITIVE,
                hype_score=0.8,
                catalyst=CatalystType.PRODUCT,
                checks=["Only one check"],  # Invalid: < 3
                risks=["Risk 1", "Risk 2"],
                liquidity_ok=True
            )


class TestOrderPlan:
    """Test OrderPlan model."""
    
    def test_valid_order_plan(self):
        """Test valid order plan creation."""
        order_plan = OrderPlan(
            type=OrderType.LIMIT,
            entry_note="Breakout entry",
            limit_price=150.50,
            stop_logic="2% below entry",
            take_profit_logic="1.5R target",
            size_pct_equity=0.75,
            qty_estimate=100
        )
        
        assert order_plan.type == OrderType.LIMIT
        assert order_plan.limit_price == 150.50
        assert order_plan.size_pct_equity == 0.75
    
    def test_entry_note_length(self):
        """Test entry note length validation."""
        with pytest.raises(ValidationError):
            OrderPlan(
                type=OrderType.MARKET,
                entry_note="This entry note is way too long and exceeds the limit",
                stop_logic="2% stop",
                take_profit_logic="1.5R",
                size_pct_equity=0.5,
                qty_estimate=50
            )


class TestDecisionItem:
    """Test DecisionItem model."""
    
    def test_valid_long_decision(self):
        """Test valid long decision."""
        order_plan = OrderPlan(
            type=OrderType.MARKET,
            entry_note="Strong momentum",
            stop_logic="2% stop",
            take_profit_logic="1.5R",
            size_pct_equity=0.75,
            qty_estimate=100
        )
        
        decision = DecisionItem(
            symbol="AAPL",
            action=ActionType.LONG,
            confidence=0.85,
            upside_downside_ratio=1.8,
            exp_return_brief="15% upside potential",
            order_plan=order_plan
        )
        
        assert decision.action == ActionType.LONG
        assert decision.confidence == 0.85
        assert decision.order_plan is not None
    
    def test_no_trade_decision(self):
        """Test no-trade decision without order plan."""
        decision = DecisionItem(
            symbol="AAPL",
            action=ActionType.NO_TRADE,
            confidence=0.3,
            upside_downside_ratio=0.5,
            exp_return_brief="Insufficient conviction"
        )
        
        assert decision.action == ActionType.NO_TRADE
        assert decision.order_plan is None
    
    def test_trading_action_requires_order_plan(self):
        """Test that trading actions require order plan."""
        with pytest.raises(ValidationError):
            DecisionItem(
                symbol="AAPL",
                action=ActionType.LONG,
                confidence=0.85,
                upside_downside_ratio=1.8,
                exp_return_brief="Strong signal",
                order_plan=None  # Invalid: trading action needs order plan
            )


class TestTradingDecision:
    """Test complete TradingDecision model."""
    
    def create_sample_decision(self) -> TradingDecision:
        """Create a sample trading decision for testing."""
        from datetime import timezone
        
        source = SourceInfo(
            title="AAPL Earnings Beat",
            url="https://example.com/aapl-earnings",
            publisher="example.com",
            date=date(2024, 1, 15),
            takeaway="Strong Q4 results"
        )
        
        fundamentals = FundamentalsBrief(
            mkt_cap="$3.0T",
            rev_ltm="$400B",
            growth_yoy="8.5%",
            margin_brief="Op: 28.5%",
            next_earnings=date(2024, 4, 15)
        )
        
        research = ResearchItem(
            symbol="AAPL",
            sources=[source],
            fundamentals_brief=fundamentals,
            thesis="Strong earnings momentum continues",
            sentiment=SentimentType.POSITIVE,
            hype_score=0.85,
            catalyst=CatalystType.EARNINGS,
            checks=["Earnings beat", "Revenue growth", "Margin expansion"],
            risks=["Market volatility", "Valuation concerns"],
            liquidity_ok=True
        )
        
        order_plan = OrderPlan(
            type=OrderType.MARKET,
            entry_note="Earnings momentum",
            stop_logic="2% ATR stop",
            take_profit_logic="1.8R target",
            size_pct_equity=0.75,
            qty_estimate=50
        )
        
        decision_item = DecisionItem(
            symbol="AAPL",
            action=ActionType.LONG,
            confidence=0.85,
            upside_downside_ratio=1.8,
            exp_return_brief="Strong upside potential",
            order_plan=order_plan
        )
        
        positions_context = PositionsContext(
            cash_estimate="$50,000",
            notable_exposures=["TECH sector"]
        )
        
        monitoring = MonitoringPlan(
            interval="daily close",
            auto_exit=["sentiment flip", "stop breach"],
            review_checks=["earnings follow-through", "volume confirmation"],
            next_review_after_hours=24
        )
        
        safety = SafetyChecks(
            why_no_trade_if_any=None,
            drawdown_kill_switch_suggestion="pause if drawdown > 6%"
        )
        
        return TradingDecision(
            schema_version=1,
            run_id="test_run_123",
            timestamp_local=datetime.now(timezone.utc),
            universe_considered=["AAPL", "MSFT", "GOOGL"],
            positions_context=positions_context,
            research=[research],
            decision=[decision_item],
            monitoring=monitoring,
            notes=["Strong earnings season"],
            safety=safety
        )
    
    def test_valid_trading_decision(self):
        """Test valid complete trading decision."""
        decision = self.create_sample_decision()
        
        assert decision.schema_version == 1
        assert decision.run_id == "test_run_123"
        assert len(decision.research) == 1
        assert len(decision.decision) == 1
        assert decision.research[0].symbol == "AAPL"
        assert decision.decision[0].action == ActionType.LONG
    
    def test_timestamp_timezone_validation(self):
        """Test that timestamp must have timezone info."""
        decision_data = self.create_sample_decision().dict()
        decision_data["timestamp_local"] = datetime(2024, 1, 15, 10, 30)  # No timezone
        
        with pytest.raises(ValidationError):
            TradingDecision(**decision_data)


class TestEnums:
    """Test enum validations."""
    
    def test_sentiment_type_values(self):
        """Test SentimentType enum values."""
        assert SentimentType.POSITIVE == "positive"
        assert SentimentType.NEGATIVE == "negative"
        assert SentimentType.NEUTRAL == "neutral"
    
    def test_catalyst_type_values(self):
        """Test CatalystType enum values."""
        assert CatalystType.EARNINGS == "earnings"
        assert CatalystType.PRODUCT == "product"
        assert CatalystType.MA == "M&A"
    
    def test_action_type_values(self):
        """Test ActionType enum values."""
        assert ActionType.LONG == "long"
        assert ActionType.SHORT == "short"
        assert ActionType.NO_TRADE == "no-trade"
    
    def test_order_type_values(self):
        """Test OrderType enum values."""
        assert OrderType.MARKET == "market"
        assert OrderType.LIMIT == "limit"


if __name__ == "__main__":
    pytest.main([__file__])

