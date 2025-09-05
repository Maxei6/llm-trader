"""
Tools for web search, market data, and fundamentals retrieval.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import re

import httpx
import requests
from bs4 import BeautifulSoup
from loguru import logger

from .config import settings, search_config


@dataclass
class NewsItem:
    """Represents a news item from search results."""
    title: str
    url: str
    publisher: str
    date: datetime
    snippet: str
    relevance_score: float = 0.0


@dataclass
class MarketQuote:
    """Represents a market quote for a symbol."""
    symbol: str
    price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    avg_volume: Optional[int] = None
    market_cap: Optional[float] = None
    timestamp: Optional[datetime] = None


@dataclass
class FundamentalsData:
    """Represents fundamental data for a symbol."""
    symbol: str
    market_cap: Optional[str] = None
    revenue_ltm: Optional[str] = None
    growth_yoy: Optional[str] = None
    margin_brief: Optional[str] = None
    next_earnings: Optional[datetime] = None
    pe_ratio: Optional[float] = None
    sector: Optional[str] = None


class WebSearchTool:
    """
    Web search tool for finding credible news sources.
    
    Uses multiple search engines and filters results by publisher quality.
    """
    
    def __init__(self):
        self.config = search_config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    async def search(
        self, 
        query: str, 
        recency_days: Optional[int] = None
    ) -> List[NewsItem]:
        """
        Search for news items related to the query.
        
        Args:
            query: Search query string
            recency_days: Limit results to last N days
            
        Returns:
            List of NewsItem objects
        """
        recency_days = recency_days or self.config.recency_days
        
        try:
            logger.info(f"Searching for: {query}")
            
            # Use multiple search strategies
            results = []
            
            # Google News search
            google_results = await self._search_google_news(query, recency_days)
            results.extend(google_results)
            
            # Yahoo Finance search (for financial news)
            if any(term in query.lower() for term in ['stock', 'earnings', 'revenue', '$']):
                yahoo_results = await self._search_yahoo_finance(query, recency_days)
                results.extend(yahoo_results)
            
            # Filter and deduplicate
            filtered_results = self._filter_and_dedupe(results)
            
            logger.info(f"Found {len(filtered_results)} relevant news items")
            return filtered_results
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    async def _search_google_news(self, query: str, recency_days: int) -> List[NewsItem]:
        """Search Google News for recent articles."""
        try:
            # Build search URL
            encoded_query = requests.utils.quote(query)
            url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            # Parse RSS feed
            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all('item')
            
            results = []
            cutoff_date = datetime.now() - timedelta(days=recency_days)
            
            for item in items[:20]:  # Limit to first 20 results
                try:
                    title = item.title.text if item.title else ""
                    link = item.link.text if item.link else ""
                    pub_date = item.pubDate.text if item.pubDate else ""
                    description = item.description.text if item.description else ""
                    
                    # Parse date
                    try:
                        date = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %Z")
                    except:
                        date = datetime.now()
                    
                    if date < cutoff_date:
                        continue
                    
                    # Extract publisher from link
                    publisher = self._extract_publisher(link)
                    
                    if self._is_publisher_allowed(publisher):
                        results.append(NewsItem(
                            title=title,
                            url=link,
                            publisher=publisher,
                            date=date,
                            snippet=description[:200],
                            relevance_score=self._calculate_relevance(title, query)
                        ))
                        
                except Exception as e:
                    logger.debug(f"Error parsing news item: {e}")
                    continue
            
            return results
            
        except Exception as e:
            logger.warning(f"Google News search failed: {e}")
            return []
    
    async def _search_yahoo_finance(self, query: str, recency_days: int) -> List[NewsItem]:
        """Search Yahoo Finance for financial news."""
        try:
            # Extract ticker if present
            ticker_match = re.search(r'\b[A-Z]{1,5}\b', query.upper())
            if not ticker_match:
                return []
            
            ticker = ticker_match.group()
            url = f"https://finance.yahoo.com/quote/{ticker}/news"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find news articles
            articles = soup.find_all('h3', class_=re.compile('Mb\\(5px\\)'))
            
            results = []
            cutoff_date = datetime.now() - timedelta(days=recency_days)
            
            for article in articles[:10]:
                try:
                    link_elem = article.find('a')
                    if not link_elem:
                        continue
                    
                    title = link_elem.get_text(strip=True)
                    href = link_elem.get('href', '')
                    
                    # Make absolute URL
                    if href.startswith('/'):
                        url = f"https://finance.yahoo.com{href}"
                    else:
                        url = href
                    
                    # Use current time as date (Yahoo doesn't always provide dates)
                    date = datetime.now()
                    
                    results.append(NewsItem(
                        title=title,
                        url=url,
                        publisher="yahoo.com",
                        date=date,
                        snippet="",
                        relevance_score=self._calculate_relevance(title, query)
                    ))
                    
                except Exception as e:
                    logger.debug(f"Error parsing Yahoo article: {e}")
                    continue
            
            return results
            
        except Exception as e:
            logger.warning(f"Yahoo Finance search failed: {e}")
            return []
    
    def _extract_publisher(self, url: str) -> str:
        """Extract publisher domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            
            return domain
        except:
            return "unknown"
    
    def _is_publisher_allowed(self, publisher: str) -> bool:
        """Check if publisher is allowed based on configuration."""
        if not publisher:
            return False
        
        # Check blocked list first
        if self.config.blocked_publishers:
            for blocked in self.config.blocked_publishers:
                if blocked.lower() in publisher.lower():
                    return False
        
        # Check allowed list
        if self.config.allowed_publishers:
            for allowed in self.config.allowed_publishers:
                if allowed.lower() in publisher.lower():
                    return True
            return False  # Not in allowed list
        
        return True  # No restrictions
    
    def _calculate_relevance(self, title: str, query: str) -> float:
        """Calculate relevance score for a news item."""
        title_lower = title.lower()
        query_lower = query.lower()
        
        # Simple keyword matching
        query_words = query_lower.split()
        matches = sum(1 for word in query_words if word in title_lower)
        
        return matches / len(query_words) if query_words else 0.0
    
    def _filter_and_dedupe(self, results: List[NewsItem]) -> List[NewsItem]:
        """Filter and deduplicate search results."""
        # Remove duplicates by URL
        seen_urls = set()
        unique_results = []
        
        for item in results:
            if item.url not in seen_urls:
                seen_urls.add(item.url)
                unique_results.append(item)
        
        # Sort by relevance and date
        unique_results.sort(key=lambda x: (x.relevance_score, x.date), reverse=True)
        
        # Apply quality filter
        filtered_results = [
            item for item in unique_results 
            if item.relevance_score >= self.config.min_source_quality_score
        ]
        
        return filtered_results[:10]  # Limit to top 10


class MarketDataTool:
    """
    Market data tool for quotes, bars, and volume information.
    
    Integrates with Alpaca and fallback sources for market data.
    """
    
    def __init__(self, alpaca_client=None):
        self.alpaca_client = alpaca_client
        self.session = requests.Session()
    
    async def get_quote(self, symbol: str) -> Optional[MarketQuote]:
        """
        Get current quote for a symbol.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            MarketQuote object or None
        """
        try:
            # Try Alpaca first if available
            if self.alpaca_client:
                quote = await self._get_alpaca_quote(symbol)
                if quote:
                    return quote
            
            # Fallback to Yahoo Finance
            return await self._get_yahoo_quote(symbol)
            
        except Exception as e:
            logger.error(f"Error getting quote for {symbol}: {e}")
            return None
    
    async def _get_alpaca_quote(self, symbol: str) -> Optional[MarketQuote]:
        """Get quote from Alpaca API."""
        try:
            if not self.alpaca_client:
                return None
            
            # Get latest quote
            quote_data = self.alpaca_client.get_latest_quote(symbol)
            
            # Get bars for volume data
            bars_data = self.alpaca_client.get_latest_bar(symbol)
            
            return MarketQuote(
                symbol=symbol,
                price=float(quote_data.ask_price + quote_data.bid_price) / 2,
                bid=float(quote_data.bid_price),
                ask=float(quote_data.ask_price),
                volume=int(bars_data.volume) if bars_data else None,
                timestamp=quote_data.timestamp
            )
            
        except Exception as e:
            logger.warning(f"Alpaca quote failed for {symbol}: {e}")
            return None
    
    async def _get_yahoo_quote(self, symbol: str) -> Optional[MarketQuote]:
        """Get quote from Yahoo Finance."""
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if not data.get('chart', {}).get('result'):
                return None
            
            result = data['chart']['result'][0]
            meta = result.get('meta', {})
            
            return MarketQuote(
                symbol=symbol,
                price=meta.get('regularMarketPrice', 0.0),
                volume=meta.get('regularMarketVolume'),
                avg_volume=meta.get('averageDailyVolume10Day'),
                market_cap=meta.get('marketCap'),
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.warning(f"Yahoo quote failed for {symbol}: {e}")
            return None
    
    def calculate_bid_ask_spread_pct(self, quote: MarketQuote) -> Optional[float]:
        """Calculate bid-ask spread as percentage."""
        if not quote.bid or not quote.ask or quote.ask <= 0:
            return None
        
        spread = quote.ask - quote.bid
        return (spread / quote.ask) * 100


class FundamentalsTool:
    """
    Fundamentals tool for company financial data.
    
    Provides basic fundamental metrics and earnings dates.
    """
    
    def __init__(self):
        self.session = requests.Session()
    
    async def get_snapshot(self, symbol: str) -> Optional[FundamentalsData]:
        """
        Get fundamental snapshot for a symbol.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            FundamentalsData object or None
        """
        try:
            # Try Yahoo Finance for basic fundamentals
            return await self._get_yahoo_fundamentals(symbol)
            
        except Exception as e:
            logger.error(f"Error getting fundamentals for {symbol}: {e}")
            return None
    
    async def _get_yahoo_fundamentals(self, symbol: str) -> Optional[FundamentalsData]:
        """Get fundamentals from Yahoo Finance."""
        try:
            # Get summary data
            url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
            params = {
                'modules': 'summaryDetail,defaultKeyStatistics,financialData,calendarEvents'
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if not data.get('quoteSummary', {}).get('result'):
                return None
            
            result = data['quoteSummary']['result'][0]
            
            # Extract data
            summary = result.get('summaryDetail', {})
            key_stats = result.get('defaultKeyStatistics', {})
            financial = result.get('financialData', {})
            calendar = result.get('calendarEvents', {})
            
            # Format market cap
            market_cap = summary.get('marketCap', {}).get('raw')
            market_cap_str = self._format_large_number(market_cap) if market_cap else None
            
            # Format revenue
            revenue = financial.get('totalRevenue', {}).get('raw')
            revenue_str = self._format_large_number(revenue) if revenue else None
            
            # Get growth rate
            growth = financial.get('revenueGrowth', {}).get('raw')
            growth_str = f"{growth:.1%}" if growth else None
            
            # Get margins
            margin = financial.get('operatingMargins', {}).get('raw')
            margin_str = f"Op: {margin:.1%}" if margin else None
            
            # Get next earnings
            earnings_date = None
            earnings_data = calendar.get('earnings', {}).get('earningsDate')
            if earnings_data and len(earnings_data) > 0:
                earnings_timestamp = earnings_data[0].get('raw')
                if earnings_timestamp:
                    earnings_date = datetime.fromtimestamp(earnings_timestamp)
            
            return FundamentalsData(
                symbol=symbol,
                market_cap=market_cap_str,
                revenue_ltm=revenue_str,
                growth_yoy=growth_str,
                margin_brief=margin_str,
                next_earnings=earnings_date,
                pe_ratio=summary.get('trailingPE', {}).get('raw'),
                sector=summary.get('sector')
            )
            
        except Exception as e:
            logger.warning(f"Yahoo fundamentals failed for {symbol}: {e}")
            return None
    
    def _format_large_number(self, value: float) -> str:
        """Format large numbers with appropriate suffixes."""
        if value >= 1e12:
            return f"${value/1e12:.1f}T"
        elif value >= 1e9:
            return f"${value/1e9:.1f}B"
        elif value >= 1e6:
            return f"${value/1e6:.1f}M"
        else:
            return f"${value:,.0f}"


# Global tool instances
web_search = WebSearchTool()
market_data = MarketDataTool()
fundamentals = FundamentalsTool()

