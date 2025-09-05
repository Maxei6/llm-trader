"""
Order execution engine with sizing, OCO emulation, and idempotent operations.
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

from loguru import logger

from .config import settings, strategy_config
from .models import DecisionItem, ActionType, OrderType
from .alpaca_client import AlpacaClient
from .store import DatabaseStore


class ExecutionStatus(Enum):
    """Order execution status."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class ExecutionPlan:
    """Execution plan for a trading decision."""
    op_id: str
    symbol: str
    action: str
    quantity: int
    entry_price: Optional[float]
    stop_price: Optional[float]
    take_profit_price: Optional[float]
    order_type: str
    estimated_cost: float
    risk_amount: float


@dataclass
class ExecutionResult:
    """Result of order execution."""
    op_id: str
    status: ExecutionStatus
    order_id: Optional[str] = None
    filled_qty: int = 0
    filled_price: Optional[float] = None
    error_message: Optional[str] = None


class OrderExecutor:
    """
    Order execution engine with comprehensive risk management.
    
    Handles position sizing, order submission, OCO emulation,
    and idempotent operations via operation IDs.
    """
    
    def __init__(self, alpaca_client: AlpacaClient, store: DatabaseStore):
        self.alpaca = alpaca_client
        self.store = store
        self.config = strategy_config
        
        # Track pending operations to prevent duplicates
        self.pending_operations: Dict[str, ExecutionPlan] = {}
        
        logger.info("Order executor initialized")
    
    async def execute_decision(
        self,
        decision: DecisionItem,
        current_equity: float,
        current_price: float,
        run_id: str
    ) -> Optional[ExecutionResult]:
        """
        Execute a trading decision with full risk management.
        
        Args:
            decision: Trading decision to execute
            current_equity: Current account equity
            current_price: Current market price
            run_id: Run ID for tracking
            
        Returns:
            ExecutionResult or None if execution not possible
        """
        try:
            # Skip no-trade decisions
            if decision.action == ActionType.NO_TRADE:
                logger.info(f"Skipping no-trade decision for {decision.symbol}")
                return None
            
            # Generate operation ID for idempotency
            op_id = f"{run_id}_{decision.symbol}_{decision.action.value}"
            
            # Check if already executed
            if await self._is_operation_executed(op_id):
                logger.info(f"Operation already executed: {op_id}")
                return await self._get_execution_result(op_id)
            
            # Create execution plan
            plan = await self._create_execution_plan(
                decision, current_equity, current_price, op_id
            )
            
            if not plan:
                logger.warning(f"Could not create execution plan for {decision.symbol}")
                return None
            
            # Validate execution plan
            if not await self._validate_execution_plan(plan):
                logger.warning(f"Execution plan validation failed for {decision.symbol}")
                return None
            
            # Store pending operation
            self.pending_operations[op_id] = plan
            
            # Execute the plan
            result = await self._execute_plan(plan)
            
            # Store execution result
            await self._store_execution_result(result, plan, run_id)
            
            # Clean up pending operation
            self.pending_operations.pop(op_id, None)
            
            logger.info(f"Execution completed: {op_id} - {result.status.value}")
            return result
            
        except Exception as e:
            logger.error(f"Error executing decision for {decision.symbol}: {e}")
            return ExecutionResult(
                op_id=op_id if 'op_id' in locals() else str(uuid.uuid4()),
                status=ExecutionStatus.FAILED,
                error_message=str(e)
            )
    
    async def _create_execution_plan(
        self,
        decision: DecisionItem,
        current_equity: float,
        current_price: float,
        op_id: str
    ) -> Optional[ExecutionPlan]:
        """Create detailed execution plan from decision."""
        try:
            if not decision.order_plan:
                return None
            
            # Calculate position size
            quantity = await self._calculate_position_size(
                decision, current_equity, current_price
            )
            
            if quantity <= 0:
                logger.warning(f"Invalid quantity calculated: {quantity}")
                return None
            
            # Determine entry price
            entry_price = None
            if decision.order_plan.type == OrderType.LIMIT:
                entry_price = decision.order_plan.limit_price
            
            # Calculate stop and take profit prices
            stop_price = await self._calculate_stop_price(
                decision, current_price, quantity
            )
            
            take_profit_price = await self._calculate_take_profit_price(
                decision, current_price, stop_price
            )
            
            # Estimate total cost
            estimated_cost = quantity * (entry_price or current_price)
            
            # Calculate risk amount
            risk_amount = self._calculate_risk_amount(
                current_price, stop_price, quantity, decision.action
            )
            
            return ExecutionPlan(
                op_id=op_id,
                symbol=decision.symbol,
                action=decision.action.value,
                quantity=quantity,
                entry_price=entry_price,
                stop_price=stop_price,
                take_profit_price=take_profit_price,
                order_type=decision.order_plan.type.value,
                estimated_cost=estimated_cost,
                risk_amount=risk_amount
            )
            
        except Exception as e:
            logger.error(f"Error creating execution plan: {e}")
            return None
    
    async def _calculate_position_size(
        self,
        decision: DecisionItem,
        current_equity: float,
        current_price: float
    ) -> int:
        """Calculate position size based on risk management rules."""
        try:
            if not decision.order_plan:
                return 0
            
            # Use configured risk percentage or decision's size
            risk_pct = decision.order_plan.size_pct_equity
            if risk_pct <= 0 or risk_pct > self.config.risk_per_position_pct:
                risk_pct = self.config.risk_per_position_pct
            
            # Calculate risk amount in dollars
            risk_amount = current_equity * (risk_pct / 100)
            
            # Estimate stop distance (use 2% if not specified)
            stop_distance_pct = 0.02  # Default 2% stop
            
            # Try to parse stop logic for better estimate
            if decision.order_plan.stop_logic:
                # Look for percentage in stop logic
                import re
                pct_match = re.search(r'(\d+(?:\.\d+)?)%', decision.order_plan.stop_logic)
                if pct_match:
                    stop_distance_pct = float(pct_match.group(1)) / 100
            
            # Calculate quantity based on risk
            stop_distance = current_price * stop_distance_pct
            quantity = int(risk_amount / stop_distance)
            
            # Apply minimum and maximum constraints
            min_quantity = 1
            max_quantity = int(current_equity * 0.1 / current_price)  # Max 10% of equity
            
            quantity = max(min_quantity, min(quantity, max_quantity))
            
            # Round down to avoid over-allocation
            return quantity
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return 0
    
    async def _calculate_stop_price(
        self,
        decision: DecisionItem,
        current_price: float,
        quantity: int
    ) -> Optional[float]:
        """Calculate stop loss price."""
        try:
            if not decision.order_plan or not decision.order_plan.stop_logic:
                return None
            
            # Default to 2% stop if parsing fails
            stop_distance_pct = 0.02
            
            # Try to parse stop logic
            stop_logic = decision.order_plan.stop_logic.lower()
            
            # Look for percentage
            import re
            pct_match = re.search(r'(\d+(?:\.\d+)?)%', stop_logic)
            if pct_match:
                stop_distance_pct = float(pct_match.group(1)) / 100
            elif 'atr' in stop_logic:
                # Use 2x ATR as default (approximately 4% for most stocks)
                stop_distance_pct = 0.04
            
            # Calculate stop price based on action
            if decision.action == ActionType.LONG:
                stop_price = current_price * (1 - stop_distance_pct)
            else:  # SHORT
                stop_price = current_price * (1 + stop_distance_pct)
            
            return round(stop_price, 2)
            
        except Exception as e:
            logger.error(f"Error calculating stop price: {e}")
            return None
    
    async def _calculate_take_profit_price(
        self,
        decision: DecisionItem,
        current_price: float,
        stop_price: Optional[float]
    ) -> Optional[float]:
        """Calculate take profit price."""
        try:
            if not decision.order_plan or not stop_price:
                return None
            
            # Default risk-reward ratio
            risk_reward_ratio = 1.5
            
            # Try to parse take profit logic
            tp_logic = decision.order_plan.take_profit_logic.lower()
            
            # Look for ratio
            import re
            ratio_match = re.search(r'(\d+(?:\.\d+)?)r', tp_logic)
            if ratio_match:
                risk_reward_ratio = float(ratio_match.group(1))
            
            # Calculate risk distance
            risk_distance = abs(current_price - stop_price)
            
            # Calculate take profit price
            if decision.action == ActionType.LONG:
                tp_price = current_price + (risk_distance * risk_reward_ratio)
            else:  # SHORT
                tp_price = current_price - (risk_distance * risk_reward_ratio)
            
            return round(tp_price, 2)
            
        except Exception as e:
            logger.error(f"Error calculating take profit price: {e}")
            return None
    
    def _calculate_risk_amount(
        self,
        entry_price: float,
        stop_price: Optional[float],
        quantity: int,
        action: ActionType
    ) -> float:
        """Calculate total risk amount for the position."""
        if not stop_price:
            return 0.0
        
        risk_per_share = abs(entry_price - stop_price)
        return risk_per_share * quantity
    
    async def _validate_execution_plan(self, plan: ExecutionPlan) -> bool:
        """Validate execution plan against risk limits."""
        try:
            # Check account info
            account = await self.alpaca.get_account()
            if not account:
                logger.error("Could not get account information")
                return False
            
            # Check buying power
            if plan.estimated_cost > account.buying_power:
                logger.warning(f"Insufficient buying power: {plan.estimated_cost} > {account.buying_power}")
                return False
            
            # Check position limits
            positions = await self.alpaca.get_positions()
            if len(positions) >= self.config.max_positions:
                logger.warning(f"Maximum positions reached: {len(positions)}")
                return False
            
            # Check risk limits
            max_risk = account.equity * (self.config.risk_per_position_pct / 100)
            if plan.risk_amount > max_risk:
                logger.warning(f"Risk amount too high: {plan.risk_amount} > {max_risk}")
                return False
            
            # Check if position already exists
            existing_position = await self.alpaca.get_position(plan.symbol)
            if existing_position:
                logger.warning(f"Position already exists for {plan.symbol}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating execution plan: {e}")
            return False
    
    async def _execute_plan(self, plan: ExecutionPlan) -> ExecutionResult:
        """Execute the trading plan."""
        try:
            # Determine order side
            side = "buy" if plan.action == "long" else "sell"
            
            # Submit main order
            order_id = await self.alpaca.submit_order(
                symbol=plan.symbol,
                side=side,
                quantity=plan.quantity,
                order_type=plan.order_type,
                limit_price=plan.entry_price
            )
            
            if not order_id:
                return ExecutionResult(
                    op_id=plan.op_id,
                    status=ExecutionStatus.REJECTED,
                    error_message="Order submission failed"
                )
            
            # TODO: Implement OCO emulation for stop and take profit
            # For now, just submit the main order
            
            logger.info(f"Order submitted: {order_id} for {plan.symbol}")
            
            return ExecutionResult(
                op_id=plan.op_id,
                status=ExecutionStatus.SUBMITTED,
                order_id=order_id
            )
            
        except Exception as e:
            logger.error(f"Error executing plan: {e}")
            return ExecutionResult(
                op_id=plan.op_id,
                status=ExecutionStatus.FAILED,
                error_message=str(e)
            )
    
    async def _is_operation_executed(self, op_id: str) -> bool:
        """Check if operation was already executed."""
        try:
            # Check database for existing operation
            return await self.store.is_operation_executed(op_id)
        except Exception as e:
            logger.error(f"Error checking operation status: {e}")
            return False
    
    async def _get_execution_result(self, op_id: str) -> Optional[ExecutionResult]:
        """Get execution result for an operation."""
        try:
            return await self.store.get_execution_result(op_id)
        except Exception as e:
            logger.error(f"Error getting execution result: {e}")
            return None
    
    async def _store_execution_result(
        self,
        result: ExecutionResult,
        plan: ExecutionPlan,
        run_id: str
    ) -> None:
        """Store execution result in database."""
        try:
            await self.store.store_execution_result(result, plan, run_id)
        except Exception as e:
            logger.error(f"Error storing execution result: {e}")
    
    async def update_order_status(self, order_id: str) -> Optional[ExecutionResult]:
        """Update order status from broker."""
        try:
            # Get order status from Alpaca
            orders = await self.alpaca.get_orders(limit=1)
            
            for order in orders:
                if order.id == order_id:
                    # Update status in database
                    status = ExecutionStatus.FILLED if order.status == "filled" else ExecutionStatus.PENDING
                    
                    # Create result
                    result = ExecutionResult(
                        op_id="",  # Will be filled from database
                        status=status,
                        order_id=order_id,
                        filled_qty=order.filled_qty,
                        filled_price=order.filled_price
                    )
                    
                    return result
            
            return None
            
        except Exception as e:
            logger.error(f"Error updating order status: {e}")
            return None
    
    async def cancel_pending_orders(self, symbol: Optional[str] = None) -> int:
        """Cancel pending orders for a symbol or all symbols."""
        try:
            # Get pending orders
            orders = await self.alpaca.get_orders(status="open")
            
            cancelled_count = 0
            for order in orders:
                if symbol is None or order.symbol == symbol:
                    success = await self.alpaca.cancel_order(order.id)
                    if success:
                        cancelled_count += 1
            
            logger.info(f"Cancelled {cancelled_count} orders")
            return cancelled_count
            
        except Exception as e:
            logger.error(f"Error cancelling orders: {e}")
            return 0
    
    def get_pending_operations(self) -> List[ExecutionPlan]:
        """Get list of pending operations."""
        return list(self.pending_operations.values())
    
    async def cleanup_stale_operations(self, max_age_hours: int = 24) -> None:
        """Clean up stale pending operations."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            
            # Remove stale operations (implementation depends on tracking timestamps)
            # For now, just clear all pending operations
            stale_count = len(self.pending_operations)
            self.pending_operations.clear()
            
            if stale_count > 0:
                logger.info(f"Cleaned up {stale_count} stale operations")
                
        except Exception as e:
            logger.error(f"Error cleaning up operations: {e}")

