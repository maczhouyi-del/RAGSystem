"""TEST ONLY / MOCK. Real RQ/PG/PDF; scripted unpaid chat/embedding/reranking.

Not included in deployment artifacts. No runtime fallback to mocked inference.
"""

from ragagent import worker
from ragagent.domain.research import AnswerDraft
from ragagent.graphs.state import AnalysisResult
from tests.integration.test_conversation_worker import ScientificScript
from tests.integration.test_retrieval import Embedder, FixtureReranker


class InstallationScript(ScientificScript):
    async def complete(self, instruction, payload, schema):
        response = await super().complete(instruction, payload, schema)
        if schema in {AnswerDraft, AnalysisResult}:
            for claim in response.claims:
                claim.text = "Original source text on page one."
        return response


worker.make_agents = lambda _settings: {
    role: InstallationScript() for role in ("supervisor", "retriever", "analyst", "reviewer")
}
worker.make_embedder = lambda _settings: Embedder()
worker.make_reranker = lambda _settings: FixtureReranker()
worker.main()
