# Agentic Architecture & Workflow Engine

This document captures the architectural decisions and agentic workflows to be used in Open-NotebookLM.

## 1. The Workflow Engine
Open-NotebookLM operates primarily via the `workflow_engine/` which handles complex document retrieval, knowledge extraction, and synthesis.
- Ensure that the ReAct loops used for deep research have a strict `max_loops` threshold.
- Graph-based workflows (`workflow_engine/graphbuilder/`) must avoid unbounded cyclic paths without iteration limits.

## 2. Provider Agnostic LLM Interface (Target Architecture)
Open-NotebookLM is planned to transition to the Universal LLM Client specification (the `BaseLLMClient` factory pattern) for all model connections. 
- A configuration-driven approach (e.g., YAML) will be used to seamlessly route between OpenAI-compatible endpoints, local models (HuggingFace, vLLM), and enterprise APIs (AWS Bedrock, Anthropic, Gemini). 
- Ensure all future refactoring and new features move towards requesting their LLM client via this factory abstraction, rather than hardcoding direct SDK connections like `ChatOpenAI`.

## 3. Context Management
When synthesizing large LawNidhi case portfolios:
- Use chunking and vector retrieval (`workflow_engine/toolkits/ragtool/`).
- Avoid dumping raw Pydantic representations of hundreds of cases into a single LLM prompt.

## 4. Conditional Guardrails
Do not force smaller/cheaper models to output massive JSON structures without validation loops. Utilize the conditional guardrails pattern established in previous agentic projects to adapt prompt complexity to the model's capabilities.
