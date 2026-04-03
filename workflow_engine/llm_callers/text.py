from typing import List
from langchain_core.messages import BaseMessage,AIMessage
from langchain_openai import ChatOpenAI

from .base import BaseLLMCaller
from workflow_engine.logger import get_logger

log = get_logger(__name__)

class TextLLMCaller(BaseLLMCaller):
    """Text LLM Caller - Original implementation"""
    
    async def call(self, messages: List[BaseMessage], bind_post_tools: bool = False) -> AIMessage:
        log.info(f"TextLLM call, model: {self.model_name}")
        
        llm = ChatOpenAI(
            openai_api_base=self.state.request.chat_api_url,
            openai_api_key=self.state.request.api_key,
            model_name=self.model_name,
            temperature=self.temperature,
            # max_tokens=self.max_tokens,
        )
        
        # Bind tools (if needed)
        if bind_post_tools and self.tool_manager:
            from langchain_core.tools import Tool
            tools = self.tool_manager.get_post_tools("current_role")  # Need to pass role name
            if tools:
                llm = llm.bind_tools(tools, tool_choice=self.tool_mode)
                log.info(f"Bound {len(tools)} tools to LLM")
        
        response = await llm.ainvoke(messages)
        return response