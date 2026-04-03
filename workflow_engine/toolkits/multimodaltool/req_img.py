import os
import json
import base64
from typing import Tuple, Optional, List, Union
import httpx
from io import BytesIO
from workflow_engine.utils import get_project_root
from workflow_engine.logger import get_logger
from workflow_engine.toolkits.multimodaltool.utils import (
    Provider, detect_provider, extract_base64, encode_image_to_base64 as _encode_image_to_base64,
    is_gemini_model as _is_gemini_model, is_gemini_25, is_gemini_3_pro
)
from workflow_engine.toolkits.multimodaltool.providers import get_provider

log = get_logger(__name__)

async def _post_stream_and_accumulate(
    url: str,
    api_key: str,
    payload: dict,
    timeout: int,
) -> dict:
    """
    Handles streaming response, accumulates content and returns a non-streaming response structure
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    log.info(f"POST STREAM {url}")
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), http2=False) as client:
        try:
            full_content = []
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                log.info(f"status={response.status_code}")
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if not line or not line.strip():
                        continue
                    
                    if line.startswith("data: "):
                        line = line[6:]  # remove "data: " prefix
                    
                    if line.strip() == "[DONE]":
                        break
                        
                    try:
                        chunk = json.loads(line)
                        # Handle OpenAI compatible stream format choices[0].delta.content
                        if "choices" in chunk and len(chunk["choices"]) > 0:
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_content.append(content)
                    except json.JSONDecodeError:
                        log.warning(f"Failed to decode stream line: {line}")
                        continue
                        
            joined_content = "".join(full_content)
            
            # Construct return structure compatible with non-streaming parsing
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": joined_content
                        }
                    }
                ]
            }
            
        except httpx.HTTPStatusError as e:
            log.error(f"HTTPError {e}")
            await response.aread() # Ensure response body is read for printing
            log.error(f"Response body: {response.text}")
            raise

async def _post_raw(
    url: str,
    api_key: str,
    payload: dict,
    timeout: int,
) -> dict:
    """
    Unified POST, does not prepend path, full URL is passed by caller
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    log.info(f"POST {url}")
    
    # Debug print payload, truncate base64
    try:
        debug_payload = json.loads(json.dumps(payload))
        if "messages" in debug_payload:
            for msg in debug_payload["messages"]:
                if isinstance(msg.get("content"), list):
                    for part in msg["content"]:
                        if part.get("type") == "image_url":
                            url_str = part["image_url"].get("url", "")
                            if len(url_str) > 50:
                                part["image_url"]["url"] = url_str[:20] + "...[base64]..."
        elif "contents" in debug_payload:
             for content in debug_payload["contents"]:
                 for part in content.get("parts", []):
                     if "inline_data" in part:
                         part["inline_data"]["data"] = " ...[base64]... "
                         
        log.info(f"Payload Preview: {json.dumps(debug_payload, ensure_ascii=False)}")
    except Exception:
        pass

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), http2=False) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            log.info(f"status={resp.status_code}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            log.error(f"HTTPError {e}")
            log.error(f"Response body: {e.response.text}")
            raise

def _is_dalle_model(model: str) -> bool:
    """
    Determines if it is a DALL-E series model
    """
    return model.lower().startswith(('dall-e', 'dall-e-2', 'dall-e-3'))

async def call_dalle_image_edit_async(
    api_url: str,
    api_key: str,
    model: str,
    prompt: str,
    image_path: str,
    mask_path: Optional[str] = None,
    size: str = "1024x1024",
    response_format: str = "b64_json",
    timeout: int = 120,
) -> str:
    """
    DALL-E image edit (Retain special logic: Multipart Form Data)
    """
    url = f"{api_url.rstrip('/')}/images/edits"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    files = {}
    data = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "response_format": response_format,
    }

    with open(image_path, "rb") as f:
        files["image"] = (os.path.basename(image_path), f.read(), "image/png")

    if mask_path and os.path.exists(mask_path):
        with open(mask_path, "rb") as f:
            files["mask"] = (os.path.basename(mask_path), f.read(), "image/png")

    log.info(f"POST {url}")
    log.debug(f"data: {data}")

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        try:
            resp = await client.post(url, headers=headers, data=data, files=files)
            log.info(f"status={resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
            
            if response_format == "b64_json":
                return data["data"][0]["b64_json"]
            else:
                image_url = data["data"][0]["url"]
                image_resp = await client.get(image_url)
                image_resp.raise_for_status()
                return base64.b64encode(image_resp.content).decode("utf-8")
                
        except httpx.HTTPStatusError as e:
            log.error(f"HTTPError {e}")
            log.error(f"Response body: {e.response.text}")
            raise

async def gemini_multi_image_edit_async(
    prompt: str,
    image_paths: List[str],
    save_path: str,
    api_url: str,
    api_key: str,
    model: str,
    aspect_ratio: str = "16:9",
    resolution: str = "2K",
    timeout: int = 300,
) -> str:
    """
    Specialized multi-image edit for Gemini
    """
    image_b64_list = []
    for img_path in image_paths:
        if not os.path.exists(img_path):
            raise FileNotFoundError(f"Image not found: {img_path}")
        
        b64, fmt = _encode_image_to_base64(img_path)
        image_b64_list.append((b64, fmt))
        
    # Select strategy based on Provider
    provider = get_provider(api_url, model)
    log.info(f"Multi-Image Edit using Provider: {provider.__class__.__name__}")
    
    url, payload, is_stream = provider.build_multi_image_edit_request(
        api_url=api_url,
        model=model,
        prompt=prompt,
        image_b64_list=image_b64_list,
        aspect_ratio=aspect_ratio,
        resolution=resolution
    )
    
    # Dynamic timeout adjustment (for Gemini-3 Pro)
    if is_gemini_3_pro(model):
        timeout_map = {"1K": 180, "2K": 300, "4K": 360}
        timeout = max(timeout, timeout_map.get(resolution, 300))
        
    log.info(f"[Multi-Image] POST {url} (images={len(image_paths)})")
    
    if is_stream:
        resp_data = await _post_stream_and_accumulate(url, api_key, payload, timeout)
    else:
        resp_data = await _post_raw(url, api_key, payload, timeout)
    
    try:
        b64_res = provider.parse_generation_response(resp_data)
    except Exception as e:
        log.error(f"Failed to parse response: {e}")
        log.error(f"Full response: {resp_data}")
        raise
        
    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(base64.b64decode(b64_res))
        
    log.info(f"Multi-image edit saved to {save_path}")
    return b64_res

# -------------------------------------------------
# 对外主接口
# -------------------------------------------------
async def generate_or_edit_and_save_image_async(
    prompt: str,
    save_path: str,
    api_url: str,
    api_key: str,
    model: str,
    *,
    image_path: Optional[str] = None,
    mask_path: Optional[str] = None,
    use_edit: bool = False,
    size: str = "1024x1024",
    aspect_ratio: str = '16:9',
    resolution: str = "2K",
    quality: str = "standard",
    style: str = "vivid",
    response_format: str = "b64_json",
    timeout: int = 120,
    **kwargs,
) -> str:
    """
    Selects different APIs for image generation/editing based on model type
    After refactoring: use Strategy Pattern to automatically match Provider
    """
    
    # Dynamic timeout adjustment (retain original logic for Gemini-3 Pro)
    if _is_gemini_model(model) and is_gemini_3_pro(model):
        timeout_map = {"1K": 40, "2K": 180, "4K": 350}
        timeout = timeout_map.get(resolution, 180)
    
    log.info(f"generate_or_edit: model={model}, provider_check={detect_provider(api_url)}")

    # Special case processing: DALL-E Edit (Multipart)
    # Currently Provider interface only supports JSON payload, so Multipart still needs separate handling
    if _is_dalle_model(model) and use_edit:
        if not image_path:
            raise ValueError("DALL-E Edit mode must provide image_path")
        b64 = await call_dalle_image_edit_async(
            api_url, api_key, model, prompt, image_path, mask_path, 
            size, response_format, timeout
        )
    else:
        # Universal flow: use Strategy Pattern
        provider = get_provider(api_url, model)
        log.info(f"Selected Provider: {provider.__class__.__name__}")

        if use_edit:
            if not image_path:
                raise ValueError("Edit mode must provide image_path")
            
            # Read and encode image
            b64_input, fmt = _encode_image_to_base64(image_path)
            
            url, payload, is_stream = provider.build_edit_request(
                api_url=api_url,
                model=model,
                prompt=prompt,
                image_b64=b64_input,
                image_fmt=fmt,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                size=size,
                quality=quality,
                style=style,
                response_format=response_format,
                mask_path=mask_path,  # Explicitly pass mask_path
                **kwargs
            )
        else:
            # Text-to-Image
            url, payload, is_stream = provider.build_generation_request(
                api_url=api_url,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                size=size,
                quality=quality,
                style=style,
                response_format=response_format,
                **kwargs
            )

    # Send request
    if payload.get("__is_multipart__"):
        # Handle Multipart upload request (Provider returned special marker)
        log.info(f"POST Multipart {url}")
        
        files = payload.get("files", {})
        data = payload.get("data", {})
        headers = {
            "Authorization": f"Bearer {api_key}",
        }
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            try:
                resp = await client.post(url, headers=headers, data=data, files=files)
                log.info(f"status={resp.status_code}")
                resp.raise_for_status()
                resp_data = resp.json()
            except httpx.HTTPStatusError as e:
                log.error(f"HTTPError {e}")
                log.error(f"Response body: {e.response.text}")
                raise
    elif is_stream:
        resp_data = await _post_stream_and_accumulate(url, api_key, payload, timeout)
    else:
        resp_data = await _post_raw(url, api_key, payload, timeout)

    # Parse response
    # If it is Multipart (usually OpenAI format), also use the same parsing logic
    # Because DALL-E/GPT-Image return structure is usually the same
    b64 = provider.parse_generation_response(resp_data)

    # Save file
    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
    
    # Check if a URL is returned (e.g., GPT-Image-1)
    if b64.startswith("http"):
        log.info(f"Received URL, downloading image: {b64}")
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            resp = await client.get(b64)
            resp.raise_for_status()
            with open(save_path, "wb") as f:
                f.write(resp.content)
            # Also update b64 variable with actual base64 content to maintain consistency of return value
            b64 = base64.b64encode(resp.content).decode("utf-8")
    else:
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(b64))

    log.info(f"Image saved to {save_path}")
    return b64

if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    from PIL import Image

    load_dotenv()

    # --- Helper function: Create test image ---
    def create_dummy_image(path: str, color='blue', size=(256, 256)):
        if not os.path.exists(path):
            img = Image.new('RGB', size, color=color)
            img.save(path)
            print(f"Created dummy image: {path}")
        return path

    async def _test():
        API_URL = os.getenv("DF_API_URL", "http://127.0.0.1:3000/v1")
        API_KEY = os.getenv("DF_API_KEY", "sk-xxx")
        # Change test model to the recommended gpt-image-1 as per documentation
        MODEL = os.getenv("DF_IMG_MODEL", "gpt-image-1") 

        print(f"--- Config ---")
        print(f"URL: {API_URL}")
        print(f"Model: {MODEL}")
        print(f"----------------")

        # 1. Test Text-to-Image
        print("\n[1] Testing Text-to-Image Generation...")
        
        # Special handling for SeeDream models
        gen_kwargs = {
            "prompt": "A futuristic cityscape with neon lights, cyberpunk style",
            "save_path": "./test_gen_result.png",
            "api_url": API_URL,
            "api_key": API_KEY,
            "model": MODEL,
            "use_edit": False,
            "aspect_ratio": "16:9",
            "resolution": "4K"
        }
        
        if "seedream" in MODEL.lower():
            gen_kwargs["size"] = "2048x2048"
            
        try:
            await generate_or_edit_and_save_image_async(**gen_kwargs)
            print(">> Generation Success: ./test_gen_result.png")
        except Exception as e:
            print(f">> Generation Failed: {e}")

        # 2. Test Image-to-Image (Edit)
        print("\n[2] Testing Image Editing...")
        dummy_input = f"{get_project_root()}/tests/test_02.png"
        try:
            await generate_or_edit_and_save_image_async(
                prompt="Make it red",
                save_path="./test_edit_result.png",
                api_url=API_URL,
                api_key=API_KEY,
                model=MODEL,
                use_edit=True,
                image_path=dummy_input
            )
            print(">> Edit Success: ./test_edit_result.png")
        except Exception as e:
            print(f">> Edit Failed: {e}")

        # 3. Test Multi-Image Edit (Gemini Specific)
        # Test only when model is gemini
        if "gemini" in MODEL.lower():
            print("\n[3] Testing Multi-Image Edit (Gemini Specific)...")
            img1 = f"{get_project_root()}/tests/test_02.png"
            img2 = f"{get_project_root()}/tests/cat_icon.png"
            try:
                await gemini_multi_image_edit_async(
                    prompt="Merge these two images and describe the result style",
                    image_paths=[img1, img2],
                    save_path="./test_multi_result.png",
                    api_url=API_URL,
                    api_key=API_KEY,
                    model=MODEL
                )
                print(">> Multi-Image Success: ./test_multi_result.png")
            except Exception as e:
                print(f">> Multi-Image Failed: {e}")
        else:
            print("\n[3] Skipping Multi-Image Edit (Not a Gemini model)")

    asyncio.run(_test())
