"""LLM client supporting Ollama and Anthropic backends.

Configuration via environment variables:
    LLM_PROVIDER: "ollama" (default) or "anthropic"
    LLM_BASE_URL: Base URL (default: http://ollama:11434)
    LLM_MODEL: Model name (default: gemma3:4b)
    LLM_API_KEY: API key (required for anthropic)
    LLM_TIMEOUT: Request timeout in seconds (default: 30)
"""

import json
import os
import re

import httpx
import structlog

logger = structlog.get_logger()

_JSON_BLOCK = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)
_JSON_OBJECT = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}")


class LLMClient:
    """Async LLM client with Ollama and Anthropic support."""

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "ollama")
        self.base_url = os.getenv("LLM_BASE_URL", "http://ollama:11434")
        self.model = os.getenv("LLM_MODEL", "gemma3:4b")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.timeout = int(os.getenv("LLM_TIMEOUT", "30"))
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def complete(self, system_prompt: str, user_prompt: str) -> str | None:
        """Send a completion request and return the text response.

        Returns None on any error (timeout, network, parse error).
        """
        try:
            if self.provider == "anthropic":
                return await self._complete_anthropic(system_prompt, user_prompt)
            return await self._complete_ollama(system_prompt, user_prompt)
        except Exception as exc:
            logger.warning(
                "llm_call_failed",
                provider=self.provider,
                error_type=type(exc).__name__,
                error=str(exc) or repr(exc),
            )
            return None

    async def _complete_ollama(self, system_prompt: str, user_prompt: str) -> str | None:
        client = await self._get_client()
        resp = await client.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.1},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"]

    async def _complete_anthropic(self, system_prompt: str, user_prompt: str) -> str | None:
        client = await self._get_client()
        resp = await client.post(
            f"{self.base_url}/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]

    async def health_check(self) -> bool:
        """Check if the LLM backend is reachable."""
        try:
            client = await self._get_client()
            if self.provider == "anthropic":
                # Just check if the API responds (any status)
                resp = await client.get(
                    f"{self.base_url}/v1/messages",
                    headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                )
                return resp.status_code in (200, 401, 405)
            else:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except (httpx.HTTPError, httpx.TimeoutException):
            return False

    @staticmethod
    def parse_json(text: str) -> dict | None:
        """Extract JSON object from LLM response text.

        Handles:
        - ```json ... ``` code blocks
        - Raw JSON objects
        - JSON mixed with explanation text
        """
        if not text:
            return None

        # Try code block first
        match = _JSON_BLOCK.search(text)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try raw JSON object
        match = _JSON_OBJECT.search(text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # Try the whole text
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            return None

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Module-level singleton
llm_client = LLMClient()
