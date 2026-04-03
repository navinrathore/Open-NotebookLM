import os
import base64
import httpx
import subprocess
import uuid
from typing import List, Dict, Any, Optional
from workflow_engine.logger import get_logger
from workflow_engine.toolkits.multimodaltool.providers import get_provider

log = get_logger(__name__)

def _compress_video(input_path: str) -> str:
    """
    Compress video using ffmpeg.
    Returns the path of the compressed temporary file, or the original path if it fails.
    """
    output_path = f"/tmp/compressed_{uuid.uuid4()}.mp4"
    
    # Compression strategy: scale to 720p, CRF 28 (balance quality and size)
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-c:v", "libx264", "-crf", "28", "-preset", "faster",
        "-vf", "scale='min(1280,iw)':-2",
        "-c:a", "aac", "-b:a", "128k",
        output_path
    ]
    
    log.info(f"Compressing video > 20MB: {input_path}")
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if os.path.exists(output_path):
            new_size = os.path.getsize(output_path)
            log.info(f"Compression success. Size: {new_size/1024/1024:.2f}MB")
            return output_path
    except subprocess.CalledProcessError as e:
        log.error(f"FFmpeg compression failed: {e.stderr.decode() if e.stderr else str(e)}")
    except Exception as e:
        log.error(f"Compression error: {e}")
    
    return input_path

def _encode_video_to_base64(video_path: str) -> tuple[str, str]:
    """
    Read video file and encode as Base64. If the video is larger than 20MB, attempt automatic compression.
    Returns: (base64_str, mime_type)
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
        
    ext = video_path.rsplit(".", 1)[-1].lower()
    
    # Default MIME type handling
    mime_map = {
        "mp4": "video/mp4",
        "mov": "video/quicktime",
        "quicktime": "video/quicktime",
        "avi": "video/x-msvideo",
        "mpeg": "video/mpeg",
        "wmv": "video/x-ms-wmv"
    }
    mime_type = mime_map.get(ext, "video/mp4")
    if ext not in mime_map:
        log.warning(f"Unknown video extension {ext}, defaulting to video/mp4")

    # Check file size (20MB)
    file_size = os.path.getsize(video_path)
    final_path = video_path
    is_compressed = False

    if file_size > 20 * 1024 * 1024:
        log.warning(f"Video size {file_size/1024/1024:.2f}MB > 20MB, attempting compression...")
        compressed_path = _compress_video(video_path)
        if compressed_path != video_path:
            final_path = compressed_path
            mime_type = "video/mp4" # ffmpeg output is always mp4
            is_compressed = True
    
    try:
        with open(final_path, "rb") as f:
            raw = f.read()
        b64 = base64.b64encode(raw).decode("utf-8")
    finally:
        # Clean up temporary compressed file
        if is_compressed and os.path.exists(final_path):
            try:
                os.remove(final_path)
                log.info(f"Removed temp compressed video: {final_path}")
            except Exception as e:
                log.warning(f"Failed to remove temp video: {e}")

    return b64, mime_type

async def _post_raw(
    url: str,
    api_key: str,
    payload: dict,
    timeout: int,
) -> dict:
    """Helper for POST request"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    log.info(f"[Video] POST {url}")
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()

async def call_video_understanding_async(
    model: str,
    messages: List[Dict[str, Any]],
    api_url: str,
    api_key: str,
    video_path: str,
    max_tokens: int = 4096,
    temperature: float = 0.2,
    timeout: int = 300, # Video processing might take longer
    **kwargs,
) -> str:
    """
    Calls video understanding model
    """
    b64, mime_type = _encode_video_to_base64(video_path)
    log.info(f"[Video] Encoded video {video_path}, mime={mime_type}, size={len(b64)/1024/1024:.2f}MB")

    # 1. Prepare Messages
    processed_messages = [msg.copy() for msg in messages]
    
    # Inject video into the last user message
    target_msg = None
    for m in reversed(processed_messages):
        if m["role"] == "user":
            target_msg = m
            break
            
    # OpenAI Vision Format / Gemini OpenAI-Compat Format
    video_content = {
        "type": "image_url",
        "image_url": {
            "url": f"data:{mime_type};base64,{b64}"
        },
        "mime_type": mime_type
    }
            
    if target_msg:
        original_content = target_msg["content"]
        if isinstance(original_content, str):
            target_msg["content"] = [
                {"type": "text", "text": original_content},
                video_content
            ]
        elif isinstance(original_content, list):
            target_msg["content"].append(video_content)
    else:
         processed_messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze this video."},
                video_content
            ]
        })

    # 3. Use Provider to construct request
    provider = get_provider(api_url, model)
    url, payload = provider.build_chat_request(
        api_url=api_url,
        model=model,
        messages=processed_messages,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs
    )
    
    # 4. Send request
    data = await _post_raw(url, api_key, payload, timeout)
    
    # 5. Parse response
    return provider.parse_chat_response(data)

if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv

    load_dotenv()
    
    # Creating an empty dummy video file is not easily handled by ffmpeg
    # So video test is only attempted when user provides a valid path, or tries to find one
    def find_any_mp4():
        for root, dirs, files in os.walk("."):
            for f in files:
                if f.endswith(".mp4"):
                    return os.path.join(root, f)
        return None

    async def _test():
        API_URL = os.getenv("DF_API_URL", "http://127.0.0.1:3000/v1")
        API_KEY = os.getenv("DF_API_KEY", "sk-xxx")
        MODEL = os.getenv("DF_IMG_MODEL", "gemini-2.5-flash") # Use a chat/vision model

        print(f"--- Video Understanding Config ---")
        print(f"URL: {API_URL}")
        print(f"Model: {MODEL}")
        print(f"----------------------------------")

        # Try using environment variable specified video, otherwise find
        video_path = os.getenv("TEST_VIDEO_PATH")
        if not video_path:
            video_path = find_any_mp4()
        
        if not video_path or not os.path.exists(video_path):
            print("No video found for testing. Set TEST_VIDEO_PATH env var.")
            return

        print(f"Using video: {video_path}")
        
        try:
            print("[1] Testing Video Understanding...")
            result = await call_video_understanding_async(
                model=MODEL,
                messages=[{"role": "user", "content": "Describe what happens in this video."}],
                api_url=API_URL,
                api_key=API_KEY,
                video_path=video_path
            )
            print(">> Video Result:", result)
        except Exception as e:
            print(f">> Video Failed: {e}")

    asyncio.run(_test())
