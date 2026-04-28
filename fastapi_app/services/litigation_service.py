import json
import re
import httpx
import os
from typing import List, Dict, Any, Optional
from pathlib import Path
from workflow_engine.logger import get_logger
from workflow_engine.promptstemplates.resources.pt_litigation_repo import QuestionGenerator, LitigationAgent
from fastapi_app.notebook_paths import get_notebook_paths
from fastapi_app.source_manager import SourceManager
from fastapi_app.services.lawnidhi.config_helper import get_primary_counsel

# Dedicated logger for litigation intelligence service
log = get_logger(__name__)

async def call_llm(
    system_prompt: str,
    user_prompt: str,
    api_url: str,
    api_key: str,
    model: str
) -> Dict[str, Any]:
    """
    Standard helper for asynchronous LLM calls.
    Ensures URL structure and response format (JSON) is consistent.
    """
    try:
        # Standardize OpenAI-compatible endpoint URL
        if not api_url.endswith('/chat/completions'):
            api_url = api_url.rstrip('/') + '/chat/completions'

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # We request json_object format to ensure parsing reliability
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,
            "response_format": {"type": "json_object"}
        }

        log.debug(f"[litigation_service] Calling LLM model: {model}")
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(api_url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            
            # Content is expected to be valid JSON as per response_format
            content = result["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception as e:
        log.error(f"[litigation_service] LLM call failed for {model}: {e}")
        # Return empty dict on failure to prevent downstream crashes
        return {}

def extract_date_from_filename(filename: str) -> Optional[str]:
    """
    Utility to identify a hearing/order date embedded in a filename.
    Supports YYYY-MM-DD, DD.MM.YYYY, and DD-MM-YYYY formats.
    """
    patterns = [
        r'\d{4}-\d{2}-\d{2}',     # 2024-04-08
        r'\d{2}\.\d{2}\.\d{4}',   # 08.04.2024
        r'\d{2}-\d{2}-\d{4}'      # 08-04-2024
    ]
    for p in patterns:
        match = re.search(p, filename)
        if match:
            return match.group(0)
    return None

async def perform_litigation_intelligence_extraction(
    context_text: str,
    api_url: str,
    api_key: str,
    model: str,
    counsel_name: str,
    our_respondent: Optional[str] = None
) -> Dict[str, Any]:
    """
    Core AI logic to extract litigation metadata (Coram, Action Items, Petitioner/Respondent).
    This function uses the LitigationAgent prompts from pt_litigation_repo.
    """
    # Personalize the system prompt with the primary counsel's name
    system_prompt = LitigationAgent.system_prompt_for_litigation.replace(
        "Hemlata Singh", counsel_name
    ).format(context="")
    
    # Process the first 15k characters which usually contain the critical directions
    user_prompt = LitigationAgent.extraction_task_prompt.format(
        content=context_text[:15000]
    )

    log.debug(f"[litigation_service] Extracting metadata from document context (len: {len(context_text)})")
    intelligence = await call_llm(system_prompt, user_prompt, api_url, api_key, model)
    
    # Post-process: Filter and mark action items specifically assigned to our respondent/client
    if intelligence and "action_items" in intelligence and our_respondent:
        our_respondent_lower = our_respondent.lower()
        for item in intelligence["action_items"]:
            resp = str(item.get("responsible", "")).lower()
            # If our respondent's name or global "Respondent" keyword is found, flag it
            item["is_our_respondent"] = (our_respondent_lower in resp) or ("respondent" in resp and "no." not in resp)
    
    return intelligence

async def update_litigation_intelligence_task(
    notebook_id: str,
    notebook_title: str,
    email: str,
    user_id: str,
    api_url: str,
    api_key: str,
    model: str,
    our_respondent: Optional[str] = None
):
    """
    Asynchronous background task to synthesize 'Litigation Pulse' for a case notebook.
    
    Workflow:
    1. Scan all markdown sources in the notebook.
    2. Identify the FIRST (baseline) and LATEST (current status) orders.
    3. Run AI extraction on both to provide a chronological comparison.
    4. Generate suggested ice-breaker questions for the user.
    5. Save results to litigation_intelligence.json in the notebook root.
    """
    log.info(f"[PulseTask] STARTING synthesis for notebook: {notebook_title} ({notebook_id})")
    try:
        # Load necessary paths and source manager
        paths = get_notebook_paths(notebook_id, notebook_title, email or user_id)
        mgr = SourceManager(paths)
        
        # Retrieve all processed markdown documents
        sources = mgr.get_all_markdowns()
        if not sources:
            log.warning(f"[PulseTask] No markdown sources found for {notebook_id}. Skipping synthesis.")
            return
            
        # 1. Identify First and Latest orders by document name chronology
        # We sort by filename stem to ensure chronological sequence (assuming YYYY-MM-DD prefix)
        sources.sort(key=lambda x: x[0]) 
        
        first_source = sources[0]
        latest_source = sources[-1]
        
        # Fetch the Primary Counsel from LawNidhi configuration
        counsel_name = get_primary_counsel()
        log.info(f"[PulseTask] Using Primary Counsel: {counsel_name}")
        
        # 2. AI Extraction for the LATEST order (Current Status)
        log.info(f"[PulseTask] Analyzing LATEST order: {latest_source[0]}")
        latest_intel = await perform_litigation_intelligence_extraction(
            latest_source[1], api_url, api_key, model, counsel_name, our_respondent
        )
        
        # 3. AI Extraction for the FIRST order (Case Baseline)
        first_intel = {}
        if first_source[0] != latest_source[0]:
            log.info(f"[PulseTask] Analyzing FIRST order (Baseline): {first_source[0]}")
            first_intel = await perform_litigation_intelligence_extraction(
                first_source[1], api_url, api_key, model, counsel_name, our_respondent
            )
        else:
            # If only one order exists, first and latest are the same
            first_intel = latest_intel
        
        # 4. Generate Suggested Questions (focused on current next steps)
        log.info(f"[PulseTask] Generating suggested ice-breaker questions")
        from fastapi_app.services.suggest_questions import generate_suggested_questions
        questions = await generate_suggested_questions(
            latest_source[1], api_url, api_key, model, counsel_name
        )

        # 5. Compile and save the unified intelligence artifact
        intelligence_data = {
            "questions": questions,
            "latest_intelligence": latest_intel,
            "first_order_intelligence": first_intel,
            "updated_at": Path(latest_source[0]).name, # Use filename as version anchor
            "our_respondent": our_respondent,
            "analysis_timestamp": json.dumps(json.dumps(""))[:0] + str(Path(latest_source[0]).name) # Heuristic
        }
        
        # Save to litigation_intelligence.json in the notebook's root directory
        intel_path = paths.notebook_dir / "litigation_intelligence.json"
        with open(intel_path, "w") as f:
            json.dump(intelligence_data, f, indent=2)
            
        log.info(f"[PulseTask] SUCCESS! Litigation Intelligence saved to {intel_path}")
        
    except Exception as e:
        log.error(f"[PulseTask] FAILED for notebook {notebook_id}: {e}", exc_info=True)


def get_litigation_intelligence(notebook_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Helper function to load the 'Litigation Pulse' artifact from a notebook's directory.
    This allows the UI to instantly display the most recent AI findings without 
    triggering a new synthesis.
    """
    intelligence_file = notebook_dir / "litigation_intelligence.json"
    if not intelligence_file.exists():
        return None
        
    try:
        with open(intelligence_file, "r") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"[litigation_service] Failed to read {intelligence_file}: {e}")
        return None
