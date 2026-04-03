"""
LawNidhi Integration — Reports Router (Stub)

Provides report generation endpoints (counsel appearance logs, portfolio stats).
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Body

from workflow_engine.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/reports", tags=["Reports (LawNidhi)"])


@router.get("/counsels")
async def list_counsels():
    """List all unique counsel found in the cause lists."""
    try:
        from lawnidhi.app import queries
        counsels = queries.list_all_counsels()
        return {"success": True, "counsels": counsels}
    except Exception as e:
        log.error("Failed to list counsels: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/appearance-log")
async def generate_appearance_log(
    counsel: Optional[str] = Body(None, embed=True),
    start_date: Optional[str] = Body(None, embed=True),
    end_date: Optional[str] = Body(None, embed=True),
):
    """Generate a counsel appearance log for billing/invoicing."""
    try:
        from lawnidhi.app.reports import generate_counsel_appearance_log
        from lawnidhi import config

        counsel_name = counsel or config.get_counsel_name()
        if not counsel_name:
            raise HTTPException(status_code=400, detail="Counsel name required")

        report_text = generate_counsel_appearance_log(counsel_name, start_date, end_date)
        return {
            "success": True,
            "report_text": report_text,
            "counsel": counsel_name,
            "filters": {"start_date": start_date, "end_date": end_date}
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to generate appearance log: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/case-stats")
async def portfolio_stats():
    """Get overall portfolio statistics for the reports dashboard."""
    try:
        from lawnidhi.db import my_cases_repo
        from lawnidhi.app import queries

        cases = my_cases_repo.list_cases()
        db_stats = queries.get_db_stats()
        schedules = queries.list_schedules()

        status_counts = {}
        for c in cases:
            s = c.status.value if hasattr(c.status, 'value') else str(c.status)
            status_counts[s] = status_counts.get(s, 0) + 1

        return {
            "success": True,
            "total_cases": len(cases),
            "status_counts": status_counts,
            "total_schedules": len(schedules),
            "db_stats": db_stats,
        }
    except Exception as e:
        log.error("Failed to get portfolio stats: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
