import os
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Override environment for testing
os.environ["USE_RERANKER"] = "1"
os.environ["RAG_RERANK_TOP_N"] = "2"
os.environ["RAG_TOP_K"] = "10"

# Import required components (Mocking heavy dependencies before loading)
with patch("sentence_transformers.CrossEncoder"): 
    from workflow_engine.state import IntelligentQAState, IntelligentQARequest
    from workflow_engine.workflow.wf_intelligent_qa import try_rag_retrieve

class TestRerankerIntegration(unittest.TestCase):
    def setUp(self):
        self.state = IntelligentQAState()
        self.state.request = IntelligentQARequest(
            query="Who is the applicant?",
            file_ids=["case_123"],
            vector_store_base_dir="/tmp/test_rerank"
        )
        Path("/tmp/test_rerank").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if Path("/tmp/test_rerank").exists():
            import shutil
            shutil.rmtree("/tmp/test_rerank")

    @patch("workflow_engine.toolkits.ragtool.vector_store_tool.VectorStoreManager")
    def test_reranking_logic(self, mock_manager_class):
        # 1. Setup Mock Manager
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager
        
        # Initial search results (Vector Similarity only)
        # Result index 1 is "good" (0.8), but result index 0 is "better" (0.9)
        initial_hits = [
            {"content": "Irrelevant text A", "score": 0.9, "source_file_id": "case_123"},
            {"content": "The applicant is Mr. John Doe", "score": 0.8, "source_file_id": "case_123"},
            {"content": "Irrelevant text B", "score": 0.7, "source_file_id": "case_123"}
        ]
        mock_manager.search.return_value = initial_hits
        
        # 2. Mock Reranker behavior (Reverse the order)
        # We simulate the reranker realizing that the 2nd item is actually the best
        def mock_rerank_impl(query, results, top_n):
            # Sort such that "John Doe" is #1
            for r in results:
                if "John Doe" in r["content"]:
                    r["rerank_score"] = 5.0
                else:
                    r["rerank_score"] = 0.1
            sorted_res = sorted(results, key=lambda x: x["rerank_score"], reverse=True)
            return sorted_res[:top_n]
            
        mock_manager.rerank.side_effect = mock_rerank_impl
        
        # 3. Execute Workflow Step
        try_rag_retrieve(self.state)
        
        # 4. Assertions
        # Final selection should be restricted by RAG_RERANK_TOP_N (2)
        self.assertEqual(len(self.state.retrieved_chunks), 2)
        
        # The first chunk should now be John Doe (thanks to the reranker)
        self.assertIn("John Doe", self.state.retrieved_chunks[0]["content"])
        self.assertGreater(self.state.retrieved_chunks[0]["rerank_score"], self.state.retrieved_chunks[1]["rerank_score"])
        
        print("✅ Reranking verification test PASSED (Fast path)")

if __name__ == "__main__":
    unittest.main()
