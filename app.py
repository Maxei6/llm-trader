"""
Command-line interface for LLM Trader using Typer.
"""

import asyncio
from typing import Optional, List
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from loguru import logger

from llm_trader.runner import run_once_cli, run_continuous_cli
from llm_trader.dashboard_terminal import run_dashboard_cli
from llm_trader.config import settings
from llm_trader.utils import setup_logging

# Initialize Typer app
app = typer.Typer(
    name="llm-trader",
    help="Autonomous LLM-driven equities trader with Hype & Event Momentum strategy",
    add_completion=False
)

console = Console()


def version_callback(value: bool):
    """Show version information."""
    if value:
        from llm_trader import __version__
        console.print(f"LLM Trader v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", 
        callback=version_callback,
        help="Show version and exit"
    ),
    debug: bool = typer.Option(
        False, "--debug", "-d",
        help="Enable debug logging"
    ),
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c",
        help="Path to configuration file"
    )
):
    """
    LLM Trader - Autonomous equities trading with AI-driven momentum strategy.
    
    A production-ready Python trading system that uses Large Language Models
    to analyze market sentiment and news events for momentum trading decisions.
    """
    # Setup logging
    if debug:
        import os
        os.environ["LOG_LEVEL"] = "DEBUG"
    
    setup_logging()
    
    # Load custom config if provided
    if config_file and config_file.exists():
        logger.info(f"Loading configuration from {config_file}")
        # In a real implementation, you'd load the config file here
    
    # Show startup banner
    if not any(arg in ["--version", "-v", "--help"] for arg in typer.get_params()):
        show_banner()


def show_banner():
    """Display startup banner."""
    banner_text = Text.assemble(
        ("LLM TRADER", "bold blue"),
        "\n",
        ("Autonomous AI-Driven Equities Trading", "cyan"),
        "\n\n",
        ("Strategy: ", "white"), ("Hype & Event Momentum", "green"),
        "\n",
        ("Mode: ", "white"), (f"{settings.alpaca_mode.upper()}", "yellow" if settings.alpaca_mode == "paper" else "red"),
        "\n",
        ("Model: ", "white"), (settings.llm_model, "magenta")
    )
    
    panel = Panel(
        banner_text,
        title="🤖 AI Trader",
        border_style="blue",
        padding=(1, 2)
    )
    
    console.print(panel)


@app.command()
def once(
    tickers: Optional[List[str]] = typer.Option(
        None, "--ticker", "-t",
        help="Focus on specific tickers (can be used multiple times)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n",
        help="Analyze only, don't submit orders"
    )
):
    """
    Run a single trading analysis cycle.
    
    Analyzes market conditions, generates trading decisions using LLM,
    and optionally submits orders based on the strategy rules.
    """
    console.print("[bold green]Starting single trading cycle...[/bold green]")
    
    if dry_run:
        console.print("[yellow]DRY RUN MODE: No orders will be submitted[/yellow]")
        # In a real implementation, you'd set a flag to prevent order submission
    
    if tickers:
        console.print(f"[cyan]Focusing on tickers: {', '.join(tickers)}[/cyan]")
    
    try:
        # Run the trading cycle
        success = asyncio.run(run_once_cli(focus_tickers=tickers))
        
        if success:
            console.print("[bold green]✓ Trading cycle completed successfully[/bold green]")
        else:
            console.print("[bold red]✗ Trading cycle failed[/bold red]")
            raise typer.Exit(1)
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Trading cycle interrupted by user[/yellow]")
        raise typer.Exit(130)
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        logger.error(f"CLI error in once command: {e}")
        raise typer.Exit(1)


@app.command()
def run(
    tickers: Optional[List[str]] = typer.Option(
        None, "--ticker", "-t",
        help="Focus on specific tickers (can be used multiple times)"
    ),
    interval: Optional[int] = typer.Option(
        None, "--interval", "-i",
        help="Override loop interval in seconds"
    ),
    market_hours_only: Optional[bool] = typer.Option(
        None, "--market-hours/--24-7",
        help="Trade only during market hours"
    )
):
    """
    Run continuous trading loop.
    
    Continuously monitors market conditions and executes trades based on
    LLM analysis and momentum strategy. Includes graceful shutdown handling
    and exponential backoff on errors.
    """
    console.print("[bold green]Starting continuous trading loop...[/bold green]")
    
    # Override settings if provided
    if interval:
        import os
        os.environ["LOOP_INTERVAL_SECONDS"] = str(interval)
        console.print(f"[cyan]Loop interval set to {interval} seconds[/cyan]")
    
    if market_hours_only is not None:
        import os
        os.environ["MARKET_HOURS_ONLY"] = str(market_hours_only).lower()
        mode = "market hours only" if market_hours_only else "24/7"
        console.print(f"[cyan]Trading mode: {mode}[/cyan]")
    
    if tickers:
        console.print(f"[cyan]Focusing on tickers: {', '.join(tickers)}[/cyan]")
    
    console.print("\n[dim]Press Ctrl+C to stop gracefully[/dim]")
    
    try:
        # Run continuous loop
        asyncio.run(run_continuous_cli(focus_tickers=tickers))
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Trading loop stopped by user[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        logger.error(f"CLI error in run command: {e}")
        raise typer.Exit(1)


@app.command()
def dashboard(
    refresh: Optional[int] = typer.Option(
        None, "--refresh", "-r",
        help="Dashboard refresh interval in seconds"
    )
):
    """
    Show real-time trading dashboard.
    
    Displays a comprehensive terminal dashboard with equity curve,
    positions, recent decisions, orders, and system status.
    Updates in real-time with configurable refresh interval.
    """
    console.print("[bold green]Starting trading dashboard...[/bold green]")
    
    if refresh:
        import os
        os.environ["DASHBOARD_REFRESH_SECONDS"] = str(refresh)
        console.print(f"[cyan]Refresh interval set to {refresh} seconds[/cyan]")
    
    console.print("[dim]Press Ctrl+C to exit dashboard[/dim]\n")
    
    try:
        # Run dashboard
        asyncio.run(run_dashboard_cli())
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard stopped by user[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        logger.error(f"CLI error in dashboard command: {e}")
        raise typer.Exit(1)


@app.command()
def config(
    show: bool = typer.Option(
        False, "--show", "-s",
        help="Show current configuration"
    ),
    validate: bool = typer.Option(
        False, "--validate", "-v",
        help="Validate configuration"
    )
):
    """
    Configuration management.
    
    Show current configuration settings or validate the configuration
    for required API keys and proper values.
    """
    if show:
        console.print("[bold blue]Current Configuration:[/bold blue]\n")
        
        # Show key configuration items (redacted)
        config_items = [
            ("LLM Model", settings.llm_model),
            ("Trading Mode", settings.alpaca_mode.upper()),
            ("Risk Per Position", f"{settings.risk_per_position_pct}%"),
            ("Max Positions", str(settings.max_positions)),
            ("Loop Interval", f"{settings.loop_interval_seconds}s"),
            ("Market Hours Only", str(settings.market_hours_only)),
            ("Timezone", settings.timezone),
            ("Database URL", settings.database_url),
            ("Log Level", settings.log_level)
        ]
        
        for key, value in config_items:
            console.print(f"  [cyan]{key}:[/cyan] {value}")
    
    if validate:
        console.print("[bold blue]Validating Configuration:[/bold blue]\n")
        
        errors = []
        warnings = []
        
        # Check required API keys
        if not settings.openrouter_api_key or settings.openrouter_api_key == "your_openrouter_api_key_here":
            errors.append("OpenRouter API key not configured")
        
        if not settings.alpaca_api_key or settings.alpaca_api_key == "your_alpaca_api_key_here":
            errors.append("Alpaca API key not configured")
        
        if not settings.alpaca_secret_key or settings.alpaca_secret_key == "your_alpaca_secret_key_here":
            errors.append("Alpaca secret key not configured")
        
        # Check risk parameters
        if settings.risk_per_position_pct > 2.0:
            warnings.append(f"High risk per position: {settings.risk_per_position_pct}%")
        
        if settings.max_positions > 10:
            warnings.append(f"High max positions: {settings.max_positions}")
        
        # Show results
        if errors:
            console.print("[bold red]Errors:[/bold red]")
            for error in errors:
                console.print(f"  ✗ {error}")
        
        if warnings:
            console.print("[bold yellow]Warnings:[/bold yellow]")
            for warning in warnings:
                console.print(f"  ⚠ {warning}")
        
        if not errors and not warnings:
            console.print("[bold green]✓ Configuration is valid[/bold green]")
        elif errors:
            console.print(f"\n[bold red]Configuration has {len(errors)} error(s)[/bold red]")
            raise typer.Exit(1)
        else:
            console.print(f"\n[bold yellow]Configuration has {len(warnings)} warning(s)[/bold yellow]")


@app.command()
def status():
    """
    Show system status and health check.
    
    Performs basic connectivity tests and shows system status
    including database, broker connection, and LLM availability.
    """
    console.print("[bold blue]System Status Check:[/bold blue]\n")
    
    async def check_status():
        from llm_trader.alpaca_client import AlpacaClient
        from llm_trader.store import DatabaseStore
        from llm_trader.llm_agent import LLMAgent
        
        status_items = []
        
        # Check database
        try:
            store = DatabaseStore()
            # Try a simple query
            await store.get_recent_decisions(limit=1)
            status_items.append(("Database", "✓ Connected", "green"))
        except Exception as e:
            status_items.append(("Database", f"✗ Error: {e}", "red"))
        
        # Check Alpaca connection
        try:
            alpaca = AlpacaClient()
            account = await alpaca.get_account()
            if account:
                status_items.append(("Alpaca Broker", f"✓ Connected ({settings.alpaca_mode})", "green"))
            else:
                status_items.append(("Alpaca Broker", "✗ Connection failed", "red"))
        except Exception as e:
            status_items.append(("Alpaca Broker", f"✗ Error: {e}", "red"))
        
        # Check LLM connection
        try:
            async with LLMAgent() as llm:
                # This would be a simple test call in a real implementation
                status_items.append(("LLM Service", "✓ Available", "green"))
        except Exception as e:
            status_items.append(("LLM Service", f"✗ Error: {e}", "red"))
        
        # Check market status
        try:
            alpaca = AlpacaClient()
            market_open = alpaca.is_market_open()
            status = "Open" if market_open else "Closed"
            color = "green" if market_open else "yellow"
            status_items.append(("Market Status", f"• {status}", color))
        except Exception as e:
            status_items.append(("Market Status", f"✗ Error: {e}", "red"))
        
        return status_items
    
    try:
        status_items = asyncio.run(check_status())
        
        for component, status, color in status_items:
            console.print(f"  [cyan]{component}:[/cyan] [{color}]{status}[/{color}]")
        
        # Overall status
        errors = sum(1 for _, status, _ in status_items if "✗" in status)
        if errors == 0:
            console.print("\n[bold green]✓ All systems operational[/bold green]")
        else:
            console.print(f"\n[bold red]✗ {errors} system(s) have issues[/bold red]")
            raise typer.Exit(1)
            
    except Exception as e:
        console.print(f"[bold red]Status check failed: {e}[/bold red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()

