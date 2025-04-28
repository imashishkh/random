from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class RateLimitType(Enum):
    """Types of rate limits that can be applied."""
    REQUEST_WEIGHT = "REQUEST_WEIGHT"  # Weight-based limit (Binance style)
    REQUEST_COUNT = "REQUEST_COUNT"    # Count-based limit
    ORDER_COUNT = "ORDER_COUNT"        # Order-specific limit
    RAW_REQUESTS = "RAW_REQUESTS"      # Simple request count limit


class RateLimitInterval(Enum):
    """Time intervals for rate limits."""
    SECOND = "SECOND"
    MINUTE = "MINUTE"
    HOUR = "HOUR"
    DAY = "DAY"


@dataclass
class RateLimitRule:
    """Defines a single rate limit rule for an endpoint or globally."""
    limit_type: RateLimitType
    interval: RateLimitInterval
    limit: int
    interval_num: int = 1  # For multiple intervals, e.g. 5 SECOND
    is_global: bool = False
    weight_map: Dict[str, int] = field(default_factory=dict)  # For weight-based endpoints
    
    @property
    def interval_ms(self) -> int:
        """Convert interval to milliseconds."""
        multiplier = {
            RateLimitInterval.SECOND: 1000,
            RateLimitInterval.MINUTE: 60 * 1000,
            RateLimitInterval.HOUR: 60 * 60 * 1000,
            RateLimitInterval.DAY: 24 * 60 * 60 * 1000
        }
        return self.interval_num * multiplier[self.interval]


@dataclass
class RequestRecord:
    """Record of a request for rate limiting purposes."""
    timestamp: datetime
    endpoint: str
    weight: int = 1
    method: str = "GET"
    response_time_ms: Optional[int] = None
    success: bool = True
    retry_count: int = 0


@dataclass
class RateLimitInfo:
    """Current state of rate limits for an endpoint or globally."""
    current_usage: int = 0
    max_limit: int = 0
    reset_time: Optional[datetime] = None
    remaining: int = 0
    
    @property
    def is_exceeded(self) -> bool:
        """Check if the rate limit is currently exceeded."""
        return self.remaining <= 0


@dataclass
class RateLimitPolicy:
    """Policy for handling rate limit scenarios."""
    retry_after_exceeded: bool = True
    max_retries: int = 3
    backoff_factor: float = 1.5  # For exponential backoff
    jitter_ms: int = 100  # Random jitter to add to delays
    prioritize_endpoints: List[str] = field(default_factory=list)  # Higher priority endpoints
    
    # Circuit breaker settings
    circuit_breaker_enabled: bool = True
    error_threshold: int = 5  # Number of consecutive errors to trigger circuit open
    reset_timeout_ms: int = 30000  # How long to wait before testing if circuit can close
    half_open_success_threshold: int = 3  # Successful requests needed to close circuit 