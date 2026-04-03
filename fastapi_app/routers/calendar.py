"""
LawNidhi Integration — Hearing Calendar Router (Stub)

Provides hearing schedule data from parsed cause lists.
Calendar dates are identifiable by counsel name and case ID.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException

from workflow_engine.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/calendar", tags=["Calendar (LawNidhi)"])


@router.get("/hearings")
async def list_hearings(
    case: Optional[str] = None,
    counsel: Optional[str] = None,
):
    """
    Get hearing schedule from parsed cause lists.
    Returns individual case appearances.
    """
    try:
        from lawnidhi.app import queries
        from lawnidhi import config

        counsel_name = counsel or config.get_counsel_name()
        
        if not counsel_name:
            # Fallback to general schedules if no counsel specified
            schedules = queries.list_schedules()
            return {
                "success": True,
                "hearings": schedules,
                "total": len(schedules),
                "type": "general_schedules"
            }

        # Use aliases for robust matching
        aliases = config.get_counsel_aliases()
        if aliases and counsel_name in aliases:
            all_hearings = queries.get_cases_by_counsel_names(aliases)
        else:
            all_hearings = queries.get_cases_by_counsel(counsel_name)

        # Filter by case if requested (e.g. "83/2025")
        if case:
            all_hearings = [h for h in all_hearings if f"{h['case_number']}/{h['case_year']}" == case or h['case_number'] == case]

        return {
            "success": True,
            "hearings": all_hearings,
            "total": len(all_hearings),
            "counsel": counsel_name,
            "type": "case_hearings"
        }
    except Exception as e:
        log.error("Failed to get hearings: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
