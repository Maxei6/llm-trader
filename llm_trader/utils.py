"""
Utility functions for timezone handling, logging setup, and JSON operations.
"""

import json
import sys
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union
from pathlib import Path
import zoneinfo

from loguru import logger

from .config import settings


def get_local_timezone() -> timezone:
    """
    Get the configured local timezone.
    
    Returns:
        timezone object for the configured timezone
    """
    try:
        return zoneinfo.ZoneInfo(settings.timezone)
    except Exception as e:
        logger.warning(f"Invalid timezone {settings.timezone}, using UTC: {e}")
        return timezone.utc


def format_timestamp(dt: datetime, include_timezone: bool = True) -> str:
    """
    Format datetime for display.
    
    Args:
        dt: datetime object to format
        include_timezone: whether to include timezone info
        
    Returns:
        Formatted timestamp string
    """
    if include_timezone:
        return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    else:
        return dt.strftime("%Y-%m-%d %H:%M:%S")


def now_local() -> datetime:
    """Get current time in local timezone."""
    return datetime.now(get_local_timezone())


def is_market_hours(dt: Optional[datetime] = None) -> bool:
    """
    Check if given time (or current time) is during market hours.
    
    Args:
        dt: datetime to check (defaults to current time)
        
    Returns:
        True if during market hours, False otherwise
    """
    if dt is None:
        dt = now_local()
    
    # Convert to market timezone (Eastern)
    try:
        market_tz = zoneinfo.ZoneInfo("America/New_York")
        market_time = dt.astimezone(market_tz)
    except:
        # Fallback if timezone conversion fails
        market_time = dt
    
    # Check if weekday (Monday=0, Sunday=6)
    if market_time.weekday() >= 5:  # Saturday or Sunday
        return False
    
    # Check if during trading hours (9:30 AM - 4:00 PM ET)
    market_open = market_time.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = market_time.replace(hour=16, minute=0, second=0, microsecond=0)
    
    return market_open <= market_time <= market_close


def setup_logging() -> None:
    """
    Setup structured logging with Loguru.
    
    Configures file rotation, retention, and format based on settings.
    """
    # Remove default handler
    logger.remove()
    
    # Console handler with colors
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        colorize=True
    )
    
    # File handler with rotation
    if settings.log_file:
        logger.add(
            settings.log_file,
            level=settings.log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            rotation=settings.log_rotation,
            retention=settings.log_retention,
            compression="gz",
            serialize=False
        )
    
    # Structured JSON handler for analysis
    json_log_file = Path(settings.log_file).with_suffix('.json') if settings.log_file else None
    if json_log_file:
        logger.add(
            json_log_file,
            level="INFO",
            format="{message}",
            rotation=settings.log_rotation,
            retention=settings.log_retention,
            serialize=True
        )
    
    logger.info("Logging configured")


def redact_secrets(data: Union[Dict[str, Any], str]) -> Union[Dict[str, Any], str]:
    """
    Redact sensitive information from data for logging.
    
    Args:
        data: Dictionary or string to redact
        
    Returns:
        Data with secrets redacted
    """
    if isinstance(data, str):
        # Redact common secret patterns
        patterns = [
            (r'("api_key":\s*")[^"]+(")', r'\1***REDACTED***\2'),
            (r'("secret_key":\s*")[^"]+(")', r'\1***REDACTED***\2'),
            (r'("password":\s*")[^"]+(")', r'\1***REDACTED***\2'),
            (r'("token":\s*")[^"]+(")', r'\1***REDACTED***\2'),
            (r'(Bearer\s+)[A-Za-z0-9\-._~+/]+=*', r'\1***REDACTED***'),
        ]
        
        result = data
        for pattern, replacement in patterns:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        
        return result
    
    elif isinstance(data, dict):
        redacted = {}
        secret_keys = {
            'api_key', 'secret_key', 'password', 'token', 'auth', 'authorization',
            'openrouter_api_key', 'alpaca_api_key', 'alpaca_secret_key'
        }
        
        for key, value in data.items():
            if key.lower() in secret_keys:
                redacted[key] = "***REDACTED***"
            elif isinstance(value, dict):
                redacted[key] = redact_secrets(value)
            elif isinstance(value, str):
                redacted[key] = redact_secrets(value)
            else:
                redacted[key] = value
        
        return redacted
    
    return data


def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """
    Safely parse JSON string with fallback.
    
    Args:
        json_str: JSON string to parse
        default: Default value if parsing fails
        
    Returns:
        Parsed JSON or default value
    """
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError) as e:
        logger.debug(f"JSON parsing failed: {e}")
        return default


def safe_json_dumps(obj: Any, default: str = "{}") -> str:
    """
    Safely serialize object to JSON string.
    
    Args:
        obj: Object to serialize
        default: Default string if serialization fails
        
    Returns:
        JSON string or default
    """
    try:
        return json.dumps(obj, default=str, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        logger.debug(f"JSON serialization failed: {e}")
        return default


def format_currency(amount: float, currency: str = "USD") -> str:
    """
    Format currency amount for display.
    
    Args:
        amount: Amount to format
        currency: Currency code
        
    Returns:
        Formatted currency string
    """
    if currency == "USD":
        if abs(amount) >= 1_000_000:
            return f"${amount/1_000_000:.2f}M"
        elif abs(amount) >= 1_000:
            return f"${amount/1_000:.1f}K"
        else:
            return f"${amount:.2f}"
    else:
        return f"{amount:.2f} {currency}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """
    Format percentage for display.
    
    Args:
        value: Percentage value (e.g., 0.05 for 5%)
        decimals: Number of decimal places
        
    Returns:
        Formatted percentage string
    """
    return f"{value * 100:.{decimals}f}%"


def format_number(value: Union[int, float], decimals: int = 2) -> str:
    """
    Format number with appropriate suffixes.
    
    Args:
        value: Number to format
        decimals: Number of decimal places
        
    Returns:
        Formatted number string
    """
    if abs(value) >= 1_000_000_000:
        return f"{value/1_000_000_000:.{decimals}f}B"
    elif abs(value) >= 1_000_000:
        return f"{value/1_000_000:.{decimals}f}M"
    elif abs(value) >= 1_000:
        return f"{value/1_000:.{decimals}f}K"
    else:
        return f"{value:.{decimals}f}"


def validate_symbol(symbol: str) -> bool:
    """
    Validate stock ticker symbol format.
    
    Args:
        symbol: Stock ticker symbol
        
    Returns:
        True if valid format, False otherwise
    """
    if not symbol or not isinstance(symbol, str):
        return False
    
    # Basic validation: 1-5 uppercase letters
    pattern = r'^[A-Z]{1,5}$'
    return bool(re.match(pattern, symbol.upper()))


def calculate_atr_stop(
    current_price: float,
    atr_value: float,
    multiplier: float = 2.0,
    action: str = "long"
) -> float:
    """
    Calculate ATR-based stop loss price.
    
    Args:
        current_price: Current market price
        atr_value: Average True Range value
        multiplier: ATR multiplier (default 2.0)
        action: "long" or "short"
        
    Returns:
        Stop loss price
    """
    stop_distance = atr_value * multiplier
    
    if action.lower() == "long":
        return current_price - stop_distance
    else:  # short
        return current_price + stop_distance


def calculate_position_size(
    account_equity: float,
    risk_per_trade_pct: float,
    entry_price: float,
    stop_price: float
) -> int:
    """
    Calculate position size based on risk management.
    
    Args:
        account_equity: Total account equity
        risk_per_trade_pct: Risk percentage per trade (e.g., 1.0 for 1%)
        entry_price: Entry price per share
        stop_price: Stop loss price per share
        
    Returns:
        Number of shares to trade
    """
    if entry_price <= 0 or stop_price <= 0:
        return 0
    
    risk_amount = account_equity * (risk_per_trade_pct / 100)
    risk_per_share = abs(entry_price - stop_price)
    
    if risk_per_share <= 0:
        return 0
    
    position_size = int(risk_amount / risk_per_share)
    return max(0, position_size)


def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds
        
    Returns:
        Decorator function
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            import asyncio
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries:
                        logger.error(f"Function {func.__name__} failed after {max_retries} retries: {e}")
                        raise
                    
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Function {func.__name__} failed (attempt {attempt + 1}), retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
            
        return wrapper
    return decorator


class RateLimiter:
    """Simple rate limiter for API calls."""
    
    def __init__(self, max_calls: int, time_window: float):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
    
    async def acquire(self) -> None:
        """Acquire rate limit token, waiting if necessary."""
        import asyncio
        
        now = datetime.now().timestamp()
        
        # Remove old calls outside the time window
        self.calls = [call_time for call_time in self.calls if now - call_time < self.time_window]
        
        # If we're at the limit, wait
        if len(self.calls) >= self.max_calls:
            oldest_call = min(self.calls)
            wait_time = self.time_window - (now - oldest_call)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
        
        # Record this call
        self.calls.append(now)


def create_run_id() -> str:
    """Create a unique run ID for tracking."""
    import uuid
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = str(uuid.uuid4())[:8]
    return f"{timestamp}_{short_uuid}"


def parse_time_duration(duration_str: str) -> float:
    """
    Parse time duration string to seconds.
    
    Args:
        duration_str: Duration string like "5m", "1h", "30s"
        
    Returns:
        Duration in seconds
    """
    pattern = r'^(\d+(?:\.\d+)?)\s*([smhd]?)$'
    match = re.match(pattern, duration_str.lower().strip())
    
    if not match:
        raise ValueError(f"Invalid duration format: {duration_str}")
    
    value = float(match.group(1))
    unit = match.group(2) or 's'
    
    multipliers = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400
    }
    
    return value * multipliers[unit]


# Initialize logging when module is imported
setup_logging()

