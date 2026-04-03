"""
FireRedTTS2 Manager
Lazy loading + Auto-unload
"""
import os
import time
import threading
import torch

REPO_ID = "FireRedTeam/FireRedTTS2"
IDLE_TIMEOUT = int(os.getenv("TTS_IDLE_TIMEOUT", "300"))

_model = None
_device = None
_model_path = None
_last_used = None
_lock = threading.Lock()
_unload_timer = None


def _pick_device():
    """Pick the best GPU available"""
    if not torch.cuda.is_available():
        return "cpu"

    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        if not lines:
            return "cuda:0"

        gpu_mem = []
        for line in lines:
            parts = line.split(",")
            if len(parts) == 2:
                idx, mem = parts[0].strip(), parts[1].strip()
                gpu_mem.append((int(idx), int(mem)))

        if gpu_mem:
            best_gpu = max(gpu_mem, key=lambda x: x[1])
            return f"cuda:{best_gpu[0]}"
    except Exception:
        pass

    return "cuda:0"


def _schedule_unload():
    """Schedule automatic unloading"""
    global _unload_timer
    if _unload_timer is not None:
        _unload_timer.cancel()

    def _unload():
        global _model, _device, _last_used
        with _lock:
            if _last_used and (time.time() - _last_used >= IDLE_TIMEOUT):
                print(f"[TTS] Idle for {IDLE_TIMEOUT}s, unloading model")
                _model = None
                _device = None
                _last_used = None
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

    _unload_timer = threading.Timer(IDLE_TIMEOUT, _unload)
    _unload_timer.daemon = True
    _unload_timer.start()


def _load_model():
    """Lazy load the model"""
    global _model, _device, _model_path, _last_used

    if _model is not None:
        _last_used = time.time()
        _schedule_unload()
        return _model, _device, _model_path

    print(f"[TTS] Loading FireRedTTS2 model: {REPO_ID}")

    try:
        from fireredtts2.fireredtts2 import FireRedTTS2
    except ImportError as e:
        raise RuntimeError(f"fireredtts2 not installed: {e}\nRun: pip install fireredtts2")

    # Download model to HuggingFace cache
    try:
        from huggingface_hub import snapshot_download
        _model_path = snapshot_download(
            repo_id=REPO_ID,
            resume_download=True,
            local_files_only=False
        )
        print(f"[TTS] Model downloaded to: {_model_path}")
    except Exception as e:
        print(f"[TTS] Model download failed: {e}")
        raise

    _device = _pick_device()
    print(f"[TTS] Using device: {_device}")

    try:
        _model = FireRedTTS2(
            pretrained_dir=_model_path,
            gen_type="dialogue",
            device=_device,
        )
    except Exception as e:
        print(f"[TTS] Load failed: {e}")
        raise

    _last_used = time.time()
    _schedule_unload()
    print(f"[TTS] Model load complete")

    return _model, _device, _model_path


def generate_speech(text: str, voice_name: str = "S1", temperature: float = 0.9) -> bytes:
    """
    Generate speech, return WAV audio bytes

    Args:
        text: Text content, must contain speaker tag format "[S1]text\n[S2]text"
        voice_name: Not used (kept for parameter compatibility)
        temperature: Generation temperature

    Returns:
        WAV format audio bytes (24kHz, 16-bit, mono)
    """
    with _lock:
        model, device, model_path = _load_model()

    # Parse text into dialogue list, and split long lines
    text_list = []
    max_line_len = 200  # Max 200 chars per line
    for line in text.strip().split("\n"):
        line = line.strip()
        if line and (line.startswith("[S1]") or line.startswith("[S2]")):
            speaker = line[:4]  # [S1] or [S2]
            content = line[4:].strip()
            # Split overly long content
            if len(content) <= max_line_len:
                text_list.append(line)
            else:
                # Split by sentence
                import re
                sentences = re.split(r'([。！？.!?])', content)
                current = ""
                for i in range(0, len(sentences), 2):
                    sent = sentences[i]
                    punct = sentences[i+1] if i+1 < len(sentences) else ""
                    if len(current) + len(sent) + len(punct) <= max_line_len:
                        current += sent + punct
                    else:
                        if current:
                            text_list.append(f"{speaker}{current}")
                        current = sent + punct
                if current:
                    text_list.append(f"{speaker}{current}")

    if not text_list:
        raise ValueError("No valid dialogue lines found in text")

    print(f"[TTS] Generated {len(text_list)} lines of dialogue, total length: {sum(len(t) for t in text_list)}")

    # Generate audio (using model default voice)
    import torchaudio
    import io
    audio = model.generate_dialogue(
        text_list=text_list,
        temperature=temperature,
        topk=30,
    )

    # Save as WAV bytes
    buf = io.BytesIO()
    torchaudio.save(buf, audio, 24000, format="wav")
    return buf.getvalue()


def is_available() -> bool:
    """Check if FireRedTTS2 is available"""
    try:
        from fireredtts2.fireredtts2 import FireRedTTS2
        return True
    except ImportError:
        return False


def check_and_download_model():
    """Check and automatically download FireRedTTS2 model on startup"""
    # Check and install fireredtts2
    try:
        import fireredtts2
        print(f"[TTS] fireredtts2 is installed")
    except ImportError:
        print(f"[TTS] Installing fireredtts2...")
        import subprocess
        import sys
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "fireredtts2"])
            print(f"[TTS] fireredtts2 installation complete")
        except Exception as e:
            print(f"[TTS] fireredtts2 installation failed: {e}")
            return

    print(f"[TTS] Checking model: {REPO_ID}")
    print(f"[TTS] Will automatically download from HuggingFace or use local cache on first use")


