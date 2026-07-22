import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# --- MOCK HEAVY DEPENDENCIES ---
# We mock these in sys.modules so the imports inside the core files don't fail
mock_faiss = MagicMock()
sys.modules["faiss"] = mock_faiss
sys.modules["sentence_transformers"] = MagicMock()
sys.modules["langgraph"] = MagicMock()
sys.modules["langgraph.graph"] = MagicMock()
sys.modules["langgraph.graph.message"] = MagicMock()
sys.modules["langchain_text_splitters"] = MagicMock()
sys.modules["fitz"] = MagicMock()

# Mock classes for State
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

class TestRerankerHermetic(unittest.TestCase):
    @patch("workflow_engine.workflow.wf_intelligent_qa.get_logger")
    @patch("workflow_engine.toolkits.ragtool.vector_store_tool.VectorStoreManager")
    def test_reranking_logic_hermetic(self, mock_manager_class, mock_get_logger):
        # 1. Setup Mock Manager
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager
        
        # Initial search results
        initial_hits = [
            {"content": "Bad result", "score": 0.9},
            {"content": "Perfect: John Doe", "score": 0.8},
            {"content": "Mediocre result", "score": 0.7}
        ]
        mock_manager.search.return_value = initial_hits
        
        # 2. Mock Reranker scoring (John Doe wins)
        def mock_rerank_impl(query, results, top_n):
            for r in results:
                r["rerank_score"] = 10.0 if "John Doe" in r["content"] else -5.0
            sorted_res = sorted(results, key=lambda x: x["rerank_score"], reverse=True)
            return sorted_res[:top_n]
            
        mock_manager.rerank.side_effect = mock_rerank_impl
        
        # 3. Import and Run
        from workflow_engine.workflow.wf_intelligent_qa import try_rag_retrieve
        state = MockState("Who is the applicant?", ["case_123"], "/tmp/fake")
        try_rag_retrieve(state)
        
        # 4. Assertions
        self.assertEqual(len(state.retrieved_chunks), 2)
        self.assertEqual(state.retrieved_chunks[0]["content"], "Perfect: John Doe")
        self.assertEqual(state.retrieved_chunks[0]["rerank_score"], 10.0)
        
        print("\n✅ Reranking Hermetic Test PASSED (No dependencies required)")

if __name__ == "__main__":
    unittest.main()
