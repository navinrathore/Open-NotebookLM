# LLM Caller Refactoring Proposal

This document outlines a future refactoring plan for the LLM caller implementations in `workflow_engine/llm_callers/`. The goal is to move towards a more robust, enterprise-grade `BaseLLMClient` pattern, decoupling the logic from specific providers (e.g., OpenAI) and the overall workflow state.

## Current State Critique

1. **Provider Lock-in & Hardcoded SDKs**: `TextLLMCaller` directly imports and uses `ChatOpenAI`. This violates the architectural rule to be provider-agnostic.
2. **Tight Coupling to Workflow State**: `BaseLLMCaller` takes `MainState` in its constructor, tightly coupling the LLM client to the overarching workflow instead of a simple configuration object.
3. **Mixing Concerns in VisionLLMCaller**: `VisionLLMCaller` acts as a "God Class" that handles general image understanding, OCR, video understanding, and importantly, **image generation/editing**. Image generation should be separate from chat completions. It also uses hardcoded string matching for specific model quirks (e.g., `qwen-vl-ocr`).
4. **Bypassing Abstractions**: `VisionLLMCaller` bypasses Langchain's native `ainvoke` and manually extracts messages to call custom external functions, losing the benefits of standardized message schemas.

## Proposed Architecture (`BaseLLMClient` Pattern)

To make the LLM integration enterprise-ready, we propose the following changes:

1. **Abstract the Provider (Factory Pattern)**:
   - Define a pure interface `BaseLLMClient`.
   - Implement concrete adapters like `OpenAIClient`, `AnthropicClient`, etc.
   - Use a factory function (e.g., `get_llm_client(config)`) to return the correct client based on the requested provider.

2. **Decouple from `MainState`**:
   - Initialize the client with an `LLMConfig` dataclass (url, key, model, max_tokens, etc.) rather than `MainState`. This makes the clients easily unit-testable in isolation.

3. **Separate Generation from Chat**:
   - Remove image generation and editing from chat callers. Create a separate abstraction (e.g., `BaseMediaGenerator`) for Text-to-Image tasks.

4. **Standardize Multimodal Inputs**:
   - Use standard multi-modal message formats (e.g., Langchain's content arrays with images) instead of bespoke modes (`ocr`, `video_understanding`) branching inside the caller.
