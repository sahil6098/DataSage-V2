import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from time import time

from app.core.config import get_settings


@dataclass(slots=True)
class BudgetSnapshot:
    requests_per_minute: int
    tokens_per_minute: int
    requests_per_day: int = 0  # 0 means no daily limit


@dataclass(slots=True)
class DailyCounter:
    day: int = 0  # ordinal day number
    count: int = 0


class TokenBudgetService:
    def __init__(self) -> None:
        settings = get_settings()
        self.budgets = {
            "groq": BudgetSnapshot(
                requests_per_minute=settings.groq_requests_per_minute,
                tokens_per_minute=settings.groq_tokens_per_minute,
                requests_per_day=settings.groq_requests_per_day,
            ),
            "deepseek": BudgetSnapshot(
                requests_per_minute=settings.deepseek_requests_per_minute,
                tokens_per_minute=settings.deepseek_tokens_per_minute,
                requests_per_day=settings.deepseek_requests_per_day,
            ),
        }
        self.request_windows: dict[str, deque[float]] = defaultdict(deque)
        self.token_windows: dict[str, deque[tuple[float, int]]] = defaultdict(deque)
        self.daily_counters: dict[str, DailyCounter] = defaultdict(DailyCounter)
        self.lock = asyncio.Lock()

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return max(1, round(len(text) / 4))

    async def reserve(self, provider: str, estimated_tokens: int) -> bool:
        async with self.lock:
            now = time()
            budget_key = self._budget_key(provider)
            self._cleanup(provider, now)
            budget = self.budgets[budget_key]
            current_requests = len(self.request_windows[provider])
            current_tokens = sum(token_count for _, token_count in self.token_windows[provider])
            if current_requests + 1 > budget.requests_per_minute:
                return False
            if current_tokens + estimated_tokens > budget.tokens_per_minute:
                return False
            # Check daily limit if configured
            if budget.requests_per_day > 0:
                daily = self._get_daily(provider, now)
                if daily.count + 1 > budget.requests_per_day:
                    return False
                daily.count += 1
            self.request_windows[provider].append(now)
            self.token_windows[provider].append((now, estimated_tokens))
            return True

    async def can_accept(self, provider: str, estimated_tokens: int) -> bool:
        async with self.lock:
            now = time()
            budget_key = self._budget_key(provider)
            self._cleanup(provider, now)
            budget = self.budgets[budget_key]
            current_requests = len(self.request_windows[provider])
            current_tokens = sum(token_count for _, token_count in self.token_windows[provider])
            if current_requests + 1 > budget.requests_per_minute:
                return False
            if current_tokens + estimated_tokens > budget.tokens_per_minute:
                return False
            if budget.requests_per_day > 0:
                daily = self._get_daily(provider, now)
                if daily.count + 1 > budget.requests_per_day:
                    return False
            return True

    def _budget_key(self, provider: str) -> str:
        if provider.startswith("groq:"):
            return "groq"
        return provider

    def _get_daily(self, provider: str, now: float) -> DailyCounter:
        """Get or reset the daily counter for a provider."""
        import datetime
        today = datetime.date.today().toordinal()
        counter = self.daily_counters[provider]
        if counter.day != today:
            counter.day = today
            counter.count = 0
        return counter

    def _cleanup(self, provider: str, now: float) -> None:
        request_window = self.request_windows[provider]
        while request_window and now - request_window[0] >= 60:
            request_window.popleft()

        token_window = self.token_windows[provider]
        while token_window and now - token_window[0][0] >= 60:
            token_window.popleft()
