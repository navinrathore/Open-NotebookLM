import os
import unittest
from pathlib import Path
import json

# Setup mock environment
from workflow_engine.toolkits.ragtool.vector_store_tool import VectorStoreManager

class TestPhysicalHealthCheck(unittest.TestCase):
    def setUp(self):
        self.base_dir = Path("/tmp/test_health")
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
        manager = VectorStoreManager(base_dir=self.base_dir)
        # Should be unhealthy because we have files in manifest but no .index file yet
        health = manager.verify_health()
        self.assertFalse(health["is_healthy"])
        self.assertIn("knowledge_base.index", health["missing_files"])
        print("✅ Correctly detected missing index file.")

    def test_health_check_empty_index(self):
        # Create an empty index file
        (self.vstore_dir / "knowledge_base.index").touch()
        (self.vstore_dir / "knowledge_base.meta").touch()
        (self.vstore_dir / "knowledge_base.bm25").touch()
        
        manager = VectorStoreManager(base_dir=self.base_dir)
        health = manager.verify_health()
        
        self.assertFalse(health["is_healthy"])
        self.assertIn("knowledge_base.index (EMPTY)", health["missing_files"])
        print("✅ Correctly detected empty index file.")

    def test_health_check_healthy(self):
        # Create a non-empty index file
        with open(self.vstore_dir / "knowledge_base.index", "wb") as f:
            f.write(b"fake data")
        with open(self.vstore_dir / "knowledge_base.meta", "wb") as f:
            f.write(b"fake meta")
        with open(self.vstore_dir / "knowledge_base.bm25", "wb") as f:
            f.write(b"fake bm25")
            
        manager = VectorStoreManager(base_dir=self.base_dir)
        health = manager.verify_health()
        
        self.assertTrue(health["is_healthy"])
        self.assertEqual(len(health["missing_files"]), 0)
        print("✅ Correctly verified healthy index.")

if __name__ == "__main__":
    unittest.main()
