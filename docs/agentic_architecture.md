# Agentic Architecture & Workflow Engine

This document captures the architectural decisions and agentic workflows to be used in Open-NotebookLM.

## 1. The Workflow Engine
Open-NotebookLM operates primarily via the `workflow_engine/` which handles complex document retrieval, knowledge extraction, and synthesis.
- Ensure that the ReAct loops used for deep research have a strict `max_loops` threshold.
- Graph-based workflows (`workflow_engine/graphbuilder/`) must avoid unbounded cyclic paths without iteration limits.

## 2. Provider Agnostic LLM Interface
The API relies on an OpenAI-compatible endpoint format (`DEFAULT_LLM_API_URL`), making it naturally provider-agnostic. 
- Ensure all new features respect this abstraction rather than directly importing proprietary SDKs like `anthropic`.

## 3. Context Management
When synthesizing large LawNidhi case portfolios:
- Use chunking and vector retrieval (`workflow_engine/toolkits/ragtool/`).
- Avoid dumping raw Pydantic representations of hundreds of cases into a single LLM prompt.

## 4. Conditional Guardrails
Do not force smaller/cheaper models to output massive JSON structures without validation loops. Utilize the conditional guardrails pattern established in previous agentic projects to adapt prompt complexity to the model's capabilities.
