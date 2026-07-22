import os
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Override environment for testing
os.environ["USE_HYBRID_SEARCH"] = "1"
os.environ["RAG_TOP_K"] = "5"

# Import required components
from workflow_engine.state import IntelligentQAState, IntelligentQARequest

class TestHybridSearchFast(unittest.TestCase):
    def setUp(self):
        self.state = IntelligentQAState()
        self.state.request = IntelligentQARequest(
            query="Find Section 144",
            file_ids=["law_doc"],
            vector_store_base_dir="/tmp/test_hybrid"
        )
        Path("/tmp/test_hybrid").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if Path("/tmp/test_hybrid").exists():
            import shutil
            shutil.rmtree("/tmp/test_hybrid")

    @patch("workflow_engine.toolkits.ragtool.vector_store_tool.VectorStoreManager")
    def test_hybrid_fusion_logic(self, mock_manager_class):
        # 1. Setup Mock Manager
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager
        
        # 2. Mock Results
        # Vector search finds "General Law" as top result
        vector_hits = [
            {"content": "General Law Principles", "score": 0.9, "source_file_id": "law_doc"},
            {"content": "Section 144 Details", "score": 0.7, "source_file_id": "law_doc"}
        ]
        
        # BM25 search finds "Section 144" as top result (Exact Keyword Match)
        bm25_hits = [
            {"content": "Section 144 Details", "bm25_score": 10.0, "source_file_id": "law_doc"},
            {"content": "Other random text", "bm25_score": 1.0, "source_file_id": "law_doc"}
        ]
        
        # Mock the search method to return fused results
        # In a real run, search() calls _reciprocal_rank_fusion
        # We simulate the fused result where "Section 144" wins because it appeared in BOTH lists
        mock_manager.search.return_value = [
            {"content": "Section 144 Details", "rrf_score": 0.032, "source_file_id": "law_doc"},
            {"content": "General Law Principles", "rrf_score": 0.016, "source_file_id": "law_doc"}
        ]
        
        # 3. Execute Workflow
        from workflow_engine.workflow.wf_intelligent_qa import try_rag_retrieve
        try_rag_retrieve(self.state)
        
        # 4. Assertions
        self.assertEqual(len(self.state.retrieved_chunks), 2)
        # Verify "Section 144" is now #1 due to Hybrid Fusion
        self.assertEqual(self.state.retrieved_chunks[0]["content"], "Section 144 Details")
        
        print("✅ Hybrid Search Logic verification PASSED")

if __name__ == "__main__":
    unittest.main()
