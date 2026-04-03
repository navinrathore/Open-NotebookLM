"""
Complete integration of Ali DeepResearch into Open-NotebookLM
Uses internal deep_research module
"""
import os
import json
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path

from workflow_engine.logger import get_logger
from fastapi_app.deep_research.react_agent import MultiTurnReactAgent
from qwen_agent.llm.schema import Message

log = get_logger(__name__)


class DeepResearchIntegration:
    """Full integration of Ali DeepResearch"""

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        max_iterations: Optional[int] = None,
        serper_key: Optional[str] = None,
        jina_keys: Optional[str] = None,
        dashscope_key: Optional[str] = None,
        sandbox_endpoints: Optional[str] = None,
    ):
        # Configuration parameters (priority: passed parameters > environment variables)
        self.model_name = model_name or os.getenv("DEEP_RESEARCH_MODEL", "qwen-plus")
        self.api_base = api_base or os.getenv("DEEP_RESEARCH_API_BASE", "http://127.0.0.1:6001")
        self.api_key = api_key or os.getenv("DEEP_RESEARCH_API_KEY", "EMPTY")
        self.max_iterations = max_iterations or int(os.getenv("DEEP_RESEARCH_MAX_ITERATIONS", "50"))

        # Tool configuration (priority: passed parameters > environment variables)
        self.serper_key = serper_key or os.getenv("SERPER_KEY_ID", os.getenv("SERPER_API_KEY", ""))
        self.jina_keys = jina_keys or os.getenv("JINA_API_KEYS", "")
        self.dashscope_key = dashscope_key or os.getenv("DASHSCOPE_API_KEY", "")
        self.sandbox_endpoints = sandbox_endpoints or os.getenv("SANDBOX_FUSION_ENDPOINT", "")

        # Debug logging
        log.info(f"[DeepResearchIntegration] Initializing configuration:")
        log.info(f"  - model_name: {self.model_name}")
        log.info(f"  - api_base: {self.api_base}")
        log.info(f"  - serper_key: {'***' if self.serper_key else 'None'} (length: {len(self.serper_key) if self.serper_key else 0})")
        log.info(f"  - jina_keys: {'***' if self.jina_keys else 'None'}")
        log.info(f"  - max_iterations: {self.max_iterations}")

    async def run_research(
        self,
        query: str,
        max_iterations: Optional[int] = None,
        temperature: float = 0.85,
        presence_penalty: float = 1.1,
    ) -> Dict[str, Any]:
        """
        Run complete DeepResearch reasoning.

        Args:
            query: Research question
            max_iterations: Maximum iterations
            temperature: Sampling temperature
            presence_penalty: Presence penalty

        Returns:
            {
                "success": bool,
                "query": str,
                "answer": str,
                "messages": List[Dict],
                "sources": List[Dict],
                "termination": str,
                "iterations": int
            }
        """
        log.info(f"[DeepResearch] Starting research: {query}")

        try:
            # Check necessary configuration
            if not self.serper_key:
                raise ValueError("SERPER_KEY_ID or SERPER_API_KEY is not configured")

            # ⚠️ Important: Set environment variables before creating the Agent
            # because tools read them during module loading.
            import os
            os.environ["SERPER_KEY_ID"] = self.serper_key
            if self.jina_keys:
                os.environ["JINA_API_KEYS"] = self.jina_keys
            if self.dashscope_key:
                os.environ["DASHSCOPE_API_KEY"] = self.dashscope_key

            # ⚠️ Visit tool's call_server needs these three environment variables to call LLM for page summary
            os.environ["API_KEY"] = self.api_key
            os.environ["API_BASE"] = self.api_base
            os.environ["SUMMARY_MODEL_NAME"] = self.model_name

            # Configure LLM
            llm_config = {
                "model": self.model_name,
                "api_base": self.api_base,
                "api_key": self.api_key,
                "generate_cfg": {
                    "temperature": temperature,
                    "top_p": 0.95,
                    "presence_penalty": presence_penalty,
                    "max_tokens": 10000,
                }
            }

            # Create Agent
            agent = MultiTurnReactAgent(llm=llm_config)

            # Set maximum iterations
            max_iter = max_iterations or self.max_iterations

            # Run reasoning (run in thread pool to avoid blocking)
            result = await asyncio.to_thread(
                self._run_agent_sync,
                agent,
                query,
                max_iter
            )

            log.info(f"[DeepResearch] Research completed, iterations: {result['iterations']}")

            return result

        except ImportError as e:
            log.error(f"[DeepResearch] Import failed: {e}")
            return {
                "success": False,
                "query": query,
                "answer": "",
                "messages": [],
                "sources": [],
                "error": f"DeepResearch module import failed: {str(e)}",
                "termination": "import_error"
            }
        except Exception as e:
            log.error(f"[DeepResearch] Execution failed: {e}")
            return {
                "success": False,
                "query": query,
                "answer": "",
                "messages": [],
                "sources": [],
                "error": str(e),
                "termination": "error"
            }

    def _run_agent_sync(self, agent, query, max_iterations):
        """Run Agent synchronously (called in thread pool)"""
        try:
            # Construct data parameter, following requirements of original _run method
            # Pass full API base URL instead of port number
            data = {
                "item": {
                    "question": query,
                    "answer": ""  # Unknown answer, leave blank
                },
                "planning_port": self.api_base  # Pass full API base URL
            }

            log.info(f"[DeepResearch] Calling Agent, API base: {self.api_base}, model: {self.model_name}")

            # Call Agent's _run method
            result = agent._run(
                data=data,
                model=self.model_name
            )

            # Parse results
            messages = result.get("messages", [])
            answer = result.get("prediction", "")
            termination = result.get("termination", "unknown")

            # Extract sources
            sources = self._extract_sources_from_messages(messages)

            return {
                "success": True,
                "query": query,
                "answer": answer,
                "messages": messages,
                "sources": sources,
                "termination": termination,
                "iterations": len([m for m in messages if m.get("role") == "assistant"])
            }

        except Exception as e:
            log.error(f"[DeepResearch] Agent run failed: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _extract_answer(self, messages: List) -> str:
        """Extract final answer from messages list"""
        for msg in reversed(messages):
            content = str(msg.content) if hasattr(msg, 'content') else str(msg)

            # Look for <answer> tag
            if "<answer>" in content and "</answer>" in content:
                import re
                match = re.search(r'<answer>(.*?)</answer>', content, re.DOTALL)
                if match:
                    return match.group(1).strip()

            # If no answer tag, return last assistant message
            if hasattr(msg, 'role') and msg.role == "assistant":
                # Remove think tag
                import re
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
                content = re.sub(r'<tool_call>.*?</tool_call>', '', content, flags=re.DOTALL)
                return content.strip()

        return "No answer generated"

    def _extract_sources(self, messages: List) -> List[Dict]:
        """Extract quoted sources from messages (Message object compatible)"""
        sources = []
        seen_urls = set()

        for msg in messages:
            content = str(msg.content) if hasattr(msg, 'content') else str(msg)

            # Extract URLs from tool_response
            if "<tool_response>" in content:
                import re
                # Extract all URLs
                urls = re.findall(r'https?://[^\s<>"\']+', content)
                for url in urls:
                    if url not in seen_urls:
                        seen_urls.add(url)
                        sources.append({
                            "url": url,
                            "type": "web_search"
                        })

        return sources

    def _extract_sources_from_messages(self, messages: List[Dict]) -> List[Dict]:
        """Extract quoted sources from messages list of dicts"""
        sources = []
        seen_urls = set()

        for msg in messages:
            content = msg.get("content", "")

            # Extract URLs from tool_response
            if "<tool_response>" in content:
                import re
                # Extract all URLs
                urls = re.findall(r'https?://[^\s<>"\']+', content)
                for url in urls:
                    if url not in seen_urls:
                        seen_urls.add(url)
                        sources.append({
                            "url": url,
                            "type": "web_search"
                        })

        return sources

    def _determine_termination(self, messages: List, max_iterations: int) -> str:
        """Determine termination reason"""
        if not messages:
            return "no_messages"

        last_msg = messages[-1]
        content = str(last_msg.content) if hasattr(last_msg, 'content') else str(last_msg)

        if "<answer>" in content and "</answer>" in content:
            return "answer"

        assistant_count = len([m for m in messages if hasattr(m, 'role') and m.role == "assistant"])
        if assistant_count >= max_iterations:
            return "max_iterations"

        return "unknown"

    def _message_to_dict(self, msg) -> Dict:
        """Convert Message object to dict"""
        if hasattr(msg, 'role') and hasattr(msg, 'content'):
            return {
                "role": msg.role,
                "content": msg.content
            }
        else:
            return {
                "role": "unknown",
                "content": str(msg)
            }

    def format_result_as_markdown(self, result: Dict[str, Any]) -> str:
        """Format research results as Markdown"""
        md_lines = [
            f"# Deep Research: {result['query']}",
            "",
            "## Research Answer",
            "",
            result.get("answer", "No answer generated."),
            "",
        ]

        # Add sources
        sources = result.get("sources", [])
        if sources:
            md_lines.extend([
                "## Sources",
                "",
            ])
            for i, source in enumerate(sources, 1):
                url = source.get("url", "")
                md_lines.append(f"{i}. [{url}]({url})")
            md_lines.append("")

        # Add metadata
        md_lines.extend([
            "---",
            "",
            "**Metadata:**",
            f"- Termination: {result.get('termination', 'unknown')}",
            f"- Iterations: {result.get('iterations', 0)}",
            f"- Total messages: {len(result.get('messages', []))}",
            "",
        ])

        return "\n".join(md_lines)

    async def check_dependencies(self) -> Dict[str, bool]:
        """Check if dependencies are met"""
        checks = {
            "serper_key": bool(self.serper_key),
            "jina_keys": bool(self.jina_keys),
            "qwen_agent": False,
        }

        try:
            import qwen_agent
            checks["qwen_agent"] = True
        except ImportError:
            pass

        return checks

    def get_config_info(self) -> Dict[str, Any]:
        """Get configuration information"""
        return {
            "model": self.model_name,
            "api_base": self.api_base,
            "max_iterations": self.max_iterations,
            "serper_configured": bool(self.serper_key),
            "jina_configured": bool(self.jina_keys),
            "dashscope_configured": bool(self.dashscope_key),
            "sandbox_configured": bool(self.sandbox_endpoints),
        }
