"""
DeepResearch Module
Deep research agent system from Alibaba Qwen Laboratory
Fully integrated into Open-NotebookLM
"""

from .react_agent import MultiTurnReactAgent
from .tool_search import Search
from .tool_visit import Visit
from .tool_python import PythonInterpreter
from .tool_scholar import Scholar
from .tool_file import FileParser

__all__ = [
    'MultiTurnReactAgent',
    'Search',
    'Visit',
    'PythonInterpreter',
    'Scholar',
    'FileParser',
]
