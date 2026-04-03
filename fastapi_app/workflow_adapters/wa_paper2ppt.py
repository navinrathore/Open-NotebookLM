from __future__ import annotations

"""
paper2ppt Workflow Wrapper.

Split into three APIs:
- run_paper2page_content_wf_api: Runs only paper2page_content, focusing on parsing/generating pagecontent
- run_paper2page_content_refine_wf_api: Runs only paper2page_content, used for refining outline based on feedback
- run_paper2ppt_wf_api: Runs only paper2ppt, generates PPT resources based on existing pagecontent
- run_paper2ppt_full_pipeline: Full pipeline, serializing paper2page_content + paper2ppt
"""

import json
import time
from pathlib import Path
from typing import Any, List

from workflow_engine.logger import get_logger
from workflow_engine.state import Paper2FigureState
from workflow_engine.toolkits.multimodaltool.mineru_tool import _shrink_markdown
from workflow_engine.utils import get_project_root
from workflow_engine.workflow import run_workflow

from fastapi_app.notebook_paths import get_notebook_paths
from fastapi_app.schemas import Paper2PPTRequest, Paper2PPTResponse

log = get_logger(__name__)


def _to_serializable(obj: Any):
    """Recursively convert objects to a JSON-serializable structure"""
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_serializable(i) for i in obj]
    if hasattr(obj, "__dict__"):
        return _to_serializable(obj.__dict__)
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _ensure_result_path_for_full(
    email: str | None,
    notebook_id: str | None = None,
    notebook_title: str | None = None,
) -> Path:
    """
    Unified root output directory for full pipeline.
    New layout: outputs/{title}_{id}/ppt/{timestamp}/
    Legacy fallback: outputs/{email or 'default'}/paper2ppt/<timestamp>/
    """
    ts = int(time.time())
    if notebook_id:
        nb_paths = get_notebook_paths(notebook_id, notebook_title or "", email)
        base_dir = nb_paths.feature_output_dir("ppt", ts)
    else:
        project_root = get_project_root()
        code = email or "default"
        base_dir = (project_root / "outputs" / code / "paper2ppt" / str(ts)).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _init_state_from_request(
    req: Paper2PPTRequest,
    result_path: Path | None = None,
    override_pagecontent: list[dict] | None = None,
) -> Paper2FigureState:
    """
    Initialize Paper2FigureState from Paper2PPTRequest, compatible with three scenarios:
    - full pipeline: Needs to set paper_file / text_content based on input_type / input_content;
    - pagecontent-only: Focused on PDF/TEXT/PPT parsing, not necessarily generating PPT resources immediately;
    - ppt-only: Directly generate PPT from externally provided pagecontent / result_path.
    """
    state = Paper2FigureState(
        messages=[],
        agent_results={},
        request=req,
    )

    # Set input based on scenario
    input_type = (req.input_type or "").upper()
    input_content = req.input_content or ""

    # Parsing of PDF / TEXT / FIGURE remains consistent with wf_paper2page_content conventions
    if input_type == "PDF":
        state.paper_file = input_content
    elif input_type in ("PPT", "PPTX"):
        # For PPT/PPTX, we also unify under paper_file; wf_paper2page_content will follow ppt_to_images path
        state.paper_file = input_content
    elif input_type == "TEXT":
        # Plain text scenario: Use directly as text_content
        state.text_content = input_content
    elif input_type == "TOPIC":
        state.text_content = input_content
    else:
        log.warning(f"[paper2ppt] Unknown input_type on init_state: {input_type}")

    # Compatible with style and other control parameters
    state.aspect_ratio = req.aspect_ratio
    state.style = req.style
    state.render_dpi = getattr(req, "render_dpi", None)

    # Override pagecontent (mainly used for running only paper2ppt)
    if override_pagecontent is not None:
        try:
            state.pagecontent = list(override_pagecontent)
        except TypeError:
            log.warning("[paper2ppt] override_pagecontent is not list[dict], ignoring.")

    # Unified result_path (if explicitly specified by caller, use that first)
    if result_path is not None:
        state.result_path = str(Path(result_path).resolve())

    return state


def _try_load_existing_mineru_markdown(result_root: Path) -> tuple[str, str]:
    """
    Attempt to load MinerU parsed markdown from existing result_root.
    Compatible with different MinerU backend output directories like auto / hybrid_auto.

    Returns:
        (mineru_output, mineru_root_dir)
    """
    candidates = []
    for pattern in ["*/auto/*.md", "*/hybrid_auto/*.md"]:
        try:
            candidates.extend(result_root.glob(pattern))
        except Exception:
            pass
    if not candidates:
        # Fallback: .md in any subdirectory
        try:
            candidates = list(result_root.glob("*/*/*.md"))
        except Exception:
            candidates = []

    if not candidates:
        return "", ""

    md_path = candidates[0]
    try:
        md = md_path.read_text(encoding="utf-8")
    except Exception:
        return "", ""

    mineru_output = _shrink_markdown(md, max_h1=8, max_chars=30_000)
    return mineru_output, str(md_path.parent.resolve())


async def run_paper2page_content_wf_api(
    req: Paper2PPTRequest,
    result_path: Path | None = None,
    notebook_id: str | None = None,
    notebook_title: str | None = None,
) -> Paper2PPTResponse:
    """
    Runs only the paper2page_content workflow, mainly used to parse structured 
    pagecontent from PDF / PPTX / TEXT.

    - Input: Paper2PPTRequest (requires input_type / input_content, etc.)
    - Output: Paper2PPTResponse, where:
        - success: Whether successful
        - pagecontent: Parsed page content (structured list)
        - result_path: Unified output directory used by this workflow
    """
    # Unified result_path: Use caller-specified path first, otherwise generate based on notebook layout
    if result_path is None:
        result_root = _ensure_result_path_for_full(req.email, notebook_id, notebook_title)
    else:
        result_root = result_path

    state = _init_state_from_request(req, result_path=result_root)

    log.info(f"[paper2page_content_wf_api] start, result_path={state.result_path}, input_type={req.input_type}")
    if req.use_long_paper:
        final_state: Paper2FigureState = await run_workflow("paper2page_content_for_long_paper", state)
    else:    
        final_state: Paper2FigureState = await run_workflow("paper2page_content", state)
    # Extract results
    pagecontent = final_state["pagecontent"] or []
    log.critical(f"[paper2page_content_wf_api] pagecontent={pagecontent}")
    result_path = final_state["result_path"] or str(result_root)

    # Construct response: Currently Paper2PPTResponse only has success, placeholder expansion fields are injected via dynamic attributes
    resp_data: dict[str, Any] = {
        "success": True,
        "pagecontent": pagecontent,
        "result_path": result_path,
    }

    return Paper2PPTResponse(**resp_data)


async def run_paper2page_content_refine_wf_api(
    req: Paper2PPTRequest,
    pagecontent: list[dict],
    outline_feedback: str,
    result_path: Path | None = None,
    notebook_id: str | None = None,
    notebook_title: str | None = None,
) -> Paper2PPTResponse:
    """
    Runs only the paper2page_content workflow, used for refining existing outline based on feedback.
    """
    if result_path is None:
        result_root = _ensure_result_path_for_full(req.email, notebook_id, notebook_title)
    else:
        result_root = result_path

    state = _init_state_from_request(req, result_path=result_root)
    state.pagecontent = list(pagecontent or [])
    state.outline_feedback = outline_feedback or ""
    if not getattr(state, "minueru_output", ""):
        mineru_output, mineru_root = _try_load_existing_mineru_markdown(result_root)
        if mineru_output:
            state.minueru_output = mineru_output
        if mineru_root:
            state.mineru_root = mineru_root

    log.info(f"[paper2page_content_refine_wf_api] start, result_path={state.result_path}")
    final_state: Paper2FigureState = await run_workflow("paper2page_content", state)

    pagecontent = final_state["pagecontent"] or []
    result_path = final_state["result_path"] or str(result_root)

    resp_data: dict[str, Any] = {
        "success": True,
        "pagecontent": pagecontent,
        "result_path": result_path,
    }
    return Paper2PPTResponse(**resp_data)


async def run_paper2ppt_wf_api(
    req: Paper2PPTRequest,
    pagecontent: list[dict] | None = None,
    result_path: str | None = None,
    get_down: bool | None = None,
    edit_page_num: int | None = None,
    edit_page_prompt: str | None = None,
    auto_fill_generated_pages: bool = True,
) -> Paper2PPTResponse:
    """
    Runs only the paper2ppt workflow. Usually used for:
    - Existing pagecontent (possibly from front-end edited JSON), only want to generate PPT resources;
    - Or already ran paper2page_content, hope to generate repeatedly under same result_path.

    Parameters:
    - req: Paper2PPTRequest
    - pagecontent: If provided, overrides state.pagecontent
    - result_path: If provided, forces use of this output directory; otherwise wf_paper2ppt decides
    - get_down: Corresponds to workflow state.gen_down
        * False/None: Run generate_pages (batch generation)
        * True: Run edit_single_page (per-page secondary editing)
    - edit_page_num/edit_page_prompt: Only effective when get_down=True
    - auto_fill_generated_pages: In edit mode, whether to scan page_*.png from result_path/ppt_pages to backfill state.generated_pages
    """
    base_dir: Path | None = None
    if result_path:
        base_dir = Path(result_path).expanduser().resolve()
        base_dir.mkdir(parents=True, exist_ok=True)

    state = _init_state_from_request(
        req,
        result_path=base_dir,
        override_pagecontent=pagecontent,
    )

    # Map get_down -> workflow state.gen_down
    if get_down is not None:
        state.gen_down = bool(get_down)

    # Edit mode parameter injection
    if bool(getattr(state, "gen_down", False)):
        if edit_page_num is not None:
            state.edit_page_num = int(edit_page_num)
        if edit_page_prompt is not None:
            state.edit_page_prompt = str(edit_page_prompt)

        if auto_fill_generated_pages and base_dir is not None:
            try:
                img_dir = base_dir / "ppt_pages"
                if img_dir.exists():
                    imgs = sorted(img_dir.glob("page_*.png"))
                    state.generated_pages = [str(p.resolve()) for p in imgs]
            except Exception as e:  # pragma: no cover
                log.warning(f"[paper2ppt_wf_api] auto_fill_generated_pages failed: {e}")
         
    # mineru_root auto detection (compatible with auto / hybrid_auto)
    mineru_root_found = ""
    if base_dir is not None:
        input_dir = base_dir / "input"
        if input_dir.exists():
            for sub in ["auto", "hybrid_auto"]:
                candidate = input_dir / sub
                if candidate.exists() and candidate.is_dir():
                    mineru_root_found = str(candidate)
                    break
            if not mineru_root_found:
                # Fallback: Scan subdirectories under input containing .md
                for child in sorted(input_dir.iterdir()):
                    if child.is_dir() and list(child.glob("*.md")):
                        mineru_root_found = str(child)
                        break
    state.mineru_root = mineru_root_found or f"{base_dir}/input/auto"

    # Attempt to backfill mineru_output (markdown) for table_extractor, etc.
    try:
        md_dir = Path(state.mineru_root)
        if md_dir.exists():
            md_files = list(md_dir.glob("*.md"))
            if md_files:
                # Default to the first md
                md_path = md_files[0]
                raw_md = md_path.read_text(encoding="utf-8")
                state.mineru_output = _shrink_markdown(raw_md, max_h1=8, max_chars=30_000)
                log.info(f"[paper2ppt_wf_api] Loaded mineru_output from {md_path}, len={len(state.mineru_output)}")
            else:
                log.warning(f"[paper2ppt_wf_api] No .md file found in {md_dir}")
        else:
            log.warning(f"[paper2ppt_wf_api] mineru_root dir not found: {md_dir}")
    except Exception as e:
        log.warning(f"[paper2ppt_wf_api] Failed to load mineru_output: {e}")

    log.info(
        f"[paper2ppt_wf_api] start, result_path={getattr(state, 'result_path', None)}, "
        f"pagecontent_len={len(getattr(state, 'pagecontent', []) or [])}"
    )

    # final_state: Paper2FigureState = await run_workflow("paper2ppt_parallel", state)
    log.critical(f'[wa_paper2ppt] req.ref_img path {req.ref_img}')
    final_state: Paper2FigureState = await run_workflow("paper2ppt_parallel_consistent_style", state)

    # Extract key outputs
    ppt_pdf_path = getattr(final_state, "ppt_pdf_path", "")
    ppt_pptx_path = getattr(final_state, "ppt_pptx_path", "")
    final_pagecontent = getattr(final_state, "pagecontent", []) or []
    final_result_path = getattr(final_state, "result_path", result_path or "")

    resp_data: dict[str, Any] = {
        "success": True,
        "ppt_pdf_path": str(ppt_pdf_path) if ppt_pdf_path else "",
        "ppt_pptx_path": str(ppt_pptx_path) if ppt_pptx_path else "",
        "pagecontent": final_pagecontent,
        "result_path": final_result_path,
    }

    return Paper2PPTResponse(**resp_data)


async def run_paper2ppt_full_pipeline(
    req: Paper2PPTRequest,
    notebook_id: str | None = None,
    notebook_title: str | None = None,
) -> Paper2PPTResponse:
    """
    full pipeline:
    - First run paper2page_content: Parse pagecontent based on PDF/PPT/TEXT
    - Then run paper2ppt: Generate PPT resources (PDF + PPTX) based on pagecontent

    Inputs:
    - Paper2PPTRequest (requires at least input_type / input_content)

    Outputs:
    - Paper2PPTResponse:
        - success
        - ppt_pdf_path
        - ppt_pptx_path
        - pagecontent
        - result_path
    """
    # Unified output root directory, shared by both workflows
    result_root = _ensure_result_path_for_full(req.email, notebook_id, notebook_title)

    # ---------- Step 1: paper2page_content ----------
    state_pc = _init_state_from_request(req, result_path=result_root)
    log.info(
        f"[paper2ppt_full_pipeline] step1 paper2page_content, "
        f"result_path={state_pc.result_path}, input_type={req.input_type}, use_long_paper={req.use_long_paper}"
    )
    if req.use_long_paper:
        state_pc = await run_workflow("paper2page_content_for_long_paper", state_pc)
    else:
        state_pc = await run_workflow("paper2page_content", state_pc)

    pagecontent = getattr(state_pc, "pagecontent", []) or []
    # Ensure result_path consistency
    final_result_path = getattr(state_pc, "result_path", str(result_root))

    # ---------- Step 2: paper2ppt ----------
    # Reuse state_pc to continue executing paper2ppt, avoid losing intermediate state
    log.info(
        f"[paper2ppt_full_pipeline] step2 paper2ppt, "
        f"result_path={final_result_path}, pagecontent_len={len(pagecontent)}"
    )
    state_pc.pagecontent = pagecontent
    state_pc.result_path = final_result_path

    state_pp: Paper2FigureState = await run_workflow("paper2ppt_parallel_consistent_style", state_pc)

    ppt_pdf_path = getattr(state_pp, "ppt_pdf_path", "")
    ppt_pptx_path = getattr(state_pp, "ppt_pptx_path", "")
    final_pagecontent = getattr(state_pp, "pagecontent", []) or []

    resp_data: dict[str, Any] = {
        "success": True,
        "ppt_pdf_path": str(ppt_pdf_path) if ppt_pdf_path else "",
        "ppt_pptx_path": str(ppt_pptx_path) if ppt_pptx_path else "",
        "pagecontent": final_pagecontent,
        "result_path": final_result_path,
    }

    return Paper2PPTResponse(**resp_data)
