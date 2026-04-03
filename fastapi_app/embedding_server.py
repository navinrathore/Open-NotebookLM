"""
Local Embedding Service: Loads Octen/Octen-Embedding-0.6B, provides OpenAI-compatible POST /v1/embeddings.
Can be started independently: uvicorn fastapi_app.embedding_server:app --host 127.0.0.1 --port 17997
Or automatically started by the main backend if USE_LOCAL_EMBEDDING=1.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import List, Union

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

EMBEDDING_MODEL_NAME = "Octen-Embedding-0.6B"
HF_MODEL_ID = "Octen/Octen-Embedding-0.6B"


def _pick_device() -> str:
    """Query the GPU with the most free memory via nvidia-smi to avoid touching corrupted CUDA contexts."""
    import subprocess
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.free,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            print(f"[embedding_server] nvidia-smi failed, falling back to CPU")
            return "cpu"
        best_idx, best_free = -1, 0
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            idx, free, total = int(parts[0]), int(parts[1]), int(parts[2])
            print(f"[embedding_server] GPU {idx}: Free {free} MB / Total {total} MB")
            if free > best_free:
                best_free = free
                best_idx = idx
        if best_idx >= 0 and best_free > 512:  # At least 512 MB free
            device = f"cuda:{best_idx}"
            print(f"[embedding_server] Selected {device} ({best_free} MB free)")
            return device
        print("[embedding_server] Insufficient GPU memory, falling back to CPU")
        return "cpu"
    except Exception as e:
        print(f"[embedding_server] Failed to query GPU: {e}, falling back to CPU")
        return "cpu"


def _get_embedder():
    """Lazy loading: downloads and loads the model on first request, automatically selects free GPU."""
    if _get_embedder._model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError(
                "Please install sentence-transformers: pip install sentence-transformers"
            )
        device = _pick_device()
        _get_embedder._model = SentenceTransformer(HF_MODEL_ID, device=device)
    return _get_embedder._model


_get_embedder._model = None


class EmbeddingRequest(BaseModel):
    model: str = Field(default=EMBEDDING_MODEL_NAME, description="Model name, optional")
    input: Union[str, List[str]] = Field(..., description="Single text string or list of text strings")


class EmbeddingItem(BaseModel):
    object: str = "embedding"
    embedding: List[float]
    index: int


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[EmbeddingItem]
    model: str = EMBEDDING_MODEL_NAME
    usage: dict = Field(default_factory=lambda: {"prompt_tokens": 0, "total_tokens": 0})


def _ensure_model_loaded():
    """Startup check: Log if cached, download and load if not."""
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=HF_MODEL_ID, local_files_only=True)
        print(f"[embedding_server] Model cached, loading {HF_MODEL_ID} ...")
    except Exception:
        print(f"[embedding_server] Model not cached, downloading and loading {HF_MODEL_ID} (slow for the first time)...")
    _get_embedder()
    print(f"[embedding_server] {EMBEDDING_MODEL_NAME} is ready.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup check: download and load model, no longer depends on remote embedding
    try:
        _ensure_model_loaded()
    except Exception as e:
        print(f"[embedding_server] Load failed: {e}")
        raise
    yield
    if _get_embedder._model is not None:
        try:
            del _get_embedder._model
            _get_embedder._model = None
        except Exception:
            pass


app = FastAPI(
    title="Local Embedding (Octen-Embedding-0.6B)",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/v1/embeddings", response_model=EmbeddingResponse)
async def embeddings(req: EmbeddingRequest):
    """OpenAI-compatible embedding interface."""
    if isinstance(req.input, str):
        texts = [req.input]
    else:
        texts = list(req.input)
    if not texts:
        raise HTTPException(status_code=400, detail="input cannot be empty")

    # Limit batch size to avoid OOM
    max_batch = int(os.getenv("EMBEDDING_MAX_BATCH", "32"))
    if len(texts) > max_batch:
        raise HTTPException(
            status_code=400,
            detail=f"Max {max_batch} items per request, current is {len(texts)}",
        )

    try:
        model = _get_embedder()
        # Newlines might affect quality, behavior consistent with VectorStoreManager
        texts_clean = [t.replace("\n", " ").strip() or " " for t in texts]
        emb = model.encode(
            texts_clean,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if emb.ndim == 1:
        emb = emb.reshape(1, -1)
    data = [
        EmbeddingItem(embedding=emb[i].tolist(), index=i)
        for i in range(len(texts))
    ]
    return EmbeddingResponse(data=data)


@app.get("/health")
async def health():
    return {"status": "ok", "model": EMBEDDING_MODEL_NAME}
