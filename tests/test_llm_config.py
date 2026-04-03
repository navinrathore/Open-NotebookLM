import os
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root))

from fastapi_app.config import settings
from fastapi_app.routers.kb import _build_chat_request

def test_llm_config():
    print("Testing LLM configuration...")
    
    # Ensure DF_API_KEY and OPENAI_API_KEY are not in environment for this test
    os.environ.pop("DF_API_KEY", None)
    os.environ.pop("OPENAI_API_KEY", None)
    
    # Mock parameters
    files = []
    query = "test query"
    history = []
    email = "test@example.com"
    notebook_id = "test_nb"
    api_url = None
    api_key = None
    model = settings.KB_CHAT_MODEL
    
    # Build request
    req = _build_chat_request(files, query, history, email, notebook_id, api_url, api_key, model)
    
    print(f"Request API URL: {req.chat_api_url}")
    print(f"Request API Key: {req.api_key}")
    
    assert req.api_key == "no-key-required", f"Expected 'no-key-required', got '{req.api_key}'"
    print("Verification successful: Default API key is used.")

if __name__ == "__main__":
    try:
        test_llm_config()
    except Exception as e:
        print(f"Verification failed: {e}")
        sys.exit(1)
