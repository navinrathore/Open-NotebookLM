"""
Suggested Questions Service
Generates 3-5 ice-breaker questions based on legal document context.
"""
import json
import re
import httpx
from typing import List, Dict, Any
from workflow_engine.logger import get_logger
from workflow_engine.promptstemplates.resources.pt_litigation_repo import QuestionGenerator

log = get_logger(__name__)

async def generate_suggested_questions(
    context_text: str,
    api_url: str,
    api_key: str,
    model: str,
    counsel_name: str = "Hemlata Singh"
) -> List[str]:
    """
    Generate suggested questions from legal document context.
    """
    # Limit context size to avoid token limits
    max_chars = 15000 
    if len(context_text) > max_chars:
        context_text = context_text[:max_chars] + "..."

    # Build prompt using the litigation repo
    system_prompt = QuestionGenerator.system_prompt_for_suggested_questions.replace(
        "Hemlata Singh", counsel_name
    )
    task_prompt = QuestionGenerator.task_prompt_for_suggested_questions.format(
        context_sample=context_text
    )

    log.info(f"[suggest_questions] Generating questions for counsel: {counsel_name} using model: {model}")

    try:
        # Ensure API URL is correct
        if not api_url.endswith('/chat/completions'):
            api_url = api_url.rstrip('/') + '/chat/completions'

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt}
            ],
            "temperature": 0.5,
            "response_format": {"type": "json_object"}
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(api_url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

        content = result["choices"][0]["message"]["content"]
        
        # Parse JSON response
        try:
            data = json.loads(content)
            questions = data.get("questions", [])
            # Fallback if it's a list directly
            if not questions and isinstance(data, list):
                questions = data
        except json.JSONDecodeError:
            # Fallback regex parsing if JSON fails
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                questions = json.loads(match.group(0))
            else:
                log.warning(f"[suggest_questions] Failed to parse JSON from content: {content}")
                questions = []

        # Clean up and limit
        questions = [q.strip() for q in questions if isinstance(q, str) and q.strip()]
        return questions[:5]

    except Exception as e:
        log.error(f"[suggest_questions] LLM call failed: {e}")
        return []

def get_cached_questions(notebook_path: Path) -> List[str]:
    """Read cached questions from notebook dir."""
    cache_file = notebook_path / "suggested_questions.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def cache_questions(notebook_path: Path, questions: List[str]):
    """Save questions to cache file."""
    cache_file = notebook_path / "suggested_questions.json"
    try:
        cache_file.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning(f"[suggest_questions] Failed to cache questions: {e}")

async def update_suggested_questions_task(
    notebook_id: str,
    notebook_title: str,
    email: str,
    user_id: str,
    api_url: str,
    api_key: str,
    model: str
):
    """
    Background task to update suggested questions for a notebook.
    """
    try:
        from fastapi_app.notebook_paths import get_notebook_paths
        from fastapi_app.source_manager import SourceManager
        from fastapi_app.services.lawnidhi.config_helper import get_primary_counsel
        
        paths = get_notebook_paths(notebook_id, notebook_title, email or user_id)
        mgr = SourceManager(paths)
        
        markdowns = mgr.get_all_markdowns()
        if not markdowns:
            return
            
        context_parts = []
        for stem, text in markdowns:
            context_parts.append(f"--- DOCUMENT: {stem} ---\n{text[:5000]}")
            
        full_context = "\n\n".join(context_parts)
        counsel_name = get_primary_counsel()
        
        questions = await generate_suggested_questions(
            context_text=full_context,
            api_url=api_url,
            api_key=api_key,
            model=model,
            counsel_name=counsel_name
        )
        
        if questions:
            cache_questions(paths.root, questions)
            log.info(f"[suggest_questions] Pre-calculated {len(questions)} questions for notebook {notebook_id}")
            
    except Exception as e:
        log.warning(f"[suggest_questions] Background update failed: {e}")
