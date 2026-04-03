from __future__ import annotations

import os
from pathlib import Path
from typing import Set
from urllib.parse import urlparse, unquote

from fastapi import HTTPException, Request

from workflow_engine.logger import get_logger
from workflow_engine.utils import get_project_root

log = get_logger(__name__)



def _to_outputs_url(abs_path: str, request: Request | None = None) -> str:
    """
    Converts an absolute path to a full URL accessible by the browser.
    Default assumes all output files are located in the outputs/ directory under the project root.
    """
    project_root = get_project_root()
    outputs_root = project_root / "outputs"

    log.info(f"[DEBUG] project_root: {project_root}")
    log.info(f"[DEBUG] outputs_root: {outputs_root}")
    log.info(f"[DEBUG] abs_path: {abs_path}")

    p = Path(abs_path)
    # If relative path, convert to absolute (relative to project root)
    if not p.is_absolute():
        p = (project_root / p).resolve()

    try:
        rel = p.relative_to(outputs_root)
        path_part = rel.as_posix().replace("@", "%40")

        if request is not None:
            base_url = str(request.base_url).rstrip("/")
            url = f"{base_url}/outputs/{path_part}"
        else:
            url = f"/outputs/{path_part}"

        log.warning(f"[DEBUG] generated URL: {url}")
        return url
    except ValueError as e:
        log.error(f"[ERROR] Path conversion failed: {e}")
        if "/outputs/" in abs_path:
            idx = abs_path.index("/outputs/")
            fallback_url = abs_path[idx:].replace("@", "%40")
            log.warning(f"[WARN] Using fallback URL: {fallback_url}")
            return fallback_url
        log.error(f"[ERROR] Cannot convert path to URL: {abs_path}")
        return abs_path


def _from_outputs_url(url_or_path: str) -> str:
    """
    Attempts to convert a URL (containing /outputs/) from the frontend back to a local absolute path.
    Returns the original value if it's not a URL or conversion fails.
    """
    if not url_or_path or not isinstance(url_or_path, str):
        return url_or_path

    # If already an absolute path and exists, return as is
    if os.path.isabs(url_or_path) and os.path.exists(url_or_path):
        return url_or_path

    # Simple check if it's an http URL
    if not url_or_path.startswith("http") and not url_or_path.startswith("/outputs/"):
        return url_or_path

    # Find position of /outputs/
    if "/outputs/" not in url_or_path:
        return url_or_path

    try:
        # Get part after /outputs/
        path_str = url_or_path
        if url_or_path.startswith("http"):
            parsed = urlparse(url_or_path)
            path_str = parsed.path

        if "/outputs/" in path_str:
            idx = path_str.index("/outputs/")
            # outputs/xxx/yyy (Url-encoded characters like %40 must be decoded to match disk paths)
            rel_path = path_str[idx + len("/outputs/") :].lstrip("/")
            rel_path = unquote(rel_path)

            project_root = get_project_root()
            outputs_root = project_root / "outputs"
            abs_path = (outputs_root / rel_path).resolve()

            log.info(f"[DEBUG] Converted URL {url_or_path} to path {abs_path}")
            return str(abs_path)

    except Exception as e:
        log.warning(f"[WARN] Failed to convert URL to path: {e}")

    return url_or_path
