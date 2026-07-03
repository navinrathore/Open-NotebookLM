# AI Instructions for Open-NotebookLM

This document outlines the architectural rules and Spec-Driven Development (SDD) methodology for the Open-NotebookLM project.

## Spec-Driven Development (SDD) Rules

Open-NotebookLM strictly follows the SDD lifecycle. **Never write implementation code without an approved spec.**

### The SDD Phase Lifecycle
Features are developed in named phases (e.g., `specs/phase-1-ui-updates/`). Each phase directory MUST contain:
1. `requirements.md`: What is being built and why.
2. `plan.md`: The technical design and steps.
3. `validation.md`: How the changes will be tested.

### Phase Completion Checklist
Before moving to the next phase, the AI must ensure:
- [ ] Spec files are complete and committed.
- [ ] Code is fully implemented according to the plan.
- [ ] The full test suite passes.
- [ ] Backend code is linted/formatted (e.g., `ruff`).
- [ ] `specs/roadmap.md` is updated to mark the phase as `(Completed)`.
- [ ] Deferred items or technical debt are logged in `specs/backlog.md`.
- [ ] All changes are committed to Git.

## Project Architecture & Patterns

- **FastAPI Backend**: The core is built on FastAPI (`fastapi_app/main.py`). Use Dependency Injection where appropriate.
- **LawNidhi Integration**: Maintain strict isolation for LawNidhi specific bridges in `fastapi_app/services/lawnidhi/`.
- **Workflow Engine**: The RAG pipeline and agentic reasoning happen in `workflow_engine/`. 
- **Provider Agnostic LLMs**: Do not hardcode OpenAI or Anthropic calls. Use the configured LLM API endpoints and `BaseLLMClient` patterns.

## Code Quality Gates
- Follow PEP-8 for Python.
- Use strict type hints.
- Ensure API routes are fully documented in OpenAPI (FastAPI).
