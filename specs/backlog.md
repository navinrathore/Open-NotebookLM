# Open-NotebookLM Backlog

This document tracks deferred items, technical debt, and future ideas that are not part of the active phase.

## Technical Debt
- [ ] Refactor legacy LLM callers in `workflow_engine/` to fully adapt the unified `BaseLLMClient` pattern. (See proposal details in [docs/llm_caller_refactor_proposal.md](../docs/llm_caller_refactor_proposal.md))
- [ ] Enhance test coverage for the LawNidhi REST endpoints in `fastapi_app/routers/cases.py`.

## Ideas
- [ ] Improve multi-tenant data isolation if LawNidhi expands to multiple concurrent users.
