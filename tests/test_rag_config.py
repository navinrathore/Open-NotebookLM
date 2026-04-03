import os
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Set up environment for test
os.environ["RAG_TOP_K"] = "10"
os.environ["RAG_SIMILARITY_THRESHOLD"] = "0.5"

# Import after setting env
from workflow_engine.state import IntelligentQAState, IntelligentQARequest
from workflow_engine.workflow.wf_intelligent_qa import try_rag_retrieve

class TestRAGConfig(unittest.TestCase):
    def setUp(self):
        self.state = IntelligentQAState()
        self.state.request = IntelligentQARequest(
            query="test query",
            file_ids=["file1"],
            vector_store_base_dir="/tmp/test_rag"
        )
        # Ensure path exists for the check
        Path("/tmp/test_rag").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if Path("/tmp/test_rag").exists():
            import shutil
            shutil.rmtree("/tmp/test_rag")

    @patch("workflow_engine.toolkits.ragtool.vector_store_tool.VectorStoreManager")
    def test_rag_threshold_filtering(self, mock_manager_class):
        # Setup mock manager
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager
        mock_manager.index = MagicMock()
        mock_manager.index.ntotal = 100
        mock_manager.manifest = {"files": [{"id": "file1", "original_path": "file1"}]}
        
        # Mock search results with varying scores
        # 0.1, 0.2, 0.3, 0.4 (Below 0.5)
        # 0.5, 0.6, 0.7, 0.8, 0.9 (Above/At 0.5)
        mock_results = [
            {"content": f"chunk {i}", "score": i/10.0}
            for i in range(1, 11)
        ]
        mock_manager.search.return_value = mock_results
        
        # Run retrieval
        with patch("os.getenv", side_effect=lambda k, d: os.environ.get(k, d)):
             try_rag_retrieve(self.state)
        
        # Verify filtering (Scores >= 0.5 should remain: 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
        # Total in mock_results: 10. Indices with score >= 0.5: 5, 6, 7, 8, 9, 10
        # Wait, range(1, 11) is 1, 2, 3, 4, 5, 6, 7, 8, 9, 10.
        # Scores: 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0
        # Passing: 0.5, 0.6, 0.7, 0.8, 0.9, 1.0 (6 items)
        
        self.assertEqual(len(self.state.retrieved_chunks), 6)
        for chunk in self.state.retrieved_chunks:
            self.assertGreaterEqual(chunk["score"], 0.5)
            
        print("✅ Threshold filtering test passed!")

    @patch("workflow_engine.toolkits.ragtool.vector_store_tool.VectorStoreManager")
    def test_rag_top_k_param(self, mock_manager_class):
        # Setup mock
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager
        mock_manager.index = MagicMock()
        mock_manager.index.ntotal = 100
        mock_manager.manifest = {"files": [{"id": "file1", "original_path": "file1"}]}
        mock_manager.search.return_value = []
        
        # Change env to K=3
        os.environ["RAG_TOP_K"] = "3"
        
        # Force reload of constants or just re-run with mocked getenv
        import workflow_engine.workflow.wf_intelligent_qa as wf
        wf.RAG_TOP_K = 3 # Manually update for test context if needed
        
        try_rag_retrieve(self.state)
        
        # Verify search was called with top_k=3
        # Use call_args if available
        args, kwargs = mock_manager.search.call_args
        self.assertEqual(kwargs.get("top_k"), 3)
        
        print("✅ Top-K parameter test passed!")

if __name__ == "__main__":
    unittest.main()
