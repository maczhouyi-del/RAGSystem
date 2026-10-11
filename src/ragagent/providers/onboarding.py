"""Explicit user-requested model directory check; never generates tokens.

A directory response proves connectivity/credential acceptance for that endpoint,
not inference, all advertised capabilities or scientific answer quality.
"""

from typing import Any

import httpx

from ragagent.errors import ConfigurationError, ProviderError
from ragagent.providers.config import AgentModel
from ragagent.providers.environment import runtime_value

MAX_DIRECTORY_BYTES = 1024 * 1024


async def check_connection(
    model: AgentModel, *, client: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    base = model.api_base or {
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "ollama_chat": "http://localhost:11434",
    }.get(model.provider)
    if not base:
        raise ConfigurationError("invalid_provider_config")
    headers = {}
    if model.key_environment:
        key = runtime_value(model.key_environment)
        if not key:
            raise ConfigurationError("provider_key_missing")
        if model.provider == "anthropic":
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        else:
            headers = {"Authorization": "Bearer " + key}
    path = "/api/tags" if model.provider == "ollama_chat" else "/models"
    base = base.rstrip("/")
    if model.provider == "anthropic" and not base.endswith("/v1"):
        base += "/v1"
    owned = client is None
    client = client or httpx.AsyncClient(timeout=10, follow_redirects=False)
    try:
        async with client.stream("GET", base + path, headers=headers, follow_redirects=False) as r:
            if r.status_code in (401, 403):
                raise ProviderError("provider_credential_rejected")
            if r.status_code == 429:
                raise ProviderError("provider_rate_limited")
            if r.status_code in (404, 405):
                raise ProviderError("provider_catalog_unavailable")
            if r.status_code != 200:
                raise ProviderError("provider_connection_failed")
            body = bytearray()
            async for chunk in r.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_DIRECTORY_BYTES:
                    raise ProviderError("provider_catalog_invalid")
            import json

            data = json.loads(body)
        values = data.get("models" if model.provider == "ollama_chat" else "data")
        if not isinstance(values, list):
            raise ProviderError("provider_catalog_invalid")
        names = {
            item.get("name" if model.provider == "ollama_chat" else "id")
            for item in values
            if isinstance(item, dict)
            and isinstance(item.get("name" if model.provider == "ollama_chat" else "id"), str)
        }
        return {
            "ok": True,
            "model": model.model,
            "connectivity": "success",
            "model_advertised": model.model in names,
            "inference": "not_tested",
        }
    except (ConfigurationError, ProviderError):
        raise
    except (httpx.HTTPError, OSError):
        raise ProviderError("provider_network_failed") from None
    except Exception:
        raise ProviderError("provider_catalog_invalid") from None
    finally:
        if owned:
            await client.aclose()
