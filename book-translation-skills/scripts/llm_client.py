"""Unified LLM client supporting multiple providers (OpenAI, Kimi, Gemini, etc.)

Usage:
    from llm_client import LLMClient, create_client_from_secrets
    
    client = create_client_from_secrets(provider="kimi")  # or "openai", "gemini"
    response = client.chat_completion(
        messages=[{"role": "user", "content": "Hello"}],
        model="kimi-moonshot-v1-8k",
        temperature=0.2
    )
"""

from __future__ import annotations

import json
import pathlib
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class LLMResponse:
    """Standardized LLM response."""
    content: str
    model: str
    usage: dict[str, int] | None = None
    raw_response: dict | None = None


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""
    
    def __init__(self, api_key: str, base_url: str | None = None, **kwargs):
        self.api_key = api_key
        self.base_url = base_url
        self.extra_config = kwargs
    
    @abstractmethod
    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        **kwargs
    ) -> LLMResponse:
        """Send a chat completion request."""
        pass
    
    def call_with_retry(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        max_retries: int = 3,
        **kwargs
    ) -> LLMResponse:
        """Call with retry logic."""
        last_error = None
        for attempt in range(max_retries):
            try:
                return self.chat_completion(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs
                )
            except Exception as e:
                last_error = e
                wait_time = 5 * (attempt + 1)
                print(f"  Retry {attempt + 1}/{max_retries} after {wait_time}s: {e}", file=sys.stderr)
                time.sleep(wait_time)
        raise RuntimeError(f"Failed after {max_retries} retries: {last_error}")


class OpenAICompatibleClient(BaseLLMClient):
    """Client for OpenAI-compatible APIs (OpenAI, Kimi, Azure, etc.)."""
    
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", **kwargs):
        super().__init__(api_key, base_url, **kwargs)
    
    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        thinking_level: str | None = None,
        **kwargs
    ) -> LLMResponse:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Kimi K2.5 only supports temperature=1
        if "kimi" in model.lower() and "k2.5" in model.lower():
            temperature = 1.0
        
        payload: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "messages": messages,
        }
        
        if max_tokens:
            payload["max_completion_tokens"] = max_tokens
        
        # Add thinking_level for supported models (e.g., Gemini via OpenRouter)
        if thinking_level:
            payload["thinking_level"] = thinking_level
        
        # Add any extra parameters
        payload.update(kwargs)
        
        response = requests.post(url, headers=headers, json=payload, timeout=600)
        
        if response.status_code != 200:
            # Try without thinking_level if not supported
            if thinking_level and "Unknown parameter" in response.text:
                payload.pop("thinking_level", None)
                response = requests.post(url, headers=headers, json=payload, timeout=600)
                if response.status_code != 200:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
            else:
                raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
        
        data = response.json()
        choice = data["choices"][0]
        content = choice["message"]["content"]
        
        return LLMResponse(
            content=content,
            model=data.get("model", model),
            usage=data.get("usage"),
            raw_response=data
        )


class GeminiClient(BaseLLMClient):
    """Client for Google Gemini API."""
    
    def __init__(self, api_key: str, **kwargs):
        # Gemini uses a different URL pattern
        super().__init__(api_key, None, **kwargs)
    
    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        **kwargs
    ) -> LLMResponse:
        # Convert OpenAI-style messages to Gemini format
        # Gemini uses: contents=[{role: "user"/"model", parts: [{text: "..."}]}]
        
        gemini_model = model
        if not gemini_model.startswith("models/") and "/" not in gemini_model:
            gemini_model = f"models/{gemini_model}"
        
        url = f"https://generativelanguage.googleapis.com/v1beta/{gemini_model}:generateContent"
        
        # Convert messages
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })
        
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
            }
        }
        
        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens
        
        params = {"key": self.api_key}
        
        response = requests.post(url, params=params, json=payload, timeout=600)
        
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
        
        data = response.json()
        
        # Extract content from Gemini response format
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("No candidates in Gemini response")
        
        content_parts = candidates[0].get("content", {}).get("parts", [])
        if not content_parts:
            raise RuntimeError("No content parts in Gemini response")
        
        text = content_parts[0].get("text", "")
        
        # Map usage if available
        usage = None
        if "usageMetadata" in data:
            meta = data["usageMetadata"]
            usage = {
                "prompt_tokens": meta.get("promptTokenCount", 0),
                "completion_tokens": meta.get("candidatesTokenCount", 0),
                "total_tokens": meta.get("totalTokenCount", 0)
            }
        
        return LLMResponse(
            content=text,
            model=model,
            usage=usage,
            raw_response=data
        )


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude API."""
    
    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com", **kwargs):
        super().__init__(api_key, base_url, **kwargs)
    
    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        **kwargs
    ) -> LLMResponse:
        url = f"{self.base_url}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        # Convert messages: system message goes to separate field
        system_message = None
        anthropic_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        payload: dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096
        }
        
        if system_message:
            payload["system"] = system_message
        
        response = requests.post(url, headers=headers, json=payload, timeout=600)
        
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
        
        data = response.json()
        
        content = ""
        if data.get("content"):
            content = data["content"][0].get("text", "")
        
        usage = None
        if "usage" in data:
            u = data["usage"]
            usage = {
                "prompt_tokens": u.get("input_tokens", 0),
                "completion_tokens": u.get("output_tokens", 0),
                "total_tokens": u.get("input_tokens", 0) + u.get("output_tokens", 0)
            }
        
        return LLMResponse(
            content=content,
            model=model,
            usage=usage,
            raw_response=data
        )


class LLMClient:
    """Unified LLM client that routes to appropriate provider."""
    
    PROVIDERS = {
        "openai": OpenAICompatibleClient,
        "kimi": OpenAICompatibleClient,  # Kimi uses OpenAI-compatible API
        "gemini": GeminiClient,
        "anthropic": AnthropicClient,
        "claude": AnthropicClient,
    }
    
    def __init__(self, provider: str, api_key: str, base_url: str | None = None, **kwargs):
        self.provider = provider.lower()
        
        if self.provider not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}. Available: {list(self.PROVIDERS.keys())}")
        
        client_class = self.PROVIDERS[self.provider]
        
        # Default base URLs for known providers
        if not base_url:
            if self.provider == "openai":
                base_url = "https://api.openai.com/v1"
            elif self.provider == "kimi":
                base_url = "https://api.moonshot.cn/v1"
            elif self.provider in ("anthropic", "claude"):
                base_url = "https://api.anthropic.com"
        
        self.client = client_class(api_key, base_url, **kwargs)
    
    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        **kwargs
    ) -> LLMResponse:
        """Send a chat completion request."""
        if not model:
            raise ValueError("Model name is required")
        
        return self.client.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
    
    def call_with_retry(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        max_retries: int = 3,
        **kwargs
    ) -> LLMResponse:
        """Call with retry logic."""
        return self.client.call_with_retry(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=max_retries,
            **kwargs
        )


def load_secrets() -> dict:
    """Load secrets from workspace/local.secrets.json or secrets.json."""
    candidates = ["local.secrets.json", "secrets.json"]
    
    # Try workspace directory first
    for candidate in candidates:
        path = pathlib.Path("workspace") / candidate
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    
    # Try current directory
    for candidate in candidates:
        path = pathlib.Path(candidate)
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    
    raise FileNotFoundError("No secrets.json or local.secrets.json found")


def create_client_from_secrets(
    provider: str | None = None,
    task: str = "translate"
) -> tuple[LLMClient, str]:
    """Create LLM client from secrets configuration.
    
    Args:
        provider: Provider name (openai, kimi, gemini, anthropic). 
                 If None, uses default_provider from secrets.
        task: Task type (extract, translate, supplement) to select appropriate model.
    
    Returns:
        Tuple of (client, model_name)
    """
    secrets = load_secrets()
    
    # Determine provider
    if not provider:
        provider = secrets.get("default_provider", "openai")
    
    provider = provider.lower()
    
    # Get provider configuration
    if provider not in secrets:
        raise ValueError(f"Provider '{provider}' not found in secrets. Available: {list(secrets.get('providers', secrets).keys())}")
    
    config = secrets[provider]
    
    api_key = config.get("api_key")
    if not api_key:
        raise ValueError(f"api_key not configured for provider: {provider}")
    
    base_url = config.get("base_url")
    
    # Get model for task
    models = config.get("models", {})
    if task in models:
        model = models[task]
    elif "model" in config:
        model = config["model"]
    else:
        raise ValueError(f"No model configured for task '{task}' in provider '{provider}'")
    
    client = LLMClient(provider, api_key, base_url)
    
    return client, model


def get_thinking_level() -> str | None:
    """Get thinking level from secrets if configured."""
    try:
        secrets = load_secrets()
        provider = secrets.get("default_provider", "openai")
        config = secrets.get(provider, {})
        return config.get("thinking_level") or config.get("translate_thinking_level")
    except Exception:
        return None
