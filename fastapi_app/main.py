from __future__ import annotations

import os
import subprocess
import sys
import time
import shutil
import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Iterable, List, Optional

# Load .env to make SUPABASE_* and other env vars available in os.getenv
try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parent.parent
    # Load .env first, then .env.local (override=True allows .env.local to override .env)
    load_dotenv(_root / "fastapi_app" / ".env")
    load_dotenv(_root / "fastapi_app" / ".env.local", override=True)
except ImportError:
    pass

from workflow_engine.logger import get_logger

log = get_logger(__name__)

# Check Supabase config on startup
_supabase_url = os.getenv("SUPABASE_URL")
_supabase_anon = os.getenv("SUPABASE_ANON_KEY")
_supabase_service = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
if _supabase_url and _supabase_anon:
    log.info(f"Supabase configured: URL={_supabase_url[:30]}..., ANON_KEY={'Set' if _supabase_anon else 'Not Set'}, SERVICE_KEY={'Set' if _supabase_service else 'Not Set'}")
else:
    log.info(f"Supabase not configured: URL={'Set' if _supabase_url else 'Not Set'}, ANON_KEY={'Set' if _supabase_anon else 'Not Set'}")


from urllib.parse import unquote

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from fastapi_app.routers import auth, data_extract, files, kb, kb_embedding, paper2drawio, paper2ppt
# LawNidhi Integration routers (isolated in separate files)
from fastapi_app.routers import cases as lawnidhi_cases
from fastapi_app.routers import scrapers as lawnidhi_scrapers
from fastapi_app.routers import calendar as lawnidhi_calendar
from fastapi_app.routers import reports as lawnidhi_reports
from fastapi_app.middleware.api_key import APIKeyMiddleware
from fastapi_app.middleware.logging import LoggingMiddleware
from workflow_engine.utils import get_project_root

# Local Embedding service port (Octen-Embedding-0.6B)
LOCAL_EMBEDDING_PORT = int(os.getenv("LOCAL_EMBEDDING_PORT", "26210"))
LOCAL_EMBEDDING_MODEL = os.getenv("LOCAL_EMBEDDING_MODEL", "Octen/Octen-Embedding-0.6B")

LOCAL_TTS_PORT = int(os.getenv("LOCAL_TTS_PORT", "26211"))
LOCAL_TTS_MODEL = os.getenv("LOCAL_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")


def _resolve_command(env_name: str, default_binary: str) -> str:
    configured = os.getenv(env_name, "").strip()
    if configured:
        return configured

    current_env_binary = Path(sys.executable).resolve().parent / default_binary
    if current_env_binary.exists():
        return str(current_env_binary)

    return shutil.which(default_binary) or default_binary


def _resolve_gpu_memory_utilization(env_name: str, default: str = "0.95") -> str:
    value = os.getenv(env_name, "").strip() or os.getenv("VLLM_GPU_MEMORY_UTILIZATION", "").strip()
    if not value:
        return default
    return value


def _default_hf_cache_root() -> Path:
    hf_home = os.getenv("HF_HOME", "").strip()
    if hf_home:
        return Path(hf_home).expanduser() / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _resolve_cached_model_path(model_name: str) -> str:
    model_name = model_name.strip()
    if not model_name:
        return model_name

    local_path = Path(model_name).expanduser()
    if local_path.exists():
        return str(local_path.resolve())

    if "/" not in model_name:
        return model_name

    org, repo = model_name.split("/", 1)
    cache_root = _default_hf_cache_root()
    snapshots_dir = cache_root / f"models--{org}--{repo}" / "snapshots"
    if not snapshots_dir.exists():
        log.warning("No local cache snapshot found for model, continuing with repo id: %s", model_name)
        return model_name

    snapshots = [path for path in snapshots_dir.iterdir() if path.is_dir()]
    if not snapshots:
        log.warning("No snapshots found in model cache directory, continuing with repo id: %s", model_name)
        return model_name

    latest_snapshot = max(snapshots, key=lambda path: path.stat().st_mtime)
    resolved = str(latest_snapshot.resolve())
    log.info("Model %s resolved to local cache path %s", model_name, resolved)
    return resolved


def _query_available_gpus() -> list[str]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,memory.free,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []

    rows: list[tuple[int, int, int]] = []
    for line in result.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            continue
        try:
            rows.append((int(parts[0]), int(parts[1]), int(parts[2])))
        except ValueError:
            continue

    rows.sort(key=lambda item: (-item[1], item[2], item[0]))
    return [str(index) for index, _, _ in rows]


def _select_cuda_visible_devices(env_name: str, reserved: set[str]) -> Optional[str]:
    configured = os.getenv(env_name, "").strip()
    if configured:
        return configured

    available = _query_available_gpus()
    for gpu in available:
        if gpu not in reserved:
            reserved.add(gpu)
            return gpu
    return None


def _build_child_env(project_root: str, cuda_visible_devices: Optional[str] = None) -> dict[str, str]:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    if existing_pythonpath:
        env["PYTHONPATH"] = f"{project_root}:{existing_pythonpath}"
    else:
        env["PYTHONPATH"] = project_root
    if cuda_visible_devices:
        env["CUDA_VISIBLE_DEVICES"] = cuda_visible_devices
    return env


def _http_ready(url: str, timeout: float = 2.0) -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", 200) < 500
    except Exception:
        return False


def _port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _pick_service_port(preferred_port: int, reserved_ports: set[int]) -> int:
    if preferred_port not in reserved_ports and not _port_in_use(preferred_port):
        reserved_ports.add(preferred_port)
        return preferred_port

    for candidate in range(preferred_port + 1, preferred_port + 20):
        if candidate in reserved_ports:
            continue
        if not _port_in_use(candidate):
            reserved_ports.add(candidate)
            return candidate

    raise RuntimeError(f"Could not find an available port for local service, starting port={preferred_port}")


def _wait_for_ready(url: str, label: str, proc: Optional[subprocess.Popen], timeout_s: float = 180.0) -> None:
    deadline = time.time() + timeout_s
    last_error = ""
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(f"{label} child process exited with code={proc.returncode}")
        if _http_ready(url):
            return
        time.sleep(1.0)
    raise RuntimeError(f"{label} startup timed out waiting for address: {url}. {last_error}")


def _resolve_stage_config_path() -> str:
    configured = os.getenv("VLLM_OMNI_STAGE_CONFIG", "").strip()
    if configured:
        return configured

    spec = importlib.util.find_spec("vllm_omni")
    if spec and spec.submodule_search_locations:
        base = Path(next(iter(spec.submodule_search_locations)))
        candidate = base / "model_executor" / "stage_configs" / "qwen3_tts.yaml"
        if candidate.exists():
            return str(candidate)

    return "vllm_omni/model_executor/stage_configs/qwen3_tts.yaml"


def _spawn_process_with_candidates(
    command_candidates: Iterable[List[str]],
    cwd: str,
    ready_url: str,
    label: str,
    timeout_s: float = 180.0,
    extra_env: Optional[dict[str, str]] = None,
) -> subprocess.Popen:
    errors = []
    for cmd in command_candidates:
        log.info("%s start command: %s", label, " ".join(cmd))
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=extra_env,
                stdout=None,
                stderr=None,
            )
        except FileNotFoundError as e:
            errors.append(f"{cmd[0]} does not exist: {e}")
            continue
        try:
            _wait_for_ready(ready_url, label, proc, timeout_s=timeout_s)
            return proc
        except Exception as e:
            errors.append(f"{' '.join(cmd)} -> {e}")
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            continue
    raise RuntimeError(f"{label} startup failed: {' | '.join(errors)}")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    managed_procs: list[subprocess.Popen] = []
    project_root = str(Path(__file__).resolve().parent.parent)
    embedding_cmd = _resolve_command("LOCAL_EMBEDDING_CMD", "vllm")
    tts_command = _resolve_command("LOCAL_TTS_CMD", "vllm-omni")
    resolved_embedding_model = _resolve_cached_model_path(LOCAL_EMBEDDING_MODEL)
    resolved_tts_model = _resolve_cached_model_path(LOCAL_TTS_MODEL)
    reserved_gpus: set[str] = set()
    reserved_ports: set[int] = set()

    # Default use local Embedding (Octen-Embedding-0.6B) vLLM service; set USE_LOCAL_EMBEDDING=0 to disable
    use_local = os.getenv("USE_LOCAL_EMBEDDING", "1").strip().lower() in ("1", "true", "yes")
    if use_local:
        embedding_port = LOCAL_EMBEDDING_PORT
        embedding_base_url = f"http://127.0.0.1:{embedding_port}/v1"
        embedding_url = f"{embedding_base_url}/embeddings"
        embedding_ready_url = f"{embedding_base_url}/models"
        if _http_ready(embedding_ready_url):
            log.info("Local Embedding vLLM is already running, reusing @ %s", embedding_url)
            reserved_ports.add(embedding_port)
        else:
            if _port_in_use(embedding_port):
                embedding_port = _pick_service_port(embedding_port, reserved_ports)
                embedding_base_url = f"http://127.0.0.1:{embedding_port}/v1"
                embedding_url = f"{embedding_base_url}/embeddings"
                embedding_ready_url = f"{embedding_base_url}/models"
                log.warning("Local Embedding default port is occupied, using port %s instead", embedding_port)
            else:
                reserved_ports.add(embedding_port)
            embedding_cuda = _select_cuda_visible_devices("LOCAL_EMBEDDING_CUDA_VISIBLE_DEVICES", reserved_gpus)
            embedding_env = _build_child_env(project_root, embedding_cuda)
            if embedding_cuda:
                log.info("Local Embedding vLLM using GPU=%s", embedding_cuda)
            embedding_gpu_util = _resolve_gpu_memory_utilization(
                "LOCAL_EMBEDDING_GPU_MEMORY_UTILIZATION"
            )
            embedding_candidates = [
                [
                    embedding_cmd,
                    "serve",
                    resolved_embedding_model,
                    "--host", "127.0.0.1",
                    "--port", str(embedding_port),
                    "--runner", "pooling",
                    "--trust-remote-code",
                    "--gpu-memory-utilization", embedding_gpu_util,
                ],
            ]
            proc = _spawn_process_with_candidates(
                embedding_candidates,
                cwd=project_root,
                ready_url=embedding_ready_url,
                label="Local Embedding vLLM",
                timeout_s=240.0,
                extra_env=embedding_env,
            )
            managed_procs.append(proc)
            log.info("Local Embedding vLLM ready @ %s", embedding_url)
        os.environ["EMBEDDING_API_URL"] = embedding_url
        os.environ["EMBEDDING_MODEL"] = resolved_embedding_model

    # Local TTS uses vLLM-Omni service, backend waits for ready on startup
    use_local_tts = os.getenv("USE_LOCAL_TTS", "0").strip().lower() in ("1", "true", "yes")
    tts_engine = os.getenv("TTS_ENGINE", "qwen").strip().lower()
    if use_local_tts:
        if tts_engine == "qwen":
            tts_port = LOCAL_TTS_PORT
            tts_base_url = f"http://127.0.0.1:{tts_port}/v1"
            tts_ready_url = f"{tts_base_url}/audio/voices"
            if _http_ready(tts_ready_url):
                log.info("Local Qwen3-TTS vLLM-Omni is already running, reusing @ %s", tts_base_url)
                reserved_ports.add(tts_port)
            else:
                if _port_in_use(tts_port):
                    tts_port = _pick_service_port(tts_port, reserved_ports)
                    tts_base_url = f"http://127.0.0.1:{tts_port}/v1"
                    tts_ready_url = f"{tts_base_url}/audio/voices"
                    log.warning("Local TTS default port is occupied, using port %s instead", tts_port)
                else:
                    reserved_ports.add(tts_port)
                tts_cuda = _select_cuda_visible_devices("LOCAL_TTS_CUDA_VISIBLE_DEVICES", reserved_gpus)
                tts_env = _build_child_env(project_root, tts_cuda)
                tts_env["HF_HUB_OFFLINE"] = "1"
                if tts_cuda:
                    log.info("Local Qwen3-TTS vLLM-Omni using GPU=%s", tts_cuda)
                stage_config_path = _resolve_stage_config_path()
                tts_gpu_util = _resolve_gpu_memory_utilization("LOCAL_TTS_GPU_MEMORY_UTILIZATION")
                tts_cmd = [
                    tts_command,
                    "serve",
                    LOCAL_TTS_MODEL,  # vLLM-Omni needs repo ID, not local path
                    "--host", "127.0.0.1",
                    "--port", str(tts_port),
                    "--trust-remote-code",
                    "--omni",
                    "--stage-configs-path", stage_config_path,
                    "--gpu-memory-utilization", tts_gpu_util,
                    "--enforce-eager",
                    "--chat-template", "{% for message in messages %}{{ message['content'] }}{% endfor %}",
                ]
                proc = _spawn_process_with_candidates(
                    [tts_cmd],
                    cwd=project_root,
                    ready_url=tts_ready_url,
                    label="Local Qwen3-TTS vLLM-Omni",
                    timeout_s=300.0,
                    extra_env=tts_env,
                )
                managed_procs.append(proc)
                log.info("Local Qwen3-TTS vLLM-Omni ready @ %s", tts_base_url)
            os.environ["LOCAL_TTS_API_URL"] = tts_base_url
        else:
            log.warning("TTS_ENGINE=%s currently not switched to vLLM-Omni, will use original local/remote fallback logic", tts_engine)

    # Local MinerU uses vLLM service, backend waits for ready on startup
    use_local_mineru = os.getenv("USE_LOCAL_MINERU", "0").strip().lower() in ("1", "true", "yes")
    if use_local_mineru:
        mineru_port = int(os.getenv("LOCAL_MINERU_PORT", "26215"))
        mineru_model = os.getenv("LOCAL_MINERU_MODEL", "opendatalab/MinerU2.5-2509-1.2B")
        mineru_command = os.getenv("LOCAL_MINERU_CMD", "vllm").strip() or "vllm"
        resolved_mineru_model = _resolve_cached_model_path(mineru_model)

        mineru_base_url = f"http://127.0.0.1:{mineru_port}/v1"
        mineru_ready_url = f"{mineru_base_url}/models"
        if _http_ready(mineru_ready_url):
            log.info("Local MinerU vLLM already running, reusing @ %s", mineru_base_url)
            reserved_ports.add(mineru_port)
        else:
            if _port_in_use(mineru_port):
                mineru_port = _pick_service_port(mineru_port, reserved_ports)
                mineru_base_url = f"http://127.0.0.1:{mineru_port}/v1"
                mineru_ready_url = f"{mineru_base_url}/models"
                log.warning("Local MinerU default port occupied, using port %s instead", mineru_port)
            else:
                reserved_ports.add(mineru_port)
            mineru_cuda = _select_cuda_visible_devices("LOCAL_MINERU_CUDA_VISIBLE_DEVICES", reserved_gpus)
            mineru_env = _build_child_env(project_root, mineru_cuda)
            if mineru_cuda:
                log.info("Local MinerU vLLM using GPU=%s", mineru_cuda)
            mineru_gpu_util = _resolve_gpu_memory_utilization("LOCAL_MINERU_GPU_MEMORY_UTILIZATION", "0.5")
            mineru_max_seqs = os.getenv("LOCAL_MINERU_MAX_NUM_SEQS", "64").strip()

            mineru_cmd = [
                mineru_command,
                "serve",
                resolved_mineru_model,
                "--host", "127.0.0.1",
                "--port", str(mineru_port),
                "--served-model-name", "mineru",
                "--logits-processors", "mineru_vl_utils:MinerULogitsProcessor",
                "--gpu-memory-utilization", mineru_gpu_util,
                "--max-num-seqs", mineru_max_seqs,
                "--trust-remote-code",
                "--enforce-eager",
            ]
            proc = _spawn_process_with_candidates(
                [mineru_cmd],
                cwd=project_root,
                ready_url=mineru_ready_url,
                label="Local MinerU vLLM",
                timeout_s=300.0,
                extra_env=mineru_env,
            )
            managed_procs.append(proc)
            log.info("Local MinerU vLLM ready @ %s", mineru_base_url)
        os.environ["LOCAL_MINERU_API_URL"] = mineru_base_url
        os.environ["LOCAL_MINERU_MODEL"] = resolved_mineru_model

    yield
    for proc in managed_procs:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def create_app() -> FastAPI:
    """
    Create FastAPI app instance.

    Basic framework Setup:
    - CORS configuration
    - Router mounting
    - Static file serving
    """
    app = FastAPI(
        title="DataFlow Agent FastAPI Backend",
        version="0.1.0",
        description="HTTP API wrapper for dataflow_agent.workflow.* pipelines",
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Logging middleware (first to capture all requests)
    app.add_middleware(LoggingMiddleware)

    # API key verification for /api/* routes
    app.add_middleware(APIKeyMiddleware)

    # Router mounting (Notebook / frontend-v2 related)
    app.include_router(kb.router, prefix="/api/v1", tags=["Knowledge Base"])
    app.include_router(kb_embedding.router, prefix="/api/v1", tags=["Knowledge Base Embedding"])
    app.include_router(files.router, prefix="/api/v1", tags=["Files"])
    app.include_router(data_extract.router, prefix="/api/v1", tags=["Data Extract"])
    app.include_router(paper2drawio.router, prefix="/api/v1", tags=["Paper2Drawio"])
    app.include_router(paper2ppt.router, prefix="/api/v1", tags=["Paper2PPT"])
    app.include_router(auth.router, prefix="/api/v1", tags=["Auth"])

    # LawNidhi Integration routers (case management, scraping, calendar, reports)
    app.include_router(lawnidhi_cases.router, prefix="/api/v1", tags=["Cases (LawNidhi)"])
    app.include_router(lawnidhi_scrapers.router, prefix="/api/v1", tags=["Scrapers (LawNidhi)"])
    app.include_router(lawnidhi_calendar.router, prefix="/api/v1", tags=["Calendar (LawNidhi)"])
    app.include_router(lawnidhi_reports.router, prefix="/api/v1", tags=["Reports (LawNidhi)"])

    # Static files: files under /outputs (compatible with both %40 and @ in URLs)
    project_root = get_project_root()
    outputs_dir = project_root / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    @app.get("/outputs/{path:path}")
    async def serve_outputs(path: str):
        # Try URL decoded path first (%40 -> @), then try literal path (compatible with old dev%40... data)
        path_decoded = unquote(path)
        outputs_resolved = outputs_dir.resolve()
        for candidate in (path_decoded, path):
            try:
                file_path = (outputs_dir / candidate).resolve()
                if not str(file_path).startswith(str(outputs_resolved)):
                    continue
                if file_path.is_file():
                    resp = FileResponse(path=str(file_path), filename=file_path.name)
                    # Use inline for PDF to enable browser embedded preview instead of download
                    if file_path.suffix.lower() == ".pdf":
                        resp.headers["Content-Disposition"] = "inline"
                    return resp
            except Exception as e:
                log.debug(f"File path resolution failed: {candidate}, error: {e}")
                continue
        raise HTTPException(status_code=404, detail="Not found")

    log.info(f"Serving /outputs from {outputs_dir}")

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    @app.get("/hello")
    async def hello_world():
        return {"message": "Hello World"}

    log.info("Backend ready")
    return app


# For uvicorn use: uvicorn fastapi_app.main:app --reload --port 9999
app = create_app()
