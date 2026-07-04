# Universal LLM Client Specification (v1.0)

## Overview
This specification defines a standard, declarative YAML format for configuring LLM connections across all agentic AI projects. 
The goal is to decouple the **configuration** of an LLM from the **implementation** of the caller. By standardizing the configuration, you can easily swap out the underlying engine (e.g., raw Langchain, LiteLLM, or custom HTTP clients) without changing the agent's logic.

This approach is specifically designed to support both **Open Source / Local models** (HuggingFace, Ollama, vLLM) and **Commercial Cloud models** (OpenAI, Anthropic, Bedrock).

---

## 1. The Configuration Schema (`llm_config.yaml`)

Every agent or project should define its LLM connection using this standard schema.

```yaml
version: "1.0"

connection:
  # The provider group (e.g., huggingface, local_vllm, openai, anthropic, bedrock)
  provider: "huggingface"
  
  # The specific model identifier
  model: "meta-llama/Meta-Llama-3-8B-Instruct"
  
  # Optional: The base URL. CRITICAL for local models (e.g., http://localhost:8000/v1) or HF Inference Endpoints
  endpoint: "https://api-inference.huggingface.co/models/"
  
  # Authentication details
  auth:
    type: "env"                      # Options: env, explicit, none (for local)
    key_name: "HF_TOKEN"             # The environment variable to look for

parameters:
  # Standard generation parameters
  temperature: 0.1
  max_tokens: 4096
  top_p: 0.95
  
capabilities:
  # Explicitly declare what this specific model can do. 
  # This prevents the workflow engine from sending unsupported requests (like images to a text-only model).
  supports_vision: false
  supports_tools: true
  supports_streaming: true
  context_window_size: 8192
```

---

## 2. Supported Provider Types

To ensure the factory/generator knows how to construct the client, `provider` must fall into one of these buckets:

1. **`openai_compatible`**: Uses the standard OpenAI REST schema.
   - *Use cases*: OpenAI, Groq, Together, DeepSeek.
2. **`local_vllm` / `local_ollama`**: Subsets of `openai_compatible` but explicitly signal that no API key is required and routing goes to `localhost`.
3. **`huggingface`**: Uses the HuggingFace Inference API (Serverless or Dedicated). Needs specific header formatting (`Authorization: Bearer <TOKEN>`).
4. **`anthropic`**: Uses Anthropic's Messages API (requires special handling for system prompts).
5. **`bedrock`**: Uses AWS's Converse API (requires AWS IAM SigV4 signing instead of standard Bearer tokens).
6. **`gemini`**: Uses Google's GenerateContent API.

---

## 3. Architecture Implementation Guide

When implementing this spec in a new project, follow these steps:

### Phase 1: The Loader
Write a simple utility that reads `llm_config.yaml` and parses it into a Python Dataclass (`LLMConfig`).

### Phase 2: The Factory (The "Generator")
Write a factory function that takes the `LLMConfig` dataclass and returns a `BaseLLMClient`. 

Because you use a declarative YAML, you can change the implementation of this factory at any time without touching the agents.
- **Iteration 1**: The factory returns the existing custom callers from the `Agent` project.
- **Iteration 2**: The factory returns a `LiteLLM` wrapper.
- **Iteration 3**: The factory generates raw `aiohttp` async requests for maximum performance.

### Phase 3: The Interface (`BaseLLMClient`)
No matter what the factory uses under the hood, the client it returns must adhere to a strict Python interface:

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseLLMClient(ABC):
    @abstractmethod
    async def chat(self, messages: List[Dict[str, Any]], tools: List[Dict] = None) -> str:
        """
        Executes a chat completion.
        Messages should ALWAYS follow the format: [{"role": "user", "content": "hello"}]
        """
        pass
        
    @property
    @abstractmethod
    def capabilities(self) -> Dict[str, bool]:
        """Returns the capabilities defined in the YAML config."""
        pass
```

## Summary
By adopting this YAML spec, you achieve your goal: **Big and complete for architectural learning, but simple to use.** 
You just drop the `llm_config.yaml` into your project, read it, and let the factory instantiate the connection. It seamlessly bridges free local HuggingFace models and enterprise AWS Bedrock models behind a single interface.
