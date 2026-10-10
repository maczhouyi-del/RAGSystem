"""TEST ONLY / MOCK. Real RQ/PG/PDF; scripted unpaid chat/embedding/reranking.

Not included in deployment artifacts. No runtime fallback to mocked inference.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ragagent import worker  # noqa: E402
from ragagent.domain.research import AnswerDraft  # noqa: E402
from ragagent.graphs.state import AnalysisResult  # noqa: E402
from tests.integration.test_conversation_worker import ScientificScript  # noqa: E402
from tests.integration.test_retrieval import Embedder, FixtureReranker  # noqa: E402


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
