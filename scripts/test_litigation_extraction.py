import os
import json
import asyncio
import sys
from typing import List, Dict
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from workflow_engine.promptstemplates.resources.pt_litigation_repo import LitigationAgent
from fastapi_app.services.lawnidhi.config_helper import get_primary_counsel
from openai import AsyncOpenAI

# Configuration
SAMPLE_FILES = [
    "/mnt/c/Users/Navin Singh/Downloads/sample_order_1.pdf",
    "/mnt/c/Users/Navin Singh/Downloads/sample order 2.pdf",
    "/mnt/c/Users/Navin Singh/Downloads/sample_3.pdf"
]

async def extract_metadata(file_path: str, client: AsyncOpenAI, model: str):
    print(f"[*] Processing: {os.path.basename(file_path)}...")
    
    try:
        import fitz # PyMuPDF
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
    except Exception as e:
        return {"error": f"Failed to read PDF: {e}"}

    counsel_name = get_primary_counsel()
    
    # Build the prompt
    system_prompt = LitigationAgent.system_prompt_for_litigation.replace("Hemlata Singh", counsel_name).format(context="")
    user_prompt = LitigationAgent.extraction_task_prompt.format(
        content=text[:10000]
    )

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"error": f"LLM Call failed: {e}"}

async def main():
    # Load API Keys from .env
    from dotenv import load_dotenv
    load_dotenv("fastapi_app/.env")
    
    api_url = os.getenv("DEFAULT_LLM_API_URL")
    api_key = os.getenv("DEFAULT_LLM_API_KEY") or os.getenv("HF_TOKEN")
    model = os.getenv("KB_CHAT_MODEL", "gpt-4o")
    
    if not api_url or not api_key:
        print("[!] Error: API URL or Key not found in .env")
        return

    client = AsyncOpenAI(base_url=api_url, api_key=api_key)
    results = []

    for f in SAMPLE_FILES:
        if not os.path.exists(f):
            print(f"[!] Warning: File not found: {f}")
            continue
        data = await extract_metadata(f, client, model)
        results.append({"file": os.path.basename(f), "data": data})

    non_interactive = "--non-interactive" in sys.argv
    
    # Print Table
    print("\n" + "="*80)
    print(f"{'FILE':<25} | {'CASE NO':<20} | {'NEXT HEARING':<15}")
    print("-" * 80)
    for res in results:
        d = res['data']
        # Handle case info
        case_info = d.get('case_info') or d.get('case_id') or {}
        if isinstance(case_info, dict):
            case_no = case_info.get('case_number') or case_info.get('case_id') or 'N/A'
        else:
            case_no = str(case_info)
            
        # Handle next hearing
        next_hearing_data = d.get('next_hearing', 'N/A')
        if isinstance(next_hearing_data, dict):
            hearing = next_hearing_data.get('date', 'N/A')
        else:
            hearing = str(next_hearing_data)
            
        print(f"{res['file']:<25} | {case_no:<20} | {hearing:<15}")
    print("="*80)

    if non_interactive:
        print("\n[NON-INTERACTIVE] Printing all results:")
        for res in results:
            print(f"\n--- {res['file']} ---")
            print(json.dumps(res['data'], indent=2))
        return

    # Interactive Mode
    while True:
        print("\n[*] Select a file number (1-3) to see full Action Items, or 'q' to quit:")
        choice = input("> ").strip().lower()
        if choice == 'q':
            break
        if choice in ['1', '2', '3']:
            idx = int(choice) - 1
            if idx < len(results):
                data = results[idx]['data']
                print(f"\n[DETAILS for {results[idx]['file']}]")
                print(json.dumps(data, indent=2))
            else:
                print("[!] Invalid index")
        else:
            print("[!] Please enter 1, 2, 3 or q")

if __name__ == "__main__":
    asyncio.run(main())
