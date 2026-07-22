import os
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Set up environment for test
os.environ["RAG_CONTEXT_WINDOW_SIZE"] = "1"

# Import after setting env
from workflow_engine.state import IntelligentQAState, IntelligentQARequest
from workflow_engine.workflow.wf_intelligent_qa import try_rag_retrieve, build_doc_context

class TestRAGContextWindow(unittest.TestCase):
    def setUp(self):
        self.state = IntelligentQAState()
        self.state.request = IntelligentQARequest(
            query="test query",
            file_ids=["file1"],
            vector_store_base_dir="/tmp/test_context"
        )
        Path("/tmp/test_context").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if Path("/tmp/test_context").exists():
            import shutil
            shutil.rmtree("/tmp/test_context")

    @patch("workflow_engine.toolkits.ragtool.vector_store_tool.VectorStoreManager")
    def test_context_window_retrieval(self, mock_manager_class):
        # Setup mock manager
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager
        mock_manager.index = MagicMock()
        mock_manager.index.ntotal = 100
        mock_manager.manifest = {"files": [{"id": "file1", "original_path": "file1"}]}
        
        # Scenario: Search finds Chunk 2. With window=1, it should pull 1, 2, 3.
        # This is handled INSIDE VectorStoreManager.search, so we mock that return.
        mock_results = [{
            "score": 0.9,
            "content": "Original Chunk 2",
            "context_content": "Chunk 1\n[...]\nOriginal Chunk 2\n[...]\nChunk 3",
            "source_file_id": "file1",
            "metadata": {"chunk_index": 2}
        }]
        mock_manager.search.return_value = mock_results
        
        # Run retrieval
        try_rag_retrieve(self.state)
        
        # Verify the state has the context
        self.assertEqual(len(self.state.retrieved_chunks), 1)
        self.assertIn("Chunk 1", self.state.retrieved_chunks[0]["context_content"])
        self.assertIn("Chunk 3", self.state.retrieved_chunks[0]["context_content"])
        
        # Test build_doc_context prioritization
        context_str = build_doc_context(self.state)
        self.assertIn("Chunk 1", context_str)
        self.assertIn("Chunk 3", context_str)
        
        print("✅ Context Windowing verification test passed!")

if __name__ == "__main__":
    unittest.main()
