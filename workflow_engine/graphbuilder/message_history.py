from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Literal
from datetime import datetime, timedelta
from langchain_core.messages import (
    BaseMessage, 
    HumanMessage, 
    AIMessage, 
    SystemMessage,
    ToolMessage,
    RemoveMessage
)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.message import add_messages, REMOVE_ALL_MESSAGES
from langchain_core.messages.utils import trim_messages
import hashlib

# ==================== Core Wrapper Class ====================
@dataclass
class AdvancedMessageHistory:
    """
    Advanced Message History Manager - Encapsulates LangGraph native capabilities.
    
    Features:
    1. Message merging (multi-source, deduplication)
    2. Message filtering (type, time, content)
    3. Message cleaning (bulk, compression)
    4. Unified interface (hides underlying complexity)
    """
    
    # ===== Core Configuration =====
    checkpointer: BaseCheckpointSaver = field(default_factory=MemorySaver)
    thread_id: str = "default"
    
    # ===== History Management Configuration =====
    max_messages: int = 100
    max_tokens: Optional[int] = None
    max_age_hours: Optional[int] = None  # Maximum message retention time
    
    # ===== Message Processing Configuration =====
    auto_deduplicate: bool = True  # Automatic deduplication
    keep_system_messages: bool = True  # Always keep system messages
    
    # ===== Internal Cache =====
    _message_cache: Dict[str, BaseMessage] = field(default_factory=dict, init=False)
    _metadata_cache: Dict[str, Dict[str, Any]] = field(default_factory=dict, init=False)
    
    def __post_init__(self):
        """Initialize configuration"""
        self._ensure_checkpointer()
    
    def _ensure_checkpointer(self):
        """Ensure Checkpointer is initialized"""
        if self.checkpointer is None:
            self.checkpointer = MemorySaver()
    
    # ==================== Core Methods: Message Operations ====================
    
    def add_messages(
        self,
        messages: List[BaseMessage],
        deduplicate: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add messages to history (supports deduplication).
        
        Args:
            messages: List of messages to add
            deduplicate: Whether to deduplicate (None uses default config)
            metadata: Message metadata
        
        Example:
            >>> history.add_messages([
            ...     HumanMessage(content="Hello"),
            ...     AIMessage(content="Hi there!")
            ... ])
        """
        deduplicate = deduplicate if deduplicate is not None else self.auto_deduplicate
        
        # Deduplication processing
        if deduplicate:
            messages = self._deduplicate_messages(messages)
        
        # Add metadata
        if metadata:
            for msg in messages:
                msg_id = self._get_message_id(msg)
                self._metadata_cache[msg_id] = metadata
        
        # Use LangGraph native mechanism to save.
        # Here we don't use checkpointer directly, but return update instructions
        # to let LangGraph's state management system handle it.
        return messages
    
    def merge_histories(
        self,
        *histories: List[BaseMessage],
        strategy: Literal["chronological", "interleave", "priority"] = "chronological"
    ) -> List[BaseMessage]:
        """
        Merge multiple message histories.
        
        Args:
            histories: Multiple lists of message histories
            strategy: Merge strategy
                - chronological: By time order
                - interleave: Alternate merging
                - priority: By priority (first list has priority)
        
        Example:
            >>> history1 = [HumanMessage(content="Q1"), AIMessage(content="A1")]
            >>> history2 = [HumanMessage(content="Q2"), AIMessage(content="A2")]
            >>> merged = manager.merge_histories(history1, history2)
        """
        if not histories:
            return []
        
        if strategy == "chronological":
            return self._merge_chronological(*histories)
        elif strategy == "interleave":
            return self._merge_interleave(*histories)
        elif strategy == "priority":
            return self._merge_priority(*histories)
        else:
            raise ValueError(f"Unknown merge strategy: {strategy}")
    
    def filter_messages(
        self,
        messages: List[BaseMessage],
        message_types: Optional[List[type]] = None,
        content_pattern: Optional[str] = None,
        time_range: Optional[tuple[datetime, datetime]] = None,
        custom_filter: Optional[Callable[[BaseMessage], bool]] = None
    ) -> List[BaseMessage]:
        """
        Filter messages.
        
        Args:
            messages: List of messages to filter
            message_types: Message types to keep (e.g., [HumanMessage, AIMessage])
            content_pattern: Content matching pattern (regex)
            time_range: Time range (start, end)
            custom_filter: Custom filter function
        
        Example:
            >>> # Keep only Human and AI messages
            >>> filtered = manager.filter_messages(
            ...     messages,
            ...     message_types=[HumanMessage, AIMessage]
            ... )
        """
        filtered = messages
        
        # Filter by type
        if message_types:
            filtered = [m for m in filtered if type(m) in message_types]
        
        # Filter by content
        if content_pattern:
            import re
            pattern = re.compile(content_pattern)
            filtered = [m for m in filtered if pattern.search(m.content)]
        
        # Filter by time
        if time_range:
            filtered = self._filter_by_time(filtered, time_range)
        
        # Custom filter
        if custom_filter:
            filtered = [m for m in filtered if custom_filter(m)]
        
        return filtered
    
    def clean_messages(
        self,
        messages: List[BaseMessage],
        remove_duplicates: bool = True,
        remove_empty: bool = True,
        compress_consecutive: bool = True,
        max_length: Optional[int] = None
    ) -> List[BaseMessage]:
        """
        Clean message history.
        
        Args:
            messages: List of messages to clean
            remove_duplicates: Remove duplicate messages
            remove_empty: Remove empty messages
            compress_consecutive: Compress consecutive messages of the same type
            max_length: Maximum number of messages to keep
        
        Example:
            >>> cleaned = manager.clean_messages(
            ...     messages,
            ...     remove_duplicates=True,
            ...     compress_consecutive=True
            ... )
        """
        result = list(messages)
        
        # Remove empty messages
        if remove_empty:
            result = [m for m in result if m.content and m.content.strip()]
        
        # Deduplicate
        if remove_duplicates:
            result = self._deduplicate_messages(result)
        
        # Compress consecutive messages
        if compress_consecutive:
            result = self._compress_consecutive_messages(result)
        
        # Length limitation
        if max_length and len(result) > max_length:
            # Keep system messages
            if self.keep_system_messages:
                system_msgs = [m for m in result if isinstance(m, SystemMessage)]
                other_msgs = [m for m in result if not isinstance(m, SystemMessage)]
                result = system_msgs + other_msgs[-(max_length - len(system_msgs)):]
            else:
                result = result[-max_length:]
        
        return result
    
    def trim_messages_smart(
        self,
        messages: List[BaseMessage],
        max_tokens: Optional[int] = None,
        strategy: Literal["last", "first", "summary"] = "last"
    ) -> List[BaseMessage]:
        """
        Smart message trimming (based on LangGraph's trim_messages).
        
        Args:
            messages: List of messages to trim
            max_tokens: Maximum number of tokens
            strategy: Trimming strategy
        
        Example:
            >>> trimmed = manager.trim_messages_smart(
            ...     messages,
            ...     max_tokens=1000,
            ...     strategy="last"
            ... )
        """
        max_tokens = max_tokens or self.max_tokens
        
        if not max_tokens:
            return messages
        
        if strategy == "summary":
            # Use summary strategy
            return self._trim_with_summary(messages, max_tokens)
        else:
            # Use LangGraph native trim_messages
            return trim_messages(
                messages,
                strategy=strategy,
                max_tokens=max_tokens,
                token_counter=len,  # Can be replaced with a more precise counter
                start_on="human",
                end_on=("human", "tool")
            )
    
    # ==================== Helper Methods ====================
    
    def _get_message_id(self, message: BaseMessage) -> str:
        """Generate a unique ID for a message."""
        if hasattr(message, 'id') and message.id:
            return message.id
        
        # Generate ID based on content
        content = f"{message.type}:{message.content}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _deduplicate_messages(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """Deduplicate messages."""
        seen = set()
        result = []
        
        for msg in messages:
            msg_id = self._get_message_id(msg)
            if msg_id not in seen:
                seen.add(msg_id)
                result.append(msg)
        
        return result
    
    def _compress_consecutive_messages(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """Compress consecutive messages of the same type."""
        if not messages:
            return []
        
        result = []
        current_group = [messages[0]]
        
        for msg in messages[1:]:
            if type(msg) == type(current_group[0]):
                current_group.append(msg)
            else:
                # Merge current group
                if len(current_group) > 1:
                    merged_content = "\n\n".join(m.content for m in current_group)
                    merged_msg = type(current_group[0])(content=merged_content)
                    result.append(merged_msg)
                else:
                    result.append(current_group[0])
                
                current_group = [msg]
        
        # Handle the last group
        if len(current_group) > 1:
            merged_content = "\n\n".join(m.content for m in current_group)
            merged_msg = type(current_group[0])(content=merged_content)
            result.append(merged_msg)
        else:
            result.append(current_group[0])
        
        return result
    
    def _merge_chronological(self, *histories: List[BaseMessage]) -> List[BaseMessage]:
        """Merge by chronological order."""
        all_messages = []
        for history in histories:
            all_messages.extend(history)
        
        # Assume messages have timestamps, otherwise maintain original order
        return sorted(
            all_messages,
            key=lambda m: getattr(m, 'timestamp', datetime.now())
        )
    
    def _merge_interleave(self, *histories: List[BaseMessage]) -> List[BaseMessage]:
        """Merge by interleaving."""
        result = []
        max_len = max(len(h) for h in histories)
        
        for i in range(max_len):
            for history in histories:
                if i < len(history):
                    result.append(history[i])
        
        return result
    
    def _merge_priority(self, *histories: List[BaseMessage]) -> List[BaseMessage]:
        """Merge by priority (keep the first occurrence when deduplicating)."""
        result = []
        seen = set()
        
        for history in histories:
            for msg in history:
                msg_id = self._get_message_id(msg)
                if msg_id not in seen:
                    seen.add(msg_id)
                    result.append(msg)
        
        return result
    
    def _filter_by_time(
        self,
        messages: List[BaseMessage],
        time_range: tuple[datetime, datetime]
    ) -> List[BaseMessage]:
        """Filter by time."""
        start, end = time_range
        return [
            m for m in messages
            if hasattr(m, 'timestamp') and start <= m.timestamp <= end
        ]
    
    def _trim_with_summary(
        self,
        messages: List[BaseMessage],
        max_tokens: int
    ) -> List[BaseMessage]:
        """Trim using a summary strategy."""
        # This could integrate LangMem's SummarizationNode
        # Simplified version: keep only recent messages + a summary
        
        from langchain_core.messages.utils import count_tokens_approximately
        
        current_tokens = count_tokens_approximately(messages)
        
        if current_tokens <= max_tokens:
            return messages
        
        # Keep system messages
        system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
        other_msgs = [m for m in messages if not isinstance(m, SystemMessage)]
        
        # Simple strategy: keep the last 10 messages + summary of previous ones
        # In practice, this should call an LLM to generate a summary.
        summary_content = f"[Earlier conversation summarized: {len(other_msgs) - 10} messages]"
        summary_msg = SystemMessage(content=summary_content)
        
        return system_msgs + [summary_msg] + other_msgs[-10:]
    

    
    def get_messages(
        self, 
        thread_id: Optional[str] = None,
        limit: Optional[int] = None,
        before: Optional[str] = None
    ) -> List[BaseMessage]:
        """
        Get message history.
        
        Args:
            thread_id: Thread ID, if None, use default thread
            limit: Limit the number of messages returned
            before: Get messages before the specified checkpoint_id
            
        Returns:
            List of messages
            
        Example:
            >>> # Get all messages for the default thread
            >>> messages = manager.get_messages()
            >>> 
            >>> # Get the latest 10 messages for a specified thread
            >>> messages = manager.get_messages(thread_id="session_1", limit=10)
        """
        # Use provided thread_id or default value
        tid = thread_id or self.thread_id
        
        # Build configuration
        config = {"configurable": {"thread_id": tid}}
        
        try:
            # If before is specified, add it to the configuration
            if before:
                config["configurable"]["checkpoint_id"] = before
            
            # Get latest state from checkpointer
            checkpoint = self.checkpointer.get(config)
            
            if checkpoint is None:
                return []
            
            # Extract messages from checkpoint
            messages = []
            if hasattr(checkpoint, 'values'):
                # checkpoint.values is a dictionary containing the full state
                state = checkpoint.values
                if isinstance(state, dict) and 'messages' in state:
                    messages = state['messages']
                elif isinstance(state, dict):
                    # Try to get from other possible keys
                    for key in ['message', 'msg', 'history']:
                        if key in state:
                            messages = state[key]
                            break
            
            # Ensure return is a list
            if not isinstance(messages, list):
                messages = [messages] if messages else []
            
            # Apply limit
            if limit and len(messages) > limit:
                messages = messages[-limit:]  # Take the latest N messages
            
            return messages
            
        except Exception as e:
            # If retrieval fails, return an empty list
            # Logs should be recorded in production environments
            import logging
            logging.warning(f"Failed to get messages for thread {tid}: {e}")
            return []

    def save_messages(
        self,
        messages: List[BaseMessage],
        thread_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Save messages to checkpointer.
        
        Args:
            messages: List of messages to save
            thread_id: Thread ID
            metadata: Additional metadata
            
        Returns:
            Whether saved successfully
            
        Example:
            >>> success = manager.save_messages([
            ...     HumanMessage(content="Hello"),
            ...     AIMessage(content="Hi!")
            ... ], thread_id="session_1")
        """
        tid = thread_id or self.thread_id
        config = {"configurable": {"thread_id": tid}}
        
        try:
            # Build the state to save
            state = {"messages": messages}
            if metadata:
                state["metadata"] = metadata
            
            # Use checkpointer's put method to save
            # Note: Different checkpointer implementations might have different interfaces
            # Here we provide a general implementation
            from langgraph.checkpoint.base import Checkpoint
            
            checkpoint = Checkpoint(
                v=1,
                ts=datetime.now().isoformat(),
                id=hashlib.md5(f"{tid}:{datetime.now()}".encode()).hexdigest(),
                channel_values=state,
                channel_versions={},
                versions_seen={}
            )
            
            self.checkpointer.put(config, checkpoint, metadata or {})
            return True
            
        except Exception as e:
            import logging
            logging.error(f"Failed to save messages for thread {tid}: {e}")
            return False
            
    # New methods ===========================================
    def get_message_count(self, thread_id: Optional[str] = None) -> int:
        """
        Get the number of messages.
        
        Args:
            thread_id: Thread ID
            
        Returns:
            Number of messages
            
        Example:
            >>> count = manager.get_message_count("session_1")
            >>> print(f"Total messages: {count}")
        """
        messages = self.get_messages(thread_id)
        return len(messages)

    def delete_messages(
        self,
        thread_id: Optional[str] = None,
        before: Optional[datetime] = None
    ) -> bool:
        """
        Delete message history.
        
        Args:
            thread_id: Thread ID, if None, delete default thread
            before: Delete messages before this time (if None, delete all)
            
        Returns:
            Whether deletion was successful
            
        Example:
            >>> # Delete history of the entire thread
            >>> manager.delete_messages("session_1")
            >>> 
            >>> # Delete messages from 7 days ago
            >>> from datetime import datetime, timedelta
            >>> week_ago = datetime.now() - timedelta(days=7)
            >>> manager.delete_messages("session_1", before=week_ago)
        """
        tid = thread_id or self.thread_id
        
        try:
            if before:
                # Get existing messages
                messages = self.get_messages(tid)
                
                # Filter messages to keep
                kept_messages = [
                    m for m in messages
                    if not hasattr(m, 'timestamp') or m.timestamp >= before
                ]
                
                # Save filtered messages
                return self.save_messages(kept_messages, tid)
            else:
                # Delete entire thread
                config = {"configurable": {"thread_id": tid}}
                
                # Save empty message list
                return self.save_messages([], tid)
                
        except Exception as e:
            import logging
            logging.error(f"Failed to delete messages for thread {tid}: {e}")
            return False

    def get_all_threads(self) -> List[str]:
        """
        Get all thread IDs.
        
        Returns:
            List of thread IDs
            
        Example:
            >>> threads = manager.get_all_threads()
            >>> for thread in threads:
            ...     print(f"Thread: {thread}")
        """
        try:
            # This method depends on the checkpointer implementation.
            # MemorySaver might need to iterate through internal storage.
            # PostgresSaver can query the database.
            
            # For MemorySaver
            if hasattr(self.checkpointer, 'storage'):
                storage = self.checkpointer.storage
                threads = set()
                for key in storage.keys():
                    # Key format is usually (thread_id, checkpoint_ns, checkpoint_id)
                    if isinstance(key, tuple) and len(key) >= 1:
                        threads.add(key[0])
                return list(threads)
            
            # Different implementations might require different methods
            return []
            
        except Exception as e:
            import logging
            logging.warning(f"Failed to get all threads: {e}")
            return []

    def get_latest_checkpoint_id(self, thread_id: Optional[str] = None) -> Optional[str]:
        """
        Get the latest checkpoint ID.
        
        Args:
            thread_id: Thread ID
            
        Returns:
            Latest checkpoint ID, or None if none exist
            
        Example:
            >>> checkpoint_id = manager.get_latest_checkpoint_id("session_1")
            >>> if checkpoint_id:
            ...     print(f"Latest checkpoint: {checkpoint_id}")
        """
        tid = thread_id or self.thread_id
        config = {"configurable": {"thread_id": tid}}
        
        try:
            checkpoint = self.checkpointer.get(config)
            if checkpoint and hasattr(checkpoint, 'id'):
                return checkpoint.id
            return None
        except:
            return None

    def get_message_history(
        self,
        thread_id: Optional[str] = None,
        limit: Optional[int] = None,
        include_metadata: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get detailed message history (including metadata).
        
        Args:
            thread_id: Thread ID
            limit: Limit the number returned
            include_metadata: Whether to include metadata
            
        Returns:
            Message history list, each element containing the message and optional metadata
            
        Example:
            >>> history = manager.get_message_history(
            ...     thread_id="session_1",
            ...     limit=10,
            ...     include_metadata=True
            ... )
            >>> for item in history:
            ...     print(f"Message: {item['message'].content}")
            ...     if 'metadata' in item:
            ...         print(f"Metadata: {item['metadata']}")
        """
        messages = self.get_messages(thread_id, limit)
        
        result = []
        for msg in messages:
            item = {"message": msg}
            
            if include_metadata:
                msg_id = self._get_message_id(msg)
                if msg_id in self._metadata_cache:
                    item["metadata"] = self._metadata_cache[msg_id]
            
            result.append(item)
        
        return result

    def clear_cache(self):
        """
        Clear internal cache.
        
        Example:
            >>> manager.clear_cache()
        """
        self._message_cache.clear()
        self._metadata_cache.clear()

    def export_history(
        self,
        thread_id: Optional[str] = None,
        format: Literal["json", "dict", "markdown"] = "dict"
    ) -> Any:
        """
        Export message history.
        
        Args:
            thread_id: Thread ID
            format: Export format
                - json: JSON string
                - dict: Python dictionary
                - markdown: Markdown format text
            
        Returns:
            Exported data
            
        Example:
            >>> # Export as dictionary
            >>> data = manager.export_history("session_1", format="dict")
            >>> 
            >>> # Export as JSON
            >>> json_str = manager.export_history("session_1", format="json")
            >>> 
            >>> # Export as Markdown
            >>> md = manager.export_history("session_1", format="markdown")
        """
        messages = self.get_messages(thread_id)
        
        if format == "dict":
            return {
                "thread_id": thread_id or self.thread_id,
                "message_count": len(messages),
                "messages": [
                    {
                        "type": msg.type,
                        "content": msg.content,
                        "id": self._get_message_id(msg)
                    }
                    for msg in messages
                ]
            }
        
        elif format == "json":
            import json
            data = self.export_history(thread_id, format="dict")
            return json.dumps(data, indent=2, ensure_ascii=False)
        
        elif format == "markdown":
            lines = [f"# Chat History - {thread_id or self.thread_id}\n"]
            for i, msg in enumerate(messages, 1):
                role = msg.type.upper()
                lines.append(f"## Message {i} - {role}")
                lines.append(f"{msg.content}\n")
            return "\n".join(lines)
        
        else:
            raise ValueError(f"Unknown format: {format}")
        

        
    #     # ==================== Scenario: Clean and optimize history ====================
    # # 1. Get messages
    # messages = history_manager.get_messages("session_1")

    # # 2. Clean messages (deduplicate, remove empty)
    # cleaned = history_manager.clean_messages(
    #     messages,
    #     remove_duplicates=True,
    #     remove_empty=True,
    #     compress_consecutive=True
    # )

    # # 3. Filter to keep only dialogue messages
    # dialogue_only = history_manager.filter_messages(
    #     cleaned,
    #     message_types=[HumanMessage, AIMessage]
    # )

    # # 4. Smart trimming
    # trimmed = history_manager.trim_messages_smart(
    #     dialogue_only,
    #     max_tokens=2000,
    #     strategy="last"
    # )

    # # 5. Save optimized history
    # history_manager.save_messages(trimmed, "session_1")

    # print(f"Optimization complete: {len(messages)} -> {len(trimmed)} messages")