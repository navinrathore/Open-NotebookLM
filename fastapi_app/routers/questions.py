"""
Suggested Questions Router
Exposes endpoint to generate ice-breaker questions for a notebook.
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

from fastapi_app.notebook_paths import get_notebook_paths
from fastapi_app.source_manager import SourceManager
from fastapi_app.config import settings
from fastapi_app.services.suggest_questions import generate_suggested_questions
from fastapi_app.services.lawnidhi.config_helper import get_primary_counsel
from workflow_engine.logger import get_logger

router = APIRouter(prefix="/questions", tags=["Questions"])
log = get_logger(__name__)

class QuestionRequest(BaseModel):
    notebook_id: str
    notebook_title: Optional[str] = ""
    email: Optional[str] = "default"
    user_id: Optional[str] = "local"

@router.post("/suggest")
async def suggest_questions(request: QuestionRequest):
    """
    Generate suggested questions based on notebook sources.
    """
    try:
        # 1. Resolve paths
        paths = get_notebook_paths(request.notebook_id, request.notebook_title or "", request.email or request.user_id)
        
        # 2. Check for cached questions
        from fastapi_app.services.suggest_questions import get_cached_questions, cache_questions
        cached = get_cached_questions(paths.root)
        if cached:
            log.info(f"[router_questions] Returning cached questions for notebook {request.notebook_id}")
            return {"questions": cached}

        # 3. Resolve source manager
        mgr = SourceManager(paths)
        
        # 4. Collect all markdown text from sources
        markdowns = mgr.get_all_markdowns()
        if not markdowns:
            log.info(f"[router_questions] No sources found for notebook {request.notebook_id}")
            return {"questions": []}
            
        # Aggregate context
        context_parts = []
        for stem, text in markdowns:
            context_parts.append(f"--- DOCUMENT: {stem} ---\n{text[:5000]}")
            
        full_context = "\n\n".join(context_parts)
        
        # 5. Get primary counsel name
        counsel_name = get_primary_counsel()
        
        # 6. Call LLM service
        questions = await generate_suggested_questions(
            context_text=full_context,
            api_url=settings.DEFAULT_LLM_API_URL,
            api_key=settings.DEFAULT_LLM_API_KEY or settings.HF_TOKEN,
            model=settings.KB_CHAT_MODEL,
            counsel_name=counsel_name
        )
        
        # 7. Update cache
        if questions:
            cache_questions(paths.root, questions)
        
        return {"questions": questions}
        
    except Exception as e:
        log.error(f"[router_questions] Failed to suggest questions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
