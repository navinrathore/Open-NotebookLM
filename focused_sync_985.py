import json
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from workflow_engine.toolkits.ragtool.vector_store_tool import process_knowledge_base_files
from fastapi_app.notebook_paths import get_notebook_paths
from fastapi_app.services.litigation_service import update_litigation_intelligence_task
from fastapi_app.fastapi_app_settings import settings

async def main():
    nb_id = "743a910f3ddce23f"
    nb_title = "Case 985/2019 (Bhanwar Pal)"
    user_id = "local"
    
    print(f"--- Starting Focused Sync for Case 985/2019 ---")
    
    paths = get_notebook_paths(nb_id, nb_title, user_id)
    sources_dir = paths.sources_dir
    
    # Identify items with PDFs in 'original'
    if not sources_dir.exists():
        print(f"Error: Sources directory {sources_dir} not found.")
        return
        
    sourced_items = [d for d in sources_dir.iterdir() if d.is_dir() and (d / "original").exists()]
    print(f"Found {len(sourced_items)} selected documents.")
    
    process_list = []
    for item in sourced_items:
        pdfs = list((item / "original").glob("*.pdf"))
        # Only add if markdown doesn't exist yet (optimization)
        md_exists = any((item / "markdown").glob("*.md")) if (item / "markdown").exists() else False
        
        if pdfs and not md_exists:
            process_list.append({"path": str(pdfs[0]), "description": "Selected Order"})
            
    if process_list:
        print(f"Starting extraction for {len(process_list)} files...")
        await process_knowledge_base_files(
            process_list,
            base_dir=str(paths.vector_store_dir),
            mineru_output_base=str(paths.sources_dir)
        )
        print("Extraction complete.")
    else:
        print("All documents already have markdown versions. Skipping extraction.")
        
    print("Synthesizing Litigation Pulse...")
    await update_litigation_intelligence_task(
        nb_id, nb_title, user_id, user_id,
        settings.DEFAULT_LLM_API_URL,
        settings.DEFAULT_LLM_API_KEY,
        settings.KB_CHAT_MODEL,
        "Bhanwar Pal"
    )
    print("--- Litigation Pulse READY ---")

if __name__ == "__main__":
    asyncio.run(main())
