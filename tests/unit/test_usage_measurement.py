from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from ragagent.errors import ProviderError
from ragagent.providers.chat import LiteLLMProvider, Usage, usage_record
from ragagent.providers.config import AgentModel
from ragagent.providers.embedding import LiteLLMEmbedder, LocalEmbedder
from ragagent.worker import graph_events


class Answer(BaseModel):
    answer: str


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"prompt_tokens": 0},
        {"prompt_tokens": 7, "completion_tokens": 3},
        {"prompt_tokens": True, "completion_tokens": -1},
    ],
)
async def test_chat_sdk_usage_distinguishes_missing_zero_and_malformed(monkeypatch, usage):
    import litellm

    async def respond(**kwargs):
        return SimpleNamespace(
            usage=usage,
            model="DEMO-response",
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"answer":"DEMO"}'))],
        )

    monkeypatch.setattr(litellm, "acompletion", respond)
    monkeypatch.setattr(litellm, "completion_cost", lambda **kwargs: 0.02)
    provider = LiteLLMProvider(AgentModel(provider="ollama_chat", model="DEMO"))
    assert (await provider.complete("fixture", {}, Answer)).answer == "DEMO"
    record = usage_record(provider.usage)
    assert (
        record["cost_basis"] == "sdk_estimate" and record["configured_model"] == "ollama_chat/DEMO"
    )
    assert record["prompt_token_reports"] == int(
        usage is not None and "prompt_tokens" in usage and type(usage["prompt_tokens"]) is int
    )
    assert record["completion_token_reports"] == int(
        usage == {"prompt_tokens": 7, "completion_tokens": 3}
    )


async def test_failed_chat_keeps_unknown_tokens_and_cost(monkeypatch):
    import litellm

    async def fail(**kwargs):
        raise ValueError("PRIVATE provider error")

    monkeypatch.setattr(litellm, "acompletion", fail)
    provider = LiteLLMProvider(AgentModel(provider="ollama_chat", model="DEMO"))
    with pytest.raises(ProviderError, match="provider_request_or_schema_failed"):
        await provider.complete("fixture", {}, Answer)
    record = usage_record(provider.usage)
    assert record["calls"] == record["unknown_cost_calls"] == 1
    assert record["prompt_token_reports"] == record["completion_token_reports"] == 0


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": 0}, {"prompt_tokens": False}])
async def test_embedding_sdk_missing_usage_is_not_reported_zero(monkeypatch, usage):
    import litellm

    async def respond(**kwargs):
        return SimpleNamespace(
            usage=usage, model="DEMO", data=[{"index": 0, "embedding": [1.0, 0.0]}]
        )

    monkeypatch.setattr(litellm, "aembedding", respond)
    monkeypatch.setattr(litellm, "completion_cost", lambda **kwargs: 0)
    provider = LiteLLMEmbedder("openai/DEMO", 2, "https://api.example/v1")
    await provider.embed(["DEMO"])
    assert provider.usage.prompt_token_reports == int(
        usage == {"prompt_tokens": 0} and type(usage.get("prompt_tokens")) is int
    )
    assert provider.usage.completion_token_reports == 1


async def test_local_embedding_records_dispatch_without_inventing_tokens(monkeypatch):
    provider = LocalEmbedder("DEMO", 2)
    monkeypatch.setattr(provider, "_encode", lambda texts: [[1.0, 0.0]])
    snapshots = []
    provider.usage.on_update = lambda usage: snapshots.append(usage_record(usage))
    await provider.embed(["DEMO"])
    assert snapshots[0]["calls"] == snapshots[0]["in_flight_calls"] == 1
    assert snapshots[-1]["cost_basis"] == "local_service" and snapshots[-1]["known_cost"] == 0
    assert provider.usage.prompt_token_reports == 0


async def test_node_interval_is_measured_outside_scientific_state(monkeypatch):
    from ragagent import worker

    class Graph:
        async def astream(self, *args, **kwargs):
            yield {"answer": {"answer": "DEMO"}}

    ticks = iter([1.0, 3.5, 4.0])
    monkeypatch.setattr(worker, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    observed = []
    monkeypatch.setattr(
        worker, "event", lambda session, run, node, payload: observed.append(payload)
    )
    state = await graph_events(Graph(), Answer(answer=""), None, None, 3)
    assert state.model_dump() == {"answer": "DEMO"}
    assert observed[0]["execution_timing"] == {"elapsed_seconds": 2.5, "basis": "node_interval"}


@pytest.mark.parametrize("value", [None, True, -1, "7", float("nan")])
def test_token_recorder_ignores_unreported_values(value):
    usage = Usage()
    usage.record_tokens(value, value)
    assert usage.prompt_token_reports == usage.completion_token_reports == 0


async def test_local_reranking_records_model_without_download_or_invented_tokens(monkeypatch):
    from ragagent.retrieval.reranker import CrossEncoderReranker

    provider = CrossEncoderReranker("DEMO-reranker")
    monkeypatch.setattr(provider, "_rank", lambda query, candidates, top_k: candidates)
    await provider.rerank("DEMO", [], 1)
    assert provider.usage.calls == 0
    await provider.rerank("DEMO", ["MOCK candidate"], 1)
    assert provider.usage.configured_model == "DEMO-reranker"
    assert provider.usage.calls == 1 and provider.usage.cost == 0
    assert provider.usage.prompt_token_reports == 0
