import json
from abc import ABC, abstractmethod
from typing import Tuple, Optional, Any, Dict, List
from workflow_engine.toolkits.multimodaltool.utils import (
    Provider, detect_provider, extract_base64, 
    is_gemini_model, is_gemini_25, is_gemini_3_pro
)
from workflow_engine.logger import get_logger

log = get_logger(__name__)

class AIProviderStrategy(ABC):
    """
    Common AI Provider Strategy Base Class
    Supports:
    1. Image Generation (Generation)
    2. Multimodal Understanding (Chat/Vision/Video/OCR)
    """
    
    @abstractmethod
    def match(self, api_url: str, model: str) -> bool:
        """Determines if the current strategy is applicable"""
        pass
        
    # --- Generation Interface ---
    
    @abstractmethod
    def build_generation_request(
        self, 
        api_url: str, 
        model: str, 
        prompt: str, 
        **kwargs
    ) -> Tuple[str, Dict[str, Any], bool]:
        """
        Constructs a text-to-image request
        Returns: (url, payload, is_stream)
        """
        pass

    def build_edit_request(
        self, 
        api_url: str, 
        model: str, 
        prompt: str, 
        image_b64: str, 
        **kwargs
    ) -> Tuple[str, Dict[str, Any], bool]:
        """
        Constructs an image-to-image/edit request
        Returns: (url, payload, is_stream)
        
        Note: If the returned payload contains "__is_multipart__": True,
        then payload should contain "files" and "data" fields for use in multipart/form-data upload.
        """
        raise NotImplementedError("Edit not supported by this provider")

    def build_multi_image_edit_request(
        self,
        api_url: str,
        model: str,
        prompt: str,
        image_b64_list: List[Tuple[str, str]],
        **kwargs
    ) -> Tuple[str, Dict[str, Any], bool]:
        """
        Constructs a multi-image edit request
        Returns: (url, payload, is_stream)
        """
        raise NotImplementedError("Multi-image edit not supported by this provider")
        
    @abstractmethod
    def parse_generation_response(self, response_data: Dict[str, Any]) -> str:
        """
        Parses the generation response and returns the image Base64 string
        """
        pass

    # --- TTS Interface ---

    def build_tts_request(self, api_url: str, model: str, text: str, **kwargs) -> Tuple[str, Dict[str, Any], bool]:
        """
        Constructs a TTS request
        Returns: (url, payload, is_stream)
        """
        raise NotImplementedError("TTS not supported by this provider")
    
    def parse_tts_response(self, response_data: Dict[str, Any]) -> bytes:
        """
        Parses the TTS response and returns the audio binary data
        """
        raise NotImplementedError("TTS not supported by this provider")

    # --- Understanding / Chat Interface ---

    def build_chat_request(
        self,
        api_url: str,
        model: str,
        messages: List[Dict[str, Any]],
        **kwargs
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Constructs a chat/understanding request (OCR, Image Understanding, Video Understanding)
        Returns: (url, payload)
        
        Default implementation: OpenAI Standard Format
        """
        url = f"{api_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.1),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        return url, payload

    def parse_chat_response(self, response_data: Dict[str, Any]) -> str:
        """
        Parses the chat/understanding response and returns the text content
        
        Default implementation: OpenAI Standard Format
        """
        if "choices" in response_data and len(response_data["choices"]) > 0:
            return response_data["choices"][0]["message"]["content"]
        if "error" in response_data:
             raise RuntimeError(f"API Error: {response_data['error']}")
        raise RuntimeError(f"Unknown API response format: {str(response_data)[:200]}")


class ApiYiGeminiProvider(AIProviderStrategy):
    """
    Special handling for Gemini models by APIYI provider
    """
    def match(self, api_url: str, model: str) -> bool:
        return detect_provider(api_url) is Provider.APIYI and is_gemini_model(model)

    def _get_base_url(self, api_url: str) -> str:
        base = api_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        return base

    # --- Generation ---

    def build_generation_request(self, api_url: str, model: str, prompt: str, **kwargs) -> Tuple[str, Dict[str, Any], bool]:
        base = self._get_base_url(api_url)
        aspect_ratio = kwargs.get("aspect_ratio", "16:9")
        resolution = kwargs.get("resolution", "2K")

        if is_gemini_25(model):
            url = f"{base}/v1beta/models/gemini-2.5-flash-image:generateContent"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseModalities": ["IMAGE"],
                    "imageConfig": {"aspectRatio": aspect_ratio},
                },
            }
            return url, payload, False

        if is_gemini_3_pro(model):
            url = f"{base}/v1beta/models/gemini-3-pro-image-preview:generateContent"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseModalities": ["IMAGE"],
                    "imageConfig": {
                        "aspectRatio": aspect_ratio,
                        "imageSize": resolution,
                    },
                },
            }
            return url, payload, False
        
        raise ValueError(f"Unsupported Gemini model for APIYI Generation: {model}")

    def build_edit_request(self, api_url: str, model: str, prompt: str, image_b64: str, **kwargs) -> Tuple[str, Dict[str, Any], bool]:
        base = self._get_base_url(api_url)
        aspect_ratio = kwargs.get("aspect_ratio", "1:1")
        resolution = kwargs.get("resolution", "2K")
        fmt = kwargs.get("image_fmt", "png")

        if is_gemini_25(model) and aspect_ratio != "1:1":
             url = f"{base}/v1beta/models/gemini-2.5-flash-image:generateContent"
             payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": f"image/{fmt}", "data": image_b64}}
                        ]
                    }
                ],
                "generationConfig": {
                    "responseModalities": ["IMAGE"],
                    "imageConfig": {"aspectRatio": aspect_ratio},
                },
            }
             return url, payload, False

        if is_gemini_3_pro(model):
            url = f"{base}/v1beta/models/gemini-3-pro-image-preview:generateContent"
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": f"image/{fmt}", "data": image_b64}}
                        ]
                    }
                ],
                "generationConfig": {
                    "responseModalities": ["IMAGE"],
                    "imageConfig": {
                        "aspectRatio": aspect_ratio,
                        "imageSize": resolution,
                    },
                },
            }
            return url, payload, False
            
        raise ValueError(f"Unsupported Gemini Edit combination for APIYI: {model}")

    def build_multi_image_edit_request(
        self,
        api_url: str,
        model: str,
        prompt: str,
        image_b64_list: List[Tuple[str, str]],
        **kwargs
    ) -> Tuple[str, Dict[str, Any], bool]:
        base = self._get_base_url(api_url)
        aspect_ratio = kwargs.get("aspect_ratio", "16:9")
        resolution = kwargs.get("resolution", "2K")

        parts = [{"text": prompt}]
        for b64, fmt in image_b64_list:
            parts.append({
                "inline_data": {
                    "mime_type": f"image/{fmt}",
                    "data": b64
                }
            })

        url = f"{base}/v1beta/models/{model}:generateContent"
        
        image_config = {"aspectRatio": aspect_ratio}
        if is_gemini_3_pro(model):
            image_config["imageSize"] = resolution
            
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": image_config
            }
        }
        return url, payload, False

    def parse_generation_response(self, data: Dict[str, Any]) -> str:
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("candidates is empty")
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            inline_data = parts[0].get("inlineData", {})
            return inline_data.get("data")
        except Exception as e:
            log.error(f"Failed to parse APIYI Gemini response: {e}")
            log.error(f"Response preview: {str(data)[:500]}")
            raise

    def build_tts_request(self, api_url: str, model: str, text: str, **kwargs) -> Tuple[str, Dict[str, Any], bool]:
        base = self._get_base_url(api_url)
        url = f"{base}/v1beta/models/{model}:generateContent"
        
        voice_name = kwargs.get("voice_name", "Kore")
        
        payload = {
            "contents": [{
                "parts": [{"text": text}]
            }],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice_name
                        }
                    }
                }
            }
        }
        return url, payload, False

    def parse_tts_response(self, data: Dict[str, Any]) -> bytes:
        if "error" in data:
            raise RuntimeError(f"API Error: {data['error']}")
            
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"No candidates in response: {str(data)[:200]}")
            
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            raise RuntimeError("No parts in content")
            
        inline_data = parts[0].get("inlineData", {})
        b64 = inline_data.get("data")
        
        if not b64:
             raise RuntimeError("No inlineData.data found")
             
        import base64
        return base64.b64decode(b64)


class Local123GeminiProvider(AIProviderStrategy):
    """
    Special handling for Gemini models by Local 123 provider
    """
    def match(self, api_url: str, model: str) -> bool:
        return detect_provider(api_url) is Provider.LOCAL_123 and is_gemini_model(model)

    def build_generation_request(self, api_url: str, model: str, prompt: str, **kwargs) -> Tuple[str, Dict[str, Any], bool]:
        base = api_url.rstrip("/")
        aspect_ratio = kwargs.get("aspect_ratio", "")
        resolution = kwargs.get("resolution", "2K")

        # Logic from original req_img.py
        if aspect_ratio:
            prompt = f"{prompt} Generation ratio: {aspect_ratio}, 4K resolution"

        url = f"{base}/chat/completions"
        payload = {
            "model": model,
            "group": "default",
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "temperature": 0.7,
            "top_p": 1,
            "frequency_penalty": 0,
            "presence_penalty": 0,
            "generationConfig": {
                "imageConfig": {
                    "aspect_ratio": aspect_ratio,
                    "image_size": resolution
                }
            }
        }
        return url, payload, True

    def build_edit_request(self, api_url: str, model: str, prompt: str, image_b64: str, **kwargs) -> Tuple[str, Dict[str, Any], bool]:
        base = api_url.rstrip("/")
        aspect_ratio = kwargs.get("aspect_ratio", "1:1")
        resolution = kwargs.get("resolution", "2K")
        fmt = kwargs.get("image_fmt", "png")

        if is_gemini_3_pro(model):
            url = f"{base}/chat/completions"
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{fmt};base64,{image_b64}",
                            },
                        },
                    ],
                }
            ]
            payload = {
                "model": model,
                "messages": messages,
                "stream": True,
                "temperature": 0.7,
                "generationConfig": {
                    "imageConfig": {
                        "aspect_ratio": aspect_ratio, 
                        "image_size": resolution
                    }
                }
            }
            return url, payload, True

        if is_gemini_25(model):
            url = f"{base}/chat/completions"
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": f"image/{fmt}", "data": image_b64}},
                        ],
                    }
                ],
                "generationConfig": {
                    "width": 1920,
                    "height": 1080,
                    "quality": "high",
                },
            }
            return url, payload, False

        raise ValueError(f"Unsupported Gemini Edit model for Local123: {model}")

    def build_multi_image_edit_request(
        self,
        api_url: str,
        model: str,
        prompt: str,
        image_b64_list: List[Tuple[str, str]],
        **kwargs
    ) -> Tuple[str, Dict[str, Any], bool]:
        base = api_url.rstrip("/")
        aspect_ratio = kwargs.get("aspect_ratio", "16:9")
        resolution = kwargs.get("resolution", "2K")
        
        content_parts = [{"type": "text", "text": prompt}]
        for b64, fmt in image_b64_list:
            content_parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{fmt};base64,{b64}"
                }
            })

        url = f"{base}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": content_parts
                }
            ],
            "stream": True,
            "temperature": 0.7,
            "generationConfig": {
                "imageConfig": {
                    "aspect_ratio": aspect_ratio, 
                    "image_size": resolution
                }
            }
        }
        return url, payload, True

    def parse_generation_response(self, data: Dict[str, Any]) -> str:
        # Local 123 returns OpenAI-like format
        if "choices" in data:
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, str):
                b64 = extract_base64(content)
            elif isinstance(content, list):
                joined = " ".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
                b64 = extract_base64(joined)
            else:
                raise RuntimeError(f"Unsupported content type: {type(content)}")
            
            if not b64:
                raise RuntimeError("Failed to extract base64 from Local123 response")
            return b64
        raise RuntimeError("Unknown Local123 response structure")


class ApiYiSeeDreamProvider(AIProviderStrategy):
    """
    APIYI SeeDream series model support (Compatible with OpenAI Image API)
    """
    def match(self, api_url: str, model: str) -> bool:
        return model.lower().startswith("seedream")

    def build_generation_request(self, api_url: str, model: str, prompt: str, **kwargs) -> Tuple[str, Dict[str, Any], bool]:
        url = f"{api_url.rstrip('/')}/images/generations"
        
        size = kwargs.get("size", "2048x2048")
        quality = kwargs.get("quality", "standard")
        response_format = kwargs.get("response_format", "b64_json")
        
        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "quality": quality,
            "response_format": response_format,
        }
        
        # Merge extra parameters (e.g., output_format)
        for k, v in kwargs.items():
            if k not in payload and k not in ["api_key", "timeout"]:
                payload[k] = v
                
        return url, payload, False

    def parse_generation_response(self, data: Dict[str, Any]) -> str:
        if "data" in data and len(data["data"]) > 0:
            item = data["data"][0]
            if "b64_json" in item:
                return item["b64_json"]
            if "url" in item:
                return item["url"]
        raise RuntimeError(f"Failed to parse SeeDream response: {str(data)[:200]}")


class ApiYiGPTImageProvider(AIProviderStrategy):
    """
    APIYI GPT-Image series model support (Compatible with OpenAI Image API)
    """
    def match(self, api_url: str, model: str) -> bool:
        return model.lower().startswith("gpt-image")

    def build_generation_request(self, api_url: str, model: str, prompt: str, **kwargs) -> Tuple[str, Dict[str, Any], bool]:
        url = f"{api_url.rstrip('/')}/images/generations"
        
        size = kwargs.get("size", "1024x1024")
        # Map quality parameter: DALL-E's standard/hd -> GPT-Image's low/medium/high/auto
        quality = kwargs.get("quality", "auto")
        if quality == "standard":
            quality = "medium"
        elif quality == "hd":
            quality = "high"
            
        payload = {
            "model": model,
            "prompt": prompt,
            "n": kwargs.get("n", 1),
            "size": size,
            "quality": quality,
        }
        
        # Whitelist filtering: only pass parameters supported by GPT-Image documentation
        # Remove unsupported parameters like style, aspect_ratio, resolution, etc.
        # Remove response_format (API reported as unsupported)
        supported_params = [
            "output_format", 
            "output_compression", 
            "background", 
            "user"
        ]
        
        for k in supported_params:
            if k in kwargs:
                payload[k] = kwargs[k]
                
        return url, payload, False

    def build_edit_request(
        self, 
        api_url: str, 
        model: str, 
        prompt: str, 
        image_b64: str, 
        **kwargs
    ) -> Tuple[str, Dict[str, Any], bool]:
        """
        Constructs an image editing request for APIYI GPT-Image series models (Multipart format)
        
        Parameters:
            api_url (str): API base address
            model (str): Model name (e.g., gpt-image-1)
            prompt (str): Text prompt describing the desired editing effect
            image_b64 (str): Base64 encoded string of the original image
            **kwargs: Other optional parameters
                - mask_path (str): File path to mask image (if present)
                - n (int): Number of images to generate, default is 1
                - size (str): Output image size (e.g., 1024x1024)
                - response_format (str): Return format (url or b64_json), note GPT-Image-1 might not support this
                - user (str): User identifier
        
        Returns:
            Tuple[str, Dict[str, Any], bool]: (Request URL, Request Payload, Is Stream)
            
        Note:
            The returned payload contains a special marker "__is_multipart__": True.
            "files": Contains 'image' and optional 'mask' file data (bytes).
            "data": Contains other form fields (prompt, n, size, etc.).
        """
        import base64
        import os
        
        url = f"{api_url.rstrip('/')}/images/edits"
        
        # 1. Decode image Base64 to binary
        image_bytes = base64.b64decode(image_b64)
        
        files = {
            "image": ("image.png", image_bytes, "image/png")
        }
        
        # 2. Handle mask image
        mask_path = kwargs.get("mask_path")
        if mask_path and os.path.exists(mask_path):
            with open(mask_path, "rb") as f:
                mask_bytes = f.read()
            files["mask"] = (os.path.basename(mask_path), mask_bytes, "image/png")
            
        # 3. Construct form data
        data = {
            "model": model,
            "prompt": prompt,
            "n": kwargs.get("n", 1),
            "size": kwargs.get("size", "1024x1024"),
        }
        
        # Add optional parameters (Whitelist filtering)
        supported_params = ["response_format", "user"] # Standard Edit API usually supports response_format, kept just in case or for later testing
        # If GPT-Image Edit similarly doesn't support response_format, it should be removed later.
        # For safety, mirroring Generation, we temporarily exclude response_format unless documentation explicitly states Edit support.
        # Documentation indeed mentioned response_format in the Edit API.
        # But given Generation failed, we try without it first, or only pass when explicitly in kwargs.
        
        if "user" in kwargs:
            data["user"] = kwargs["user"]
            
        # Construct special return payload
        payload = {
            "__is_multipart__": True,
            "files": files,
            "data": data
        }
        
        return url, payload, False

    def parse_generation_response(self, data: Dict[str, Any]) -> str:
        if "data" in data and len(data["data"]) > 0:
            item = data["data"][0]
            if "b64_json" in item:
                return item["b64_json"]
            if "url" in item:
                return item["url"]
        raise RuntimeError(f"Failed to parse GPT-Image response: {str(data)[:200]}")


class OpenAIDalleProvider(AIProviderStrategy):
    """
    OpenAI DALL-E series (images/generations)
    Note: DALL-E only supports generation, not understanding/Chat
    """
    def match(self, api_url: str, model: str) -> bool:
        return model.lower().startswith(('dall-e', 'dall-e-2', 'dall-e-3'))

    def build_generation_request(self, api_url: str, model: str, prompt: str, **kwargs) -> Tuple[str, Dict[str, Any], bool]:
        url = f"{api_url.rstrip('/')}/images/generations"
        
        size = kwargs.get("size", "1024x1024")
        quality = kwargs.get("quality", "standard")
        style = kwargs.get("style", "vivid")
        response_format = kwargs.get("response_format", "b64_json")
        
        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "response_format": response_format,
        }
        
        if model.lower() == "dall-e-3":
            payload["quality"] = quality
            payload["style"] = style
            
        return url, payload, False

    def parse_generation_response(self, data: Dict[str, Any]) -> str:
        if "data" in data and len(data["data"]) > 0:
            if "b64_json" in data["data"][0]:
                return data["data"][0]["b64_json"]
        raise RuntimeError("Failed to parse DALL-E response")


class OpenAICompatGeminiProvider(AIProviderStrategy):
    """
    Common OpenAI compatible format
    Generation: chat/completions (image response)
    Understanding: chat/completions (text response)
    """
    def match(self, api_url: str, model: str) -> bool:
        # Always True as fallback if no others match
        return True

    def build_generation_request(self, api_url: str, model: str, prompt: str, **kwargs) -> Tuple[str, Dict[str, Any], bool]:
        url = f"{api_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "image"},
            "max_tokens": 1024,
            "temperature": 0.7,
        }
        return url, payload, False

    def build_edit_request(self, api_url: str, model: str, prompt: str, image_b64: str, **kwargs) -> Tuple[str, Dict[str, Any], bool]:
        url = f"{api_url.rstrip('/')}/chat/completions"
        fmt = kwargs.get("image_fmt", "png")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{fmt};base64,{image_b64}",
                        },
                    },
                ],
            }
        ]
        payload = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "image"},
            "max_tokens": 1024,
            "temperature": 0.7,
        }
        return url, payload, False

    def build_multi_image_edit_request(
        self,
        api_url: str,
        model: str,
        prompt: str,
        image_b64_list: List[Tuple[str, str]],
        **kwargs
    ) -> Tuple[str, Dict[str, Any], bool]:
        base = api_url.rstrip("/")
        
        content_parts = [{"type": "text", "text": prompt}]
        for b64, fmt in image_b64_list:
            content_parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{fmt};base64,{b64}"
                }
            })
            
        url = f"{base}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": content_parts
                }
            ],
            "response_format": {"type": "image"},
            "max_tokens": 1024,
            "temperature": 0.7,
        }
        return url, payload, False

    def parse_generation_response(self, data: Dict[str, Any]) -> str:
        if "choices" in data:
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, str):
                b64 = extract_base64(content)
            elif isinstance(content, list):
                joined = " ".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
                b64 = extract_base64(joined)
            else:
                raise RuntimeError(f"Unsupported content type: {type(content)}")
            
            if not b64:
                raise RuntimeError("Failed to extract base64 from OpenAI-compat response")
            return b64
        raise RuntimeError("Unknown OpenAI-compat response structure")


class GoogleNativeProvider(AIProviderStrategy):
    """
    Google Official Gemini API 
    """
    def match(self, api_url: str, model: str) -> bool:
        return "googleapis.com" in api_url and is_gemini_model(model)

    def build_generation_request(self, api_url: str, model: str, prompt: str, **kwargs) -> Tuple[str, Dict[str, Any], bool]:
        base = api_url.rstrip("/")
        if "v1" not in base and "v1beta" not in base:
            base = f"{base}/v1beta"
        url = f"{base}/models/{model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        return url, payload, False

    def parse_generation_response(self, data: Dict[str, Any]) -> str:
        candidates = data.get("candidates", [])
        if candidates:
            return candidates[0]["content"]["parts"][0]["inlineData"]["data"]
        raise RuntimeError("No candidates in Google response")

    # Native Chat Implementation can also be added here (e.g., converting messages to contents)


# Strategy registration order
STRATEGIES = [
    ApiYiGeminiProvider(),
    ApiYiSeeDreamProvider(),
    ApiYiGPTImageProvider(),
    Local123GeminiProvider(),
    OpenAIDalleProvider(),
    # Add GoogleNativeProvider() here if needed
    OpenAICompatGeminiProvider(), # Default Fallback
]

def get_provider(api_url: str, model: str) -> AIProviderStrategy:
    for strategy in STRATEGIES:
        if strategy.match(api_url, model):
            return strategy
    return OpenAICompatGeminiProvider()
