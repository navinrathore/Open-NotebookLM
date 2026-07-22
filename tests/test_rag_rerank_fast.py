import os
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Mock classes to avoid heavy imports (langgraph, torch, etc)
class MockRequest:
    def __init__(self, query, file_ids, vector_store_base_dir):
        self.query = query
        self.file_ids = file_ids
        self.vector_store_base_dir = vector_store_base_dir

class MockState:
    def __init__(self, query, file_ids, vstore):
        self.request = MockRequest(query, file_ids, vstore)
        self.retrieved_chunks = []

# Set environment
os.environ["USE_RERANKER"] = "1"
os.environ["RAG_RERANK_TOP_N"] = "2"

class TestRerankerFast(unittest.TestCase):
    def setUp(self):
        # We don't even need the real file system if we mock everything
        self.state = MockState("Who is the applicant?", ["case_123"], "/tmp/fake_vstore")

    @patch("workflow_engine.workflow.wf_intelligent_qa.get_logger")
    @patch("workflow_engine.toolkits.ragtool.vector_store_tool.VectorStoreManager")
    def test_reranking_logic_isolated(self, mock_manager_class, mock_get_logger):
        # 1. Setup Mock Manager
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager
        
        # Initial search results
        initial_hits = [
            {"content": "Irrelevant A", "score": 0.9},
            {"content": "Target: John Doe", "score": 0.8},
            {"content": "Irrelevant B", "score": 0.7}
        ]
        mock_manager.search.return_value = initial_hits
        
        # 2. Mock Reranker behavior (Reverse the order)
        def mock_rerank_impl(query, results, top_n):
            for r in results:
                r["rerank_score"] = 5.0 if "John Doe" in r["content"] else 0.1
            sorted_res = sorted(results, key=lambda x: x["rerank_score"], reverse=True)
            return sorted_res[:top_n]
            
        mock_manager.rerank.side_effect = mock_rerank_impl
        
        # 3. Import and Run the specific function (mocking the logger to avoid more imports)
        from workflow_engine.workflow.wf_intelligent_qa import try_rag_retrieve
        try_rag_retrieve(self.state)
        
        # 4. Assertions
        self.assertEqual(len(self.state.retrieved_chunks), 2)
        self.assertIn("John Doe", self.state.retrieved_chunks[0]["content"])
        
        print("✅ Reranking Isolated Test PASSED (Instant)")

if __name__ == "__main__":
    unittest.main()
