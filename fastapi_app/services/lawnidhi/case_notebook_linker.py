"""
LawNidhi Integration — Case ↔ Notebook Linker Service

This is the core bridge between LawNidhi's case management and Open-NotebookLM's
AI notebook system. It handles:
  1. Auto-creating notebooks when cases are added
  2. Mapping case documents (orders, cause lists) to notebook sources
  3. Syncing new downloads into the linked notebook

All LawNidhi integration services are isolated in this directory.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any

from workflow_engine.logger import get_logger
from workflow_engine.utils import get_project_root

log = get_logger(__name__)

# Mapping file: tracks which notebook_id is linked to which case
_LINK_FILE = "case_notebook_links.json"


def _links_path() -> Path:
    """Path to the JSON file that stores case → notebook mappings."""
    root = get_project_root()
    return root / "data" / _LINK_FILE


def _load_links() -> Dict[str, str]:
    """Load case → notebook_id mappings from disk."""
    path = _links_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_links(links: Dict[str, str]) -> None:
    """Persist case → notebook_id mappings to disk."""
    path = _links_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(links, indent=2, ensure_ascii=False), encoding="utf-8")


def _case_key(case_number: str, case_year: str) -> str:
    """Stable key for a case."""
    return f"{case_number}/{case_year}"


def _generate_notebook_id(case_number: str, case_year: str) -> str:
    """Generate a deterministic notebook ID for a case."""
    import hashlib
    raw = f"lawnidhi-case-{case_number}-{case_year}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def create_notebook_for_case(
    case_number: str,
    case_year: str,
    case_title: Optional[str] = None,
    counsel: Optional[str] = None,
) -> str:
    """
    Create an AI notebook directory for a case and register the link.

    Returns the notebook_id.
    """
    key = _case_key(case_number, case_year)
    links = _load_links()

    # If notebook already exists for this case, return existing ID
    if key in links:
        log.info("Notebook already exists for case %s: %s", key, links[key])
        return links[key]

    notebook_id = _generate_notebook_id(case_number, case_year)
    title = case_title or f"Case {case_number}/{case_year}"
    if counsel:
        title = f"{title} ({counsel})"

    root = get_project_root()

    # Create notebook directory structure matching Open-NotebookLM's layout
    # Layout: outputs/{safe_title}_{notebook_id}/sources/
    safe_title = _sanitize_dirname(title)
    notebook_dir = root / "outputs" / f"{safe_title}_{notebook_id}"
    sources_dir = notebook_dir / "sources"
    vector_store_dir = notebook_dir / "vector_store"

    sources_dir.mkdir(parents=True, exist_ok=True)
    vector_store_dir.mkdir(parents=True, exist_ok=True)

    # Write notebook metadata
    metadata = {
        "notebook_id": notebook_id,
        "case_number": case_number,
        "case_year": case_year,
        "case_title": case_title,
        "counsel": counsel,
        "title": title,
        "type": "lawnidhi_case",
    }
    meta_path = notebook_dir / "notebook_meta.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    # Register the link
    links[key] = notebook_id
    _save_links(links)

    log.info("Created notebook for case %s: notebook_id=%s, dir=%s", key, notebook_id, notebook_dir)
    return notebook_id


def get_notebook_id_for_case(case_number: str, case_year: str) -> Optional[str]:
    """Get the notebook_id linked to a case, or None if not linked."""
    key = _case_key(case_number, case_year)
    links = _load_links()
    return links.get(key)


def import_document_to_notebook(
    case_number: str,
    case_year: str,
    file_path: str,
    doc_type: str = "order",
) -> Optional[dict]:
    """
    Import a document (order PDF, cause list, etc.) into the case's linked notebook.

    Copies the file into the notebook's sources directory and returns the
    metadata for the imported file.
    """
    notebook_id = get_notebook_id_for_case(case_number, case_year)
    if not notebook_id:
        log.warning("No notebook linked to case %s/%s, cannot import document", case_number, case_year)
        return None

    source_path = Path(file_path)
    if not source_path.exists():
        log.warning("Document not found: %s", file_path)
        return None

    root = get_project_root()

    # Find the notebook directory
    notebook_dir = _find_notebook_dir(notebook_id)
    if not notebook_dir:
        log.warning("Notebook directory not found for notebook_id=%s", notebook_id)
        return None

    # Copy to sources/{stem}/original/
    stem = source_path.stem
    dest_dir = notebook_dir / "sources" / stem / "original"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / source_path.name

    if not dest_path.exists():
        shutil.copy2(str(source_path), str(dest_path))
        log.info("Imported %s into notebook %s: %s", source_path.name, notebook_id, dest_path)

    # Return metadata & relative URL path
    try:
        rel = dest_path.relative_to(root)
        url = "/" + rel.as_posix()
    except ValueError:
        url = str(dest_path)

    return {
        "url": url,
        "notebook_id": notebook_id,
        "storage_path": url, # URL typically matches storage path in this system
        "local_path": str(dest_path)
    }




def get_case_documents(case_number: str, case_year: str) -> List[Dict[str, Any]]:
    """
    Get all documents associated with a case notebook.
    Returns a list of metadata for each document found in:
      1. The notebook's sources directory (Imported)
      2. The central LawNidhi orders directory (Available)
    """
    notebook_id = get_notebook_id_for_case(case_number, case_year)
    
    # 1. Get documents already imported into the notebook
    documents = []
    notebook_dir = None
    if notebook_id:
        notebook_dir = _find_notebook_dir(notebook_id)
        if notebook_dir:
            sources_base = notebook_dir / "sources"
            if sources_base.exists():
                # Scan sources for already imported documents
                root = get_project_root()
                for stem_dir in sources_base.iterdir():
                    if not stem_dir.is_dir(): continue
                    orig_dir = stem_dir / "original"
                    if not orig_dir.exists(): continue
                    for doc_file in orig_dir.iterdir():
                        if doc_file.is_file() and not doc_file.name.startswith("."):
                            try:
                                rel = doc_file.relative_to(root)
                                url = "/" + rel.as_posix()
                            except ValueError:
                                url = str(doc_file)
                            documents.append({
                                "name": doc_file.name,
                                "url": url,
                                "storage_path": url,
                                "local_path": str(doc_file),
                                "status": "imported",
                                "type": "order" if doc_file.suffix.lower() == ".pdf" else "document"
                            })

    # 2. Discover available orders from the central repository matching the Diary Number
    try:
        from lawnidhi.db import my_cases_repo
        case = my_cases_repo.get_case(case_number, case_year)
        if case:
            # Patterns for matching: {diary_number}_DATE_order.pdf or {case_no}-{case_year}_DATE_order.pdf
            # Diary Number can be e.g. "070110200257-2025" or "070110200257/2025"
            safe_diary = str(case.diary_number).replace("/", "-") if case.diary_number else None
            safe_case = f"{case_number}-{case_year}"
            
            # Central orders repository location (relative to Open-NotebookLM root)
            root = get_project_root()
            orders_dir = root.parent / "LawNidhi" / "data" / "orders"
            
            if orders_dir.exists():
                imported_names = {d["name"] for d in documents}
                for order_file in orders_dir.iterdir():
                    if not order_file.is_file(): continue
                    
                    found_match = False
                    if safe_diary and (order_file.name.startswith(safe_diary) or order_file.name.startswith(safe_diary.replace("-", ""))):
                        found_match = True
                    elif order_file.name.startswith(safe_case) or f"_{safe_case}" in order_file.name:
                        found_match = True
                        
                    if found_match and order_file.name not in imported_names:
                        rel_path = str(order_file)
                        documents.append({
                            "name": order_file.name,
                            "url": "/api/v1/files/download?path=" + rel_path,
                            "storage_path": rel_path,
                            "local_path": str(order_file),
                            "status": "available",
                            "type": "order"
                        })
                            # Important: the frontend should handle "available" status using an import action
    except ImportError:
        log.warning("LawNidhi package not found, skipping central order discovery")
    except Exception as e:
        log.error("Failed to discover central LawNidhi orders: %s", e)

    return documents


def _find_notebook_dir(notebook_id: str) -> Optional[Path]:
    """Find the notebook directory by its ID (scanning outputs/)."""
    root = get_project_root()
    outputs = root / "outputs"
    if not outputs.exists():
        return None
    for item in outputs.iterdir():
        if item.is_dir() and item.name.endswith(f"_{notebook_id}"):
            return item
    return None


def _sanitize_dirname(name: str) -> str:
    """Make a string safe for use as a directory name."""
    import re
    safe = re.sub(r'[^\w\s\-.]', '_', (name or "").strip())
    return (safe or "case")[:60].strip()
