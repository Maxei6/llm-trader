"""
Alpaca client wrapper for trading operations with retries and error handling.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest,
    GetOrdersRequest, ClosePositionRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus, AssetClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from loguru import logger

from .config import settings, alpaca_config


class OrderType(Enum):
    """Order types supported by Alpaca."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


@dataclass
class AlpacaPosition:
    """Represents a position from Alpaca."""
    symbol: str
    quantity: int
    avg_cost: float
    current_price: float
    unrealized_pnl: float
    market_value: float
    side: str  # "long" or "short"


@dataclass
class AlpacaOrder:
    """Represents an order from Alpaca."""
    id: str
    symbol: str
    side: str
    quantity: int
    order_type: str
    status: str
    filled_qty: int
    filled_price: Optional[float]
    limit_price: Optional[float]
    stop_price: Optional[float]
    submitted_at: datetime
    filled_at: Optional[datetime]


@dataclass
class AlpacaAccount:
    """Represents account information from Alpaca."""
    equity: float
    cash: float
    buying_power: float
    portfolio_value: float
    day_trade_count: int
    pattern_day_trader: bool


class AlpacaClient:
    """
    Alpaca trading client with retry logic and error handling.
    
    Provides a simplified interface for trading operations with
    comprehensive error handling and logging.
    """
    
    def __init__(self):
        self.config = alpaca_config
        
        # Initialize trading client
        self.trading_client = TradingClient(
            api_key=self.config.api_key,
            secret_key=self.config.secret_key,
            paper=self.config.mode == "paper"
        )
        
        # Initialize data client
        self.data_client = StockHistoricalDataClient(
            api_key=self.config.api_key,
            secret_key=self.config.secret_key
        )
        
        self.max_retries = 3
        self.retry_delay = 1.0
        
        logger.info(f"Alpaca client initialized in {self.config.mode} mode")
    
    async def get_account(self) -> Optional[AlpacaAccount]:
        """
        Get account information.
        
        Returns:
            AlpacaAccount object or None if failed
        """
        try:
            account = await self._retry_operation(
                lambda: self.trading_client.get_account()
            )
            
            if not account:
                return None
            
            return AlpacaAccount(
                equity=float(account.equity),
                cash=float(account.cash),
                buying_power=float(account.buying_power),
                portfolio_value=float(account.portfolio_value),
                day_trade_count=account.day_trade_count,
                pattern_day_trader=account.pattern_day_trader
            )
            
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return None
    
    async def get_positions(self) -> List[AlpacaPosition]:
        """
        Get all current positions.
        
        Returns:
            List of AlpacaPosition objects
        """
        try:
            positions = await self._retry_operation(
                lambda: self.trading_client.get_all_positions()
            )
            
            if not positions:
                return []
            
            result = []
            for pos in positions:
                result.append(AlpacaPosition(
                    symbol=pos.symbol,
                    quantity=int(pos.qty),
                    avg_cost=float(pos.avg_cost),
                    current_price=float(pos.current_price) if pos.current_price else 0.0,
                    unrealized_pnl=float(pos.unrealized_pnl) if pos.unrealized_pnl else 0.0,
                    market_value=float(pos.market_value) if pos.market_value else 0.0,
                    side="long" if int(pos.qty) > 0 else "short"
                ))
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    async def get_position(self, symbol: str) -> Optional[AlpacaPosition]:
        """
        Get position for a specific symbol.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            AlpacaPosition object or None
        """
        try:
            position = await self._retry_operation(
                lambda: self.trading_client.get_open_position(symbol)
            )
            
            if not position:
                return None
            
            return AlpacaPosition(
                symbol=position.symbol,
                quantity=int(position.qty),
                avg_cost=float(position.avg_cost),
                current_price=float(position.current_price) if position.current_price else 0.0,
                unrealized_pnl=float(position.unrealized_pnl) if position.unrealized_pnl else 0.0,
                market_value=float(position.market_value) if position.market_value else 0.0,
                side="long" if int(position.qty) > 0 else "short"
            )
            
        except Exception as e:
            logger.debug(f"No position found for {symbol}: {e}")
            return None
    
    async def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: str = "day"
    ) -> Optional[str]:
        """
        Submit a trading order.
        
        Args:
            symbol: Stock ticker symbol
            side: "buy" or "sell"
            quantity: Number of shares
            order_type: "market", "limit", "stop", or "stop_limit"
            limit_price: Limit price for limit orders
            stop_price: Stop price for stop orders
            time_in_force: "day", "gtc", "ioc", "fok"
            
        Returns:
            Order ID if successful, None otherwise
        """
        try:
            # Validate inputs
            if side not in ["buy", "sell"]:
                raise ValueError(f"Invalid side: {side}")
            
            if quantity <= 0:
                raise ValueError(f"Invalid quantity: {quantity}")
            
            # Convert side to Alpaca enum
            order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
            
            # Convert time in force
            tif_map = {
                "day": TimeInForce.DAY,
                "gtc": TimeInForce.GTC,
                "ioc": TimeInForce.IOC,
                "fok": TimeInForce.FOK
            }
            tif = tif_map.get(time_in_force, TimeInForce.DAY)
            
            # Create order request based on type
            if order_type == "market":
                order_request = MarketOrderRequest(
                    symbol=symbol,
                    qty=quantity,
                    side=order_side,
                    time_in_force=tif
                )
            elif order_type == "limit":
                if not limit_price:
                    raise ValueError("Limit price required for limit orders")
                order_request = LimitOrderRequest(
                    symbol=symbol,
                    qty=quantity,
                    side=order_side,
                    time_in_force=tif,
                    limit_price=limit_price
                )
            elif order_type == "stop":
                if not stop_price:
                    raise ValueError("Stop price required for stop orders")
                order_request = StopOrderRequest(
                    symbol=symbol,
                    qty=quantity,
                    side=order_side,
                    time_in_force=tif,
                    stop_price=stop_price
                )
            else:
                raise ValueError(f"Unsupported order type: {order_type}")
            
            # Submit order
            order = await self._retry_operation(
                lambda: self.trading_client.submit_order(order_request)
            )
            
            if order:
                logger.info(f"Order submitted: {order.id} - {side} {quantity} {symbol}")
                return order.id
            
            return None
            
        except Exception as e:
            logger.error(f"Error submitting order: {e}")
            return None
    
    async def get_orders(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        symbols: Optional[List[str]] = None
    ) -> List[AlpacaOrder]:
        """
        Get orders with optional filtering.
        
        Args:
            status: Filter by order status
            limit: Maximum number of orders to return
            symbols: Filter by symbols
            
        Returns:
            List of AlpacaOrder objects
        """
        try:
            # Build request
            request = GetOrdersRequest(
                status=OrderStatus(status) if status else None,
                limit=limit,
                symbols=symbols
            )
            
            orders = await self._retry_operation(
                lambda: self.trading_client.get_orders(request)
            )
            
            if not orders:
                return []
            
            result = []
            for order in orders:
                result.append(AlpacaOrder(
                    id=order.id,
                    symbol=order.symbol,
                    side=order.side.value,
                    quantity=int(order.qty),
                    order_type=order.order_type.value,
                    status=order.status.value,
                    filled_qty=int(order.filled_qty) if order.filled_qty else 0,
                    filled_price=float(order.filled_avg_price) if order.filled_avg_price else None,
                    limit_price=float(order.limit_price) if order.limit_price else None,
                    stop_price=float(order.stop_price) if order.stop_price else None,
                    submitted_at=order.submitted_at,
                    filled_at=order.filled_at
                ))
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting orders: {e}")
            return []
    
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if successful, False otherwise
        """
        try:
            result = await self._retry_operation(
                lambda: self.trading_client.cancel_order_by_id(order_id)
            )
            
            if result:
                logger.info(f"Order cancelled: {order_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    async def close_position(self, symbol: str, percentage: Optional[float] = None) -> bool:
        """
        Close a position.
        
        Args:
            symbol: Symbol to close
            percentage: Percentage to close (None for 100%)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            request = ClosePositionRequest(
                qty=str(percentage) if percentage else None
            )
            
            result = await self._retry_operation(
                lambda: self.trading_client.close_position(symbol, request)
            )
            
            if result:
                logger.info(f"Position closed: {symbol}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error closing position {symbol}: {e}")
            return False
    
    async def get_latest_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get latest quote for a symbol.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Quote data dictionary or None
        """
        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            
            quotes = await self._retry_operation(
                lambda: self.data_client.get_stock_latest_quote(request)
            )
            
            if not quotes or symbol not in quotes:
                return None
            
            quote = quotes[symbol]
            
            return {
                "symbol": symbol,
                "bid_price": float(quote.bid_price),
                "ask_price": float(quote.ask_price),
                "bid_size": int(quote.bid_size),
                "ask_size": int(quote.ask_size),
                "timestamp": quote.timestamp
            }
            
        except Exception as e:
            logger.error(f"Error getting quote for {symbol}: {e}")
            return None
    
    async def get_latest_bar(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get latest bar (OHLCV) for a symbol.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Bar data dictionary or None
        """
        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Day,
                limit=1
            )
            
            bars = await self._retry_operation(
                lambda: self.data_client.get_stock_bars(request)
            )
            
            if not bars or symbol not in bars or not bars[symbol]:
                return None
            
            bar = bars[symbol][0]
            
            return {
                "symbol": symbol,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": int(bar.volume),
                "timestamp": bar.timestamp
            }
            
        except Exception as e:
            logger.error(f"Error getting bar for {symbol}: {e}")
            return None
    
    async def _retry_operation(self, operation, max_retries: Optional[int] = None):
        """
        Retry an operation with exponential backoff.
        
        Args:
            operation: Function to retry
            max_retries: Maximum number of retries
            
        Returns:
            Operation result or None if all retries failed
        """
        max_retries = max_retries or self.max_retries
        
        for attempt in range(max_retries + 1):
            try:
                return operation()
                
            except Exception as e:
                if attempt == max_retries:
                    logger.error(f"Operation failed after {max_retries} retries: {e}")
                    return None
                
                wait_time = self.retry_delay * (2 ** attempt)
                logger.warning(f"Operation failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
        
        return None
    
    def is_market_open(self) -> bool:
        """
        Check if the market is currently open.
        
        Returns:
            True if market is open, False otherwise
        """
        try:
            clock = self.trading_client.get_clock()
            return clock.is_open
            
        except Exception as e:
            logger.error(f"Error checking market status: {e}")
            return False
    
    def get_market_calendar(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """
        Get market calendar for date range.
        
        Args:
            start_date: Start date
            end_date: End date
            
        Returns:
            List of market calendar entries
        """
        try:
            calendar = self.trading_client.get_calendar(
                start=start_date.date(),
                end=end_date.date()
            )
            
            return [
                {
                    "date": entry.date,
                    "open": entry.open,
                    "close": entry.close
                }
                for entry in calendar
            ]
            
        except Exception as e:
            logger.error(f"Error getting market calendar: {e}")
            return []

