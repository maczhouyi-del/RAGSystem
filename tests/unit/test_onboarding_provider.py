"""MOCK network responses only; no real keys, inference, downloads or science."""

import json

import httpx
import pytest

from ragagent.errors import ConfigurationError, ProviderError
from ragagent.providers.config import AgentModel
from ragagent.providers.onboarding import MAX_DIRECTORY_BYTES, check_connection

SECRET = "UX-MOCK-KEY-NOT-A-REAL-CREDENTIAL"


@pytest.mark.parametrize(
    "provider", ["openai", "deepseek", "anthropic", "openai_compatible", "ollama_chat"]
)
async def test_directory_only_proves_connection_never_inference(provider, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    monkeypatch.setenv("DEEPSEEK_API_KEY", SECRET)
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    calls = []

    def respond(request):
        calls.append((request.method, request.url.path))
        if provider == "anthropic":
            assert request.headers["x-api-key"] == SECRET
        elif provider != "ollama_chat":
            assert request.headers["authorization"] == "Bearer " + SECRET
        return httpx.Response(
            200,
            json={
                "models" if provider == "ollama_chat" else "data": [
                    {"name" if provider == "ollama_chat" else "id": "mock-model"}
                ]
            },
        )

    model = AgentModel(
        provider=provider,
        model="mock-model",
        api_base="https://provider.invalid/v1",
        api_key_env="OPENAI_API_KEY" if provider == "openai_compatible" else None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await check_connection(model, client=client)
    assert result["connectivity"] == "success" and result["inference"] == "not_tested"
    assert result["model_advertised"] is True
    assert len(calls) == 1 and calls[0][0] == "GET"
    assert SECRET not in json.dumps(result)


async def test_missing_key_never_sends_request(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")

    def unexpected(request):
        raise AssertionError("Must not access network")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(ConfigurationError, match="provider_key_missing"):
            await check_connection(AgentModel(provider="openai", model="mock"), client=client)


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "provider_credential_rejected"),
        (403, "provider_credential_rejected"),
        (429, "provider_rate_limited"),
        (404, "provider_catalog_unavailable"),
        (500, "provider_connection_failed"),
    ],
)
async def test_provider_errors_never_export_remote_body_or_key(status, code, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(status, text=SECRET))
    ) as client:
        with pytest.raises(ProviderError, match=code) as error:
            await check_connection(AgentModel(provider="openai", model="mock"), client=client)
    assert SECRET not in str(error.value)


async def test_redirect_is_not_followed_or_given_a_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    calls = []

    def response(r):
        calls.append(r.url.host)
        return httpx.Response(302, headers={"location": "https://attacker.invalid/key"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(response), follow_redirects=True
    ) as client:
        with pytest.raises(ProviderError, match="provider_connection_failed"):
            await check_connection(AgentModel(provider="openai", model="mock"), client=client)
    assert calls == ["api.openai.com"]


@pytest.mark.parametrize("body", [b"not-json", b"{}", b"[]", b"x" * (MAX_DIRECTORY_BYTES + 1)])
async def test_malformed_or_oversized_catalog_is_not_success(body, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body))
    ) as client:
        with pytest.raises(ProviderError, match="provider_catalog_invalid"):
            await check_connection(AgentModel(provider="openai", model="mock"), client=client)


async def test_model_absent_does_not_claim_inference_failure_or_success(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"data": [{"id": "other-model"}]})
        )
    ) as client:
        result = await check_connection(AgentModel(provider="openai", model="mock"), client=client)
    assert result["connectivity"] == "success" and result["model_advertised"] is False
    assert result["inference"] == "not_tested"


async def test_network_exception_is_sanitized(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)

    def failure(r):
        raise httpx.ConnectError(SECRET)

    async with httpx.AsyncClient(transport=httpx.MockTransport(failure)) as client:
        with pytest.raises(ProviderError, match="provider_network_failed") as error:
            await check_connection(AgentModel(provider="openai", model="mock"), client=client)
    assert SECRET not in str(error.value)
