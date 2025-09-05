# LLM Trader

An autonomous LLM-driven equities trader implementing a Hype & Event Momentum strategy with strict quantitative gates and risk controls.

## Overview

This trading system uses Large Language Models to analyze market sentiment and news events, making trading decisions based on a focused momentum strategy. The system is designed to be simple yet robust for solo developers, with comprehensive risk management and monitoring capabilities.

## Strategy: Hype & Event Momentum

The bot implements a single, focused trading strategy:

### LLM Signal Generation
- Scans reputable headlines and company news
- Outputs sentiment analysis (positive/negative/neutral)
- Calculates hype scores based on volume and tone of mentions
- Identifies catalysts (earnings, product launches, regulations, etc.)
- Provides evidence with sources and links

### Quantitative Gates
All trades must pass these filters:
- Price ≥ $5 USD (no penny stocks)
- Average daily volume ≥ 1,000,000 shares
- Bid-ask spread ≤ 1%
- Not within 2 trading days of earnings (unless earnings is the catalyst)
- Sufficient liquidity for position size

### Trading Rules
- **Long**: sentiment = positive AND hype_score ≥ 0.70
- **Short**: sentiment = negative AND hype_score ≤ 0.30
- **No Trade**: Otherwise

### Risk Management
- Risk per position: 0.5-0.75% of equity (configurable)
- Initial stop: 2× ATR(14) from entry
- Take profit: 1.5-2.0× risk or trailing ATR
- Maximum positions: 6 (configurable)
- Portfolio kill switch: pause if drawdown > 6%

## Architecture

```
llm_trader/
├── __init__.py
├── config.py              # Centralized configuration and prompts
├── models.py              # Pydantic models for schema and DB
├── llm_agent.py           # OpenRouter client and JSON validation
├── tools.py               # Web search and market data interfaces
├── alpaca_client.py       # Alpaca broker integration
├── executor.py            # Order sizing and execution logic
├── store.py               # SQLite storage with WAL mode
├── runner.py              # Main trading loop with backoff
├── dashboard_terminal.py  # Rich terminal dashboard
└── utils.py               # Timezone helpers and logging
```

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd llm_trader_project
```

2. Install dependencies:
```bash
pip install -e .
```

For development:
```bash
pip install -e ".[dev]"
```

3. Copy and configure environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys and configuration
```

## Configuration

All configuration is centralized in `config.py` and can be overridden via environment variables:

### Required API Keys
- **OpenRouter**: Get your API key from [OpenRouter](https://openrouter.ai/)
- **Alpaca**: Get your API keys from [Alpaca Markets](https://alpaca.markets/)

### Key Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | - | OpenRouter API key (required) |
| `ALPACA_API_KEY` | - | Alpaca API key (required) |
| `ALPACA_SECRET_KEY` | - | Alpaca secret key (required) |
| `ALPACA_MODE` | `paper` | Trading mode: `paper` or `live` |
| `LLM_MODEL` | `anthropic/claude-3-haiku` | LLM model to use |
| `RISK_PER_POSITION_PCT` | `0.75` | Risk per position (% of equity) |
| `MAX_POSITIONS` | `6` | Maximum concurrent positions |
| `LOOP_INTERVAL_SECONDS` | `300` | Loop interval (5 minutes) |
| `MARKET_HOURS_ONLY` | `true` | Trade only during market hours |

See `.env.example` for all available configuration options.

## Usage

### CLI Commands

```bash
# Run once (single analysis cycle)
llm-trader once

# Run once with specific tickers
llm-trader once --ticker AAPL --ticker MSFT

# Run continuously
llm-trader run

# Run continuously with custom interval
llm-trader run --interval 600  # 10 minutes

# Show real-time dashboard
llm-trader dashboard

# Show configuration
llm-trader config --show

# Validate configuration
llm-trader config --validate

# Check system status
llm-trader status
```

### Dashboard

The Rich terminal dashboard displays:
- Real-time P&L and equity curve
- Open positions with unrealized P&L
- Recent trading decisions with confidence scores
- Order history and execution status
- System status and risk flags
- Performance metrics (30-day)

Press `Ctrl+C` to exit the dashboard.

### Example Output

```
┌─────────────────────────────────────────────────────────────────┐
│                        LLM TRADER DASHBOARD                     │
│                   Last Updated: 2024-01-15 14:30:22 EST        │
└─────────────────────────────────────────────────────────────────┘

┌─ Account Info ──────────┐  ┌─ Recent Decisions ─────────────────┐
│ Total Equity  $102,450  │  │ Time     Symbol  Action  Conf  R:R │
│ Cash          $47,500   │  │ 14:30:22 AAPL    LONG    0.82  1.9 │
│ Buying Power  $102,450  │  │ 14:30:22 TSLA    SHORT   0.71  1.6 │
│ Daily P&L     +$2,450   │  │ 14:25:15 MSFT    NO-TRADE 0.45 1.1 │
│ Day Trades    0         │  │ 14:20:08 GOOGL   NO-TRADE 0.38 0.9 │
│ PDT Status    No        │  └─────────────────────────────────────┘
└─────────────────────────┘
```

## Data Storage

The system uses SQLite with WAL mode for:
- Trading decisions and analysis
- Order history and fills
- Position snapshots
- Equity curve tracking
- Structured logs

Database file: `llm_trader.db` (configurable)

## Testing

Run the test suite:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=llm_trader --cov-report=html
```

Run specific test categories:
```bash
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m smoke         # Smoke tests only
```

## Development

### Code Quality

The project includes pre-commit hooks for code quality:

```bash
# Install pre-commit hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

Tools used:
- **Black**: Code formatting
- **isort**: Import sorting
- **flake8**: Linting
- **mypy**: Type checking

### Project Structure

- `llm_trader/`: Main package
- `tests/`: Test suite
- `examples/`: Example configurations and data
- `app.py`: CLI entry point
- `pyproject.toml`: Project configuration

### Adding New Features

1. Update models in `models.py` if needed
2. Add configuration options to `config.py`
3. Implement core logic in appropriate modules
4. Add comprehensive tests
5. Update documentation

## Safety Features

- **Strict JSON Schema Validation**: All LLM outputs are validated and repaired
- **Comprehensive Logging**: Structured logging with secret redaction
- **Idempotent Operations**: Operation IDs prevent duplicate executions
- **Graceful Shutdown**: Handles interrupts and cleanup properly
- **Market Hours Validation**: Respects trading hours and holidays
- **Portfolio Kill Switch**: Automatic pause on excessive drawdown
- **Risk Limits**: Position sizing and exposure controls

## Monitoring and Alerts

### Built-in Monitoring
- Real-time dashboard with system status
- Equity curve tracking and drawdown monitoring
- Order execution monitoring
- Error tracking and retry logic

### Logging
- Structured JSON logs for analysis
- Configurable log levels and rotation
- Secret redaction for security
- Performance metrics tracking

### Risk Controls
- Maximum position limits
- Drawdown kill switch (configurable threshold)
- Position sizing based on account equity
- Stop-loss and take-profit automation

## Production Deployment

### Recommended Setup
1. Use a dedicated server or VPS
2. Set up proper logging and monitoring
3. Configure alerts for system failures
4. Use `systemd` or similar for process management
5. Regular database backups
6. Monitor API rate limits and costs

### Environment Variables for Production
```bash
# Use live trading (be careful!)
ALPACA_MODE=live
ALPACA_BASE_URL=https://api.alpaca.markets

# Reduce risk in production
RISK_PER_POSITION_PCT=0.5
MAX_POSITIONS=4

# Enable comprehensive logging
LOG_LEVEL=INFO
ENABLE_METRICS=true
```

## Troubleshooting

### Common Issues

1. **API Key Errors**
   - Verify keys are correctly set in `.env`
   - Check API key permissions and limits

2. **Database Errors**
   - Ensure write permissions for database file
   - Check disk space availability

3. **Market Data Issues**
   - Verify Alpaca account status
   - Check market hours and holidays

4. **LLM Errors**
   - Monitor OpenRouter API status
   - Check rate limits and billing

### Debug Mode
```bash
llm-trader --debug run
```

### Logs Location
- Console: Real-time output
- File: `llm_trader.log` (configurable)
- JSON: `llm_trader.json` (structured logs)

## Performance

### Typical Resource Usage
- **Memory**: 50-100 MB
- **CPU**: Low (mostly I/O bound)
- **Network**: Moderate (API calls)
- **Storage**: ~1 MB/day for logs and data

### Optimization Tips
- Adjust loop interval based on strategy needs
- Use appropriate log levels in production
- Monitor API costs and rate limits
- Regular database maintenance

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## Disclaimer

**Important**: This software is for educational and research purposes only. 

- Trading involves substantial risk of loss
- Past performance does not guarantee future results
- The authors are not responsible for any financial losses
- Always test thoroughly in paper trading mode first
- Consult with financial advisors before live trading
- Use at your own risk

## Support

For issues and questions:
- Check the troubleshooting section
- Review existing GitHub issues
- Create a new issue with detailed information

## Roadmap

Future enhancements may include:
- Additional trading strategies
- More sophisticated risk management
- Portfolio optimization features
- Backtesting capabilities
- Web-based dashboard
- Mobile notifications
- Integration with additional brokers

