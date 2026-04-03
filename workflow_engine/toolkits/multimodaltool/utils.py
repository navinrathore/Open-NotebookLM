import os
import re
import base64
from enum import Enum
from io import BytesIO
from typing import Tuple
from PIL import Image
from workflow_engine.logger import get_logger

log = get_logger(__name__)

class Provider(str, Enum):
    APIYI = "apiyi"
    LOCAL_123 = "local_123"
    OTHER = "other"

_B64_RE = re.compile(r"[A-Za-z0-9+/=]+")

def detect_provider(api_url: str) -> Provider:
    """
    Roughly identifies the provider based on the api_url
    """
    if "apiyi" in api_url:
        return Provider.APIYI
    if "123.129.219.111" in api_url:
        return Provider.LOCAL_123
    return Provider.OTHER

def extract_base64(s: str) -> str:
    """
    Extracts the longest continuous Base64 string from any given string
    """
    s = "".join(s.split())                # Remove all whitespace
    matches = _B64_RE.findall(s)          # Extract candidate segments
    return max(matches, key=len) if matches else ""

def encode_image_to_base64(image_path: str) -> Tuple[str, str]:
    """
    Reads a local image and encodes it to Base64, also returning the image format (jpeg / png).
    If the image is too large (>3MB), it automatically compresses/resizes it to avoid 413 errors.
    """
    MAX_SIZE = 6 * 1024 * 1024  # 6MB
    MAX_DIM = 2048              # Maximum side length 2048

    if not os.path.exists(image_path):
         raise FileNotFoundError(f"Image not found: {image_path}")

    file_size = os.path.getsize(image_path)
    ext = image_path.rsplit(".", 1)[-1].lower()
    fmt = "jpeg" if ext in {"jpg", "jpeg"} else "png"

    # If the file is less than 3MB and is a common format, read it directly
    if file_size < MAX_SIZE and fmt in ["jpeg", "png"]:
        with open(image_path, "rb") as f:
            raw = f.read()
        b64 = base64.b64encode(raw).decode("utf-8")
        return b64, fmt

    # Otherwise, perform compression
    log.info(f"[utils] Image {os.path.basename(image_path)} too large ({file_size/1024/1024:.2f}MB), compressing...")
    try:
        with Image.open(image_path) as img:
            # 1. Resize if too large
            if max(img.size) > MAX_DIM:
                scale = MAX_DIM / max(img.size)
                new_size = (int(img.width * scale), int(img.height * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # 2. Convert to RGB if needed (for JPEG)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            # 3. Save to buffer as JPEG
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            raw = buffer.getvalue()
            
            log.info(f"[utils] Compressed size: {len(raw)/1024/1024:.2f}MB")
            b64 = base64.b64encode(raw).decode("utf-8")
            return b64, "jpeg"
            
    except Exception as e:
        log.warning(f"[utils] Compression failed: {e}, falling back to original.")
        with open(image_path, "rb") as f:
            raw = f.read()
        b64 = base64.b64encode(raw).decode("utf-8")
        return b64, fmt

def is_gemini_model(model: str) -> bool:
    """Check if it's a Gemini series model"""
    return 'gemini' in model.lower()

def is_gemini_25(model: str) -> bool:
    """Check if it's a Gemini 2.5 series"""
    return "gemini-2.5" in model.lower()

def is_gemini_3_pro(model: str) -> bool:
    """Check if it's a Gemini 3 Pro series"""
    return "gemini-3-pro" in model.lower()
