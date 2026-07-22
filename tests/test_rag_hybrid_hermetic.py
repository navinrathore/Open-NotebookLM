import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# --- MOCK HEAVY DEPENDENCIES ---
mock_faiss = MagicMock()
sys.modules["faiss"] = mock_faiss
sys.modules["sentence_transformers"] = MagicMock()
sys.modules["langgraph"] = MagicMock()
sys.modules["langgraph.graph"] = MagicMock()
sys.modules["langgraph.graph.message"] = MagicMock()
sys.modules["langchain_text_splitters"] = MagicMock()
sys.modules["fitz"] = MagicMock()
sys.modules["PIL"] = MagicMock()
sys.modules["PIL.Image"] = MagicMock()
sys.modules["rank_bm25"] = MagicMock()

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
os.environ["USE_HYBRID_SEARCH"] = "1"
os.environ["RAG_TOP_K"] = "5"

class TestHybridHermetic(unittest.TestCase):
    @patch("workflow_engine.workflow.wf_intelligent_qa.get_logger")
    @patch("workflow_engine.toolkits.ragtool.vector_store_tool.VectorStoreManager")
    def test_hybrid_logic_hermetic(self, mock_manager_class, mock_get_logger):
        # 1. Setup Mock Manager
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager
        
        # Simulated fused results (John Doe wins via RRF)
        mock_manager.search.return_value = [
            {"content": "Section 144: John Doe", "rrf_score": 0.032},
            {"content": "General Law", "rrf_score": 0.016}
        ]
        
        # 2. Import and Run
        from workflow_engine.workflow.wf_intelligent_qa import try_rag_retrieve
        state = MockState("Section 144", ["doc1"], "/tmp/fake")
        try_rag_retrieve(state)
        
        # 3. Assertions
        # Verify it was called with use_hybrid=True
        # Search is called with: query, top_k, file_ids, include_context, window_size, use_hybrid
        args, kwargs = mock_manager.search.call_args
        self.assertTrue(kwargs.get("use_hybrid"))
        
        # Verify the top chunk is the correct one
        self.assertEqual(state.retrieved_chunks[0]["content"], "Section 144: John Doe")
        
        print("\n✅ Hybrid Search Hermetic Test PASSED")

if __name__ == "__main__":
    unittest.main()
