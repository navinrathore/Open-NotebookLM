"""
BaseAgent Module - Core Base Class for the Agent System

This module defines the BaseAgent abstract base class, which is the foundation for all Agent roles.
BaseAgent provides a unified execution mode, tool management, message construction, and result parsing.

Main Features:
- Multiple Execution Modes: Simple, ReAct, Parallel, Graph
- Tool Management: Execution of pre-tools and post-tools
- Message Construction: Generation of system prompts and task prompts
- Result Parsing: Support for JSON, XML, text, and other formats
- Agent-as-Tool: Wrapping an Agent as a tool to be called by other Agents
- VLM Support: Integration of Vision Language Models

Example Usage:
    class MyAgent(BaseAgent):
        @property
        def role_name(self) -> str:
            return "MyAgent"
        
        @property
        def system_prompt_template_name(self) -> str:
            return "my_agent_system"
        
        @property
        def task_prompt_template_name(self) -> str:
            return "my_agent_task"

Author: Zhou Liu
Version: 1.0.0
"""

from __future__ import annotations

# =============================================================================
# Standard Library Imports
# =============================================================================
import asyncio
import datetime
import pickle
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Callable, Tuple

# =============================================================================
# Third-party Library Imports
# =============================================================================
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage
from langchain_core.tools import Tool
from pydantic import BaseModel, Field

# =============================================================================
# Internal Project Imports
# =============================================================================
from workflow_engine.llm_callers.base import BaseLLMCaller
from workflow_engine.parsers.parsers import BaseParser
from workflow_engine.graphbuilder.message_history import AdvancedMessageHistory
from workflow_engine.promptstemplates.prompt_template import PromptsTemplateGenerator
from workflow_engine.state import MainState
from workflow_engine.utils import robust_parse_json, get_project_root
from workflow_engine.toolkits.tool_manager import ToolManager
from workflow_engine.logger import get_logger
from workflow_engine.agentroles.cores.strategies import ExecutionStrategy

# =============================================================================
# Constants Definition
# =============================================================================
PROJDIR = get_project_root()
"""Project root directory path"""

log = get_logger(__name__)
"""Module log recorder"""

# =============================================================================
# Type Definitions
# =============================================================================
ValidatorFunc = Callable[[str, Dict[str, Any]], Tuple[bool, Optional[str]]]
"""
Validator function type definition

Used in ReAct mode to validate the correctness of LLM output.

Parameters:
    content (str): LLM raw output content
    parsed_result (Dict[str, Any]): Parsed result dictionary

Returns:
    Tuple[bool, Optional[str]]: (Validation passed, error message)
        - If passed, returns (True, None)
        - If failed, returns (False, "Error description")
"""


class BaseAgent(ABC):
    """
    BaseAgent Class - Defines general Agent execution modes
    
    BaseAgent is the abstract base class for all Agent roles, providing full lifecycle management,
    including initialization, message construction, LLM calling, result parsing, and state updates.
    
    Core Features:
        1. Auto-registration: Subclasses are automatically registered to AgentRegistry
        2. Multiple execution modes: Supports Simple, ReAct, Parallel, Graph, etc.
        3. Tool integration: Supports management and execution of pre-tools and post-tools
        4. Flexible parsing: Supports JSON, XML, text, and other format parsing
        5. VLM support: Integrated Vision Language Model capabilities
        6. Agent-as-Tool: Can wrap an Agent as a tool for others to call
    
    Abstract properties that subclasses must implement:
        - role_name: Agent role name
        - system_prompt_template_name: System prompt template name
        - task_prompt_template_name: Task prompt template name
    
    Attributes:
        tool_manager (ToolManager): Tool manager instance
        model_name (str): LLM model name
        temperature (float): LLM temperature parameter
        max_tokens (int): Maximum token count
        tool_mode (str): Tool call mode
        react_mode (bool): Whether to enable ReAct mode
        react_max_retries (int): Maximum ReAct retries
        parser_type (str): Parser type
        use_vlm (bool): Whether to use Vision Language Model
        ignore_history (bool): Whether to ignore message history
        message_history (AdvancedMessageHistory): Message history manager
    
    Example:
        >>> class WriterAgent(BaseAgent):
        ...     @property
        ...     def role_name(self) -> str:
        ...         return "Writer"
        ...     
        ...     @property
        ...     def system_prompt_template_name(self) -> str:
        ...         return "writer_system"
        ...     
        ...     @property
        ...     def task_prompt_template_name(self) -> str:
        ...         return "writer_task"
        >>> 
        >>> agent = WriterAgent(tool_manager=tm)
        >>> result = await agent.execute(state)
    """

    # =========================================================================
    # A. 类初始化与工厂方法
    # =========================================================================

    def __init_subclass__(cls, **kwargs):
        """
        Subclass registration hook
        
        Automatically called when a subclass of BaseAgent is defined, registering the subclass in AgentRegistry.
        This allows for dynamic creation of Agent instances via role names.
        
        Registration process:
            1. Create a temporary instance of the subclass (using tool_manager=None)
            2. Get its role_name
            3. Register (role_name.lower(), cls) into AgentRegistry
        
        Args:
            **kwargs: Keyword arguments passed to the parent class
        
        Note:
            If subclass initialization fails (e.g., missing required params), registration fails silently.
            This is to allow the definition of abstract subclasses.
        """
        super().__init_subclass__(**kwargs)
        try:
            # 创建临时实例以获取 role_name
            tmp = cls(tool_manager=None)
            name = tmp.role_name
            # 注册到 AgentRegistry
            from workflow_engine.agentroles.cores.registry import AgentRegistry
            AgentRegistry.register(name.lower(), cls)
        except Exception as e:
            # 静默失败，允许抽象子类
            pass
    
    def __init__(self, 
                 tool_manager: Optional[ToolManager] = None,
                 model_name: Optional[str] = None,
                 temperature: float = 0.0,
                 max_tokens: int = 65536,
                 tool_mode: str = "auto",
                 react_mode: bool = False,
                 react_max_retries: int = 3,
                 parser_type: str = "json",
                 parser_config: Optional[Dict[str, Any]] = None,
                 use_vlm: bool = False,
                 vlm_config: Optional[Dict[str, Any]] = None,
                 ignore_history: bool = True,
                 message_history: Optional[AdvancedMessageHistory] = None,
                 chat_api_url: Optional[str] = None,
                 execution_config: Optional[Any] = None):
        """
        Initialize BaseAgent instance
        
        Args:
            tool_manager (ToolManager, optional): Tool manager for managing pre and post tools
            model_name (str, optional): LLM model name, e.g., "gpt-4", "claude-3"
            temperature (float): LLM temperature parameter, controls randomness, default 0.0
            max_tokens (int): Maximum output token count, default 65536 (64k)
            tool_mode (str): Tool call mode, options "auto", "required", "none"
            react_mode (bool): Whether to enable ReAct mode (looping calls with verification)
            react_max_retries (int): Maximum retries for ReAct mode, default 3
            parser_type (str): Parser type, options "json", "xml", "text"
            parser_config (dict, optional): Parser configuration, e.g., root_tag for XML
            use_vlm (bool): Whether to use Vision Language Model
            vlm_config (dict, optional): VLM configuration, including mode, image_path, etc.
            ignore_history (bool): Whether to ignore message history, default True
            message_history (AdvancedMessageHistory, optional): Message history manager
            chat_api_url (str, optional): Custom API endpoint URL
            execution_config (Any, optional): Execution strategy configuration for advanced control
        """
        # ----- Base Configuration -----
        self.tool_manager = tool_manager
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.tool_mode = tool_mode
        self.react_mode = react_mode
        self.react_max_retries = react_max_retries
        self.chat_api_url = chat_api_url
        
        # ----- Parser Configuration -----
        self.parser_type = parser_type
        self.parser_config = parser_config or {}
        self._parser = None  # Lazy loading, created on first access
        
        # ----- VLM Configuration -----
        self.use_vlm = use_vlm
        self.vlm_config = vlm_config or {}
        
        # ----- Message History Configuration -----
        self.ignore_history = ignore_history
        self.message_history = message_history or AdvancedMessageHistory()

        # ----- Strategy Pattern Support -----
        self._execution_strategy: Optional[ExecutionStrategy] = None
        if execution_config:
            # Update agent attributes from execution config
            # This fixes the issue where parameters don't take effect when created via create_simple_agent etc.
            for f in execution_config.__dataclass_fields__:
                config_value = getattr(execution_config, f)
                if hasattr(self, f) and config_value is not None:
                    setattr(self, f, config_value)

            # Create execution strategy
            from workflow_engine.agentroles.cores.strategies import StrategyFactory
            self._execution_strategy = StrategyFactory.create(
                execution_config.mode.value,
                self,
                execution_config
            )

    @classmethod
    def create(cls, tool_manager: Optional[ToolManager] = None, **kwargs) -> "BaseAgent":
        """
        Factory Method - Unified entry point for Agent creation
        
        Provides a standardized way to create Agent instances, ensuring all Agents
        are created through the same interface, facilitating dependency injection and testing.
        
        Args:
            tool_manager (ToolManager, optional): Tool manager instance
            **kwargs: Other arguments passed to __init__
        
        Returns:
            BaseAgent: Created Agent instance (actual type is the subclass calling this method)
        
        Example:
            >>> agent = WriterAgent.create(tool_manager=tm, temperature=0.7)
        """
        return cls(tool_manager=tool_manager, **kwargs)

    # =========================================================================
    # B. 抽象属性 - 子类必须实现
    # =========================================================================
    
    @property
    @abstractmethod
    def role_name(self) -> str:
        """
        Role Name - Must be implemented by subclasses
        
        Returns a unique identification name for the Agent, used for:
        - Registration in AgentRegistry
        - Storing execution results in state.agent_results
        - Logging and debugging
        - Role matching in tool manager
        
        Returns:
            str: Agent role name, e.g., "Classifier", "Writer", "Recommender"
        
        Example:
            >>> @property
            ... def role_name(self) -> str:
            ...     return "Writer"
        """
        pass
    
    @property
    @abstractmethod
    def system_prompt_template_name(self) -> str:
        """
        System Prompt Template Name - Must be implemented by subclasses
        
        Returns the template name used for generating system prompts.
        Template files should be located in the promptstemplates/resources directory.
        
        Returns:
            str: Template name, e.g., "writer_system", "classifier_system"
        
        Note:
            Templates use Jinja2 syntax and can contain variable placeholders.
        """
        pass
    
    @property
    @abstractmethod
    def task_prompt_template_name(self) -> str:
        """
        Task Prompt Template Name - Must be implemented by subclasses
        
        Returns the template name used for generating task prompts.
        Task prompts contains specific task instructions and context information.
        
        Returns:
            str: Template name, e.g., "writer_task", "classifier_task"
        """
        pass

    # =========================================================================
    # C. 解析器相关
    # =========================================================================
    
    @property
    def parser(self) -> BaseParser:
        """
        Get Parser instance (Lazy loading)
        
        Creates the corresponding parser based on parser_type and parser_config.
        Parsers are used to transform the LLM's raw output into structured data.
        
        Supported Parser types:
        - json: JSON format parsing, supports schema verification
        - xml: XML format parsing, supports custom root_tag
        - text: Plain text, no parsing
        
        Returns:
            BaseParser: Parser instance
        
        Note:
            Parsers are created on first access and the same instance is reused thereafter.
        """
        if self._parser is None:
            from workflow_engine.parsers import ParserFactory
            
            # Merge parser_config and shortcut configs
            config = self.parser_config.copy() if self.parser_config else {}
            
            # If it's a JSON parser, merge schema related configs
            if self.parser_type == "json":
                if hasattr(self, 'response_schema') and self.response_schema:
                    config['schema'] = self.response_schema
                if hasattr(self, 'response_schema_description') and self.response_schema_description:
                    config['schema_description'] = self.response_schema_description
                if hasattr(self, 'response_example') and self.response_example:
                    config['example'] = self.response_example
                if hasattr(self, 'required_fields') and self.required_fields:
                    config['required_fields'] = self.required_fields
            
            self._parser = ParserFactory.create(self.parser_type, **config)
        return self._parser
    
    def parse_result(self, content: str) -> Dict[str, Any]:
        """
        Use the configured parser to parse LLM output results
        
        Converts the LLM's raw text output into a structured dictionary format.
        
        Args:
            content (str): LLM raw output content
        
        Returns:
            Dict[str, Any]: Parsed result dictionary
                - Returns parsed data on success
                - Returns {"raw": content, "error": error_message} on failure
        
        Example:
            >>> result = agent.parse_result('{"status": "success", "data": [1, 2, 3]}')
            >>> print(result)
            {'status': 'success', 'data': [1, 2, 3]}
        """
        try:
            parsed = self.parser.parse(content)
            log.info(f"{self.role_name} parsed successfully using {self.parser_type} parser")
            log.critical(f"[parse_result result] : {parsed}")
            return parsed
        except Exception as e:
            log.exception(f"Parsing failed: {e}")
            return {"raw": content, "error": str(e)}

    # =========================================================================
    # D. 消息构建
    # =========================================================================
    
    def build_messages(self, 
                       state: MainState, 
                       pre_tool_results: Dict[str, Any]) -> List[BaseMessage]:
        """
        Build LLM input message list
        
        Generates a complete list of messages based on system prompt templates and task prompt templates,
        including format instructions (if a parser is used).
        
        Args:
            state (MainState): Current state object, containing request info
            pre_tool_results (Dict[str, Any]): Pre-tool execution results
        
        Returns:
            List[BaseMessage]: Message list, containing SystemMessage and HumanMessage
        
        Message structure:
            1. SystemMessage: System prompt + Format instructions
            2. HumanMessage: Task prompt (including pre-tool results)
        """
        log.info("Building prompt messages...")
        
        # Create prompt generator
        ptg = PromptsTemplateGenerator(state.request.language)
        
        # Render system prompt
        sys_prompt = ptg.render(self.system_prompt_template_name)
        
        # Add parser format instructions (VLM mode might not need this)
        format_instruction = self.parser.get_format_instruction()
        if format_instruction and not self.use_vlm:
            sys_prompt += f"\n\n{format_instruction}"
        
        # Render task prompt
        task_params = self.get_task_prompt_params(pre_tool_results)
        task_prompt = ptg.render(self.task_prompt_template_name, **task_params)
        log.info(f"[build_messages] Task prompt: {task_prompt}")
        
        # Build message list
        messages = [
            SystemMessage(content=sys_prompt),
            HumanMessage(content=task_prompt),
        ]
        
        log.info("Prompt message construction complete")
        return messages
    
    def get_task_prompt_params(self, pre_tool_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get task prompt parameters - Can be overridden by subclasses
        
        Converts pre-tool results into parameters required for the task prompt template.
        Subclasses can override this method to customize parameter processing logic.
        
        Args:
            pre_tool_results (Dict[str, Any]): Pre-tool execution results
        
        Returns:
            Dict[str, Any]: Prompt template parameters dictionary
        
        Example:
            >>> def get_task_prompt_params(self, pre_tool_results):
            ...     return {
            ...         "user_input": pre_tool_results.get("input", ""),
            ...         "context": pre_tool_results.get("context", ""),
            ...     }
        """
        return pre_tool_results
    
    def build_generation_prompt(self, pre_tool_results: Dict[str, Any]) -> str:
        """
        Build generation prompt (for VLM image generation mode)
        
        Integrates pre-tool results into the prompt configured for VLM.
        
        Args:
            pre_tool_results (Dict[str, Any]): Pre-tool execution results
        
        Returns:
            str: Generation prompt
        """
        return f"{self.vlm_config.get('prompt', '')}"

    # =========================================================================
    # E. LLM 创建与调用
    # =========================================================================
    
    def get_llm_caller(self, state: MainState) -> BaseLLMCaller:
        """
        Return the corresponding LLM Caller based on the configuration
        
        Selects and returns VisionLLMCaller or TextLLMCaller based on the use_vlm configuration.
        
        Args:
            state (MainState): Current state object
        
        Returns:
            BaseLLMCaller: LLM caller instance
        
        Note:
            This method is currently not widely used; the create_llm method is primarily used instead.
        """
        if self.use_vlm:
            from workflow_engine.llm_callers import VisionLLMCaller
            log.info(f"Using VisionLLMCaller, mode: {self.vlm_config.get('mode', 'understanding')}")
            return VisionLLMCaller(
                state,
                vlm_config=self.vlm_config,
                model_name=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                tool_mode=self.tool_mode,
                tool_manager=self.tool_manager,
                chat_api_url=self.chat_api_url
            )
        else:
            from workflow_engine.llm_callers import TextLLMCaller
            return TextLLMCaller(
                state,
                model_name=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                tool_mode=self.tool_mode,
                tool_manager=self.tool_manager,
                chat_api_url=self.chat_api_url
            )

    def create_llm(self, state: MainState, bind_post_tools: bool = False) -> ChatOpenAI:
        """
        Create LLM instance
        
        Creates a ChatOpenAI instance based on the configuration, with the option to bind post-tools.
        
        Args:
            state (MainState): Current state object, containing API config
            bind_post_tools (bool): Whether to bind post-tools, default False
        
        Returns:
            ChatOpenAI: Configured LLM instance
        
        Note:
            - Model name usage priority: self.model_name, then state.request.model
            - API URL usage priority: self.chat_api_url, then state.request.chat_api_url
        """
        # Determine the actual model and URL to use
        actual_model = self.model_name or state.request.model
        actual_url = self.chat_api_url or state.request.chat_api_url
        
        log.info(f"[create_llm:] Creating LLM instance, temperature: {self.temperature}, "
                 f"max_tokens: {self.max_tokens}, model: {actual_model}, "
                 f"API URL: {actual_url}, API Key: {state.request.api_key}")
        
        # Create LLM instance (max_tokens not passed, use LangChain/API default)
        llm = ChatOpenAI(
            openai_api_base=actual_url,
            openai_api_key=state.request.api_key,
            model_name=actual_model,
            temperature=self.temperature,
        )
        
        # Bind post-tools if needed
        if bind_post_tools and self.tool_manager:
            post_tools = self.get_post_tools()
            if post_tools:
                llm = llm.bind_tools(post_tools, tool_choice=self.tool_mode)
                log.info(f"[create_llm]: Bound {len(post_tools)} post-tools for LLM: "
                        f"{[t.name for t in post_tools]}")
        
        return llm
    
    async def process_with_llm_for_graph(self, messages: List[BaseMessage], state: MainState) -> BaseMessage:
        """
        LLM call in Graph mode
        
        Calls LLM in graph execution mode, binding post-tools to support tool calls.
        
        Args:
            messages (List[BaseMessage]): Input message list
            state (MainState): Current state object
        
        Returns:
            BaseMessage: LLM response message
        
        Raises:
            Exception: Thrown if LLM call fails
        """
        llm = self.create_llm(state, bind_post_tools=True)
        try:
            response = await llm.ainvoke(messages)
            log.info(response)
            log.info(f"{self.role_name} Graph mode LLM call successful")
            return response
        except Exception as e:
            log.exception(f"{self.role_name} Graph mode LLM call failed: {e}")
            raise

    # =========================================================================
    # F. 工具管理
    # =========================================================================
    
    async def execute_pre_tools(self, state: MainState) -> Dict[str, Any]:
        """
        Execute pre-tools
        
        Tools executed before the LLM call, used for collecting context info.
        
        Args:
            state (MainState): Current state object
        
        Returns:
            Dict[str, Any]: Pre-tool execution results
        
        Note:
            If tool_manager is not provided, returns default values.
        """
        log.info(f"Starting execution of pre-tools for {self.role_name}...")
        
        # Check tool manager
        if not self.tool_manager:
            log.info("Tool manager not provided, using default values")
            return self.get_default_pre_tool_results()
        
        # Execute pre-tools
        results = await self.tool_manager.execute_pre_tools(self.role_name)
        
        # Set default values
        defaults = self.get_default_pre_tool_results()
        for key, default_value in defaults.items():
            if key not in results or results[key] is None:
                results[key] = default_value
                
        log.info(f"Pre-tool execution complete, obtained: {list(results.keys())}")
        return results
    
    def get_post_tools(self) -> List[Tool]:
        """
        Get post-tool list
        
        Get post-tools for the current role from the tool manager and remove duplicates.
        
        Returns:
            List[Tool]: Deduplicated list of post-tools
        """
        if not self.tool_manager:
            return []
        
        tools = self.tool_manager.get_post_tools(self.role_name)
        
        # 去重
        uniq, seen = [], set()
        for t in tools:
            if t.name not in seen:
                uniq.append(t)
                seen.add(t.name)
        
        return uniq
    
    def get_default_pre_tool_results(self) -> Dict[str, Any]:
        """
        Get default pre-tool results - Can be overridden by subclasses
        
        Used when there is no tool manager or when pre-tools fail to return certain fields.
        
        Returns:
            Dict[str, Any]: Default pre-tool results
        
        Example:
            >>> def get_default_pre_tool_results(self):
            ...     return {
            ...         "context": "",
            ...         "history": [],
            ...     }
        """
        return {}
    
    def has_tool_calls(self, message: BaseMessage) -> bool:
        """
        Check if the message contains tool calls
        
        Args:
            message (BaseMessage): Message to check
        
        Returns:
            bool: True if the message contains tool calls, False otherwise
        """
        return hasattr(message, 'tool_calls') and bool(getattr(message, 'tool_calls', None))

    # =========================================================================
    # G. 执行模式 - 简单模式
    # =========================================================================
    
    async def process_simple_mode(self, state: MainState, pre_tool_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simple mode processing - Single LLM call
        
        The most basic execution mode, calls LLM directly and parses the results.
        
        Args:
            state (MainState): Current state object
            pre_tool_results (Dict[str, Any]): Pre-tool execution results
        
        Returns:
            Dict[str, Any]: Parsed LLM output result
        
        Workflow:
            1. Build messages
            2. Merge history messages (if enabled)
            3. Call LLM
            4. Update message history
            5. Parse and return results
        """
        log.info(f"Executing {self.role_name} simple mode...")
        
        # Build messages
        messages = self.build_messages(state, pre_tool_results)
        
        # Message history management
        if not self.ignore_history:
            history_messages = self.message_history.get_messages()
            if history_messages:
                messages = self.message_history.merge_histories(history_messages, messages)
                log.info(f"Merged {len(history_messages)} history messages")
        
        # Create LLM (No tools bound)
        llm = self.create_llm(state, bind_post_tools=False)
        
        try:
            # Call LLM
            answer_msg = await llm.ainvoke(messages)
            answer_text = answer_msg.content
            log.info(f'LLM Raw Output: {answer_text}')
            log.info("LLM call successful, starting result parsing")
            
            # Update message history
            if not self.ignore_history:
                self.message_history.add_messages([answer_msg])
                log.info("Message history updated")
                
        except Exception as e:
            log.exception("LLM call failed: %s", e)
            return {"error": str(e)}
        
        return self.parse_result(answer_text)

    # =========================================================================
    # G. 执行模式 - ReAct 模式
    # =========================================================================
    
    async def process_react_mode(self, state: MainState, pre_tool_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        ReAct mode processing - Looping calls with verification
        
        Loops LLM calls until output passes all validators, or maximum retries are reached.
        
        Args:
            state (MainState): Current state object
            pre_tool_results (Dict[str, Any]): Pre-tool execution results
        
        Returns:
            Dict[str, Any]: Results passing verification, or a dictionary containing error info
        
        Workflow:
            1. Build initial message
            2. Looping LLM call
            3. Parse results and run validators
            4. If validation passes, return results
            5. If validation fails, add feedback message and retry
            6. Return error after reaching maximum retries
        """
        log.info(f"Executing {self.role_name} ReAct mode (max retries: {self.react_max_retries})")
        
        # Build initial messages
        messages = self.build_messages(state, pre_tool_results)
        
        # Message history management
        if not self.ignore_history:
            history_messages = self.message_history.get_messages()
            if history_messages:
                messages = self.message_history.merge_histories(history_messages, messages)
                log.info(f"Merged {len(history_messages)} history messages")
        
        # Create LLM
        llm = self.create_llm(state, bind_post_tools=False)
        
        # Looping calls until verification passes or maximum retries reached
        for attempt in range(self.react_max_retries + 1):
            try:
                # Call LLM
                log.info(f"ReAct Attempt {attempt + 1}/{self.react_max_retries + 1}")
                answer_msg = await llm.ainvoke(messages)
                answer_text = answer_msg.content
                log.info(f'LLM原始输出：{answer_text[:200]}...' if len(answer_text) > 200 else f'LLM原始输出：{answer_text}')
                
                # 解析结果
                parsed_result = self.parse_result(answer_text)
                
                # 运行验证器
                all_passed, errors = self._run_validators(answer_text, parsed_result)
                
                if all_passed:
                    log.info(f"✓ {self.role_name} ReAct验证通过，共尝试 {attempt + 1} 次")
                    
                    # 更新消息历史
                    if not self.ignore_history:
                        self.message_history.add_messages([answer_msg])
                        log.info("已更新消息历史")
                    
                    return parsed_result
                
                # 验证未通过
                if attempt < self.react_max_retries:
                    # 构建反馈消息
                    feedback = self._build_validation_feedback(errors)
                    log.warning(f"[process_react_mode] : 验证未通过 (尝试 {attempt + 1}): {feedback}")
                    
                    # 添加 LLM 的回复和人类的反馈到消息列表
                    messages.append(AIMessage(content=answer_text))
                    messages.append(HumanMessage(content=feedback))
                else:
                    # 达到最大重试次数
                    log.error(f"[process_react_mode] : {self.role_name} ReAct达到最大重试次数，验证仍未通过")
                    return {
                        "error": "ReAct验证失败",
                        "attempts": attempt + 1,
                        "last_errors": errors,
                        "last_result": parsed_result
                    }
                    
            except Exception as e:
                log.exception(f"ReAct模式LLM调用失败 (尝试 {attempt + 1}): {e}")
                if attempt >= self.react_max_retries:
                    return {"error": f"LLM调用失败: {str(e)}"}
                # 继续重试
                continue
        
        # 理论上不会到这里
        return {"error": "ReAct处理异常终止"}

    # =========================================================================
    # G. 执行模式 - 并行模式
    # =========================================================================
    
    async def process_parallel_mode(self, state: MainState, pre_tool_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        并行模式处理 - 并发执行多个 LLM 调用
        
        自动检测前置工具结果中的列表数据，对每个元素并行调用 LLM。
        
        Args:
            state (MainState): 当前状态对象
            pre_tool_results (Dict[str, Any]): 前置工具执行结果
        
        Returns:
            Dict[str, Any]: 包含所有并行结果的字典
                - parallel_results: 结果列表
                - total_processed: 处理总数
        
        数据检测优先级：
            1. pre_tool_results 本身是列表
            2. 包含 "parallel_items" 字段
            3. 任意值为列表的字段（取第一个非空列表）
        """
        log.info(f"执行 {self.role_name} 并行模式...")
        
        # ----- 智能检测并行数据 -----
        parallel_items = []
        
        # 情况1: pre_tool_results 本身是列表
        if isinstance(pre_tool_results, list):
            parallel_items = pre_tool_results
        
        # 情况2: 有明确的 parallel_items 字段
        elif "parallel_items" in pre_tool_results:
            parallel_items = pre_tool_results["parallel_items"]
        
        # 情况3: 检查任意值为列表的字段
        elif isinstance(pre_tool_results, dict):
            for key, value in pre_tool_results.items():
                if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                    parallel_items = value
                    break
        
        log.critical(f"[process_parallel_mode 并行数据] : {pre_tool_results}")
        
        # 如果没有找到合适的并行数据，回退到简单模式
        if not parallel_items:
            log.warning("未找到合适的并行数据，回退到简单模式")
            return await self.process_simple_mode(state, pre_tool_results)
        
        log.info(f"找到 {len(parallel_items)} 条数据用于并行处理")
        
        # ----- 获取并发限制 -----
        concurrency_limit = 5  # 默认值
        if hasattr(self, '_execution_strategy') and hasattr(self._execution_strategy, 'config'):
            if hasattr(self._execution_strategy.config, 'concurrency_limit'):
                concurrency_limit = self._execution_strategy.config.concurrency_limit
        
        # 创建信号量控制并发
        semaphore = asyncio.Semaphore(concurrency_limit)
        
        # ----- 定义单个并行任务处理函数 -----
        async def process_item(item: dict) -> dict:
            """处理单个并行项"""
            async with semaphore:
                try:
                    # 为每个并行项创建独立的上下文
                    item_pre_tool_results = {}
                    
                    # 先保留原始前置工具结果中的非列表字段
                    if isinstance(pre_tool_results, dict):
                        for key, value in pre_tool_results.items():
                            if not isinstance(value, list):
                                item_pre_tool_results[key] = value
                    
                    # 然后用 item 的数据覆盖（item 优先级更高）
                    if isinstance(item, dict):
                        item_pre_tool_results.update(item)
                    
                    # 使用简单模式处理单个项
                    log.info(f"[process_item]开始处理并行项 {item_pre_tool_results}")
                    result = await self.process_simple_mode(state, item_pre_tool_results)
                    return result
                except Exception as e:
                    log.error(f"并行处理单个项失败: {e}")
                    return {"error": str(e)}
        
        # ----- 并行执行所有任务 -----
        tasks = [process_item(item) for item in parallel_items]
        results = await asyncio.gather(*tasks)
        
        log.info(f"并行模式执行完成，共处理 {len(results)} 个任务")
        
        return {
            "parallel_results": results,
            "total_processed": len(results)
        }

    # =========================================================================
    # G. 执行模式 - 图模式（ReAct 子图）
    # =========================================================================
    
    async def _execute_react_graph(self, state: MainState, pre_tool_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        自动构建和执行 ReAct 子图
        
        使用 LangGraph 构建包含 assistant 和 tools 节点的子图，
        实现工具调用的自动循环。
        
        Args:
            state (MainState): 主状态对象
            pre_tool_results (Dict[str, Any]): 前置工具执行结果
        
        Returns:
            Dict[str, Any]: 子图执行结果
        
        子图结构：
            entry -> assistant -> [tools_condition] -> tools -> assistant -> ...
        """
        from langgraph.graph import StateGraph
        from langgraph.prebuilt import ToolNode, tools_condition
        
        log.info(f"开始构建 {self.role_name} 的子图...")
        
        # 1. 获取后置工具
        post_tools = self.get_post_tools()
        if not post_tools:
            log.warning(f"{self.role_name} 没有后置工具，回退到简单模式")
            return await self.process_simple_mode(state, pre_tool_results)
                
        # 2. 使用 MainState 作为子图状态
        log.critical(f"state: {state.agent_results}")
        subgraph = StateGraph(type(state))
        
        # 3. 创建 assistant 节点函数
        assistant_func = self.create_assistant_node_func(state, pre_tool_results)
        
        # 4. 添加节点
        subgraph.add_node("assistant", assistant_func)
        subgraph.add_node("tools", ToolNode(post_tools))
        
        # 5. 添加边
        subgraph.add_conditional_edges("assistant", tools_condition)
        subgraph.add_edge("tools", "assistant")
        
        # 6. 设置入口点
        subgraph.set_entry_point("assistant")
        
        # 7. 编译并执行
        compiled_graph = subgraph.compile()
        log.info(f"{self.role_name} 子图编译完成")
        
        try:
            # 执行子图
            final_state = await compiled_graph.ainvoke(state)
            log.info(f"{self.role_name} 子图执行完成")
            
            # 8. 从 final_state 中提取结果
            result = final_state["agent_results"].get(self.role_name.lower(), {}).get("results", {})

            if "messages" in final_state:
                # 9. 更新状态中的 messages
                state.messages = final_state["messages"]
            
            if not result:
                log.error("子图执行后未找到结果")
                return {"error": "子图执行异常：未找到结果"}
            
            log.info(f"{self.role_name} 子图结果解析完成")
            return result
            
        except Exception as e:
            log.exception(f"{self.role_name} 子图执行失败: {e}")
            return {"error": f"子图执行失败: {str(e)}"}
    
    def create_assistant_node_func(self, state: MainState, pre_tool_results: Dict[str, Any]):
        """
        创建 assistant 节点函数
        
        为 LangGraph 子图创建 assistant 节点的处理函数。
        
        Args:
            state (MainState): 主状态对象
            pre_tool_results (Dict[str, Any]): 前置工具执行结果
        
        Returns:
            Callable: 异步节点处理函数
        """
        async def assistant_node(graph_state):
            # 获取或构建消息
            messages = graph_state.get("messages", [])
            if not messages:
                messages = self.build_messages(state, pre_tool_results)
                log.info(f"构建 {self.role_name} 初始消息，包含前置工具结果")

            # 调用 LLM
            response = await self.process_with_llm_for_graph(messages, state)

            # 检查是否有工具调用
            if self.has_tool_calls(response):
                log.info(f"[create_assistant_node_func]: {self.role_name} LLM选择调用工具: ...")
                return {"messages": messages + [response]}
            else:
                # 没有工具调用，解析最终结果
                log.info(f"[create_assistant_node_func]: {self.role_name} LLM本次未调用工具，解析最终结果")
                result = self.parse_result(response.content)
                
                # 同步 agent_results
                state.agent_results[self.role_name.lower()] = {
                    "pre_tool_results": pre_tool_results,
                    "post_tools": [t.name for t in self.get_post_tools()],
                    "results": result
                }
                
                return {
                    "messages": messages + [response],
                    self.role_name.lower(): result,
                    "finished": True
                }
        
        return assistant_node

    # =========================================================================
    # H. ReAct 验证器
    # =========================================================================
    
    def get_react_validators(self) -> List[ValidatorFunc]:
        """
        获取 ReAct 模式的验证器列表 - 子类可重写
        
        验证器用于检查 LLM 输出是否符合预期格式和内容要求。
        
        Returns:
            List[ValidatorFunc]: 验证器函数列表
        
        Example:
            >>> def get_react_validators(self):
            ...     return [
            ...         self._default_json_validator,
            ...         self._check_required_fields,
            ...         self._validate_data_format,
            ...     ]
        """
        return [
            self._default_json_validator,
        ]
    
    @staticmethod
    def _default_json_validator(content: str, parsed_result: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        默认 JSON 格式验证器
        
        检查解析结果是否为有效的非空 JSON。
        
        Args:
            content (str): LLM 原始输出
            parsed_result (Dict[str, Any]): 解析后的结果
        
        Returns:
            Tuple[bool, Optional[str]]: (是否通过, 错误信息)
        """
        # 检查是否解析失败（只有 raw 字段）
        if "raw" in parsed_result and len(parsed_result) == 1:
            return False, (
                "你返回的内容不是有效的JSON格式。请确保返回纯JSON格式的数据，"
                "不要包含其他文字说明。正确的格式示例：\n"
                '{"key1": "value1", "key2": "value2"}'
            )
        
        # 检查是否为空字典
        if not parsed_result or (isinstance(parsed_result, dict) and not parsed_result):
            return False, "你返回的JSON为空，请提供完整的结果数据。"
        
        return True, None
    
    def _run_validators(self, content: str, parsed_result: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        运行所有验证器
        
        Args:
            content (str): LLM 原始输出
            parsed_result (Dict[str, Any]): 解析后的结果
        
        Returns:
            Tuple[bool, List[str]]: (是否全部通过, 错误信息列表)
        """
        validators = self.get_react_validators()
        errors = []
        
        for i, validator in enumerate(validators):
            try:
                passed, error_msg = validator(content, parsed_result)
                if not passed:
                    validator_name = getattr(validator, '__name__', f'validator_{i}')
                    log.warning(f"验证器 {validator_name} 未通过: {error_msg}")
                    if error_msg:
                        errors.append(error_msg)
            except Exception as e:
                log.exception(f"验证器执行出错: {e}")
                errors.append(f"验证过程出错: {str(e)}")
        
        return len(errors) == 0, errors
    
    def _build_validation_feedback(self, errors: List[str]) -> str:
        """
        构建验证失败的反馈消息
        
        Args:
            errors (List[str]): 错误信息列表
        
        Returns:
            str: 格式化的反馈消息
        """
        if not errors:
            return "输出格式有误，请按要求重新生成。"
        
        feedback_parts = ["你的输出存在以下问题，请修正后重新生成：\n"]
        for i, error in enumerate(errors, 1):
            feedback_parts.append(f"{i}. {error}")
        
        feedback_parts.append("\n请仔细检查并重新输出正确的结果。")
        return "\n".join(feedback_parts)

    # =========================================================================
    # I. Agent-as-Tool 功能
    # =========================================================================
    
    def get_tool_name(self) -> str:
        """
        获取作为工具时的名称 - 子类可重写
        
        Returns:
            str: 工具名称，格式为 "call_{role_name}_agent"
        """
        return f"call_{self.role_name.lower()}_agent"

    def get_tool_description(self) -> str:
        """
        获取作为工具时的描述 - 子类应重写提供更具体的描述
        
        Returns:
            str: 工具描述
        """
        return f"调用 {self.role_name} agent 来执行特定任务。该 agent 会根据输入参数执行相应的分析和处理。"

    def get_tool_args_schema(self) -> Type[BaseModel]:
        """
        获取作为工具时的参数模式 - 子类可重写
        
        Returns:
            Type[BaseModel]: Pydantic 模型类，定义工具参数结构
        """
        class DefaultAgentToolArgs(BaseModel):
            """默认 Agent 工具参数"""
            task_description: str = Field(
                description=f"传递给 {self.role_name} 的任务描述或指令"
            )
            additional_params: Optional[Dict[str, Any]] = Field(
                default=None,
                description="额外的参数，会被合并到前置工具结果中"
            )
        
        return DefaultAgentToolArgs

    def prepare_tool_execution_params(self, **tool_kwargs) -> Dict[str, Any]:
        """
        准备工具执行时的参数 - 子类可重写
        
        Args:
            **tool_kwargs: 工具调用时传入的参数
        
        Returns:
            Dict[str, Any]: 处理后的参数字典
        """
        params = {}
        
        # 合并 additional_params
        if 'additional_params' in tool_kwargs and tool_kwargs['additional_params']:
            params.update(tool_kwargs['additional_params'])
        
        # 添加其他参数
        for key, value in tool_kwargs.items():
            if key != 'additional_params':
                params[key] = value
        
        return params

    def extract_tool_result(self, state: MainState) -> Dict[str, Any]:
        """
        从状态中提取工具调用的结果 - 子类可重写
        
        Args:
            state (MainState): 执行后的状态对象
        
        Returns:
            Dict[str, Any]: 提取的结果
        """
        agent_result = state.agent_results.get(self.role_name, {})
        return agent_result.get('results', {})

    async def _execute_as_tool(self, state: MainState, **tool_kwargs) -> Dict[str, Any]:
        """
        作为工具执行的内部方法
        
        Args:
            state (MainState): 当前状态对象
            **tool_kwargs: 工具参数
        
        Returns:
            Dict[str, Any]: 执行结果
        """
        try:
            log.info(f"[Agent-as-Tool] 调用 {self.role_name}，参数: {tool_kwargs}")
            
            # 准备执行参数
            exec_params = self.prepare_tool_execution_params(**tool_kwargs)
            
            # 执行 Agent
            result_state = await self.execute(
                state, 
                use_agent=False,
                **exec_params
            )
            
            # 提取结果
            result = self.extract_tool_result(result_state)
            
            log.info(f"[Agent-as-Tool] {self.role_name} 执行完成")
            return result
            
        except Exception as e:
            log.exception(f"[Agent-as-Tool] {self.role_name} 执行失败: {e}")
            return {
                "error": str(e),
                "agent": self.role_name,
                "status": "failed"
            }

    def as_tool(self, state: MainState) -> Tool:
        """
        将 Agent 包装成可被调用的工具
        
        Args:
            state (MainState): 状态对象，将被传递给 Agent 执行
        
        Returns:
            Tool: LangChain Tool 实例
        
        Example:
            >>> writer_tool = writer_agent.as_tool(state)
            >>> result = await writer_tool.ainvoke({"task_description": "写一篇文章"})
        """
        async def agent_tool_func(**kwargs) -> Dict[str, Any]:
            return await self._execute_as_tool(state, **kwargs)
        
        def sync_agent_tool_func(**kwargs) -> Dict[str, Any]:
            return asyncio.run(agent_tool_func(**kwargs))
        
        return Tool(
            name=self.get_tool_name(),
            description=self.get_tool_description(),
            func=sync_agent_tool_func,
            coroutine=agent_tool_func,
            args_schema=self.get_tool_args_schema()
        )

    # =========================================================================
    # J. 状态管理与输出
    # =========================================================================
    
    def update_state_result(self, state: MainState, result: Dict[str, Any], pre_tool_results: Dict[str, Any]):
        """
        更新状态结果 - 子类可重写
        
        将执行结果存储到状态对象中。
        
        Args:
            state (MainState): 状态对象
            result (Dict[str, Any]): 执行结果
            pre_tool_results (Dict[str, Any]): 前置工具结果
        """
        # 将结果存储到与角色名对应的属性中
        setattr(state, self.role_name.lower(), result)
        
        # 存储到 agent_results
        state.agent_results[self.role_name] = {
            "pre_tool_results": pre_tool_results,
            "post_tools": [t.name for t in self.get_post_tools()],
            "results": result
        }

    def store_outputs(self, data, file_name: str = None) -> str:
        """
        保存输出结果到文件
        
        Args:
            data: 要保存的数据
            file_name (str, optional): 文件名，默认使用时间戳
        
        Returns:
            str: 保存的文件路径
        """
        # 创建输出目录
        out_dir = Path(f"{PROJDIR}/outputs/{self.role_name.lower()}")
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        if not file_name:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"{ts}.pkl"
        
        file_path = out_dir / file_name
        
        # 保存数据
        with open(file_path, "wb") as f:
            pickle.dump(data, f)
        
        log.info(f"已保存->: {file_path}")
        return str(file_path)

    # =========================================================================
    # K. 主执行入口
    # =========================================================================
    
    async def execute(self, state: MainState, use_agent: bool = False, **kwargs) -> MainState:
        """
        统一执行入口 - Agent 的核心执行方法
        
        根据配置选择合适的执行模式，完成 Agent 的完整执行流程。
        
        Args:
            state (MainState): 当前状态对象
            use_agent (bool): 是否使用代理模式（图模式），默认 False
            **kwargs: 额外参数，会被合并到前置工具结果中
        
        Returns:
            MainState: 更新后的状态对象
        
        执行流程：
            1. 检查是否使用策略模式
            2. 检查是否使用 VLM 模式
            3. 执行前置工具
            4. 根据配置选择执行模式：
               - 图模式（use_agent=True 且有后置工具）
               - ReAct 模式（react_mode=True）
               - 简单模式（默认）
            5. 更新状态结果
        
        Example:
            >>> state = await agent.execute(state, use_agent=True)
            >>> result = state.agent_results["Writer"]["results"]
        """
        # 保存状态引用
        self.state = state
        
        # ----- 策略模式执行 -----
        if self._execution_strategy:
            log.info(f"使用策略模式执行: {self._execution_strategy.__class__.__name__}")
            try:
                pre_tool_results = await self.execute_pre_tools(state)
                result = await self._execution_strategy.execute(state, **kwargs)
                self.update_state_result(state, result, pre_tool_results)
                return state
            except Exception as e:
                log.exception(f"策略执行失败: {e}")
                error_result = {"error": str(e)}
                self.update_state_result(state, error_result, {})
                return state
            
        # ----- 常规执行流程 -----
        log.info(f"开始执行 {self.role_name} (ReAct模式: {self.react_mode}, 图模式: {use_agent})")

        # VLM 模式
        if getattr(self, "use_vlm", False):
            log.critical(f'[base agent]: 走多模态路径')
            result = await self._execute_vlm(state, **kwargs)
            self.update_state_result(state, result, {})
            log.info(f"{self.role_name} 多模态执行完成")
            return state
        
        try:
            # 1. 执行前置工具
            pre_tool_results = await self.execute_pre_tools(state)
            
            # 1.1 写入 temp_data
            try:
                if not hasattr(state, 'temp_data') or state.temp_data is None:
                    state.temp_data = {}
                state.temp_data['pre_tool_results'] = pre_tool_results
            except Exception:
                pass
            
            # 1.2 合并 kwargs 到前置工具结果
            pre_tool_results.update(kwargs)
            
            # 2. 获取后置工具
            post_tools = self.get_post_tools()
            
            # 3. 根据模式选择处理方式
            if use_agent and post_tools:
                # ----- 图模式 -----
                log.info(f"[子图新模式] 自动构建 {self.role_name} 的子图，"
                        f"后置工具: {[t.name for t in post_tools]}")
                result = await self._execute_react_graph(state, pre_tool_results)
                self.update_state_result(state, result, pre_tool_results)
                log.info(f"[子图新模式] {self.role_name} 子图模式执行完成")
                
                # 更新 temp_data
                if not hasattr(state, 'temp_data'):
                    state.temp_data = {}
                state.temp_data['pre_tool_results'] = pre_tool_results
                state.temp_data[f'{self.role_name}_instance'] = self
                
            elif self.react_mode:
                # ----- ReAct 模式 -----
                log.info("ReAct模式 - 带验证循环")
                result = await self.process_react_mode(state, pre_tool_results)
                self.update_state_result(state, result, pre_tool_results)
                log.info(f"{self.role_name} ReAct模式执行完成")
                
            else:
                # ----- 简单模式 -----
                if use_agent and not post_tools:
                    log.info("图模式无可用后置工具，回退到简单模式")
                result = await self.process_simple_mode(state, pre_tool_results)
                self.update_state_result(state, result, pre_tool_results)
                log.info(f"{self.role_name} 简单模式执行完成")
            
        except Exception as e:
            log.exception(f"{self.role_name} 执行失败: {e}")
            import traceback
            traceback.print_exc()
            error_result = {"error": str(e)}
            self.update_state_result(state, error_result, {})
            
        return state
    
    async def _execute_vlm(self, state: MainState, **kwargs) -> Dict[str, Any]:
        """
        Vision-LLM 专用执行流程
        
        与文本链路完全解耦，专门处理视觉语言模型的调用。
        
        Args:
            state (MainState): 当前状态对象
            **kwargs: 额外参数
        
        Returns:
            Dict[str, Any]: VLM 执行结果
        """
        # 1. 执行前置工具
        pre_tool_results = await self.execute_pre_tools(state)
    
        # 2. 构建消息
        mode = self.vlm_config.get("mode", "understanding")
        messages = self.build_messages(state, pre_tool_results)
    
        # 3. 调用 VisionLLMCaller
        from workflow_engine.llm_callers import VisionLLMCaller
        vlm_caller = VisionLLMCaller(
            state,
            vlm_config=self.vlm_config,
            model_name=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            tool_mode=self.tool_mode,
            tool_manager=self.tool_manager,
        )
        response = await vlm_caller.call(messages)
        log.info(f"{self.role_name} 多模态原始响应: {response}")
    
        # 4. 解析结果
        parsed = self.parse_result(response.content)
    
        # 5. 合并附加信息（如图像路径、base64 等）
        if hasattr(response, "additional_kwargs"):
            log.info(f"{self.role_name} 多模态附加信息: {response.additional_kwargs}")
            
            if isinstance(parsed, dict):
                parsed.update(response.additional_kwargs)
            elif isinstance(parsed, list):
                log.warning(f"{self.role_name} parsed 是列表类型，无法调用 update 方法，跳过附加参数合并")
                log.info(f"parsed 类型: {type(parsed).__name__}, 内容: {parsed}")
                log.info(f"additional_kwargs 内容: {response.additional_kwargs}")
            else:
                log.warning(f"{self.role_name} parsed 是 {type(parsed).__name__} 类型，无法调用 update 方法，跳过附加参数合并")
                log.info(f"parsed 内容: {parsed}")
                log.info(f"additional_kwargs 内容: {response.additional_kwargs}")
        
        return parsed
