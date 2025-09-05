"""
Main trading loop runner with graceful shutdown and exponential backoff.
"""

import asyncio
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from loguru import logger

from .config import settings, strategy_config
from .utils import now_local, create_run_id, format_currency

# Import modules rather than classes to make it easier to patch individual
# components in tests.  The test suite replaces these classes/functions at the
# module level (e.g. ``llm_trader.alpaca_client.AlpacaClient``), so importing the
# modules here ensures the patches are respected.
from . import alpaca_client, llm_agent, store, executor, tools


class TradingRunner:
    """
    Main trading loop runner with comprehensive error handling.
    
    Manages the continuous trading loop, market hours checking,
    graceful shutdown, and exponential backoff on errors.
    """
    
    def __init__(self):
        self.running = False
        self.shutdown_requested = False
        
        # Initialize components
        self.store = store.DatabaseStore()
        self.alpaca = alpaca_client.AlpacaClient()
        self.executor = executor.OrderExecutor(self.alpaca, self.store)
        
        # Runtime state
        self.last_run_time: Optional[datetime] = None
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.base_backoff_seconds = 30
        
        # Performance tracking
        self.metrics = {
            "total_runs": 0,
            "successful_runs": 0,
            "failed_runs": 0,
            "decisions_generated": 0,
            "orders_submitted": 0,
            "start_time": None
        }
        
        logger.info("Trading runner initialized")
    
    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self.shutdown_requested = True
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, signal_handler)
    
    async def run_once(self, focus_tickers: Optional[List[str]] = None) -> bool:
        """
        Run a single trading cycle.
        
        Args:
            focus_tickers: Optional list of tickers to focus on
            
        Returns:
            True if successful, False otherwise
        """
        run_id = create_run_id()
        
        try:
            logger.info(f"Starting trading cycle: {run_id}")
            self.metrics["total_runs"] += 1
            
            # Check market hours if configured.  Previously this used the
            # local-time based ``is_market_hours`` utility which depends on the
            # actual system clock and made tests difficult to control.  We now
            # delegate the check to the Alpaca client so it can be easily
            # mocked in tests.
            if settings.market_hours_only:
                is_open = await self.alpaca.is_market_open()
                if not is_open:
                    logger.info("Market is closed, skipping trading cycle")
                    return True
            
            # Get account information
            account = await self.alpaca.get_account()
            if not account:
                logger.error("Could not retrieve account information")
                return False
            
            # Get current positions
            positions = await self.alpaca.get_positions()
            
            # Update equity curve
            await self._update_equity_curve(account, positions)
            
            # Check kill switch
            if await self._check_kill_switch(account.equity):
                logger.warning("Kill switch activated, skipping trading")
                return True
            
            # Generate trading decision using LLM
            async with llm_agent.LLMAgent() as agent:
                decision = await agent.generate_decision(
                    focus_tickers=focus_tickers,
                    cash_estimate=format_currency(account.cash),
                    notable_exposures=[pos.symbol for pos in positions],
                    num_positions=len(positions)
                )
            
            if not decision:
                logger.warning("No trading decision generated")
                return False
            
            # Store decision in database
            await self.store.store_trading_decision(decision)
            self.metrics["decisions_generated"] += 1
            
            # Execute trading decisions
            execution_results = []
            for dec in decision.decision:
                if dec.action.value != "no-trade":
                    # Get current market price
                    # ``MarketDataTool.get_quote`` is asynchronous in production
                    # but the tests replace ``market_data`` with a simple mock
                    # returning a value directly.  Support both behaviours by
                    # awaiting the result only if the call returns an
                    # awaitable object.
                    quote_result = tools.market_data.get_quote(dec.symbol)
                    quote = await quote_result if hasattr(quote_result, "__await__") else quote_result
                    if not quote:
                        logger.warning(f"Could not get quote for {dec.symbol}")
                        continue
                    
                    # Execute the decision
                    result = await self.executor.execute_decision(
                        dec, account.equity, quote.price, run_id
                    )
                    
                    if result:
                        execution_results.append(result)
                        if result.order_id:
                            self.metrics["orders_submitted"] += 1
            
            # Log summary
            logger.info(
                f"Trading cycle completed: {run_id} - "
                f"{len(decision.research)} symbols analyzed, "
                f"{len(execution_results)} orders submitted"
            )
            
            self.metrics["successful_runs"] += 1
            self.consecutive_errors = 0
            self.last_run_time = now_local()
            
            return True
            
        except Exception as e:
            logger.error(f"Error in trading cycle {run_id}: {e}")
            self.metrics["failed_runs"] += 1
            self.consecutive_errors += 1
            return False
    
    async def run_continuous(self, focus_tickers: Optional[List[str]] = None) -> None:
        """
        Run continuous trading loop with error handling and backoff.
        
        Args:
            focus_tickers: Optional list of tickers to focus on
        """
        self.setup_signal_handlers()
        self.running = True
        self.metrics["start_time"] = now_local()
        
        logger.info("Starting continuous trading loop")
        
        try:
            while self.running and not self.shutdown_requested:
                # Check for too many consecutive errors
                if self.consecutive_errors >= self.max_consecutive_errors:
                    logger.error(
                        f"Too many consecutive errors ({self.consecutive_errors}), "
                        "stopping trading loop"
                    )
                    break
                
                # Run trading cycle
                success = await self.run_once(focus_tickers)
                
                if not success:
                    # Calculate backoff delay
                    backoff_delay = self.base_backoff_seconds * (2 ** min(self.consecutive_errors, 5))
                    logger.warning(f"Trading cycle failed, backing off for {backoff_delay}s")
                    await asyncio.sleep(backoff_delay)
                else:
                    # Normal interval between cycles
                    await asyncio.sleep(settings.loop_interval_seconds)
                
                # Periodic maintenance
                await self._periodic_maintenance()
        
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Unexpected error in trading loop: {e}")
        finally:
            await self._shutdown()
    
    async def _update_equity_curve(self, account, positions: List) -> None:
        """Update equity curve with current account state."""
        try:
            positions_value = sum(pos.market_value for pos in positions)
            unrealized_pnl = sum(pos.unrealized_pnl for pos in positions)
            
            await self.store.update_equity_curve(
                total_equity=account.equity,
                cash=account.cash,
                positions_value=positions_value,
                unrealized_pnl=unrealized_pnl
            )
            
        except Exception as e:
            logger.error(f"Error updating equity curve: {e}")
    
    async def _check_kill_switch(self, current_equity: float) -> bool:
        """Check if kill switch should be activated."""
        try:
            # Get recent equity data
            equity_data = await self.store.get_equity_curve(days=30)
            
            if not equity_data:
                return False
            
            # Find peak equity
            peak_equity = max(point["total_equity"] for point in equity_data)
            
            # Calculate current drawdown
            if peak_equity > 0:
                drawdown_pct = ((peak_equity - current_equity) / peak_equity) * 100
                
                if drawdown_pct > strategy_config.drawdown_kill_switch_pct:
                    logger.critical(
                        f"KILL SWITCH ACTIVATED: Drawdown {drawdown_pct:.2f}% "
                        f"exceeds limit {strategy_config.drawdown_kill_switch_pct}%"
                    )
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking kill switch: {e}")
            return False
    
    async def _periodic_maintenance(self) -> None:
        """Perform periodic maintenance tasks."""
        try:
            # Update order statuses
            recent_orders = await self.store.get_recent_orders(limit=10)
            
            for order in recent_orders:
                if order["status"] in ["submitted", "pending"]:
                    result = await self.executor.update_order_status(order["alpaca_order_id"])
                    if result:
                        logger.debug(f"Updated order status: {order['op_id']}")
            
            # Clean up stale operations
            await self.executor.cleanup_stale_operations()
            
            # Clean up old data (daily)
            if self.last_run_time:
                hours_since_last = (now_local() - self.last_run_time).total_seconds() / 3600
                if hours_since_last >= 24:
                    await self.store.cleanup_old_data()
            
        except Exception as e:
            logger.error(f"Error in periodic maintenance: {e}")
    
    async def _shutdown(self) -> None:
        """Perform graceful shutdown."""
        logger.info("Initiating graceful shutdown...")
        
        try:
            # Cancel pending orders if configured
            if hasattr(settings, 'cancel_orders_on_shutdown') and settings.cancel_orders_on_shutdown:
                cancelled = await self.executor.cancel_pending_orders()
                if cancelled > 0:
                    logger.info(f"Cancelled {cancelled} pending orders")
            
            # Log final metrics
            runtime = (now_local() - self.metrics["start_time"]).total_seconds() / 3600 if self.metrics["start_time"] else 0
            
            logger.info(
                f"Trading session summary: "
                f"Runtime: {runtime:.1f}h, "
                f"Runs: {self.metrics['successful_runs']}/{self.metrics['total_runs']}, "
                f"Decisions: {self.metrics['decisions_generated']}, "
                f"Orders: {self.metrics['orders_submitted']}"
            )
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            self.running = False
            logger.info("Shutdown complete")
    
    def stop(self) -> None:
        """Request shutdown of the trading loop."""
        self.shutdown_requested = True
    
    def get_status(self) -> Dict[str, Any]:
        """Get current runner status."""
        return {
            "running": self.running,
            "shutdown_requested": self.shutdown_requested,
            "last_run_time": self.last_run_time,
            "consecutive_errors": self.consecutive_errors,
            "metrics": self.metrics.copy()
        }


class MarketHoursChecker:
    """Helper class for market hours validation."""
    
    @staticmethod
    async def wait_for_market_open() -> None:
        """Wait until market opens."""
        while not is_market_hours():
            now = now_local()
            
            # Calculate time until market opens
            if now.weekday() >= 5:  # Weekend
                # Wait until Monday 9:30 AM
                days_until_monday = 7 - now.weekday()
                market_open = now.replace(
                    hour=9, minute=30, second=0, microsecond=0
                ) + timedelta(days=days_until_monday)
            else:
                # Wait until next trading day 9:30 AM
                market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
                if now.hour >= 16:  # After market close
                    market_open += timedelta(days=1)
            
            wait_seconds = (market_open - now).total_seconds()
            
            if wait_seconds > 3600:  # More than 1 hour
                logger.info(f"Market closed. Waiting {wait_seconds/3600:.1f} hours until open")
                await asyncio.sleep(3600)  # Check every hour
            else:
                logger.info(f"Market opens in {wait_seconds/60:.0f} minutes")
                await asyncio.sleep(min(wait_seconds, 300))  # Check every 5 minutes
    
    @staticmethod
    def is_trading_day(dt: Optional[datetime] = None) -> bool:
        """Check if given date is a trading day."""
        if dt is None:
            dt = now_local()
        
        # Basic check - excludes weekends
        # In production, you'd want to check for holidays too
        return dt.weekday() < 5


# Convenience functions for CLI
async def run_once_cli(focus_tickers: Optional[List[str]] = None) -> bool:
    """CLI wrapper for running once."""
    runner = TradingRunner()
    return await runner.run_once(focus_tickers)


async def run_continuous_cli(focus_tickers: Optional[List[str]] = None) -> None:
    """CLI wrapper for continuous running."""
    runner = TradingRunner()
    await runner.run_continuous(focus_tickers)

