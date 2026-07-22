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

from workflow_engine.toolkits.ragtool.vector_store_tool import VectorStoreManager

class TestHealthHermetic(unittest.TestCase):
    def setUp(self):
        self.base_dir = Path("/tmp/test_health_h")
        self.vstore_dir = self.base_dir / "vector_store"
        self.vstore_dir.mkdir(parents=True, exist_ok=True)
        
        # Create a mock manifest
        manifest = {
            "project_name": "test_health",
            "files": [{"id": "file1", "original_path": "file1.pdf"}]
        }
        with open(self.base_dir / "knowledge_manifest.json", "w") as f:
            json.dump(manifest, f)

    def tearDown(self):
        import shutil
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)

    def test_health_check_missing_index(self):
        # We need to mock VectorStoreManager._load_index because it might crash on fake files
        with patch.object(VectorStoreManager, '_load_index'):
            manager = VectorStoreManager(base_dir=self.base_dir)
            health = manager.verify_health()
            self.assertFalse(health["is_healthy"])
            self.assertIn("knowledge_base.index", health["missing_files"])
            print("\n✅ Hermetic: Correctly detected missing index file.")

    def test_health_check_healthy(self):
        with patch.object(VectorStoreManager, '_load_index'):
            # Create non-empty index and meta files
            (self.vstore_dir).mkdir(parents=True, exist_ok=True)
            with open(self.vstore_dir / "knowledge_base.index", "wb") as f:
                f.write(b"data")
            with open(self.vstore_dir / "knowledge_base.meta", "wb") as f:
                f.write(b"meta")
            with open(self.vstore_dir / "knowledge_base.bm25", "wb") as f:
                f.write(b"bm25")
                
            manager = VectorStoreManager(base_dir=self.base_dir)
            health = manager.verify_health()
            
            self.assertTrue(health["is_healthy"])
            self.assertEqual(len(health["missing_files"]), 0)
            print("\n✅ Hermetic: Correctly verified healthy index.")

if __name__ == "__main__":
    unittest.main()
