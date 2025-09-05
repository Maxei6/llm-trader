"""
Database storage layer with SQLite, WAL mode, and comprehensive data management.
"""

import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from contextlib import asynccontextmanager

from sqlalchemy import create_engine, text, func
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from loguru import logger

from .config import settings
from .models import (
    Base, DBTradingRun, DBResearchItem, DBDecision, DBOrder,
    DBPosition, DBEquityCurve, DBLog, TradingDecision
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - used only for type hints
    from .executor import ExecutionResult, ExecutionPlan, ExecutionStatus


class DatabaseStore:
    """
    Database storage layer with comprehensive data management.
    
    Handles all database operations including trading runs, orders,
    positions, equity tracking, and structured logging.
    """
    
    def __init__(self):
        self.database_url = settings.database_url
        self.engine = None
        self.SessionLocal = None
        self._initialize_database()
        
        logger.info(f"Database store initialized: {self.database_url}")
    
    def _initialize_database(self) -> None:
        """Initialize database connection and create tables."""
        try:
            # Create engine with WAL mode for SQLite
            if self.database_url.startswith("sqlite"):
                self.engine = create_engine(
                    self.database_url,
                    echo=settings.debug,
                    pool_pre_ping=True,
                    connect_args={
                        "check_same_thread": False,
                        "timeout": 30
                    }
                )
                
                # Enable WAL mode for better concurrency
                if settings.database_wal_mode:
                    with self.engine.connect() as conn:
                        conn.execute(text("PRAGMA journal_mode=WAL"))
                        conn.execute(text("PRAGMA synchronous=NORMAL"))
                        conn.execute(text("PRAGMA cache_size=10000"))
                        conn.execute(text("PRAGMA temp_store=memory"))
                        conn.commit()
                        logger.info("SQLite WAL mode enabled")
            else:
                self.engine = create_engine(
                    self.database_url,
                    echo=settings.debug,
                    pool_pre_ping=True
                )
            
            # Create session factory
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            
            # Create all tables
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created/verified")
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    @asynccontextmanager
    async def get_session(self):
        """Get database session with proper cleanup."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    async def store_trading_decision(self, decision: TradingDecision) -> bool:
        """
        Store a complete trading decision in the database.
        
        Args:
            decision: TradingDecision object to store
            
        Returns:
            True if successful, False otherwise
        """
        try:
            async with self.get_session() as session:
                # Create trading run record
                trading_run = DBTradingRun(
                    run_id=decision.run_id,
                    timestamp_local=decision.timestamp_local,
                    schema_version=decision.schema_version,
                    universe_considered=json.dumps(decision.universe_considered),
                    cash_estimate=decision.positions_context.cash_estimate,
                    notable_exposures=json.dumps(decision.positions_context.notable_exposures),
                    notes=json.dumps(decision.notes),
                    safety_notes=json.dumps({
                        "why_no_trade": decision.safety.why_no_trade_if_any,
                        "kill_switch": decision.safety.drawdown_kill_switch_suggestion
                    })
                )
                session.add(trading_run)
                
                # Store research items
                for research in decision.research:
                    research_item = DBResearchItem(
                        run_id=decision.run_id,
                        symbol=research.symbol,
                        thesis=research.thesis,
                        sentiment=research.sentiment.value,
                        hype_score=research.hype_score,
                        catalyst=research.catalyst.value,
                        liquidity_ok=research.liquidity_ok,
                        sources_json=json.dumps([
                            {
                                "title": source.title,
                                "url": source.url,
                                "publisher": source.publisher,
                                "date": source.date.isoformat(),
                                "takeaway": source.takeaway
                            }
                            for source in research.sources
                        ]),
                        fundamentals_json=json.dumps({
                            "mkt_cap": research.fundamentals_brief.mkt_cap,
                            "rev_ltm": research.fundamentals_brief.rev_ltm,
                            "growth_yoy": research.fundamentals_brief.growth_yoy,
                            "margin_brief": research.fundamentals_brief.margin_brief,
                            "next_earnings": research.fundamentals_brief.next_earnings.isoformat() if research.fundamentals_brief.next_earnings else None
                        }),
                        checks_json=json.dumps(research.checks),
                        risks_json=json.dumps(research.risks)
                    )
                    session.add(research_item)
                
                # Store decisions
                for dec in decision.decision:
                    decision_item = DBDecision(
                        run_id=decision.run_id,
                        symbol=dec.symbol,
                        action=dec.action.value,
                        confidence=dec.confidence,
                        upside_downside_ratio=dec.upside_downside_ratio,
                        exp_return_brief=dec.exp_return_brief,
                        order_plan_json=json.dumps({
                            "type": dec.order_plan.type.value,
                            "entry_note": dec.order_plan.entry_note,
                            "limit_price": dec.order_plan.limit_price,
                            "stop_logic": dec.order_plan.stop_logic,
                            "take_profit_logic": dec.order_plan.take_profit_logic,
                            "size_pct_equity": dec.order_plan.size_pct_equity,
                            "qty_estimate": dec.order_plan.qty_estimate
                        }) if dec.order_plan else None
                    )
                    session.add(decision_item)
                
                session.flush()
                logger.info(f"Stored trading decision: {decision.run_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error storing trading decision: {e}")
            return False
    
    async def store_execution_result(
        self,
        result: "ExecutionResult",
        plan: "ExecutionPlan",
        run_id: str,
    ) -> bool:
        """Store order execution result."""
        try:
            async with self.get_session() as session:
                order = DBOrder(
                    op_id=result.op_id,
                    run_id=run_id,
                    symbol=plan.symbol,
                    action=plan.action,
                    order_type=plan.order_type,
                    quantity=plan.quantity,
                    limit_price=plan.entry_price,
                    stop_price=plan.stop_price,
                    alpaca_order_id=result.order_id,
                    status=result.status.value,
                    filled_qty=result.filled_qty,
                    filled_price=result.filled_price,
                    error_message=result.error_message
                )
                session.add(order)
                session.flush()
                
                logger.info(f"Stored execution result: {result.op_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error storing execution result: {e}")
            return False
    
    async def is_operation_executed(self, op_id: str) -> bool:
        """Check if operation was already executed."""
        try:
            async with self.get_session() as session:
                order = session.query(DBOrder).filter(DBOrder.op_id == op_id).first()
                return order is not None
                
        except Exception as e:
            logger.error(f"Error checking operation status: {e}")
            return False
    
    async def get_execution_result(self, op_id: str) -> Optional["ExecutionResult"]:
        """Get execution result for an operation."""
        try:
            from .executor import ExecutionResult, ExecutionStatus  # local import to avoid circular

            async with self.get_session() as session:
                order = session.query(DBOrder).filter(DBOrder.op_id == op_id).first()

                if not order:
                    return None

                return ExecutionResult(
                    op_id=order.op_id,
                    status=ExecutionStatus(order.status),
                    order_id=order.alpaca_order_id,
                    filled_qty=order.filled_qty,
                    filled_price=order.filled_price,
                    error_message=order.error_message,
                )
                
        except Exception as e:
            logger.error(f"Error getting execution result: {e}")
            return None
    
    async def update_position(
        self,
        symbol: str,
        quantity: int,
        avg_cost: float,
        current_price: Optional[float] = None,
        entry_run_id: Optional[str] = None
    ) -> bool:
        """Update or create position record."""
        try:
            async with self.get_session() as session:
                position = session.query(DBPosition).filter(
                    DBPosition.symbol == symbol,
                    DBPosition.closed_at.is_(None)
                ).first()
                
                if position:
                    # Update existing position
                    position.quantity = quantity
                    position.avg_cost = avg_cost
                    position.current_price = current_price
                    position.updated_at = datetime.utcnow()
                    
                    if current_price:
                        position.unrealized_pnl = (current_price - avg_cost) * quantity
                else:
                    # Create new position
                    position = DBPosition(
                        symbol=symbol,
                        quantity=quantity,
                        avg_cost=avg_cost,
                        current_price=current_price,
                        unrealized_pnl=(current_price - avg_cost) * quantity if current_price else 0.0,
                        entry_run_id=entry_run_id or "unknown"
                    )
                    session.add(position)
                
                session.flush()
                logger.info(f"Updated position: {symbol}")
                return True
                
        except Exception as e:
            logger.error(f"Error updating position: {e}")
            return False
    
    async def close_position(self, symbol: str) -> bool:
        """Close a position record."""
        try:
            async with self.get_session() as session:
                position = session.query(DBPosition).filter(
                    DBPosition.symbol == symbol,
                    DBPosition.closed_at.is_(None)
                ).first()
                
                if position:
                    position.closed_at = datetime.utcnow()
                    session.flush()
                    logger.info(f"Closed position: {symbol}")
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False
    
    async def get_open_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions."""
        try:
            async with self.get_session() as session:
                positions = session.query(DBPosition).filter(
                    DBPosition.closed_at.is_(None)
                ).all()
                
                return [
                    {
                        "symbol": pos.symbol,
                        "quantity": pos.quantity,
                        "avg_cost": pos.avg_cost,
                        "current_price": pos.current_price,
                        "unrealized_pnl": pos.unrealized_pnl,
                        "opened_at": pos.opened_at,
                        "entry_run_id": pos.entry_run_id
                    }
                    for pos in positions
                ]
                
        except Exception as e:
            logger.error(f"Error getting open positions: {e}")
            return []
    
    async def update_equity_curve(
        self,
        total_equity: float,
        cash: float,
        positions_value: float,
        unrealized_pnl: float,
        realized_pnl_daily: float = 0.0
    ) -> bool:
        """Update equity curve with current values."""
        try:
            async with self.get_session() as session:
                # Get peak equity for drawdown calculation
                latest_peak = session.query(func.max(DBEquityCurve.peak_equity)).scalar() or total_equity
                peak_equity = max(latest_peak, total_equity)
                
                # Calculate drawdown
                drawdown_pct = ((peak_equity - total_equity) / peak_equity) * 100 if peak_equity > 0 else 0.0
                
                # Get position count
                num_positions = session.query(DBPosition).filter(
                    DBPosition.closed_at.is_(None)
                ).count()
                
                equity_point = DBEquityCurve(
                    timestamp=datetime.utcnow(),
                    total_equity=total_equity,
                    cash=cash,
                    positions_value=positions_value,
                    unrealized_pnl=unrealized_pnl,
                    realized_pnl_daily=realized_pnl_daily,
                    drawdown_pct=drawdown_pct,
                    peak_equity=peak_equity,
                    num_positions=num_positions
                )
                session.add(equity_point)
                session.flush()
                
                logger.debug(f"Updated equity curve: ${total_equity:.2f}")
                return True
                
        except Exception as e:
            logger.error(f"Error updating equity curve: {e}")
            return False
    
    async def get_equity_curve(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get equity curve data for the last N days."""
        try:
            async with self.get_session() as session:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                
                equity_points = session.query(DBEquityCurve).filter(
                    DBEquityCurve.timestamp >= cutoff_date
                ).order_by(DBEquityCurve.timestamp).all()
                
                return [
                    {
                        "timestamp": point.timestamp,
                        "total_equity": point.total_equity,
                        "cash": point.cash,
                        "positions_value": point.positions_value,
                        "unrealized_pnl": point.unrealized_pnl,
                        "realized_pnl_daily": point.realized_pnl_daily,
                        "drawdown_pct": point.drawdown_pct,
                        "num_positions": point.num_positions
                    }
                    for point in equity_points
                ]
                
        except Exception as e:
            logger.error(f"Error getting equity curve: {e}")
            return []
    
    async def get_recent_decisions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent trading decisions."""
        try:
            async with self.get_session() as session:
                decisions = session.query(DBDecision).order_by(
                    DBDecision.created_at.desc()
                ).limit(limit).all()
                
                return [
                    {
                        "run_id": dec.run_id,
                        "symbol": dec.symbol,
                        "action": dec.action,
                        "confidence": dec.confidence,
                        "upside_downside_ratio": dec.upside_downside_ratio,
                        "exp_return_brief": dec.exp_return_brief,
                        "created_at": dec.created_at
                    }
                    for dec in decisions
                ]
                
        except Exception as e:
            logger.error(f"Error getting recent decisions: {e}")
            return []
    
    async def get_recent_orders(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent orders."""
        try:
            async with self.get_session() as session:
                orders = session.query(DBOrder).order_by(
                    DBOrder.submitted_at.desc()
                ).limit(limit).all()
                
                return [
                    {
                        "op_id": order.op_id,
                        "symbol": order.symbol,
                        "action": order.action,
                        "quantity": order.quantity,
                        "order_type": order.order_type,
                        "status": order.status,
                        "filled_qty": order.filled_qty,
                        "filled_price": order.filled_price,
                        "submitted_at": order.submitted_at,
                        "filled_at": order.filled_at
                    }
                    for order in orders
                ]
                
        except Exception as e:
            logger.error(f"Error getting recent orders: {e}")
            return []
    
    async def log_structured(
        self,
        level: str,
        logger_name: str,
        message: str,
        run_id: Optional[str] = None,
        symbol: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Store structured log entry."""
        try:
            async with self.get_session() as session:
                log_entry = DBLog(
                    timestamp=datetime.utcnow(),
                    level=level.upper(),
                    logger=logger_name,
                    message=message,
                    run_id=run_id,
                    symbol=symbol,
                    extra_json=json.dumps(extra) if extra else None
                )
                session.add(log_entry)
                session.flush()
                return True
                
        except Exception as e:
            logger.error(f"Error storing log entry: {e}")
            return False
    
    async def get_performance_metrics(self, days: int = 30) -> Dict[str, Any]:
        """Get performance metrics for the last N days."""
        try:
            async with self.get_session() as session:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                
                # Get equity curve data
                equity_data = session.query(DBEquityCurve).filter(
                    DBEquityCurve.timestamp >= cutoff_date
                ).order_by(DBEquityCurve.timestamp).all()
                
                if not equity_data:
                    return {}
                
                # Calculate metrics
                start_equity = equity_data[0].total_equity
                end_equity = equity_data[-1].total_equity
                max_drawdown = max([point.drawdown_pct for point in equity_data])
                
                total_return = ((end_equity - start_equity) / start_equity) * 100 if start_equity > 0 else 0.0
                
                # Count trades
                total_orders = session.query(DBOrder).filter(
                    DBOrder.submitted_at >= cutoff_date
                ).count()
                
                filled_orders = session.query(DBOrder).filter(
                    DBOrder.submitted_at >= cutoff_date,
                    DBOrder.status == "filled"
                ).count()
                
                return {
                    "total_return_pct": total_return,
                    "max_drawdown_pct": max_drawdown,
                    "start_equity": start_equity,
                    "end_equity": end_equity,
                    "total_orders": total_orders,
                    "filled_orders": filled_orders,
                    "fill_rate_pct": (filled_orders / total_orders) * 100 if total_orders > 0 else 0.0,
                    "days": days
                }
                
        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return {}
    
    async def cleanup_old_data(self, days: int = 90) -> bool:
        """Clean up old data beyond retention period."""
        try:
            async with self.get_session() as session:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                
                # Clean up old logs
                deleted_logs = session.query(DBLog).filter(
                    DBLog.timestamp < cutoff_date
                ).delete()
                
                # Clean up old equity curve points (keep daily snapshots)
                # This is a simplified cleanup - in production you might want to aggregate
                
                session.flush()
                logger.info(f"Cleaned up {deleted_logs} old log entries")
                return True
                
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            return False

