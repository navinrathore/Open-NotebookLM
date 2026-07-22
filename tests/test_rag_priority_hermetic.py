import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import json
from datetime import datetime

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
sys.modules["mineru_vl_utils"] = MagicMock()
sys.modules["pptx"] = MagicMock()
sys.modules["pptx.enum.text"] = MagicMock()
sys.modules["pptx.dml"] = MagicMock()

from workflow_engine.toolkits.ragtool.vector_store_tool import VectorStoreManager

class TestPrioritizationHermetic(unittest.TestCase):
    def setUp(self):
        self.base_dir = Path("/tmp/test_priority")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        # Mock env
        os.environ["RAG_PRIORITY_SCI_WEIGHT"] = "2.0"
        os.environ["RAG_PRIORITY_NGT_WEIGHT"] = "1.5"
        os.environ["RAG_PRIORITY_AUTHORITY_WEIGHT"] = "1.3"
        os.environ["RAG_PRIORITY_RECENCY_WEIGHT"] = "1.2"

    def tearDown(self):
        import shutil
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)

    def test_filename_metadata_extraction(self):
        with patch.object(VectorStoreManager, '_load_index'):
            manager = VectorStoreManager(base_dir=self.base_dir)
            
            # Test SCI + Date
            meta1 = manager._extract_metadata_from_filename("SCI_Order_2023-12-01.pdf")
            self.assertEqual(meta1["hierarchy"], "sci")
            self.assertTrue(meta1["is_final"])
            self.assertEqual(meta1["doc_date"].year, 2023)
            
            # Test NGT + Review
            meta2 = manager._extract_metadata_from_filename("NGT_Review_Case.docx")
            self.assertEqual(meta2["hierarchy"], "ngt")
            self.assertTrue(meta2["is_final"])
            
            # Test Generic
            meta3 = manager._extract_metadata_from_filename("random_argument.txt")
            self.assertEqual(meta3["hierarchy"], "generic")
            self.assertFalse(meta3["is_final"])
            
            print("\n✅ Metadata Extraction Logic PASSED")

    def test_scoring_boost_logic(self):
        with patch.object(VectorStoreManager, '_load_index'):
            manager = VectorStoreManager(base_dir=self.base_dir)
            
            # Simulated hits with identical raw scores (0.5)
            hits = [
                {"score": 0.5, "metadata": {"hierarchy": "sci", "is_final": True, "doc_date": "2024-01-01"}, "content": "SCI Final"},
                {"score": 0.5, "metadata": {"hierarchy": "ngt", "is_final": False, "doc_date": "2023-01-01"}, "content": "NGT Normal"},
                {"score": 0.5, "metadata": {"hierarchy": "generic", "is_final": False, "doc_date": "2010-01-01"}, "content": "Old Generic"}
            ]
            
            boosted = manager._apply_prioritization_boost(hits)
            
            # Rank Check
            self.assertEqual(boosted[0]["content"], "SCI Final")
            self.assertEqual(boosted[1]["content"], "NGT Normal")
            self.assertEqual(boosted[2]["content"], "Old Generic")
            
            # Score magnification Check
            # SCI boost = 2.0 (SCI) * 1.3 (Final) * 1.2 (Recent) = 3.12
            # 0.5 * 3.12 = 1.56
            self.assertAlmostEqual(boosted[0]["score"], 1.56)
            
            print("✅ Scoring Prioritization Boost PASSED")

if __name__ == "__main__":
    unittest.main()
