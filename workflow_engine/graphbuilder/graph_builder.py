# graphbuilder/graph_builder.py
from __future__ import annotations

import asyncio
from typing import Callable, Dict, List, Tuple, Any
from pydantic import BaseModel
from langgraph.graph import StateGraph


class GenericGraphBuilder:
    """
    Enhanced Generic Graph Builder, supports:
    1. @pre_tool and @post_tool decorators
    2. Chained calls to add nodes, edges, and conditional edges
    3. Automatic tool registration and management
    """

    def __init__(self, state_model: type[BaseModel], entry_point: str = "start"):
        self.state_model = state_model
        self.entry_point = entry_point
        self.nodes: Dict[str, Tuple[Callable, str]] = {}  # name -> (func, role)
        self.edges: List[Tuple[str, str]] = []
        self.conditional_edges: Dict[str, Callable] = {}
        
        # Tool Register
        self.pre_tool_registry: Dict[str, Dict[str, Callable]] = {}  # role -> {name: func}
        self.post_tool_registry: Dict[str, List[Callable]] = {}     # role -> [func]
        
        # Lazy import tool_manager to avoid circular imports
        self.tool_manager = None

    def _get_tool_manager(self):
        """Lazy import tool_manager"""
        if self.tool_manager is None:
            from workflow_engine.toolkits.tool_manager import get_tool_manager
            self.tool_manager = get_tool_manager()
        return self.tool_manager

    def pre_tool(self, name: str, role: str):
        """Decorator: Register pre-tool to a specific role"""
        def decorator(func: Callable):
            if role not in self.pre_tool_registry:
                self.pre_tool_registry[role] = {}
            self.pre_tool_registry[role][name] = func
            return func
        return decorator

    def post_tool(self, role: str):
        """Decorator: Register post-tool to a specific role"""
        def decorator(func: Callable):
            if role not in self.post_tool_registry:
                self.post_tool_registry[role] = []
            self.post_tool_registry[role].append(func)
            return func
        return decorator

    def add_node(self, name: str, func: Callable, role: str = None) -> 'GenericGraphBuilder':
        """Add a single node, supports chaining"""
        self.nodes[name] = (func, role or name)
        return self

    def add_nodes(self, nodes: Dict[str, Callable], role_mapping: Dict[str, str] = None) -> 'GenericGraphBuilder':
        """Batch add nodes, supports role mapping"""
        role_mapping = role_mapping or {}
        for name, func in nodes.items():
            role = role_mapping.get(name, name)
            self.add_node(name, func, role)
        return self

    def add_edge(self, src: str, dst: str) -> 'GenericGraphBuilder':
        """Add a single edge"""
        self.edges.append((src, dst))
        return self

    def add_edges(self, edges: List[Tuple[str, str]]) -> 'GenericGraphBuilder':
        """Batch add edges"""
        self.edges.extend(edges)
        return self

    def add_conditional_edge(self, src: str, condition_func: Callable) -> 'GenericGraphBuilder':
        """Add a single conditional edge"""
        self.conditional_edges[src] = condition_func
        return self

    def add_conditional_edges(self, conditional_edges: Dict[str, Callable]) -> 'GenericGraphBuilder':
        """Batch add conditional edges"""
        self.conditional_edges.update(conditional_edges)
        return self

    def _register_tools_for_role(self, role: str, state: Any):
        """Register tools for a specific role"""
        tm = self._get_tool_manager()
        
        # Register pre-tools
        if role in self.pre_tool_registry:
            for tool_name, tool_func in self.pre_tool_registry[role].items():
                try:
                    tm.register_pre_tool(
                        name=tool_name,
                        role=role,
                        func=lambda s=state, f=tool_func: f(s),
                        override=True
                    )
                except TypeError:
                    # Compatible with versions that don't support the override parameter
                    tm.register_pre_tool(
                        name=tool_name,
                        role=role,
                        func=lambda s=state, f=tool_func: f(s)
                    )

        # Register post-tools
        if role in self.post_tool_registry:
            for tool_func in self.post_tool_registry[role]:
                tm.register_post_tool(tool_func, role=role)

    def _wrap_node_with_tools(self, node_func: Callable, role: str):
        """Wrap node with automatic tool registration logic"""
        async def wrapped_node(state):
            # Automatically register tools for the role before execution
            self._register_tools_for_role(role, state)
            
            # Execute original node function
            if asyncio.iscoroutinefunction(node_func):
                return await node_func(state)
            else:
                return node_func(state)
        
        return wrapped_node

    def build(self):
        """Build and return the compiled graph"""
        sg = StateGraph(self.state_model)
        
        # Add nodes (autowrap tool registration logic)
        for name, (func, role) in self.nodes.items():
            wrapped_func = self._wrap_node_with_tools(func, role)
            sg.add_node(name, wrapped_func)
        
        # Add normal edges
        for src, dst in self.edges:
            sg.add_edge(src, dst)
        
        # Add conditional edges
        for src, cond_func in self.conditional_edges.items():
            sg.add_conditional_edges(src, cond_func)
        
        sg.set_entry_point(self.entry_point)
        return sg.compile()