"""
LawNidhi Integration — Case Portfolio CRUD Router

Exposes LawNidhi's case management (SQLite-backed) as REST API endpoints.
All LawNidhi-specific code is isolated in this file and the services/lawnidhi/ directory.
"""
from __future__ import annotations

import os
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Body, BackgroundTasks
from pydantic import BaseModel, Field

from workflow_engine.logger import get_logger
from workflow_engine.toolkits.ragtool.vector_store_tool import process_knowledge_base_files, VectorStoreManager
from workflow_engine.utils import get_project_root
from fastapi_app.notebook_paths import get_notebook_paths, _sanitize_user_id

log = get_logger(__name__)

router = APIRouter(prefix="/cases", tags=["Cases (LawNidhi)"])


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------

class CaseCreate(BaseModel):
    case_number: str
    case_year: str
    case_title: Optional[str] = None
    status: str = "NEW"
    primary_counsel: Optional[str] = None
    associate_counsel: Optional[str] = None
    applicant: Optional[str] = None
    respondent: Optional[str] = None
    requester_department: Optional[str] = None
    requester_name: Optional[str] = None
    diary_number: Optional[str] = None
    notes: Optional[str] = None
    # Notebook will be auto-created if auto_create_notebook is True
    auto_create_notebook: bool = True


class CaseUpdate(BaseModel):
    case_title: Optional[str] = None
    status: Optional[str] = None
    primary_counsel: Optional[str] = None
    associate_counsel: Optional[str] = None
    applicant: Optional[str] = None
    respondent: Optional[str] = None
    requester_department: Optional[str] = None
    requester_name: Optional[str] = None
    diary_number: Optional[str] = None
    notes: Optional[str] = None


class CaseResponse(BaseModel):
    id: Optional[int] = None
    case_number: str
    case_year: str
    case_title: Optional[str] = None
    status: str = "NEW"
    primary_counsel: Optional[str] = None
    associate_counsel: Optional[str] = None
    applicant: Optional[str] = None
    respondent: Optional[str] = None
    requester_department: Optional[str] = None
    requester_name: Optional[str] = None
    diary_number: Optional[str] = None
    date_assigned: Optional[str] = None
    date_closed: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    notebook_id: Optional[str] = None
    intelligence: Optional[Dict[str, Any]] = None


class CaseImportRequest(BaseModel):
    file_path: str
    type: str = "order"


# ---------------------------------------------------------------------------
# Helper: Convert LawNidhi model to response
# ---------------------------------------------------------------------------

def _case_to_response(case_model, notebook_id: Optional[str] = None) -> CaseResponse:
    """Convert a LawNidhi MyCaseModel to a CaseResponse."""
    return CaseResponse(
        id=case_model.id,
        case_number=case_model.case_number,
        case_year=case_model.case_year,
        case_title=case_model.case_title,
        status=case_model.status.value if hasattr(case_model.status, 'value') else str(case_model.status),
        primary_counsel=case_model.primary_counsel,
        associate_counsel=case_model.associate_counsel,
        applicant=case_model.applicant,
        respondent=case_model.respondent,
        requester_department=case_model.requester_department,
        requester_name=case_model.requester_name,
        diary_number=case_model.diary_number,
        date_assigned=str(case_model.date_assigned) if case_model.date_assigned else None,
        date_closed=str(case_model.date_closed) if case_model.date_closed else None,
        notes=case_model.notes,
        created_at=str(case_model.created_at) if case_model.created_at else None,
        updated_at=str(case_model.updated_at) if case_model.updated_at else None,
        notebook_id=notebook_id,
        intelligence=kwargs.get("intelligence")
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
async def list_cases(
    status: Optional[str] = None,
    counsel: Optional[str] = None,
):
    """List all cases in the portfolio with optional filters."""
    try:
        from lawnidhi.db import my_cases_repo
        from fastapi_app.services.lawnidhi.case_notebook_linker import get_notebook_id_for_case
        
        cases = my_cases_repo.list_cases(status=status, counsel=counsel)
        results = []
        for c in cases:
            nb_id = get_notebook_id_for_case(c.case_number, c.case_year)
            results.append(_case_to_response(c, notebook_id=nb_id))
            
        return {
            "success": True,
            "cases": results,
            "total": len(results),
        }
    except Exception as e:
        log.error("Failed to list cases: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitoring/stats")
async def indexing_monitoring_stats():
    """
    Aggregation service for Front Page Monitoring.
    Scans all litigation notebooks and returns portfolio-wide indexing health.
    """
    try:
        from lawnidhi.db import my_cases_repo
        from fastapi_app.services.lawnidhi.case_notebook_linker import get_notebook_id_for_case
        from workflow_engine.toolkits.ragtool.vector_store_tool import VectorStoreManager
        from workflow_engine.utils import get_project_root
        
        cases = my_cases_repo.list_cases()
        total_chunks = 0
        indexed_files = 0
        portfolio_health = [] # Per-case health summary
        
        # Determine the correct local model for stats reconciliation
        local_model = os.getenv("LOCAL_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        
        for c in cases:
            nb_id = get_notebook_id_for_case(c.case_number, c.case_year)
            if not nb_id:
                continue
                
            # Scan ALL potential user directories to find the active notebook root
            # (admin, guest_at_local, default, or root)
            root = get_project_root()
            nb_root = None
            for user_id in ["admin", "guest_at_local", "default", "local"]:
                nb_p = get_notebook_paths(nb_id, f"Case {c.case_number}_{c.case_year}", user_id)
                if nb_p.root.exists():
                    nb_root = nb_p.root
                    break
            
            if nb_root:
                try:
                    vs = VectorStoreManager(
                        base_dir=str(nb_root),
                        embedding_model=local_model
                    )
                    n_chunks = vs.index.ntotal if vs.index else 0
                    n_files = len(vs.manifest.get("files", []))
                    
                    total_chunks += n_chunks
                    indexed_files += n_files
                    
                    portfolio_health.append({
                        "case_no": f"{c.case_number}/{c.case_year}",
                        "chunks": n_chunks,
                        "files": n_files,
                        "ready": n_chunks > 0
                    })
                except Exception:
                    # Skip notebooks with errors for the summary
                    pass
                    
        return {
            "success": True,
            "portfolio_summary": {
                "total_chunks": total_chunks,
                "indexed_files": indexed_files,
                "total_cases": len(cases),
                "ai_readiness": f"{len([p for p in portfolio_health if p['ready']])}/{len(cases)} Ready"
            },
            "case_breakdown": portfolio_health
        }
    except Exception as e:
        log.error("Monitoring stats failure: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{case_no}/{case_year}")
async def get_case(case_no: str, case_year: str):
    """Get full details of a single case."""
    try:
        from lawnidhi.db import my_cases_repo
        from fastapi_app.services.lawnidhi.case_notebook_linker import get_notebook_id_for_case
        
        case = my_cases_repo.get_case(case_no, case_year)
        if not case:
            raise HTTPException(status_code=404, detail=f"Case {case_no}/{case_year} not found")
            
        nb_id = get_notebook_id_for_case(case_no, case_year)
        
        # Fetch intelligence if linked notebook exists
        intelligence = None
        if nb_id:
            try:
                from fastapi_app.services.litigation_service import get_litigation_intelligence
                from fastapi_app.notebook_paths import get_notebook_paths
                # Logic to find the notebook root (check all likely user IDs)
                for user_id in ["admin", "guest_at_local", "default", "local"]:
                    nb_p = get_notebook_paths(nb_id, f"Case {case_no}_{case_year}", user_id)
                    if nb_p.root.exists():
                        intelligence = get_litigation_intelligence(nb_p.root)
                        break
            except Exception:
                pass

        return {"success": True, "case": _case_to_response(case, notebook_id=nb_id, intelligence=intelligence)}
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to get case %s/%s: %s", case_no, case_year, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def add_case(data: CaseCreate):
    """
    Add a new case to the portfolio.
    Automatically creates an AI notebook linked to the case.
    """
    try:
        from lawnidhi.db import my_cases_repo

        case_id = my_cases_repo.add_case(
            data.case_number, data.case_year,
            case_title=data.case_title,
            status=data.status,
            primary_counsel=data.primary_counsel,
            associate_counsel=data.associate_counsel,
            applicant=data.applicant,
            respondent=data.respondent,
            requester_department=data.requester_department,
            requester_name=data.requester_name,
            diary_number=data.diary_number,
            notes=data.notes,
        )
        log.info("Case %s/%s added (id=%s)", data.case_number, data.case_year, case_id)

        # Auto-create a linked notebook
        notebook_id = None
        if data.auto_create_notebook:
            try:
                from fastapi_app.services.lawnidhi.case_notebook_linker import create_notebook_for_case
                notebook_id = create_notebook_for_case(
                    case_number=data.case_number,
                    case_year=data.case_year,
                    case_title=data.case_title,
                    counsel=data.primary_counsel,
                )
                log.info("Auto-created notebook %s for case %s/%s", notebook_id, data.case_number, data.case_year)
            except Exception as nb_err:
                log.warning("Failed to auto-create notebook for case %s/%s: %s", data.case_number, data.case_year, nb_err)

        case = my_cases_repo.get_case(data.case_number, data.case_year)
        return {
            "success": True,
            "case": _case_to_response(case, notebook_id=notebook_id) if case else None,
            "message": f"Case {data.case_number}/{data.case_year} added to portfolio",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error("Failed to add case: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{case_no}/{case_year}")
async def update_case(case_no: str, case_year: str, data: CaseUpdate):
    """Update fields of an existing case."""
    try:
        from lawnidhi.db import my_cases_repo

        kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
        if not kwargs:
            raise HTTPException(status_code=400, detail="No fields to update")

        if "status" in kwargs:
            updated = my_cases_repo.update_status(case_no, case_year, kwargs.pop("status"))
            if kwargs:
                my_cases_repo.update_case(case_no, case_year, **kwargs)
        else:
            updated = my_cases_repo.update_case(case_no, case_year, **kwargs)

        if not updated:
            raise HTTPException(status_code=404, detail=f"Case {case_no}/{case_year} not found")

        case = my_cases_repo.get_case(case_no, case_year)
        return {
            "success": True,
            "case": _case_to_response(case) if case else None,
            "message": f"Case {case_no}/{case_year} updated",
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to update case %s/%s: %s", case_no, case_year, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{case_no}/{case_year}")
async def close_case(case_no: str, case_year: str):
    """Close/dispose a case (sets status to CLOSED)."""
    try:
        from lawnidhi.db import my_cases_repo

        updated = my_cases_repo.update_status(case_no, case_year, "CLOSED")
        if not updated:
            raise HTTPException(status_code=404, detail=f"Case {case_no}/{case_year} not found")

        return {
            "success": True,
            "message": f"Case {case_no}/{case_year} closed",
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to close case %s/%s: %s", case_no, case_year, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{case_no}/{case_year}/documents")
async def list_case_documents(case_no: str, case_year: str):
    """
    List all documents associated with a case (orders, cause lists, uploads).
    Scans the local file system for downloaded files matching this case.
    """
    try:
        from fastapi_app.services.lawnidhi.case_notebook_linker import get_case_documents
        
        docs = get_case_documents(case_no, case_year)
        
        # Add relative URLs for frontend access
        root = get_project_root()
        for doc in docs:
            # If it's already an outputs URL, keep it
            if "url" in doc and doc["url"].startswith("/outputs/"):
                continue
                
            # Otherwise, use the download proxy for external paths
            if "local_path" in doc:
                try:
                    p = Path(doc["local_path"])
                    if p.exists():
                        # Use absolute path for download proxy if outside root
                        doc["url"] = "/api/v1/files/download?path=" + str(p.absolute())
                except Exception:
                    pass
                    
        return {
            "success": True,
            "documents": docs,
            "total": len(docs),
        }
    except Exception as e:
        log.error("Failed to list documents for case %s/%s: %s", case_no, case_year, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{case_no}/{case_year}/import")
async def import_case_document(case_no: str, case_year: str, data: CaseImportRequest):
    """
    Manually import a discovered LawNidhi document into the AI notebook.
    This triggers:
      1. Copying the file to the notebook's sources directory.
      2. REAL-TIME AI Indexing (Vectorization) for unified QA power.
    """
    try:
        from fastapi_app.services.lawnidhi.case_notebook_linker import import_document_to_notebook, get_notebook_id_for_case
        
        # 1. Perform the physical import/copy
        log.info("Importing %s into notebook for case %s/%s", data.file_path, case_no, case_year)
        linked_path = import_document_to_notebook(
            case_no, case_year, 
            data.file_path, 
            doc_type=data.type
        )
        
        if not linked_path:
            raise HTTPException(status_code=500, detail="Failed to link document to notebook")

        # 2. Trigger REAL-TIME AI Indexing (Unified with General AI notebooks)
        notebook_id = get_notebook_id_for_case(case_no, case_year)
        if notebook_id:
            # Assume default user 'admin' for LawNidhi if not specified (matches linker default)
            nb_paths = get_notebook_paths(notebook_id, f"Case {case_no}_{case_year}", "admin")
            
            # Setup local VectorStoreManager (Free-tier friendly)
            # base_dir is the only required argument for recent version
            # Explicitly use the local model from .env to ensure zero-cost indexing
            local_model = os.getenv("LOCAL_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
            vs_manager = VectorStoreManager(
                base_dir=str(nb_paths.root),
                project_name="kb_project",
                embedding_model=local_model
            )
            
            log.info("Triggering AI vectorization for Case %s/%s document: %s", case_no, case_year, linked_path.get("local_path"))
            # process_knowledge_base_files handles partitioning and local CPU embedding
            # Note: it will use current env USE_EMBEDDING_LIBRARY=1 for local CPU indexing
            await process_knowledge_base_files(
                file_list=[{"path": linked_path.get("local_path")}],
                base_dir=str(nb_paths.root),
                api_url=vs_manager.embedding_api_url,
                api_key=vs_manager.api_key,
                model_name=local_model
            )
            
        return {
            "success": True,
            "message": f"Document imported and indexed for Counsel AI",
            "linked_path": linked_path
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error("Unified import failed for case %s/%s: %s", case_no, case_year, e)
        raise HTTPException(status_code=500, detail=str(e))




@router.get("/stats")
async def case_stats():
    """Get portfolio statistics."""
    try:
        from lawnidhi.app import queries
        stats = queries.get_db_stats()
        from lawnidhi.db import my_cases_repo
        cases = my_cases_repo.list_cases()
        status_counts = {}
        for c in cases:
            s = c.status.value if hasattr(c.status, 'value') else str(c.status)
            status_counts[s] = status_counts.get(s, 0) + 1
        return {
            "success": True,
            "db_stats": stats,
            "total_cases": len(cases),
            "status_counts": status_counts,
        }
    except Exception as e:
        log.error("Failed to get case stats: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{case_no}/{case_year}/recalculate-intelligence")
async def recalculate_intelligence(
    case_no: str, 
    case_year: str, 
    background_tasks: BackgroundTasks = None
):
    """Manually trigger litigation intelligence extraction."""
    try:
        from fastapi_app.services.lawnidhi.case_notebook_linker import get_notebook_id_for_case
        from fastapi_app.services.litigation_service import update_litigation_intelligence_task
        from lawnidhi.db import my_cases_repo
        from fastapi_app.fastapi_app_settings import settings
        from fastapi import BackgroundTasks

        nb_id = get_notebook_id_for_case(case_no, case_year)
        if not nb_id:
             log.warning(f"Synthesis requested for {case_no}/{case_year} but no notebook exists.")
             raise HTTPException(status_code=404, detail="No AI notebook linked to this case")
        
        # Identify the respondent to focus the AI extraction on our client
        case = my_cases_repo.get_case(case_no, case_year)
        our_respondent = case.respondent if case else None

        if background_tasks:
            log.info(f"Queueing litigation intelligence synthesis for case {case_no}/{case_year}")
            background_tasks.add_task(
                update_litigation_intelligence_task,
                nb_id,
                f"Case {case_no}_{case_year}",
                "admin", # Default workspace user
                "local", # Local user identifier
                settings.DEFAULT_LLM_API_URL,
                settings.DEFAULT_LLM_API_KEY or settings.HF_TOKEN,
                settings.KB_CHAT_MODEL,
                our_respondent
            )
            return {"success": True, "message": "Intelligence extraction started in background. Monitor the logs for progress."}
        else:
            log.error("BackgroundTasks dependency was not injected by FastAPI.")
            return {"success": False, "message": "System error: Background tasks not available."}
    except Exception as e:
        log.error("Recalculation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
