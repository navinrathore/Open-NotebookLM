# Open-NotebookLM (LawNidhi Application Backend)

This repository is a customized fork of Open-NotebookLM, heavily integrated with the **LawNidhi** legal case portfolio manager. It serves as the application-based, AI-powered RAG backend for LawNidhi, automatically bridging your local SQLite case data and NGT orders into intelligent AI Notebooks.

## Architecture & Core Components

This application seamlessly links LawNidhi's CLI/local database architecture with a FastAPI-driven web and agentic backend. 

### 1. LawNidhi Integration Services (`fastapi_app/services/lawnidhi/`)
- **`case_notebook_linker.py`**: The core bridge. When a case is tracked in LawNidhi, this service auto-creates a corresponding AI notebook. It maps NGT order PDFs and cause lists from LawNidhi's central `data/orders/` directory directly into the Notebook's vector store.
- **`config_helper.py`**: Syncs configurations (like Primary Counsel details) directly from LawNidhi's `config.ini`.

### 2. LawNidhi API Routers (`fastapi_app/routers/`)
- **`cases.py`**: Exposes LawNidhi's SQLite case management as REST API endpoints (`/cases`).
- **`calendar.py` & `reports.py`**: Endpoints to expose hearing schedules and counsel appearance logs to the web frontend.

### 3. Open-NotebookLM Core Engines
- **`workflow_engine/`**: The Agentic and RAG pipeline. Processes imported legal documents, builds the vector store, and powers the Q&A / Notion-style note editor.
- **`fastapi_app/main.py`**: The main FastAPI application tying the routers and workflow engines together.

---

## How to Run the Agent & Application

You can manage the application lifecycle using the provided bash scripts located in the `scripts/` directory. 

### Primary Commands

```bash
# 1. Start the entire stack (Backend + Frontend)
bash scripts/start.sh

# 2. Start ONLY the FastAPI Backend (Useful for API/Agent debugging)
bash scripts/start_backend.sh

# 3. Stop all running Open-NotebookLM processes
bash scripts/stop.sh
```

*(Note: The backend depends on LawNidhi being installed or available in the parent directory path as `../LawNidhi` so the case linker can discover the SQLite database and PDF orders).*
