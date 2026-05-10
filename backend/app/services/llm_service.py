import ast
import json
import re
from collections.abc import AsyncIterator, Iterable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.token_budget_service import TokenBudgetService


logger = get_logger(__name__)

SUPPORTED_PROVIDERS = {"gemini", "groq"}
PROVIDER_LABELS = {
    "gemini": "Gemini",
    "groq": "Groq",
}


class LlmService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.budget_service = TokenBudgetService()

    def available_providers(self) -> list[str]:
        providers = []
        if self.settings.gemini_api_key:
            providers.append("gemini")
        if self.settings.groq_api_key:
            providers.append("groq")
        return providers

    def ensure_user_message_limit(self, message: str) -> None:
        estimated_tokens = self.budget_service.estimate_tokens(message)
        if estimated_tokens > self.settings.max_user_message_tokens:
            raise ValueError(
                f"Message exceeds the limit of approximately {self.settings.max_user_message_tokens} tokens."
            )

    async def invoke_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        preferred_provider: str | None = None,
        schema: type[BaseModel] | dict[str, Any] | None = None,
        max_output_tokens: int = 900,
    ) -> tuple[dict, str]:
        selected_provider = self._normalize_provider(preferred_provider)
        providers = self._provider_order(preferred_provider)
        if not providers:
            raise ValueError("No LLM provider is configured. Add a Gemini or Groq API key.")

        last_error: Exception | None = None
        estimated_tokens = (
            self.budget_service.estimate_tokens(system_prompt)
            + self.budget_service.estimate_tokens(user_prompt)
            + max_output_tokens
        )

        for provider in providers:
            if not await self.budget_service.reserve(provider, estimated_tokens):
                logger.warning("Provider %s skipped because token budget is exhausted.", provider)
                continue

            model = self._build_model(provider, max_output_tokens=max_output_tokens)
            try:
                if schema is not None:
                    try:
                        payload = await self._invoke_structured_output(
                            model=model,
                            schema=schema,
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                        )
                        return self._coerce_schema_payload(payload, schema), provider
                    except Exception:
                        logger.warning(
                            "Structured output failed for provider %s. Falling back to JSON extraction.",
                            provider,
                            exc_info=True,
                        )

                content = await self._invoke_model_text(
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
                try:
                    return self._coerce_schema_payload(self._extract_json(content), schema), provider
                except ValueError:
                    repaired = await self._repair_json_output(
                        model=model,
                        provider=provider,
                        schema=schema,
                        raw_content=content,
                    )
                    if repaired is not None:
                        return self._coerce_schema_payload(repaired, schema), provider
                    raise
            except Exception as exc:  # pragma: no cover - network/provider path
                logger.exception("LLM JSON invocation failed for provider %s", provider)
                last_error = exc
                continue

        if last_error:
            if isinstance(last_error, ValueError) and "invalid JSON" in str(last_error):
                raise ValueError("The model returned malformed structured output.") from last_error
            raise ValueError(f"LLM request failed: {last_error}") from last_error
        if selected_provider:
            raise ValueError(self._rate_limit_message(selected_provider))
        raise ValueError("All configured LLM providers are currently rate-limited.")

    async def invoke_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        preferred_provider: str | None = None,
        max_output_tokens: int = 900,
    ) -> tuple[str, str]:
        selected_provider = self._normalize_provider(preferred_provider)
        providers = self._provider_order(preferred_provider)
        if not providers:
            raise ValueError("No LLM provider is configured. Add a Gemini or Groq API key.")

        last_error: Exception | None = None
        estimated_tokens = (
            self.budget_service.estimate_tokens(system_prompt)
            + self.budget_service.estimate_tokens(user_prompt)
            + max_output_tokens
        )

        for provider in providers:
            if not await self.budget_service.reserve(provider, estimated_tokens):
                logger.warning("Provider %s skipped because token budget is exhausted.", provider)
                continue

            model = self._build_model(provider, max_output_tokens=max_output_tokens)
            try:
                result = await model.ainvoke(
                    [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                )
                content = self._extract_text(result.content)
                return content, provider
            except Exception as exc:  # pragma: no cover - network/provider path
                logger.exception("LLM invocation failed for provider %s", provider)
                last_error = exc
                continue

        if last_error:
            raise ValueError(f"LLM request failed: {last_error}") from last_error
        if selected_provider:
            raise ValueError(self._rate_limit_message(selected_provider))
        raise ValueError("All configured LLM providers are currently rate-limited.")

    async def stream_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        preferred_provider: str | None = None,
        max_output_tokens: int = 900,
    ) -> AsyncIterator[tuple[str, str]]:
        selected_provider = self._normalize_provider(preferred_provider)
        providers = self._provider_order(preferred_provider)
        if not providers:
            raise ValueError("No LLM provider is configured. Add a Gemini or Groq API key.")

        last_error: Exception | None = None
        estimated_tokens = (
            self.budget_service.estimate_tokens(system_prompt)
            + self.budget_service.estimate_tokens(user_prompt)
            + max_output_tokens
        )

        for provider in providers:
            if not await self.budget_service.reserve(provider, estimated_tokens):
                logger.warning("Provider %s skipped because token budget is exhausted.", provider)
                continue

            model = self._build_model(provider, max_output_tokens=max_output_tokens)
            emitted_content = False
            try:
                async for chunk in model.astream(
                    [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                ):
                    content = self._extract_text(chunk.content)
                    if not content:
                        continue
                    emitted_content = True
                    yield provider, content
                return
            except Exception as exc:  # pragma: no cover - network/provider path
                logger.exception("LLM streaming failed for provider %s", provider)
                if emitted_content:
                    raise ValueError(f"LLM request failed: {exc}") from exc
                last_error = exc
                continue

        if last_error:
            raise ValueError(f"LLM request failed: {last_error}") from last_error
        if selected_provider:
            raise ValueError(self._rate_limit_message(selected_provider))
        raise ValueError("All configured LLM providers are currently rate-limited.")

    def _provider_order(self, preferred_provider: str | None) -> list[str]:
        available = self.available_providers()
        preferred = self._normalize_provider(preferred_provider)
        if not preferred:
            return available
        if preferred not in SUPPORTED_PROVIDERS:
            supported = ", ".join(sorted(self._provider_label(provider) for provider in SUPPORTED_PROVIDERS))
            raise ValueError(f"Unsupported LLM provider '{preferred_provider}'. Choose one of: {supported}.")
        if preferred not in available:
            key_name = "GEMINI_API_KEY" if preferred == "gemini" else "GROQ_API_KEY"
            raise ValueError(
                f"{self._provider_label(preferred)} is selected, but {key_name} is not configured on the backend."
            )
        return [preferred]

    def _normalize_provider(self, provider: str | None) -> str | None:
        normalized = (provider or "").strip().lower()
        return normalized or None

    def _provider_label(self, provider: str) -> str:
        return PROVIDER_LABELS.get(provider, provider)

    def _rate_limit_message(self, provider: str) -> str:
        return f"Selected LLM provider {self._provider_label(provider)} is currently rate-limited."
        return available

    def _build_model(self, provider: str, max_output_tokens: int):
        timeout = self.settings.llm_timeout_seconds
        if provider == "gemini":
            return ChatGoogleGenerativeAI(
                model=self.settings.gemini_model,
                google_api_key=self.settings.gemini_api_key,
                temperature=0.1,
                timeout=timeout,
                max_retries=1,
                max_output_tokens=max_output_tokens,
            )
        return ChatGroq(
            model_name=self.settings.groq_model,
            groq_api_key=self.settings.groq_api_key,
            temperature=0.1,
            timeout=timeout,
            max_tokens=max_output_tokens,
        )

    def _extract_text(self, content: str | list | dict) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            return json.dumps(content)
        if isinstance(content, Iterable):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content)

    async def _invoke_model_text(
        self,
        *,
        model,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        result = await model.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        return self._extract_text(result.content)

    async def _invoke_structured_output(
        self,
        *,
        model,
        schema: type[BaseModel] | dict[str, Any],
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        structured_model = model.with_structured_output(schema, method="json_mode")
        payload = await structured_model.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )
        if isinstance(payload, BaseModel):
            return payload.model_dump()
        if isinstance(payload, dict):
            return payload
        if hasattr(payload, "model_dump"):
            return payload.model_dump()
        raise ValueError("Structured output did not return a JSON object.")

    def _coerce_schema_payload(
        self,
        payload: dict,
        schema: type[BaseModel] | dict[str, Any] | None,
    ) -> dict:
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            return schema.model_validate(payload).model_dump()
        return payload

    def _extract_json(self, text: str) -> dict:
        decoder = json.JSONDecoder()

        for candidate in self._json_candidates(text):
            try:
                payload = json.loads(candidate)
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                pass

            for index, character in enumerate(candidate):
                if character not in "{[":
                    continue
                try:
                    payload, _ = decoder.raw_decode(candidate[index:])
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    return payload

            python_like_payload = self._extract_python_like_object(candidate)
            if python_like_payload is not None:
                return python_like_payload

        raise ValueError("LLM returned invalid JSON.")

    async def _repair_json_output(
        self,
        *,
        model,
        provider: str,
        schema: type[BaseModel] | dict[str, Any] | None,
        raw_content: str,
    ) -> dict | None:
        python_like_payload = self._extract_python_like_object(raw_content)
        if python_like_payload is not None:
            return python_like_payload

        repair_system_prompt = (
            "You repair malformed model outputs into a single valid JSON object. "
            "Return JSON only with double-quoted keys and strings. Do not add markdown fences."
        )
        repair_user_prompt = (
            f"Provider: {provider}\n\n"
            f"Original output:\n{raw_content.strip()}\n\n"
            "Rewrite it as one valid JSON object."
        )

        if schema is not None:
            try:
                return await self._invoke_structured_output(
                    model=model,
                    schema=schema,
                    system_prompt=repair_system_prompt,
                    user_prompt=repair_user_prompt,
                )
            except Exception:
                logger.warning("Structured JSON repair failed for provider %s.", provider, exc_info=True)

        try:
            repaired_text = await self._invoke_model_text(
                model=model,
                system_prompt=repair_system_prompt,
                user_prompt=repair_user_prompt,
            )
            return self._extract_json(repaired_text)
        except Exception:
            logger.warning("Plain-text JSON repair failed for provider %s.", provider, exc_info=True)
            return None

    def _extract_python_like_object(self, text: str) -> dict | None:
        for candidate in self._json_candidates(text):
            normalized = re.sub(r"\bnull\b", "None", candidate)
            normalized = re.sub(r"\btrue\b", "True", normalized, flags=re.IGNORECASE)
            normalized = re.sub(r"\bfalse\b", "False", normalized, flags=re.IGNORECASE)
            try:
                payload = ast.literal_eval(normalized)
            except (SyntaxError, ValueError):
                continue
            if isinstance(payload, dict):
                return payload
        return None

    def _json_candidates(self, text: str) -> list[str]:
        candidate = text.strip()
        candidates = [candidate]

        if "```" in candidate:
            fenced_blocks = candidate.split("```")
            for block in fenced_blocks:
                stripped = block.strip()
                if not stripped:
                    continue
                if stripped.lower().startswith("json"):
                    stripped = stripped[4:].strip()
                candidates.append(stripped)

        normalized = candidate.removeprefix("json").strip()
        if normalized != candidate:
            candidates.append(normalized)

        return [item for item in candidates if item]
