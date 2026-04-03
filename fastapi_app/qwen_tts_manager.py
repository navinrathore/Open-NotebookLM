"""
Qwen3-TTS Manager
Lazy loading + Auto-unload
"""
import os
import time
import threading
import torch

REPO_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"  # CustomVoice supports predefined speakers
IDLE_TIMEOUT = int(os.getenv("TTS_IDLE_TIMEOUT", "300"))

_model = None
_device = None
_last_used = None
_lock = threading.Lock()
_unload_timer = None


def _pick_device():
    """Select best GPU"""
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
    """Lazy loading model"""
    global _model, _device, _last_used

    if _model is not None:
        _last_used = time.time()
        _schedule_unload()
        return _model, _device

    print(f"[TTS] Loading Qwen3-TTS model: {REPO_ID}")

    try:
        from qwen_tts import Qwen3TTSModel
    except ImportError as e:
        raise RuntimeError(f"qwen_tts not installed: {e}\nRun: pip install qwen-tts")

    _device = _pick_device()
    dtype = torch.bfloat16 if _device.startswith("cuda") else torch.float32
    print(f"[TTS] Using device: {_device}, dtype: {dtype}")

    try:
        _model = Qwen3TTSModel.from_pretrained(
            REPO_ID,
            device_map=_device,
            dtype=dtype,
        )
    except Exception as e:
        print(f"[TTS] Load failed: {e}")
        raise

    _last_used = time.time()
    _schedule_unload()
    print(f"[TTS] Model load complete")

    return _model, _device


def generate_speech(text: str, voice_name: str = "vivian", language: str = "Chinese") -> bytes:
    """
    Generate speech, return WAV audio bytes

    Args:
        text: Text content
        voice_name: Speaker name (default vivian)
                   Supports: aiden, dylan, eric, ono_anna, ryan, serena, sohee, uncle_fu, vivian
        language: Language (Chinese/English, default Chinese)

    Returns:
        WAV format audio bytes
    """
    with _lock:
        model, device = _load_model()

    # Ensure voice_name is lowercase and in the supported list
    supported_speakers = ['aiden', 'dylan', 'eric', 'ono_anna', 'ryan', 'serena', 'sohee', 'uncle_fu', 'vivian']
    voice_name = voice_name.lower()
    if voice_name not in supported_speakers:
        voice_name = 'vivian'

    # Podcast style instruction
    instruct = "Speak in a natural, friendly podcast host tone with moderate pace and engaging delivery"

    # Generate audio
    wavs, sr = model.generate_custom_voice(
        text=text.strip(),
        language=language,
        speaker=voice_name,
        instruct=instruct,
    )

    # Convert to WAV bytes
    import io
    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, wavs[0], sr, format="wav")
    buf.seek(0)
    return buf.read()


def is_available() -> bool:
    """Check if Qwen3-TTS is available"""
    try:
        from qwen_tts import Qwen3TTSModel
        return True
    except ImportError:
        return False


def check_and_download_model():
    """Check and download Qwen3-TTS model on startup"""
    print(f"[TTS] Checking model: {REPO_ID}")
    print(f"[TTS] Will automatically download from HuggingFace or use local cache on first use")
