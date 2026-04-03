import base64
from typing import Any, Dict, List, Optional
from workflow_engine.state import MainState
from langchain_core.messages import AIMessage, BaseMessage

from workflow_engine.llm_callers.base import BaseLLMCaller
from workflow_engine.logger import get_logger

# Import new tools
from workflow_engine.toolkits.multimodaltool.req_ocr import call_ocr_async
from workflow_engine.toolkits.multimodaltool.req_understanding import call_image_understanding_async
from workflow_engine.toolkits.multimodaltool.req_videos import call_video_understanding_async
from workflow_engine.toolkits.multimodaltool.req_img import generate_or_edit_and_save_image_async

log = get_logger(__name__)

class VisionLLMCaller(BaseLLMCaller):
    """
    Vision LLM Caller - Unified Entry
    Supported modes:
    1. understanding       (General image understanding)
    2. generation / edit   (Image generation/editing)
    3. video_understanding (Video understanding)
    4. ocr                 (OCR specialized)
    """
    
    def __init__(self, 
                 state: MainState,
                 vlm_config: Dict[str, Any],
                 **kwargs):
        """
        Args:
            vlm_config: VLM configuration, including:
                - mode: "generation" | "edit" | "understanding" | "video_understanding" | "ocr"
                - input_image: Input image path
                - input_video: Input video path (video_understanding mode)
                - output_image: Output image save path (generation/edit mode)
                - response_format: "image" | "text" (default automatically determined by mode)
        """
        super().__init__(state, **kwargs)
        self.vlm_config = vlm_config
        self.mode       = vlm_config.get("mode", "understanding")
        self.temperature = kwargs.get("temperature", 0.1)
        self.max_tokens = kwargs.get("max_tokens", 4096)
    
    async def call(self, messages: List[BaseMessage], bind_post_tools: bool = False) -> AIMessage:
        """Calls VLM"""
        log.info(f"VisionLLM call, model: {self.model_name}, mode: {self.mode}")
        
        # 1. Image generation/editing
        if self.mode in ["generation", "edit"]:
            return await self._call_image_output(messages)
            
        # 2. Video understanding
        elif self.mode == "video_understanding":
             return await self._call_video_understanding(messages)
             
        # 3. OCR (Explicit mode or implicit detection)
        elif self.mode == "ocr" or ("qwen-vl-ocr" in self.model_name.lower() and "apiyi" in self.state.request.chat_api_url):
             return await self._call_ocr(messages)
             
        # 4. General image understanding (Default)
        else:
            return await self._call_image_understanding(messages)
        
    async def _call_ocr(self, messages: List[BaseMessage]) -> AIMessage:
        """Calls OCR module"""
        # Convert LangChain messages to list[dict]
        msgs = self._convert_messages(messages)
        image_path = self.vlm_config.get("input_image")
        
        content = await call_ocr_async(
            model=self.model_name,
            messages=msgs,
            api_url=self.state.request.chat_api_url,
            api_key=self.state.request.api_key,
            image_path=image_path,
            max_tokens=self.max_tokens,
            temperature=0.01, # OCR usually needs low temp
            timeout=self.vlm_config.get("timeout", 120)
        )
        return AIMessage(content=content)

    async def _call_video_understanding(self, messages: List[BaseMessage]) -> AIMessage:
        """Calls video understanding module"""
        msgs = self._convert_messages(messages)
        # Supports input_video or input_image (compatibility)
        video_path = self.vlm_config.get("input_video") or self.vlm_config.get("input_image")
        
        if not video_path:
            raise ValueError("video_understanding mode requires 'input_video' in vlm_config")

        content = await call_video_understanding_async(
            model=self.model_name,
            messages=msgs,
            api_url=self.state.request.chat_api_url,
            api_key=self.state.request.api_key,
            video_path=video_path,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            timeout=self.vlm_config.get("timeout", 300)
        )
        return AIMessage(content=content)

    async def _call_image_understanding(self, messages: List[BaseMessage]) -> AIMessage:
        """Calls general image understanding module"""
        msgs = self._convert_messages(messages)
        image_path = self.vlm_config.get("input_image")
        
        content = await call_image_understanding_async(
            model=self.model_name,
            messages=msgs,
            api_url=self.state.request.chat_api_url,
            api_key=self.state.request.api_key,
            image_path=image_path,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            timeout=self.vlm_config.get("timeout", 120)
        )
        return AIMessage(content=content)
    
    async def _call_image_output(self, messages: List[BaseMessage]) -> AIMessage:
        """Image generation/editing mode - Output image"""
        # Extract prompt (last user message)
        prompt = ""
        for msg in reversed(messages):
            if hasattr(msg, 'content'):
                prompt = msg.content
                break
        
        # Call image generation function
        save_path = self.vlm_config.get("output_image", "./generated_image.png")
        image_path = self.vlm_config.get("input_image") if self.mode == "edit" else None
        aspect_ratio = self.vlm_config.get("aspect_ratio", "16:9")
        
        b64 = await generate_or_edit_and_save_image_async(
            prompt=prompt,
            save_path=save_path,
            api_url=self.state.request.chat_api_url,
            api_key=self.state.request.api_key,
            model=self.model_name,
            image_path=image_path,
            use_edit=(self.mode == "edit"),
            timeout=self.vlm_config.get("timeout", 120),
            aspect_ratio = aspect_ratio 
        )
        
        content = f"Image generated and saved to: {save_path}"
        return AIMessage(content=content, additional_kwargs={
            "image_path": save_path,
            "image_base64": b64,
        })

    def _convert_messages(self, messages: List[BaseMessage]) -> List[Dict[str, Any]]:
        """Helper: Convert LangChain messages to dict format"""
        processed_messages = []
        for msg in messages:
            role = "user"
            if hasattr(msg, "type"):
                if msg.type == "human": role = "user"
                elif msg.type == "ai": role = "assistant"
                elif msg.type == "system": role = "system"
                elif msg.type == "tool": role = "tool"
            
            processed_messages.append({"role": role, "content": msg.content})
        return processed_messages

# ======================================================================
# Quick Self-Test
# ======================================================================
if __name__ == "__main__":
    import os
    import sys
    import asyncio
    from types import SimpleNamespace
    from pathlib import Path
    from langchain_core.messages import HumanMessage

    async def _quick_test(img_path: str):
        api_url = os.getenv("DF_API_URL")
        api_key = os.getenv("DF_API_KEY")
        if not api_url or not api_key:
            print("❌  Please set environment variables DF_API_URL / DF_API_KEY first")
            sys.exit(1)

        img_path = Path(img_path).expanduser().resolve()
        if not img_path.exists():
            print(f"❌  Image does not exist: {img_path}")
            sys.exit(1)

        request = SimpleNamespace(chat_api_url=api_url.rstrip("/"), api_key=api_key, model="gemini-2.5-flash-image-preview")
        state = SimpleNamespace(request=request)

        # 1. Test Understanding
        print("\n[TEST] Understanding Mode...")
        caller_und = VisionLLMCaller(
            state=state,
            vlm_config={"mode": "understanding", "input_image": str(img_path)}
        )
        res = await caller_und.call([HumanMessage(content="Describe this image in 10 words.")])
        print(f"Understanding Result: {res.content}")

        # 2. Test Generation (Requires prompt, ignores input image usually, but config needs to be valid)
        # Note: Generation writes to file, we skip if we don't want side effects or provide a test path
        
    if len(sys.argv) >= 2:
        asyncio.run(_quick_test(sys.argv[1]))
