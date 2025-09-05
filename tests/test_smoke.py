"""
Smoke tests for end-to-end integration with mocked external services.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, date

from llm_trader.models import TradingDecision, ResearchItem, DecisionItem, ActionType
from llm_trader.runner import TradingRunner
from llm_trader.llm_agent import LLMAgent
from llm_trader.alpaca_client import AlpacaClient, AlpacaAccount, AlpacaPosition
from llm_trader.store import DatabaseStore


class TestSmokeIntegration:
    """Smoke tests for full system integration."""
    
    @pytest.fixture
    def mock_account(self):
        """Mock Alpaca account."""
        return AlpacaAccount(
            equity=100000.0,
            cash=50000.0,
            buying_power=100000.0,
            portfolio_value=100000.0,
            day_trade_count=0,
            pattern_day_trader=False
        )
    
    @pytest.fixture
    def mock_positions(self):
        """Mock Alpaca positions."""
        return [
            AlpacaPosition(
                symbol="AAPL",
                quantity=100,
                avg_cost=150.0,
                current_price=155.0,
                unrealized_pnl=500.0,
                market_value=15500.0,
                side="long"
            )
        ]
    
    @pytest.fixture
    def mock_trading_decision(self):
        """Mock trading decision from LLM."""
        from llm_trader.models import (
            SourceInfo, FundamentalsBrief, OrderPlan, PositionsContext,
            MonitoringPlan, SafetyChecks, SentimentType, CatalystType, OrderType
        )
        
        source = SourceInfo(
            title="MSFT Strong Earnings",
            url="https://example.com/msft-earnings",
            publisher="example.com",
            date=date(2024, 1, 15),
            takeaway="Beat expectations"
        )
        
        fundamentals = FundamentalsBrief(
            mkt_cap="$2.8T",
            rev_ltm="$200B",
            growth_yoy="12%",
            margin_brief="Op: 35%"
        )
        
        research = ResearchItem(
            symbol="MSFT",
            sources=[source],
            fundamentals_brief=fundamentals,
            thesis="Strong cloud growth momentum",
            sentiment=SentimentType.POSITIVE,
            hype_score=0.85,
            catalyst=CatalystType.EARNINGS,
            checks=["Earnings beat", "Cloud growth", "Margin expansion"],
            risks=["Market volatility", "Competition"],
            liquidity_ok=True
        )
        
        order_plan = OrderPlan(
            type=OrderType.MARKET,
            entry_note="Earnings momentum",
            stop_logic="2% stop",
            take_profit_logic="1.5R",
            size_pct_equity=0.75,
            qty_estimate=25
        )
        
        decision_item = DecisionItem(
            symbol="MSFT",
            action=ActionType.LONG,
            confidence=0.85,
            upside_downside_ratio=1.8,
            exp_return_brief="Strong upside",
            order_plan=order_plan
        )
        
        return TradingDecision(
            schema_version=1,
            run_id="smoke_test_123",
            timestamp_local=datetime.now(timezone.utc),
            universe_considered=["MSFT", "AAPL", "GOOGL"],
            positions_context=PositionsContext(
                cash_estimate="$50,000",
                notable_exposures=["TECH"]
            ),
            research=[research],
            decision=[decision_item],
            monitoring=MonitoringPlan(
                auto_exit=["sentiment flip"],
                review_checks=["earnings follow-through"]
            ),
            notes=["Strong earnings season"],
            safety=SafetyChecks(
                drawdown_kill_switch_suggestion="pause if drawdown > 6%"
            )
        )
    
    @pytest.mark.asyncio
    async def test_full_trading_cycle_mock(
        self, 
        mock_account, 
        mock_positions, 
        mock_trading_decision
    ):
        """Test full trading cycle with mocked services."""
        
        # Mock external dependencies
        with patch('llm_trader.store.DatabaseStore') as mock_store_class, \
             patch('llm_trader.alpaca_client.AlpacaClient') as mock_alpaca_class, \
             patch('llm_trader.llm_agent.LLMAgent') as mock_llm_class, \
             patch('llm_trader.tools.market_data') as mock_market_data:
            
            # Setup mocks
            mock_store = AsyncMock()
            mock_store_class.return_value = mock_store
            
            mock_alpaca = AsyncMock()
            mock_alpaca_class.return_value = mock_alpaca
            mock_alpaca.get_account.return_value = mock_account
            mock_alpaca.get_positions.return_value = mock_positions
            mock_alpaca.is_market_open.return_value = True
            
            mock_llm = AsyncMock()
            mock_llm_class.return_value.__aenter__.return_value = mock_llm
            mock_llm.generate_decision.return_value = mock_trading_decision
            
            # Mock market data
            mock_quote = MagicMock()
            mock_quote.price = 380.0
            mock_market_data.get_quote.return_value = mock_quote
            
            # Mock store methods
            mock_store.store_trading_decision.return_value = True
            mock_store.update_equity_curve.return_value = True
            mock_store.get_equity_curve.return_value = []
            mock_store.get_recent_orders.return_value = []
            mock_store.cleanup_old_data.return_value = True
            
            # Mock executor methods
            with patch('llm_trader.executor.OrderExecutor') as mock_executor_class:
                mock_executor = AsyncMock()
                mock_executor_class.return_value = mock_executor
                mock_executor.execute_decision.return_value = MagicMock(
                    op_id="test_op_123",
                    status="submitted",
                    order_id="alpaca_order_456"
                )
                mock_executor.update_order_status.return_value = None
                mock_executor.cleanup_stale_operations.return_value = None
                
                # Create and run trading cycle
                runner = TradingRunner()
                success = await runner.run_once(focus_tickers=["MSFT"])
                
                # Verify the cycle completed successfully
                assert success is True
                
                # Verify key interactions
                mock_alpaca.get_account.assert_called_once()
                mock_alpaca.get_positions.assert_called_once()
                mock_llm.generate_decision.assert_called_once()
                mock_store.store_trading_decision.assert_called_once()
                mock_store.update_equity_curve.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_no_trade_decision(self, mock_account, mock_positions):
        """Test handling of no-trade decisions."""
        
        # Create no-trade decision
        no_trade_decision = TradingDecision(
            schema_version=1,
            run_id="no_trade_test",
            timestamp_local=datetime.now(timezone.utc),
            universe_considered=["AAPL"],
            positions_context=PositionsContext(cash_estimate="$50,000"),
            research=[],
            decision=[
                DecisionItem(
                    symbol="AAPL",
                    action=ActionType.NO_TRADE,
                    confidence=0.3,
                    upside_downside_ratio=0.5,
                    exp_return_brief="Insufficient signal"
                )
            ],
            monitoring=MonitoringPlan(
                auto_exit=[],
                review_checks=[]
            ),
            notes=[],
            safety=SafetyChecks(
                why_no_trade_if_any="Low confidence",
                drawdown_kill_switch_suggestion="pause if drawdown > 6%"
            )
        )
        
        with patch('llm_trader.store.DatabaseStore') as mock_store_class, \
             patch('llm_trader.alpaca_client.AlpacaClient') as mock_alpaca_class, \
             patch('llm_trader.llm_agent.LLMAgent') as mock_llm_class:
            
            # Setup mocks
            mock_store = AsyncMock()
            mock_store_class.return_value = mock_store
            
            mock_alpaca = AsyncMock()
            mock_alpaca_class.return_value = mock_alpaca
            mock_alpaca.get_account.return_value = mock_account
            mock_alpaca.get_positions.return_value = []
            mock_alpaca.is_market_open.return_value = True
            
            mock_llm = AsyncMock()
            mock_llm_class.return_value.__aenter__.return_value = mock_llm
            mock_llm.generate_decision.return_value = no_trade_decision
            
            mock_store.store_trading_decision.return_value = True
            mock_store.update_equity_curve.return_value = True
            mock_store.get_equity_curve.return_value = []
            mock_store.get_recent_orders.return_value = []
            
            with patch('llm_trader.executor.OrderExecutor') as mock_executor_class:
                mock_executor = AsyncMock()
                mock_executor_class.return_value = mock_executor
                
                runner = TradingRunner()
                success = await runner.run_once()
                
                # Should succeed even with no trades
                assert success is True
                
                # Should not execute any orders
                mock_executor.execute_decision.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_error_handling(self, mock_account):
        """Test error handling in trading cycle."""
        
        with patch('llm_trader.store.DatabaseStore') as mock_store_class, \
             patch('llm_trader.alpaca_client.AlpacaClient') as mock_alpaca_class, \
             patch('llm_trader.llm_agent.LLMAgent') as mock_llm_class:
            
            # Setup mocks with failures
            mock_store = AsyncMock()
            mock_store_class.return_value = mock_store
            
            mock_alpaca = AsyncMock()
            mock_alpaca_class.return_value = mock_alpaca
            mock_alpaca.get_account.side_effect = Exception("Connection failed")
            
            mock_llm = AsyncMock()
            mock_llm_class.return_value.__aenter__.return_value = mock_llm
            
            with patch('llm_trader.executor.OrderExecutor') as mock_executor_class:
                mock_executor = AsyncMock()
                mock_executor_class.return_value = mock_executor
                
                runner = TradingRunner()
                success = await runner.run_once()
                
                # Should handle error gracefully
                assert success is False
                assert runner.consecutive_errors == 1
    
    @pytest.mark.asyncio
    async def test_kill_switch_activation(self, mock_account, mock_positions):
        """Test kill switch activation on high drawdown."""
        
        # Mock high drawdown scenario
        equity_data = [
            {"total_equity": 120000.0},  # Peak
            {"total_equity": 110000.0},  # Current (8.3% drawdown)
        ]
        
        with patch('llm_trader.store.DatabaseStore') as mock_store_class, \
             patch('llm_trader.alpaca_client.AlpacaClient') as mock_alpaca_class:
            
            mock_store = AsyncMock()
            mock_store_class.return_value = mock_store
            mock_store.get_equity_curve.return_value = equity_data
            
            mock_alpaca = AsyncMock()
            mock_alpaca_class.return_value = mock_alpaca
            mock_alpaca.get_account.return_value = AlpacaAccount(
                equity=110000.0,  # Current equity showing drawdown
                cash=50000.0,
                buying_power=100000.0,
                portfolio_value=110000.0,
                day_trade_count=0,
                pattern_day_trader=False
            )
            mock_alpaca.get_positions.return_value = mock_positions
            mock_alpaca.is_market_open.return_value = True
            
            mock_store.update_equity_curve.return_value = True
            mock_store.get_recent_orders.return_value = []
            
            with patch('llm_trader.executor.OrderExecutor') as mock_executor_class:
                mock_executor = AsyncMock()
                mock_executor_class.return_value = mock_executor
                
                runner = TradingRunner()
                
                # Test kill switch check
                kill_switch_active = await runner._check_kill_switch(110000.0)
                
                # Should activate kill switch (8.3% > 6% threshold)
                assert kill_switch_active is True


class TestComponentIntegration:
    """Test integration between major components."""
    
    @pytest.mark.asyncio
    async def test_llm_agent_json_validation(self):
        """Test LLM agent JSON validation with mock response."""
        
        # Mock valid JSON response
        valid_json = {
            "schema_version": 1,
            "run_id": "test_123",
            "timestamp_local": "2024-01-15T10:30:00+00:00",
            "universe_considered": ["AAPL"],
            "positions_context": {
                "cash_estimate": "$50,000",
                "notable_exposures": []
            },
            "research": [],
            "decision": [],
            "monitoring": {
                "auto_exit": [],
                "review_checks": []
            },
            "notes": [],
            "safety": {
                "drawdown_kill_switch_suggestion": "pause if drawdown > 6%"
            }
        }
        
        with patch('llm_trader.llm_agent.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            # Mock successful API response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{
                    "message": {
                        "content": f"```json\n{valid_json}\n```"
                    }
                }],
                "usage": {"total_tokens": 1000}
            }
            mock_client.post.return_value = mock_response
            
            agent = LLMAgent()
            
            # Test decision generation
            decision = await agent.generate_decision(
                focus_tickers=["AAPL"],
                cash_estimate="$50,000"
            )
            
            assert decision is not None
            assert decision.run_id is not None
            assert decision.schema_version == 1
    
    @pytest.mark.asyncio
    async def test_database_store_operations(self):
        """Test database store operations with in-memory database."""
        
        # Use in-memory SQLite for testing
        with patch('llm_trader.config.settings') as mock_settings:
            mock_settings.database_url = "sqlite:///:memory:"
            mock_settings.database_wal_mode = False
            mock_settings.debug = False
            
            store = DatabaseStore()
            
            # Test basic operations
            success = await store.update_equity_curve(
                total_equity=100000.0,
                cash=50000.0,
                positions_value=50000.0,
                unrealized_pnl=0.0
            )
            
            assert success is True
            
            # Test equity curve retrieval
            equity_data = await store.get_equity_curve(days=1)
            assert len(equity_data) >= 1
            assert equity_data[0]["total_equity"] == 100000.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

