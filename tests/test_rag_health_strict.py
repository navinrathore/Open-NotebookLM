import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import json

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

from workflow_engine.toolkits.ragtool.vector_store_tool import VectorStoreManager

class TestStrictHealthHermetic(unittest.TestCase):
    def setUp(self):
        self.base_dir = Path("/tmp/test_health_strict")
        self.vstore_dir = self.base_dir / "vector_store"
        self.vstore_dir.mkdir(parents=True, exist_ok=True)
        
        # Create non-empty mock files
        with open(self.base_dir / "knowledge_manifest.json", "w") as f:
            json.dump({"files": [{"id": "f1"}]}, f)
        (self.vstore_dir / "knowledge_base.index").write_bytes(b"data")
        (self.vstore_dir / "knowledge_base.meta").write_bytes(b"meta")
        (self.vstore_dir / "knowledge_base.bm25").write_bytes(b"bm25")

    def tearDown(self):
        import shutil
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)

    def test_strict_health_conflict(self):
        """Test that strict mode detects mismatch between vector count and meta count."""
        with patch.object(VectorStoreManager, '_load_index'):
            manager = VectorStoreManager(base_dir=self.base_dir)
            
            # Simulate a conflict: 10 vectors in FAISS index, but 20 items in metadata
            mock_index = MagicMock()
            mock_index.ntotal = 10
            manager.index = mock_index
            manager.meta_data = [i for i in range(20)] 
            
            # Test Lite mode (should be healthy because files exist)
            health_lite = manager.verify_health(strict=False)
            self.assertTrue(health_lite["is_healthy"])
            
            # Test Strict mode (should be unhealthy due to mismatch)
            health_strict = manager.verify_health(strict=True)
            self.assertFalse(health_strict["is_healthy"])
            self.assertTrue(any("Logic Mismatch" in issue for issue in health_strict["missing_files"]))
            self.assertTrue(health_strict["can_repair"])
            
            print("\n✅ Strict Mode: Correctly detected vector/metadata mismatch.")

if __name__ == "__main__":
    unittest.main()
