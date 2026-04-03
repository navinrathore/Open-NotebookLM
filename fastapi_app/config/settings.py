"""
Application Settings

Model configurations are used as Pydantic defaults in schemas.py.
Frontend typically overrides these values, but they're kept for API compatibility.
"""

from pydantic_settings import BaseSettings
from typing import Optional
import os


class AppSettings(BaseSettings):
    """Application configuration with environment variable support."""

    # API Configuration (Locked to Free/Local Stack)
    DEFAULT_LLM_API_URL: str = "https://router.huggingface.co/v1"
    # Using HF_TOKEN as the secondary fallback for DEFAULT_LLM_API_KEY
    DEFAULT_LLM_API_KEY: str = ""
    HF_TOKEN: str = ""
    
    DF_API_KEY: Optional[str] = None
    DEFAULT_LANGUAGE: str = "en"

    # Model defaults (Locked to Meta-Llama-3-8B-Instruct for Free Tier)
    MODEL_GPT_4O: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    PAPER2VIDEO_DEFAULT_MODEL: str = "meta-llama/Meta-Llama-3-8B-Instruct"

    # Paper2PPT models
    PAPER2PPT_DEFAULT_MODEL: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    PAPER2PPT_OUTLINE_MODEL: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    PAPER2PPT_CONTENT_MODEL: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    PAPER2PPT_IMAGE_GEN_MODEL: str = "gemini-3-pro-image-preview"
    PAPER2PPT_VLM_MODEL: str = "qwen-vl-ocr-2025-11-20"
    PAPER2PPT_CHART_MODEL: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    PAPER2PPT_DESC_MODEL: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    PAPER2PPT_TECHNICAL_MODEL: str = "meta-llama/Meta-Llama-3-8B-Instruct"

    # Paper2Figure models
    PAPER2FIGURE_TEXT_MODEL: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    PAPER2FIGURE_IMAGE_MODEL: str = "gemini-3-pro-image-preview"
    PAPER2FIGURE_VLM_MODEL: str = "qwen-vl-ocr-2025-11-20"
    PAPER2FIGURE_CHART_MODEL: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    PAPER2FIGURE_DESC_MODEL: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    PAPER2FIGURE_REF_IMG_DESC_MODEL: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    PAPER2FIGURE_TECHNICAL_MODEL: str = "meta-llama/Meta-Llama-3-8B-Instruct"

    # Knowledge Base
    KB_CHAT_MODEL: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    SQLBOT_OPENAI_API_KEY: Optional[str] = None
    SQLBOT_OPENAI_API_BASE: Optional[str] = None
    SQLBOT_OPENAI_MODEL: Optional[str] = None

    # Intelligent data extraction bridge
    SQLBOT_MODE: str = "embedded"
    SQLBOT_BASE_URL: str = "http://127.0.0.1:8000"
    SQLBOT_API_KEY: Optional[str] = None

    # Search API
    SERPER_API_KEY: Optional[str] = None

    # Supabase
    SUPABASE_URL: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None

    # TTS
    USE_LOCAL_TTS: int = 0
    TTS_ENGINE: str = "qwen"
    TTS_IDLE_TIMEOUT: int = 300
    LOCAL_TTS_MODEL: str = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    LOCAL_TTS_PORT: int = 26211
    LOCAL_TTS_CMD: str = "vllm-omni"
    LOCAL_TTS_CUDA_VISIBLE_DEVICES: Optional[str] = None
    LOCAL_TTS_GPU_MEMORY_UTILIZATION: float = 0.3

    # Local Embedding
    USE_LOCAL_EMBEDDING: int = 0
    USE_EMBEDDING_LIBRARY: int = 1
    LOCAL_EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    LOCAL_EMBEDDING_PORT: int = 26210
    LOCAL_EMBEDDING_CMD: str = "vllm"
    LOCAL_EMBEDDING_CUDA_VISIBLE_DEVICES: Optional[str] = None
    LOCAL_EMBEDDING_GPU_MEMORY_UTILIZATION: float = 0.3

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global configuration instance
settings = AppSettings()

# Export critical keys to os.environ so legacy components using os.getenv() work correctly
for key in ["DEFAULT_LLM_API_KEY", "HF_TOKEN", "DF_API_KEY", "DEFAULT_LLM_API_URL"]:
    val = getattr(settings, key, None)
    if val and not os.environ.get(key):
        os.environ[key] = str(val)
