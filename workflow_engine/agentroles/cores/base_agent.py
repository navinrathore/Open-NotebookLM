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
    # A. Class Initialization and Factory Methods
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
            # Create temporary instance to get role_name
            tmp = cls(tool_manager=None)
            name = tmp.role_name
            # Register to AgentRegistry
            from workflow_engine.agentroles.cores.registry import AgentRegistry
            AgentRegistry.register(name.lower(), cls)
        except Exception as e:
            # Silent failure, allow abstract subclasses
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
    # B. Abstract Properties - Subclasses must implement
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
    # C. Parser Related
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
    # D. Message Construction
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
    # E. LLM Creation and Calling
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
    # F. Tool Management
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
        
        # Deduplicate
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
    # G. Execution Mode - Simple Mode
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
    # G. Execution Mode - ReAct Mode
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
                log.info(f"LLM Raw Output: {answer_text[:200]}..." if len(answer_text) > 200 else f"LLM Raw Output: {answer_text}")
                
                # Parse results
                parsed_result = self.parse_result(answer_text)
                
                # Run validators
                all_passed, errors = self._run_validators(answer_text, parsed_result)
                
                if all_passed:
                    log.info(f"✓ {self.role_name} ReAct validation passed, total attempts: {attempt + 1}")
                    
                    # Update message history
                    if not self.ignore_history:
                        self.message_history.add_messages([answer_msg])
                        log.info("Message history updated")
                    
                    return parsed_result
                
                # Validation failed
                if attempt < self.react_max_retries:
                    # Build feedback message
                    feedback = self._build_validation_feedback(errors)
                    log.warning(f"[process_react_mode] : Validation failed (Attempt {attempt + 1}): {feedback}")
                    
                    # Add LLM response and human feedback to message list
                    messages.append(AIMessage(content=answer_text))
                    messages.append(HumanMessage(content=feedback))
                else:
                    # Reached maximum retries
                    log.error(f"[process_react_mode] : {self.role_name} ReAct reached maximum retries, validation still failed")
                    return {
                        "error": "ReAct validation failed",
                        "attempts": attempt + 1,
                        "last_errors": errors,
                        "last_result": parsed_result
                    }
                    
            except Exception as e:
                log.exception(f"ReAct mode LLM call failed (Attempt {attempt + 1}): {e}")
                if attempt >= self.react_max_retries:
                    return {"error": f"LLM call failed: {str(e)}"}
                # Continue retry
                continue
        
        # Theoretically should not reach here
        return {"error": "ReAct processing terminated abnormally"}

    # =========================================================================
    # G. Execution Mode - Parallel Mode
    # =========================================================================
    
    async def process_parallel_mode(self, state: MainState, pre_tool_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parallel mode processing - Concurrent execution of multiple LLM calls
        
        Automatically detect list data in pre-tool results and call LLM in parallel for each element.
        
        Args:
            state (MainState): Current state object
            pre_tool_results (Dict[str, Any]): Pre-tool execution results
        
        Returns:
            Dict[str, Any]: Dictionary containing all parallel results
                - parallel_results: Result list
                - total_processed: Total processed
        
        Data detection priority:
            1. pre_tool_results is a list itself
            2. Contains "parallel_items" field
            3. Any field with a list value (take the first non-empty list)
        """
        log.info(f"Executing {self.role_name} parallel mode...")
        
        # ----- Intelligent parallel data detection -----
        parallel_items = []
        
        # Case 1: pre_tool_results is a list itself
        if isinstance(pre_tool_results, list):
            parallel_items = pre_tool_results
        
        # Case 2: Specific "parallel_items" field exists
        elif "parallel_items" in pre_tool_results:
            parallel_items = pre_tool_results["parallel_items"]
        
        # Case 3: Check any field with a list value
        elif isinstance(pre_tool_results, dict):
            for key, value in pre_tool_results.items():
                if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                    parallel_items = value
                    break
        
        log.critical(f"[process_parallel_mode parallel data] : {pre_tool_results}")
        
        # If no suitable parallel data found, fall back to simple mode
        if not parallel_items:
            log.warning("No suitable parallel data found, falling back to simple mode")
            return await self.process_simple_mode(state, pre_tool_results)
        
        log.info(f"Found {len(parallel_items)} items for parallel processing")
        
        # ----- Get concurrency limit -----
        concurrency_limit = 5  # Default value
        if hasattr(self, '_execution_strategy') and hasattr(self._execution_strategy, 'config'):
            if hasattr(self._execution_strategy.config, 'concurrency_limit'):
                concurrency_limit = self._execution_strategy.config.concurrency_limit
        
        # Create semaphore to control concurrency
        semaphore = asyncio.Semaphore(concurrency_limit)
        
        # ----- Define single parallel task handler -----
        async def process_item(item: dict) -> dict:
            """Process a single parallel item"""
            async with semaphore:
                try:
                    # Create independent context for each parallel item
                    item_pre_tool_results = {}
                    
                    # Keep non-list fields from raw pre-tool results first
                    if isinstance(pre_tool_results, dict):
                        for key, value in pre_tool_results.items():
                            if not isinstance(value, list):
                                item_pre_tool_results[key] = value
                    
                    # Then overwrite with item data (item priority is higher)
                    if isinstance(item, dict):
                        item_pre_tool_results.update(item)
                    
                    # Use simple mode for a single item
                    log.info(f"[process_item] Start processing parallel item {item_pre_tool_results}")
                    result = await self.process_simple_mode(state, item_pre_tool_results)
                    return result
                except Exception as e:
                    log.error(f"Parallel item processing failed: {e}")
                    return {"error": str(e)}
        
        # ----- Execute all tasks in parallel -----
        tasks = [process_item(item) for item in parallel_items]
        results = await asyncio.gather(*tasks)
        
        log.info(f"Parallel mode execution complete, processed {len(results)} tasks")
        
        return {
            "parallel_results": results,
            "total_processed": len(results)
        }

    # =========================================================================
    # G. Execution Mode - Graph Mode (ReAct Subgraph)
    # =========================================================================
    
    async def _execute_react_graph(self, state: MainState, pre_tool_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Automatically build and execute ReAct subgraph
        
        Use LangGraph to build a subgraph containing assistant and tools nodes,
        implement automatic tool calling loops.
        
        Args:
            state (MainState): Main state object
            pre_tool_results (Dict[str, Any]): Pre-tool execution results
        
        Returns:
            Dict[str, Any]: Subgraph execution results
        
        Subgraph structure:
            entry -> assistant -> [tools_condition] -> tools -> assistant -> ...
        """
        from langgraph.graph import StateGraph
        from langgraph.prebuilt import ToolNode, tools_condition
        
        log.info(f"Starting to build {self.role_name} subgraph...")
        
        # 1. Get post-tools
        post_tools = self.get_post_tools()
        if not post_tools:
            log.warning(f"{self.role_name} No post-tools, falling back to simple mode")
            return await self.process_simple_mode(state, pre_tool_results)
                
        # 2. Use MainState as subgraph state
        log.critical(f"state: {state.agent_results}")
        subgraph = StateGraph(type(state))
        
        # 3. Create assistant node function
        assistant_func = self.create_assistant_node_func(state, pre_tool_results)
        
        # 4. Add nodes
        subgraph.add_node("assistant", assistant_func)
        subgraph.add_node("tools", ToolNode(post_tools))
        
        # 5. Add edges
        subgraph.add_conditional_edges("assistant", tools_condition)
        subgraph.add_edge("tools", "assistant")
        
        # 6. Set entry point
        subgraph.set_entry_point("assistant")
        
        # 7. Compile and execute
        compiled_graph = subgraph.compile()
        log.info(f"{self.role_name} subgraph compilation complete")
        
        try:
            # Execute subgraph
            final_state = await compiled_graph.ainvoke(state)
            log.info(f"{self.role_name} subgraph execution complete")
            
            # 8. Extract results from final_state
            result = final_state["agent_results"].get(self.role_name.lower(), {}).get("results", {})

            if "messages" in final_state:
                # 9. Update messages in state
                state.messages = final_state["messages"]
            
            if not result:
                log.error("No results found after subgraph execution")
                return {"error": "Subgraph execution exception: No results found"}
            
            log.info(f"{self.role_name} subgraph result parsing complete")
            return result
            
        except Exception as e:
            log.exception(f"{self.role_name} subgraph execution failed: {e}")
            return {"error": f"Subgraph execution failed: {str(e)}"}
    
    def create_assistant_node_func(self, state: MainState, pre_tool_results: Dict[str, Any]):
        """
        Create assistant node function
        
        Create assistant node handler for LangGraph subgraph.
        
        Args:
            state (MainState): Main state object
            pre_tool_results (Dict[str, Any]): Pre-tool execution results
        
        Returns:
            Callable: Async node handler function
        """
        async def assistant_node(graph_state):
            # Get or build messages
            messages = graph_state.get("messages", [])
            if not messages:
                messages = self.build_messages(state, pre_tool_results)
                log.info(f"Building {self.role_name} initial message, including pre-tool results")

            # Call LLM
            response = await self.process_with_llm_for_graph(messages, state)

            # Check for tool calls
            if self.has_tool_calls(response):
                log.info(f"[create_assistant_node_func]: {self.role_name} LLM chose to call tools: ...")
                return {"messages": messages + [response]}
            else:
                # No tool calls, parsing final results
                log.info(f"[create_assistant_node_func]: {self.role_name} LLM did not call tools this time, parsing final results")
                result = self.parse_result(response.content)
                
                # Sync agent_results
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
    # H. ReAct Validators
    # =========================================================================
    
    def get_react_validators(self) -> List[ValidatorFunc]:
        """
        Get ReAct mode validators list - subclasses can override
        
        Validators are used to check if LLM output meets expected format and requirements.
        
        Returns:
            List[ValidatorFunc]: Validator functions list
        
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
        Default JSON format validator.
        Checks if the parsing result is a valid non-empty JSON.
        
        Args:
            content (str): Raw LLM output
            parsed_result (Dict[str, Any]): Parsed result
        
        Returns:
            Tuple[bool, Optional[str]]: (Success, Error message)
        """
        # Check if parsing failed (only 'raw' field remains)
        if "raw" in parsed_result and len(parsed_result) == 1:
            return False, (
                "The content you returned is not in valid JSON format. Please ensure you return data in pure JSON format, "
                "without any other text explanations. Correct format example:\n"
                '{"key1": "value1", "key2": "value2"}'
            )
        
        # Check for empty dictionary
        if not parsed_result or (isinstance(parsed_result, dict) and not parsed_result):
            return False, "The returned JSON is empty. Please provide complete result data."
        
        return True, None
    
    def _run_validators(self, content: str, parsed_result: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Run all validators.
        
        Args:
            content (str): Raw LLM output
            parsed_result (Dict[str, Any]): Parsed result
        
        Returns:
            Tuple[bool, List[str]]: (Success, List of error messages)
        """
        validators = self.get_react_validators()
        errors = []
        
        for i, validator in enumerate(validators):
            try:
                passed, error_msg = validator(content, parsed_result)
                if not passed:
                    validator_name = getattr(validator, '__name__', f'validator_{i}')
                    log.warning(f"Validator {validator_name} failed: {error_msg}")
                    if error_msg:
                        errors.append(error_msg)
            except Exception as e:
                log.exception(f"Validator execution error: {e}")
                errors.append(f"Validation process error: {str(e)}")
        
        return len(errors) == 0, errors
    
    def _build_validation_feedback(self, errors: List[str]) -> str:
        """
        Build feedback message for validation failure.
        
        Args:
            errors (List[str]): List of error messages
        
        Returns:
            str: Formatted feedback message
        """
        if not errors:
            return "Output format is incorrect. Please regenerate according to requirements."
        
        feedback_parts = ["Your output has the following issues. Please correct them and regenerate:\n"]
        for i, error in enumerate(errors, 1):
            feedback_parts.append(f"{i}. {error}")
        
        feedback_parts.append("\nPlease double-check and output the correct result.")
        return "\n".join(feedback_parts)

    # =========================================================================
    # I. Agent-as-Tool functionality
    # =========================================================================
    
    def get_tool_name(self) -> str:
        """
        Get the name when used as a tool - subclasses can override.
        
        Returns:
            str: Tool name, format "call_{role_name}_agent"
        """
        return f"call_{self.role_name.lower()}_agent"

    def get_tool_description(self) -> str:
        """
        Get the description when used as a tool - subclasses should override to provide specific details.
        
        Returns:
            str: Tool description
        """
        return f"Invoke {self.role_name} agent to perform specific tasks. This agent will execute analysis and processing based on input parameters."

    def get_tool_args_schema(self) -> Type[BaseModel]:
        """
        Get the parameter schema when used as a tool - subclasses can override.
        
        Returns:
            Type[BaseModel]: Pydantic model class defining tool parameters
        """
        class DefaultAgentToolArgs(BaseModel):
            """Default Agent tool parameters"""
            task_description: str = Field(
                description=f"Task description or instruction passed to {self.role_name}"
            )
            additional_params: Optional[Dict[str, Any]] = Field(
                default=None,
                description="Extra parameters to be merged into pre-tool results"
            )
        
        return DefaultAgentToolArgs

    def prepare_tool_execution_params(self, **tool_kwargs) -> Dict[str, Any]:
        """
        Prepare parameters for tool execution - subclasses can override
        
        Args:
            **tool_kwargs: Parameters passed during tool call
        
        Returns:
            Dict[str, Any]: Processed parameters dictionary
        """
        params = {}
        
        # Merge additional_params
        if 'additional_params' in tool_kwargs and tool_kwargs['additional_params']:
            params.update(tool_kwargs['additional_params'])
        
        # Add other parameters
        for key, value in tool_kwargs.items():
            if key != 'additional_params':
                params[key] = value
        
        return params

    def extract_tool_result(self, state: MainState) -> Dict[str, Any]:
        """
        Extract tool call results from state - subclasses can override
        
        Args:
            state (MainState): State object after execution
        
        Returns:
            Dict[str, Any]: Extracted results
        """
        agent_result = state.agent_results.get(self.role_name, {})
        return agent_result.get('results', {})

    async def _execute_as_tool(self, state: MainState, **tool_kwargs) -> Dict[str, Any]:
        """
        Internal method for executing as a tool.
        
        Args:
            state (MainState): Current state object
            **tool_kwargs: Tool parameters
        
        Returns:
            Dict[str, Any]: Execution results
        """
        try:
            log.info(f"[Agent-as-Tool] Invoking {self.role_name}, parameters: {tool_kwargs}")
            
            # Prepare execution parameters
            exec_params = self.prepare_tool_execution_params(**tool_kwargs)
            
            # Execute Agent
            result_state = await self.execute(
                state, 
                use_agent=False,
                **exec_params
            )
            
            # Extract result
            result = self.extract_tool_result(result_state)
            
            log.info(f"[Agent-as-Tool] {self.role_name} execution complete")
            return result
            
        except Exception as e:
            log.exception(f"[Agent-as-Tool] {self.role_name} execution failed: {e}")
            return {
                "error": str(e),
                "agent": self.role_name,
                "status": "failed"
            }

    def as_tool(self, state: MainState) -> Tool:
        """
        Wrap Agent as a callable tool
        
        Args:
            state (MainState): State object, passed to Agent for execution
        
        Returns:
            Tool: LangChain Tool instance
        
        Example:
            >>> writer_tool = writer_agent.as_tool(state)
            >>> result = await writer_tool.ainvoke({"task_description": "Write an article"})
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
    # J. State Management and Output
    # =========================================================================
    
    def update_state_result(self, state: MainState, result: Dict[str, Any], pre_tool_results: Dict[str, Any]):
        """
        Update state result - subclasses can override.
        Saves execution results to the state object.
        
        Args:
            state (MainState): State object
            result (Dict[str, Any]): Execution results
            pre_tool_results (Dict[str, Any]): Pre-tool results
        """
        # Store results in attributes corresponding to role name
        setattr(state, self.role_name.lower(), result)
        
        # Store in agent_results
        state.agent_results[self.role_name] = {
            "pre_tool_results": pre_tool_results,
            "post_tools": [t.name for t in self.get_post_tools()],
            "results": result
        }

    def store_outputs(self, data, file_name: str = None) -> str:
        """
        Save output results to a file.
        
        Args:
            data: Data to be saved
            file_name (str, optional): Filename, default is timestamp
        
        Returns:
            str: Saved file path
        """
        # 创建输出目录
        out_dir = Path(f"{PROJDIR}/outputs/{self.role_name.lower()}")
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        if not file_name:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"{ts}.pkl"
        
        file_path = out_dir / file_name
        
        # Save data
        with open(file_path, "wb") as f:
            pickle.dump(data, f)
        
        log.info(f"Saved to ->: {file_path}")
        return str(file_path)

    # =========================================================================
    # K. Main Execution Entry
    # =========================================================================
    
    async def execute(self, state: MainState, use_agent: bool = False, **kwargs) -> MainState:
        """
        Unified execution entry - Core execution method of the Agent
        
        Select appropriate execution mode based on configuration to complete Agent's full execution flow.
        
        Args:
            state (MainState): Current state object
            use_agent (bool): Whether to use proxy mode (graph mode), default False
            **kwargs: Extra parameters, merged into pre-tool results
        
        Returns:
            MainState: Updated state object
        
        Execution flow:
            1. Check for strategy mode
            2. Check for VLM mode
            3. Execute pre-tools
            4. Select execution mode based on configuration:
               - Graph mode (use_agent=True with post-tools)
               - ReAct mode (react_mode=True)
               - Simple mode (default)
            5. Update state result
        
        Example:
            >>> state = await agent.execute(state, use_agent=True)
            >>> result = state.agent_results["Writer"]["results"]
        """
        # Save state reference
        self.state = state
        
        # ----- Strategy Mode Execution -----
        if self._execution_strategy:
            log.info(f"Executing with strategy mode: {self._execution_strategy.__class__.__name__}")
            try:
                pre_tool_results = await self.execute_pre_tools(state)
                result = await self._execution_strategy.execute(state, **kwargs)
                self.update_state_result(state, result, pre_tool_results)
                return state
            except Exception as e:
                log.exception(f"Strategy execution failed: {e}")
                error_result = {"error": str(e)}
                self.update_state_result(state, error_result, {})
                return state
            
        # ----- Normal Execution Flow -----
        log.info(f"Starting execution for {self.role_name} (ReAct mode: {self.react_mode}, Graph mode: {use_agent})")

        # VLM Mode
        if getattr(self, "use_vlm", False):
            log.critical(f'[base agent]: Taking multimodal path')
            result = await self._execute_vlm(state, **kwargs)
            self.update_state_result(state, result, {})
            log.info(f"{self.role_name} Multimodal execution complete")
            return state
        
        try:
            # 1. Execute pre-tools
            pre_tool_results = await self.execute_pre_tools(state)
            
            # 1.1 Write to temp_data
            try:
                if not hasattr(state, 'temp_data') or state.temp_data is None:
                    state.temp_data = {}
                state.temp_data['pre_tool_results'] = pre_tool_results
            except Exception:
                pass
            
            # 1.2 Merge kwargs into pre-tool results
            pre_tool_results.update(kwargs)
            
            # 2. Get post-tools
            post_tools = self.get_post_tools()
            
            # 3. Select processing method based on mode
            if use_agent and post_tools:
                # ----- Graph Mode -----
                log.info(f"[New Subgraph Mode] Automatically building {self.role_name} subgraph, "
                        f"Post-tools: {[t.name for t in post_tools]}")
                result = await self._execute_react_graph(state, pre_tool_results)
                self.update_state_result(state, result, pre_tool_results)
                log.info(f"[New Subgraph Mode] {self.role_name} subgraph mode execution complete")
                
                # Update temp_data
                if not hasattr(state, 'temp_data'):
                    state.temp_data = {}
                state.temp_data['pre_tool_results'] = pre_tool_results
                state.temp_data[f'{self.role_name}_instance'] = self
                
            elif self.react_mode:
                # ----- ReAct Mode -----
                log.info("ReAct Mode - with validation loop")
                result = await self.process_react_mode(state, pre_tool_results)
                self.update_state_result(state, result, pre_tool_results)
                log.info(f"{self.role_name} ReAct mode execution complete")
                
            else:
                # ----- Simple Mode -----
                if use_agent and not post_tools:
                    log.info("No post-tools available for graph mode, falling back to simple mode")
                result = await self.process_simple_mode(state, pre_tool_results)
                self.update_state_result(state, result, pre_tool_results)
                log.info(f"{self.role_name} Simple mode execution complete")
            
        except Exception as e:
            log.exception(f"{self.role_name} Execution failed: {e}")
            import traceback
            traceback.print_exc()
            error_result = {"error": str(e)}
            self.update_state_result(state, error_result, {})
            
        return state
    
    async def _execute_vlm(self, state: MainState, **kwargs) -> Dict[str, Any]:
        """
        Vision-LLM Specialized Execution Flow
        
        Completely decoupled from the text path, specifically handles Vision Language Model calls.
        
        Args:
            state (MainState): Current state object
            **kwargs: Additional parameters
        
        Returns:
            Dict[str, Any]: VLM execution results
        """
        # 1. Execute pre-tools
        pre_tool_results = await self.execute_pre_tools(state)
    
        # 2. Build messages
        mode = self.vlm_config.get("mode", "understanding")
        messages = self.build_messages(state, pre_tool_results)
    
        # 3. Call VisionLLMCaller
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
        log.info(f"{self.role_name} Multimodal raw response: {response}")
    
        # 4. 解析结果
        parsed = self.parse_result(response.content)
    
        # 5. Merge additional info (e.g., image path, base64, etc.)
        if hasattr(response, "additional_kwargs"):
            log.info(f"{self.role_name} Multimodal additional info: {response.additional_kwargs}")
            
            if isinstance(parsed, dict):
                parsed.update(response.additional_kwargs)
            elif isinstance(parsed, list):
                log.warning(f"{self.role_name} parsed is a list type, cannot call update, skipping additional parameters merge")
                log.info(f"parsed type: {type(parsed).__name__}, content: {parsed}")
                log.info(f"additional_kwargs content: {response.additional_kwargs}")
            else:
                log.warning(f"{self.role_name} parsed is {type(parsed).__name__} type, cannot call update, skipping additional parameters merge")
                log.info(f"parsed content: {parsed}")
                log.info(f"additional_kwargs content: {response.additional_kwargs}")
        
        return parsed
