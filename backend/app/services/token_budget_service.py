import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from time import time

from app.core.config import get_settings


@dataclass(slots=True)
class BudgetSnapshot:
    requests_per_minute: int
    tokens_per_minute: int


class TokenBudgetService:
    def __init__(self) -> None:
        settings = get_settings()
        self.budgets = {
            "gemini": BudgetSnapshot(
                requests_per_minute=settings.gemini_requests_per_minute,
                tokens_per_minute=settings.gemini_tokens_per_minute,
            ),
            "groq": BudgetSnapshot(
                requests_per_minute=settings.groq_requests_per_minute,
                tokens_per_minute=settings.groq_tokens_per_minute,
            ),
            "deepseek": BudgetSnapshot(
                requests_per_minute=settings.deepseek_requests_per_minute,
                tokens_per_minute=settings.deepseek_tokens_per_minute,
            ),
        }
        self.request_windows: dict[str, deque[float]] = defaultdict(deque)
        self.token_windows: dict[str, deque[tuple[float, int]]] = defaultdict(deque)
        self.lock = asyncio.Lock()

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return max(1, round(len(text) / 4))

    async def reserve(self, provider: str, estimated_tokens: int) -> bool:
        async with self.lock:
            now = time()
            self._cleanup(provider, now)
            budget = self.budgets[provider]
            current_requests = len(self.request_windows[provider])
            current_tokens = sum(token_count for _, token_count in self.token_windows[provider])
            if current_requests + 1 > budget.requests_per_minute:
                return False
            if current_tokens + estimated_tokens > budget.tokens_per_minute:
                return False
            self.request_windows[provider].append(now)
            self.token_windows[provider].append((now, estimated_tokens))
            return True

    async def can_accept(self, provider: str, estimated_tokens: int) -> bool:
        async with self.lock:
            now = time()
            self._cleanup(provider, now)
            budget = self.budgets[provider]
            current_requests = len(self.request_windows[provider])
            current_tokens = sum(token_count for _, token_count in self.token_windows[provider])
            return current_requests + 1 <= budget.requests_per_minute and current_tokens + estimated_tokens <= budget.tokens_per_minute

    def _cleanup(self, provider: str, now: float) -> None:
        request_window = self.request_windows[provider]
        while request_window and now - request_window[0] >= 60:
            request_window.popleft()

        token_window = self.token_windows[provider]
        while token_window and now - token_window[0][0] >= 60:
            token_window.popleft()
