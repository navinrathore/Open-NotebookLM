import os
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root))

from fastapi_app.config.settings import AppSettings

def test_settings():
    print("Testing AppSettings...")
    
    # Ensure environment is clean
    os.environ.pop("DEFAULT_LLM_API_KEY", None)
    os.environ.pop("DF_API_KEY", None)
    
    s = AppSettings()
    print(f"Default LLM API Key: {s.DEFAULT_LLM_API_KEY}")
    assert s.DEFAULT_LLM_API_KEY == "no-key-required"
    
    # Test environment override
    os.environ["DEFAULT_LLM_API_KEY"] = "env-key"
    s2 = AppSettings()
    print(f"Overridden LLM API Key: {s2.DEFAULT_LLM_API_KEY}")
    assert s2.DEFAULT_LLM_API_KEY == "env-key"
    
    print("Settings verification successful.")

if __name__ == "__main__":
    try:
        test_settings()
    except Exception as e:
        print(f"Verification failed: {e}")
        sys.exit(1)
