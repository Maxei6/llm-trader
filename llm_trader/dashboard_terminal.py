"""
Rich terminal dashboard for real-time trading monitoring.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import sys

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.align import Align
from rich.columns import Columns
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box
from loguru import logger

from .config import settings, strategy_config
from .store import DatabaseStore
from .alpaca_client import AlpacaClient
from .utils import format_currency, format_percentage, now_local


class TradingDashboard:
    """
    Real-time trading dashboard using Rich terminal interface.
    
    Displays equity curve, positions, recent decisions, orders,
    and system status in a comprehensive terminal interface.
    """
    
    def __init__(self):
        self.console = Console()
        self.store = DatabaseStore()
        self.alpaca = AlpacaClient()
        
        self.refresh_interval = settings.dashboard_refresh_seconds
        self.running = False
        
        # Cache for data
        self._cache = {
            "account": None,
            "positions": [],
            "equity_curve": [],
            "recent_decisions": [],
            "recent_orders": [],
            "performance_metrics": {},
            "last_update": None
        }
        
        logger.info("Trading dashboard initialized")
    
    def create_layout(self) -> Layout:
        """Create the main dashboard layout."""
        layout = Layout()
        
        # Split into header and body
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body")
        )
        
        # Split body into left and right columns
        layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )
        
        # Split left column
        layout["left"].split_column(
            Layout(name="account", size=8),
            Layout(name="positions", size=12),
            Layout(name="performance", size=8)
        )
        
        # Split right column
        layout["right"].split_column(
            Layout(name="decisions", size=12),
            Layout(name="orders", size=12),
            Layout(name="status", size=4)
        )
        
        return layout
    
    async def update_data(self) -> None:
        """Update all dashboard data."""
        try:
            # Get account info
            self._cache["account"] = await self.alpaca.get_account()
            
            # Get positions
            self._cache["positions"] = await self.alpaca.get_positions()
            
            # Get equity curve
            self._cache["equity_curve"] = await self.store.get_equity_curve(days=7)
            
            # Get recent decisions
            self._cache["recent_decisions"] = await self.store.get_recent_decisions(limit=8)
            
            # Get recent orders
            self._cache["recent_orders"] = await self.store.get_recent_orders(limit=10)
            
            # Get performance metrics
            self._cache["performance_metrics"] = await self.store.get_performance_metrics(days=30)
            
            self._cache["last_update"] = now_local()
            
        except Exception as e:
            logger.error(f"Error updating dashboard data: {e}")
    
    def render_header(self) -> Panel:
        """Render dashboard header."""
        current_time = now_local().strftime("%Y-%m-%d %H:%M:%S %Z")
        
        title = Text("LLM TRADER DASHBOARD", style="bold blue")
        subtitle = Text(f"Last Updated: {current_time}", style="dim")
        
        header_text = Align.center(
            Text.assemble(title, "\n", subtitle)
        )
        
        return Panel(
            header_text,
            box=box.ROUNDED,
            style="blue"
        )
    
    def render_account_info(self) -> Panel:
        """Render account information panel."""
        account = self._cache["account"]
        
        if not account:
            return Panel(
                Align.center(Text("Account data unavailable", style="red")),
                title="Account",
                box=box.ROUNDED
            )
        
        # Create account info table
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")
        
        # Calculate daily P&L if possible
        daily_pnl = "N/A"
        if self._cache["equity_curve"]:
            recent_points = self._cache["equity_curve"][-2:]
            if len(recent_points) >= 2:
                pnl = recent_points[-1]["total_equity"] - recent_points[-2]["total_equity"]
                daily_pnl = f"{format_currency(pnl)} ({format_percentage(pnl/recent_points[-2]['total_equity'])})"
        
        table.add_row("Total Equity", format_currency(account.equity))
        table.add_row("Cash", format_currency(account.cash))
        table.add_row("Buying Power", format_currency(account.buying_power))
        table.add_row("Daily P&L", daily_pnl)
        table.add_row("Day Trades", str(account.day_trade_count))
        table.add_row("PDT Status", "Yes" if account.pattern_day_trader else "No")
        
        return Panel(
            table,
            title="Account Info",
            box=box.ROUNDED,
            style="green"
        )
    
    def render_positions(self) -> Panel:
        """Render positions panel."""
        positions = self._cache["positions"]
        
        if not positions:
            return Panel(
                Align.center(Text("No open positions", style="yellow")),
                title="Positions (0)",
                box=box.ROUNDED
            )
        
        # Create positions table
        table = Table(box=box.SIMPLE)
        table.add_column("Symbol", style="cyan", width=8)
        table.add_column("Qty", justify="right", width=6)
        table.add_column("Avg Cost", justify="right", width=8)
        table.add_column("Current", justify="right", width=8)
        table.add_column("P&L", justify="right", width=10)
        table.add_column("P&L %", justify="right", width=8)
        
        total_unrealized = 0
        
        for pos in positions:
            pnl_pct = ((pos.current_price - pos.avg_cost) / pos.avg_cost) * 100 if pos.avg_cost > 0 else 0
            pnl_style = "green" if pos.unrealized_pnl >= 0 else "red"
            
            table.add_row(
                pos.symbol,
                str(pos.quantity),
                f"${pos.avg_cost:.2f}",
                f"${pos.current_price:.2f}",
                Text(format_currency(pos.unrealized_pnl), style=pnl_style),
                Text(f"{pnl_pct:+.1f}%", style=pnl_style)
            )
            
            total_unrealized += pos.unrealized_pnl
        
        # Add total row
        table.add_section()
        total_style = "green" if total_unrealized >= 0 else "red"
        table.add_row(
            "TOTAL",
            "",
            "",
            "",
            Text(format_currency(total_unrealized), style=total_style),
            ""
        )
        
        return Panel(
            table,
            title=f"Positions ({len(positions)})",
            box=box.ROUNDED,
            style="blue"
        )
    
    def render_performance(self) -> Panel:
        """Render performance metrics panel."""
        metrics = self._cache["performance_metrics"]
        
        if not metrics:
            return Panel(
                Align.center(Text("Performance data unavailable", style="red")),
                title="Performance (30d)",
                box=box.ROUNDED
            )
        
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")
        
        # Style returns based on positive/negative
        return_style = "green" if metrics.get("total_return_pct", 0) >= 0 else "red"
        drawdown_style = "red" if metrics.get("max_drawdown_pct", 0) > 3 else "yellow"
        
        table.add_row("Total Return", 
                     Text(f"{metrics.get('total_return_pct', 0):+.2f}%", style=return_style))
        table.add_row("Max Drawdown", 
                     Text(f"{metrics.get('max_drawdown_pct', 0):.2f}%", style=drawdown_style))
        table.add_row("Total Orders", str(metrics.get("total_orders", 0)))
        table.add_row("Fill Rate", f"{metrics.get('fill_rate_pct', 0):.1f}%")
        table.add_row("Start Equity", format_currency(metrics.get("start_equity", 0)))
        table.add_row("End Equity", format_currency(metrics.get("end_equity", 0)))
        
        return Panel(
            table,
            title="Performance (30d)",
            box=box.ROUNDED,
            style="magenta"
        )
    
    def render_recent_decisions(self) -> Panel:
        """Render recent trading decisions panel."""
        decisions = self._cache["recent_decisions"]
        
        if not decisions:
            return Panel(
                Align.center(Text("No recent decisions", style="yellow")),
                title="Recent Decisions",
                box=box.ROUNDED
            )
        
        table = Table(box=box.SIMPLE)
        table.add_column("Time", width=12)
        table.add_column("Symbol", style="cyan", width=8)
        table.add_column("Action", width=8)
        table.add_column("Confidence", justify="right", width=10)
        table.add_column("R:R", justify="right", width=6)
        
        for decision in decisions:
            action_style = {
                "long": "green",
                "short": "red",
                "no-trade": "yellow"
            }.get(decision["action"], "white")
            
            confidence_style = "green" if decision["confidence"] >= 0.7 else "yellow"
            
            table.add_row(
                decision["created_at"].strftime("%H:%M:%S"),
                decision["symbol"],
                Text(decision["action"].upper(), style=action_style),
                Text(f"{decision['confidence']:.2f}", style=confidence_style),
                f"{decision['upside_downside_ratio']:.1f}"
            )
        
        return Panel(
            table,
            title="Recent Decisions",
            box=box.ROUNDED,
            style="cyan"
        )
    
    def render_recent_orders(self) -> Panel:
        """Render recent orders panel."""
        orders = self._cache["recent_orders"]
        
        if not orders:
            return Panel(
                Align.center(Text("No recent orders", style="yellow")),
                title="Recent Orders",
                box=box.ROUNDED
            )
        
        table = Table(box=box.SIMPLE)
        table.add_column("Time", width=12)
        table.add_column("Symbol", style="cyan", width=8)
        table.add_column("Side", width=6)
        table.add_column("Qty", justify="right", width=6)
        table.add_column("Status", width=10)
        table.add_column("Fill Price", justify="right", width=10)
        
        for order in orders:
            status_style = {
                "filled": "green",
                "submitted": "yellow",
                "cancelled": "red",
                "rejected": "red"
            }.get(order["status"], "white")
            
            fill_price = f"${order['filled_price']:.2f}" if order["filled_price"] else "-"
            
            table.add_row(
                order["submitted_at"].strftime("%H:%M:%S"),
                order["symbol"],
                order["action"].upper(),
                str(order["quantity"]),
                Text(order["status"].upper(), style=status_style),
                fill_price
            )
        
        return Panel(
            table,
            title="Recent Orders",
            box=box.ROUNDED,
            style="yellow"
        )
    
    def render_system_status(self) -> Panel:
        """Render system status panel."""
        # Check various system components
        status_items = []
        
        # Market status
        market_open = self.alpaca.is_market_open() if self.alpaca else False
        market_status = Text("OPEN", style="green") if market_open else Text("CLOSED", style="red")
        status_items.append(f"Market: {market_status}")
        
        # Database status
        db_status = Text("OK", style="green") if self._cache["last_update"] else Text("ERROR", style="red")
        status_items.append(f"Database: {db_status}")
        
        # Account status
        account_status = Text("OK", style="green") if self._cache["account"] else Text("ERROR", style="red")
        status_items.append(f"Account: {account_status}")
        
        # Risk status
        positions_count = len(self._cache["positions"])
        max_positions = strategy_config.max_positions
        
        if positions_count >= max_positions:
            risk_status = Text("MAX", style="red")
        elif positions_count >= max_positions * 0.8:
            risk_status = Text("HIGH", style="yellow")
        else:
            risk_status = Text("OK", style="green")
        
        status_items.append(f"Risk: {risk_status}")
        
        # Last update
        if self._cache["last_update"]:
            seconds_ago = (now_local() - self._cache["last_update"]).total_seconds()
            update_text = f"{seconds_ago:.0f}s ago"
        else:
            update_text = "Never"
        
        status_text = "\n".join([
            f"Market: {market_status}",
            f"Database: {db_status}",
            f"Account: {account_status}",
            f"Risk: {risk_status}",
            f"Updated: {update_text}"
        ])
        
        return Panel(
            status_text,
            title="System Status",
            box=box.ROUNDED,
            style="white"
        )
    
    def render_dashboard(self, layout: Layout) -> None:
        """Render all dashboard components."""
        layout["header"].update(self.render_header())
        layout["account"].update(self.render_account_info())
        layout["positions"].update(self.render_positions())
        layout["performance"].update(self.render_performance())
        layout["decisions"].update(self.render_recent_decisions())
        layout["orders"].update(self.render_recent_orders())
        layout["status"].update(self.render_system_status())
    
    async def run_dashboard(self) -> None:
        """Run the live dashboard."""
        self.running = True
        layout = self.create_layout()
        
        try:
            with Live(layout, console=self.console, refresh_per_second=1) as live:
                while self.running:
                    try:
                        # Update data
                        await self.update_data()
                        
                        # Render dashboard
                        self.render_dashboard(layout)
                        
                        # Wait for next refresh
                        await asyncio.sleep(self.refresh_interval)
                        
                    except KeyboardInterrupt:
                        break
                    except Exception as e:
                        logger.error(f"Dashboard error: {e}")
                        await asyncio.sleep(self.refresh_interval)
        
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            self.console.print("\n[yellow]Dashboard stopped[/yellow]")
    
    def stop(self) -> None:
        """Stop the dashboard."""
        self.running = False


# CLI function
async def run_dashboard_cli() -> None:
    """CLI wrapper for running dashboard."""
    dashboard = TradingDashboard()
    
    try:
        await dashboard.run_dashboard()
    except KeyboardInterrupt:
        dashboard.stop()
        print("\nDashboard stopped by user")


if __name__ == "__main__":
    asyncio.run(run_dashboard_cli())

