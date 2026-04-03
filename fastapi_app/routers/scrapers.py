"""
LawNidhi Integration — Scraper Control Router

Exposes LawNidhi's scraping capabilities (cause list sync, case search,
order download) as REST API endpoints for the frontend Scraper Control page.
"""
from __future__ import annotations

import os
from typing import List, Optional, Dict
from fastapi import APIRouter, HTTPException, Body, BackgroundTasks
from pydantic import BaseModel

from workflow_engine.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/scrapers", tags=["Scrapers (LawNidhi)"])


class SyncCauseListsRequest(BaseModel):
    start_date: Optional[str] = None  # YYYY-MM-DD, defaults to today


class SearchCaseRequest(BaseModel):
    case_number: str
    case_year: str
    zone: str = "1"
    case_type: str = "1"
    retries: int = 3

class ManualCaptchaRequest(BaseModel):
    case_number: str
    case_year: str
    captcha_text: str
    zone: str = "1"
    case_type: str = "1"


class DownloadOrdersRequest(BaseModel):
    case_number: str
    case_year: str
    zone: str = "1"
    case_type: str = "1"
    retries: int = 3
    download_all: bool = True
    order_indices: Optional[List[int]] = None
    download_dir: Optional[str] = None


async def trigger_auto_ingestion(notebook_id: str, files: List[Dict[str, str]]):
    """Background task to trigger AI embedding for newly imported files."""
    try:
        from workflow_engine.toolkits.ragtool.vector_store_tool import process_knowledge_base_files
        from fastapi_app.notebook_paths import get_notebook_paths
        from workflow_engine.utils import get_project_root
        
        project_root = get_project_root()
        # Find the notebook's vector store and mineru dirs
        # We use 'default' email as fallback for system-automated tasks
        nb_paths = get_notebook_paths(notebook_id, "", "default")
        
        process_list = []
        for f in files:
            lp = f.get("local_path")
            if lp:
                process_list.append({"path": lp, "description": "Auto-ingested court order"})
        
        if not process_list:
            return

        log.info("[AutoIngest] Starting background embedding for notebook %s (%d files)", notebook_id, len(process_list))
        
        nb_paths.vector_store_dir.mkdir(parents=True, exist_ok=True)
        nb_paths.sources_dir.mkdir(parents=True, exist_ok=True)

        await process_knowledge_base_files(
            process_list,
            base_dir=str(nb_paths.vector_store_dir),
            mineru_output_base=str(nb_paths.sources_dir),
            # Use default model settings from environment
        )
        log.info("[AutoIngest] Successfully processed files for notebook %s", notebook_id)
    except Exception as e:
        log.error("[AutoIngest] Background embedding failed: %s", e)


@router.post("/sync-cause-lists")
async def sync_cause_lists(data: SyncCauseListsRequest):
    """Trigger automated cause list sync: scan NGT site → download → parse → ingest."""
    try:
        from datetime import date, datetime
        from lawnidhi.scraper.ngt_cause_list_scraper import NGTCauseListScraper

        start = date.today()
        if data.start_date:
            start = datetime.strptime(data.start_date, "%Y-%m-%d").date()

        scraper = NGTCauseListScraper()
        processed = scraper.sync(start_date=start)

        return {
            "success": True,
            "processed": processed,
            "message": f"Successfully processed {processed} cause lists",
        }
    except Exception as e:
        log.error("Cause list sync failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search-case")
async def search_case(data: SearchCaseRequest):
    """Search for a case on NGT website (with CAPTCHA solving)."""
    try:
        from lawnidhi.scraper.dynamic_search import DynamicSearchAPI

        api = DynamicSearchAPI()
        search_result = api.auto_search(
            data.case_number, data.case_year,
            data.zone, data.case_type, data.retries,
        )

        if not search_result["success"]:
            # Check if we have a captcha image for fallback
            if search_result.get("captcha_image_b64"):
                return {
                    "success": False,
                    "captcha_required": True,
                    "captcha_image": search_result["captcha_image_b64"],
                    "message": "Automated OCR failed. Please solve the CAPTCHA below."
                }
            return {
                "success": False,
                "message": search_result.get("message", "Search failed.")
            }

        html_result = search_result["html"]
        details = api.extract_diary_number_and_links(html_result)
        diary = details.get("diary_number", "N/A")
        orders = api.list_available_orders(details)

        # Automated Metadata Refresh: Sync Diary Number to Portfolio (captured from portal)
        if diary != "N/A":
            try:
                from lawnidhi.db import my_cases_repo
                # This ensures the Diary Number is permanently linked after first discovery
                my_cases_repo.update_diary_number(data.case_number, data.case_year, diary)
                log.info("Auto-synced Diary Number %s to case %s/%s", diary, data.case_number, data.case_year)
            except Exception as db_err:
                log.warning("Failed to auto-update diary number: %s", db_err)

        return {
            "success": True,
            "diary_number": diary,
            "orders": orders,
            "total_orders": len(orders),
        }
    except Exception as e:
        log.error("Case search failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download-orders")
async def download_orders(data: DownloadOrdersRequest, background_tasks: BackgroundTasks):
    """Download order PDFs for a case and auto-import into linked notebook."""
    try:
        from lawnidhi.scraper.dynamic_search import DynamicSearchAPI
        from lawnidhi import config

        download_dir = data.download_dir or config.get_default_download_dir()
        api = DynamicSearchAPI()
        search_result = api.auto_search(
            data.case_number, data.case_year,
            data.zone, data.case_type, data.retries,
        )

        if not search_result["success"]:
             if search_result.get("captcha_image_b64"):
                return {
                    "success": False,
                    "captcha_required": True,
                    "captcha_image": search_result["captcha_image_b64"],
                    "message": "Manual verification required for download."
                }
             return {
                "success": False,
                "message": search_result.get("message", "Search failed.")
            }

        html_result = search_result["html"]
        details = api.extract_diary_number_and_links(html_result)
        orders = api.list_available_orders(details)

        if not orders:
            return {
                "success": True,
                "message": "No downloadable orders found.",
                "downloaded": [],
            }

        indices = None if data.download_all else data.order_indices
        saved = api.download_selected_orders(orders, indices=indices, download_dir=download_dir)

        # Auto-import and trigger AI ingestion
        imported_meta = []
        try:
            from fastapi_app.services.lawnidhi.case_notebook_linker import import_document_to_notebook
            for path in saved:
                meta = import_document_to_notebook(
                    data.case_number, data.case_year,
                    str(path), doc_type="order",
                )
                if meta:
                    imported_meta.append(meta)
            
            # Queue background embedding if files were imported
            if imported_meta:
                nb_id = imported_meta[0]["notebook_id"]
                background_tasks.add_task(trigger_auto_ingestion, nb_id, imported_meta)

            # Automated Metadata Refresh: Sync Diary Number to Portfolio (captured from portal)
            diary = details.get("diary_number")
            if diary:
                try:
                    from lawnidhi.db import my_cases_repo
                    my_cases_repo.update_diary_number(data.case_number, data.case_year, diary)
                except Exception as db_err:
                    log.warning("Failed to auto-update diary number: %s", db_err)

        except Exception as nb_err:
            log.warning("Failed to auto-import orders or sync metadata: %s", nb_err)

        return {
            "success": True,
            "downloaded": [str(p) for p in saved],
            "imported_to_notebook": [m["url"] for m in (imported_meta or [])],
            "total_downloaded": len(saved),
            "message": f"Downloaded {len(saved)} order(s). AI analysis in progress...",
        }
    except Exception as e:
        log.error("Order download failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/solve-manual-captcha")
async def solve_manual_captcha(data: ManualCaptchaRequest):
    """Submit a manually solved CAPTCHA to complete the search."""
    try:
        from lawnidhi.scraper.dynamic_search import DynamicSearchAPI

        api = DynamicSearchAPI()
        # Since we just had a failure, the session in `api` needs to be fresh or 
        # ideally we should have shared session. For now, we attempt a direct fetch 
        # with the provided text. NOTE: NGT session might have expired, so this is 
        # a 'best effort' sync.
        html_result = api.fetch_diary_details(
            data.case_number, data.case_year, 
            data.captcha_text, data.zone, data.case_type
        )

        if not html_result or "captcha is incorrect" in html_result.lower():
            return {
                "success": False,
                "message": "Manual CAPTCHA verification failed. Please try again."
            }

        details = api.extract_diary_number_and_links(html_result)
        diary = details.get("diary_number", "N/A")
        orders = api.list_available_orders(details)

        return {
            "success": True,
            "diary_number": diary,
            "orders": orders,
            "total_orders": len(orders),
            "message": "Manual verification successful."
        }
    except Exception as e:
        log.error("Manual CAPTCHA solving failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def scraper_status():
    """Get scraper health status and last sync info."""
    try:
        from lawnidhi.db import cause_list_repo
        from lawnidhi.app import queries

        from datetime import date
        today_str = date.today().isoformat()
        
        stats = queries.get_db_stats()
        schedules = queries.list_schedules()
        
        # Filter for schedules that have actually occurred or are today
        past_or_today = [s for s in schedules if s['schedule_date'] <= today_str]
        latest_schedule = past_or_today[0] if past_or_today else (schedules[0] if schedules else None)

        return {
            "success": True,
            "db_stats": stats,
            "latest_schedule": latest_schedule,
            "total_schedules": len(schedules),
        }
    except Exception as e:
        log.error("Failed to get scraper status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
