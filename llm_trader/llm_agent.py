"""LLM Agent for OpenRouter integration with JSON validation and repair."""

import json
import asyncio
import ast
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

import httpx
from loguru import logger
from pydantic import ValidationError

from .config import settings, agent_config
from .models import TradingDecision
from .utils import get_local_timezone, format_timestamp


class LLMAgent:
    """
    LLM Agent for generating trading decisions via OpenRouter API.
    
    Handles prompt building, API communication, JSON validation, and repair.
    """
    
    def __init__(self):
        self.base_url = settings.openrouter_base_url
        self.api_key = settings.openrouter_api_key
        self.config = settings.llm_config
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.timeout_seconds),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/llm-trader/llm-trader",
                "X-Title": "LLM Trader"
            }
        )
        self.metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "repair_attempts": 0,
            "successful_repairs": 0
        }
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.client.aclose()
    
    async def generate_decision(
        self,
        focus_tickers: Optional[List[str]] = None,
        cash_estimate: str = "Unknown",
        notable_exposures: Optional[List[str]] = None,
        num_positions: int = 0
    ) -> Optional[TradingDecision]:
        """
        Generate a trading decision using the LLM.
        
        Args:
            focus_tickers: Optional list of tickers to focus on
            cash_estimate: Current cash estimate
            notable_exposures: Current notable exposures
            num_positions: Current number of positions
            
        Returns:
            TradingDecision object or None if generation failed
        """
        run_id = str(uuid.uuid4())
        timestamp_local = datetime.now(get_local_timezone())
        
        try:
            # Build the prompt
            prompt = self._build_prompt(
                run_id=run_id,
                timestamp_local=timestamp_local,
                focus_tickers=focus_tickers or [],
                cash_estimate=cash_estimate,
                notable_exposures=notable_exposures or [],
                num_positions=num_positions
            )
            
            logger.info(f"Generating decision for run_id: {run_id}")
            
            # Make the API call
            response_text = await self._call_llm(prompt)
            if not response_text:
                logger.error("Failed to get response from LLM")
                return None
            
            # Validate and parse JSON
            decision = await self._validate_and_repair_json(response_text, run_id)
            if not decision:
                logger.error("Failed to validate JSON response")
                return None
            
            # Ensure run_id and timestamp are set correctly
            decision.run_id = run_id
            decision.timestamp_local = timestamp_local
            
            logger.info(f"Successfully generated decision for {len(decision.research)} symbols")
            return decision
            
        except Exception as e:
            logger.error(f"Error generating decision: {e}")
            self.metrics["failed_calls"] += 1
            return None
    
    def _build_prompt(
        self,
        run_id: str,
        timestamp_local: datetime,
        focus_tickers: List[str],
        cash_estimate: str,
        notable_exposures: List[str],
        num_positions: int
    ) -> str:
        """Build the complete prompt for the LLM."""
        strategy_config = settings.strategy_config
        
        return agent_config.format_run_prompt(
            timezone=str(get_local_timezone()),
            timestamp_local=format_timestamp(timestamp_local),
            cash_estimate=cash_estimate,
            notable_exposures=notable_exposures,
            num_positions=num_positions,
            max_positions=strategy_config.max_positions,
            focus_tickers=focus_tickers,
            risk_per_position_pct=strategy_config.risk_per_position_pct,
            hype_threshold_long=strategy_config.hype_threshold_long,
            hype_threshold_short=strategy_config.hype_threshold_short,
            confidence_threshold=strategy_config.confidence_threshold,
            min_price_usd=strategy_config.min_price_usd,
            min_daily_volume=strategy_config.min_daily_volume,
            max_bid_ask_spread_pct=strategy_config.max_bid_ask_spread_pct,
            earnings_lockout_days=strategy_config.earnings_lockout_days
        )
    
    async def _call_llm(self, prompt: str) -> Optional[str]:
        """
        Make an API call to OpenRouter with retries and fallbacks.
        
        Args:
            prompt: The formatted prompt to send
            
        Returns:
            Response text or None if all attempts failed
        """
        models_to_try = [self.config.model] + self.config.fallback_models
        
        for attempt in range(self.config.max_retries):
            for model in models_to_try:
                try:
                    logger.debug(f"Calling LLM: {model} (attempt {attempt + 1})")
                    
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": agent_config.get_system_prompt()},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": self.config.temperature,
                        "max_tokens": self.config.max_tokens,
                        "stream": False
                    }
                    
                    response = await self.client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        content = data["choices"][0]["message"]["content"]
                        
                        # Update metrics
                        self.metrics["total_calls"] += 1
                        self.metrics["successful_calls"] += 1
                        if "usage" in data:
                            self.metrics["total_tokens"] += data["usage"].get("total_tokens", 0)
                        
                        logger.info(f"LLM call successful: {model}")
                        return content.strip()
                    
                    else:
                        logger.warning(f"LLM call failed: {response.status_code} - {response.text}")
                        
                except httpx.TimeoutException:
                    logger.warning(f"LLM call timeout: {model}")
                except Exception as e:
                    logger.warning(f"LLM call error: {model} - {e}")
            
            # Exponential backoff between retries
            if attempt < self.config.max_retries - 1:
                wait_time = 2 ** attempt
                logger.info(f"Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
        
        self.metrics["failed_calls"] += 1
        logger.error("All LLM call attempts failed")
        return None
    
    async def _validate_and_repair_json(
        self, 
        response_text: str, 
        run_id: str
    ) -> Optional[TradingDecision]:
        """
        Validate JSON response and attempt repair if needed.
        
        Args:
            response_text: Raw response from LLM
            run_id: Run ID for logging
            
        Returns:
            TradingDecision object or None if validation failed
        """
        # Try to extract JSON from response
        json_text = self._extract_json(response_text)
        if not json_text:
            logger.error("No JSON found in LLM response")
            return None
        
        # Try to parse and validate
        for attempt in range(3):  # Allow up to 2 repair attempts
            try:
                data = json.loads(json_text)
                decision = TradingDecision(**data)
                logger.info(f"JSON validation successful on attempt {attempt + 1}")
                return decision

            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning(f"JSON validation failed (attempt {attempt + 1}): {e}")

                # Sometimes the LLM returns a Python-style dictionary using
                # single quotes instead of valid JSON.  Attempt to parse such
                # responses using ``ast.literal_eval`` before resorting to the
                # more expensive repair step.
                if isinstance(e, json.JSONDecodeError):
                    try:
                        data = ast.literal_eval(json_text)
                        decision = TradingDecision(**data)
                        logger.info(
                            f"JSON validation successful after literal eval on attempt {attempt + 1}"
                        )
                        return decision
                    except Exception:
                        pass

                if attempt < 2:  # Try to repair
                    self.metrics["repair_attempts"] += 1
                    repaired_json = await self._repair_json(json_text, str(e))
                    if repaired_json:
                        json_text = repaired_json
                        continue

                logger.error(f"JSON validation failed after all attempts: {e}")
                return None
        
        return None
    
    def _extract_json(self, text: str) -> Optional[str]:
        """
        Extract JSON from LLM response text.
        
        Args:
            text: Raw response text
            
        Returns:
            Extracted JSON string or None
        """
        text = text.strip()
        
        # If it looks like pure JSON, return as-is
        if text.startswith('{') and text.endswith('}'):
            return text
        
        # Try to find JSON in code blocks
        if '```json' in text:
            start = text.find('```json') + 7
            end = text.find('```', start)
            if end > start:
                return text[start:end].strip()
        
        # Try to find JSON between braces
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            return text[start:end+1]
        
        return None
    
    async def _repair_json(self, json_text: str, error_msg: str) -> Optional[str]:
        """
        Attempt to repair invalid JSON using the LLM.
        
        Args:
            json_text: Invalid JSON text
            error_msg: Validation error message
            
        Returns:
            Repaired JSON string or None
        """
        try:
            repair_prompt = agent_config.get_repair_prompt().format(
                errors=error_msg,
                original_json=json_text
            )
            
            logger.info("Attempting JSON repair")
            repaired_text = await self._call_llm(repair_prompt)
            
            if repaired_text:
                repaired_json = self._extract_json(repaired_text)
                if repaired_json:
                    self.metrics["successful_repairs"] += 1
                    logger.info("JSON repair successful")
                    return repaired_json
            
            logger.warning("JSON repair failed")
            return None
            
        except Exception as e:
            logger.error(f"Error during JSON repair: {e}")
            return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        return self.metrics.copy()
    
    def reset_metrics(self) -> None:
        """Reset all metrics."""
        self.metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "repair_attempts": 0,
            "successful_repairs": 0
        }

