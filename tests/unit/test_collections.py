"""Offline organization validation and immutable requested graph scope."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from ragagent.conversations.context import merge_context_filters
from ragagent.domain.collections import CollectionCreate, name_key
from ragagent.domain.conversation import ConversationFilters
from ragagent.domain.conversation_context import StructuredMemory
from ragagent.domain.research import MetadataFilter, QueryPlan
from ragagent.graphs.rag import build_rag
from ragagent.graphs.research import build_research
from ragagent.graphs.state import MultiAgentState, RAGState
from ragagent.providers.chat import MockProvider
from tests.unit.test_graphs import Search, plan


@pytest.mark.parametrize("name", ["", "  ", "a\nb", "x" * 81, "ghp_" + "a" * 30])
def test_invalid_or_credential_collection_names_are_rejected(name: str) -> None:
    with pytest.raises(ValidationError):
        CollectionCreate(kind="group", name=name)


def test_unicode_labels_and_uuid_filters_are_canonical_and_bounded() -> None:
    label = CollectionCreate(kind="tag", name="  科研 Ａ  ")
    assert label.name == "科研 Ａ" and name_key(label.name) == "科研 a"
    identifier = str(uuid4())
    assert ConversationFilters(group_ids=[identifier.upper(), identifier]).group_ids == [identifier]
    for kwargs in [{"tag_ids": ["not-an-id"]}, {"group_ids": [identifier] * 51}]:
        with pytest.raises(ValidationError):
            MetadataFilter(**kwargs)


@pytest.mark.parametrize("mode", ["rag", "research"])
async def test_planners_cannot_relax_group_or_tag_scope(mode: str) -> None:
    requested = MetadataFilter(group_ids=[str(uuid4())], tag_ids=[str(uuid4())], authors=["Alice"])
    proposed = MetadataFilter(group_ids=[str(uuid4())], tag_ids=[str(uuid4())])
    search = Search(empty_rounds=99)
    if mode == "rag":
        graph = build_rag(
            search,
            MockProvider([QueryPlan(queries=["q"], filters=proposed)]),
            MockProvider([]),
            MockProvider([]),
            MockProvider([]),
            max_retries=0,
        )
        await graph.ainvoke(RAGState(query="q", filters=requested))
    else:
        proposal = plan()
        proposal.subtasks[0].filters = proposed
        graph = build_research(
            search,
            MockProvider([proposal]),
            MockProvider([]),
            MockProvider([]),
            MockProvider([]),
            max_retrievals=1,
        )
        await graph.ainvoke(MultiAgentState(research_question="q", filters=requested))
    assert search.calls
    assert all(
        call.filters.group_ids == requested.group_ids
        and call.filters.tag_ids == requested.tag_ids
        and call.filters.authors == ["Alice"]
        for call in search.calls
    )


def test_explicit_memory_and_current_organization_scope_intersect() -> None:
    common, other = str(uuid4()), str(uuid4())
    memory = StructuredMemory(
        id="m",
        kind="constraint",
        content="project scope",
        filters=MetadataFilter(group_ids=[common], tag_ids=[common]),
    )
    result = merge_context_filters(
        MetadataFilter(group_ids=[other, common], tag_ids=[common]), [memory]
    )
    assert result.group_ids == [common] and result.tag_ids == [common]
