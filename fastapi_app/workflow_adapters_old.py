# from __future__ import annotations

# """
# Wraps workflows from dataflow_agent.workflow.* into pure Python functions callable by FastAPI routes.

# Primary reference points from gradio_app for encapsulation logic:
# - gradio_app.pages.operator_write.run_operator_write_pipeline
# - gradio_app.utils.wf_pipeine_rec.run_pipeline_workflow
# """

# import base64
# import os
# from pathlib import Path
# from typing import Any, Dict, List

# import json
# import time

# from workflow_engine.state import Paper2FigureState, DFRequest, DFState, Paper2FigureRequest as DF_Paper2FigureRequest
# from workflow_engine.workflow import run_workflow
# from workflow_engine.logger import get_logger
# from workflow_engine.state import Paper2VideoRequest, Paper2VideoState
# from workflow_engine.utils import get_project_root
# from workflow_engine.workflow.wf_pipeline_recommend_extract_json import (
#     create_pipeline_graph,
# )
# from workflow_engine.workflow.wf_pipeline_write import create_operator_write_graph

# from .schemas import (
#     OperatorWriteRequest,
#     OperatorWriteResponse,
#     PipelineRecommendRequest,
#     PipelineRecommendResponse,
#     Paper2FigureRequest,
#     Paper2FigureResponse,
#     FeaturePaper2VideoRequest,
#     FeaturePaper2VideoResponse,
# )

# log = get_logger(__name__)




# # ------------------- Operator Writing Workflow Encapsulation -------------------


# async def run_operator_write_pipeline_api(
#     req: OperatorWriteRequest,
# ) -> OperatorWriteResponse:
#     """
#     Operator writing encapsulation based on wf_pipeline_write.create_operator_write_graph.

#     Aligns with run_operator_write_pipeline in gradio_app.pages.operator_write,
#     but uses Pydantic models for input/output to facilitate direct FastAPI returns.
#     """
#     # 设置环境变量
#     if req.api_key:
#         os.environ["DF_API_KEY"] = req.api_key
#     else:
#         # Fallback to env var or a dummy key if not explicitly provided
#         req.api_key = os.getenv("DF_API_KEY", "sk-dummy")

#     # Handle default json_file
#     projdir = get_project_root()
#     json_file = req.json_file or f"{projdir}/tests/test.jsonl"

#     # 构造 DFRequest / DFState
#     df_req = DFRequest(
#         language=req.language,
#         chat_api_url=req.chat_api_url,
#         api_key=req.api_key,
#         model=req.model,
#         target=req.target,
#         need_debug=req.need_debug,
#         max_debug_rounds=req.max_debug_rounds,
#         json_file=json_file,
#     )
#     state = DFState(request=df_req, messages=[])

#     # Set output path (if provided)
#     if req.output_path:
#         state.temp_data["pipeline_file_path"] = req.output_path

#     # Set category
#     if req.category:
#         state.temp_data["category"] = req.category

#     # Initialize debug rounds
#     state.temp_data["round"] = 0

#     # Build and execute workflow graph
#     graph = create_operator_write_graph().build()
#     # Recursion limit consistent with Gradio version: main chain 4 steps + 5 steps per round * rounds + buffer 5
#     recursion_limit = 4 + 5 * req.max_debug_rounds + 5
#     final_state = await graph.ainvoke(
#         state,
#         config={"recursion_limit": recursion_limit},
#     )

#     # ---------- Extract results (refer to gradio_app/pages/operator_write.py) ----------
#     matched_ops: List[str] = []
#     code_str: str = ""
#     execution_result: Dict[str, Any] = {}
#     debug_runtime: Dict[str, Any] = {}
#     agent_results: Dict[str, Any] = {}

#     # Extract matched operators
#     try:
#         if isinstance(final_state, dict):
#             matched = final_state.get("matched_ops", [])
#             if not matched:
#                 matched = (
#                     final_state.get("agent_results", {})
#                     .get("match_operator", {})
#                     .get("results", {})
#                     .get("match_operators", [])
#                 )
#         else:
#             matched = getattr(final_state, "matched_ops", [])
#             if not matched and hasattr(final_state, "agent_results"):
#                 matched = (
#                     final_state.agent_results.get("match_operator", {})
#                     .get("results", {})
#                     .get("match_operators", [])
#                 )
#         matched_ops = list(matched or [])
#     except Exception as e:  # pragma: no cover - Logging only
#         log.warning(f"[operator_write] Failed to extract matched operators: {e}")
#         matched_ops = []

#     # Extract generated code
#     try:
#         if isinstance(final_state, dict):
#             temp_data = final_state.get("temp_data", {})
#             code_str = (
#                 temp_data.get("pipeline_code", "") if isinstance(temp_data, dict) else ""
#             )
#         else:
#             temp_data = getattr(final_state, "temp_data", {})
#             code_str = (
#                 temp_data.get("pipeline_code", "") if isinstance(temp_data, dict) else ""
#             )
#     except Exception as e:  # pragma: no cover
#         log.warning(f"[operator_write] Failed to extract code: {e}")
#         code_str = ""

#     # Extract execution results
#     try:
#         if isinstance(final_state, dict):
#             exec_res = final_state.get("execution_result", {}) or {}
#             if not exec_res or ("success" not in exec_res):
#                 exec_res = (
#                     final_state.get("agent_results", {})
#                     .get("operator_executor", {})
#                     .get("results", {})
#                     or exec_res
#                 )
#         else:
#             exec_res = getattr(final_state, "execution_result", {}) or {}
#             if (not exec_res or ("success" not in exec_res)) and hasattr(
#                 final_state, "agent_results"
#             ):
#                 exec_res = (
#                     final_state.agent_results.get("operator_executor", {}).get(
#                         "results", {}
#                     )
#                     or exec_res
#                 )
#         execution_result = dict(exec_res or {})
#     except Exception as e:  # pragma: no cover
#         log.warning(f"[operator_write] Failed to extract execution result: {e}")
#         execution_result = {}

#     # Extract debug runtime info
#     try:
#         if isinstance(final_state, dict):
#             dbg = (final_state.get("temp_data") or {}).get("debug_runtime")
#         else:
#             dbg = getattr(final_state, "temp_data", {}).get("debug_runtime")
#         debug_runtime = dict(dbg or {})
#     except Exception as e:  # pragma: no cover
#         log.warning(f"[operator_write] Failed to extract debug info: {e}")
#         debug_runtime = {}

#     # Extract agent_results
#     try:
#         if isinstance(final_state, dict):
#             agent_results = dict(final_state.get("agent_results", {}) or {})
#         else:
#             agent_results = dict(getattr(final_state, "agent_results", {}) or {})
#     except Exception as e:  # pragma: no cover
#         log.warning(f"[operator_write] Failed to extract agent_results: {e}")
#         agent_results = {}

#     # Construct log info (similar to Gradio version for easy frontend display)
#     log_lines: List[str] = []
#     log_lines.append("==== Operator Writing Results ====")
#     log_lines.append(f"\nNumber of matched operators: {len(matched_ops)}")
#     if matched_ops:
#         log_lines.append(f"Matched operators: {matched_ops}")

#     log_lines.append(f"\nGenerated code length: {len(code_str)} characters")

#     if execution_result:
#         success_flag = execution_result.get("success", False)
#         log_lines.append(f"\nExecution success: {success_flag}")
#         if not success_flag:
#             stderr = execution_result.get("stderr", "") or execution_result.get(
#                 "traceback", ""
#             )
#             if stderr:
#                 log_lines.append(f"\nError Message:\n{stderr[:500]}")

#     if debug_runtime:
#         log_lines.append("\n==== Debug Info ====")
#         input_key = debug_runtime.get("input_key")
#         available_keys = debug_runtime.get("available_keys", [])
#         if input_key:
#             log_lines.append(f"Selected input key: {input_key}")
#         if available_keys:
#             log_lines.append(f"Available keys: {available_keys}")
#         stdout = debug_runtime.get("stdout", "")
#         stderr = debug_runtime.get("stderr", "")
#         if stdout:
#             log_lines.append(f"\nStandard Output:\n{stdout[:1000]}")
#         if stderr:
#             log_lines.append(f"\nStandard Error:\n{stderr[:1000]}")

#     log_text = "\n".join(log_lines)

#     return OperatorWriteResponse(
#         success=True,
#         code=code_str or "",
#         matched_ops=matched_ops,
#         execution_result=execution_result,
#         debug_runtime=debug_runtime,
#         agent_results=agent_results,
#         log=log_text,
#     )


# # ------------------- Pipeline Recommendation Workflow Encapsulation -------------------


# async def run_pipeline_recommend_api(
#     req: PipelineRecommendRequest,
# ) -> PipelineRecommendResponse:
#     """
#     Encapsulation based on wf_pipeline_recommend_extract_json.create_pipeline_graph.

#     Aligns with run_pipeline_workflow in gradio_app.utils.wf_pipeine_rec.
#     """
#     # Environment variable setup
#     if req.api_key:
#         os.environ["DF_API_KEY"] = req.api_key
#         os.environ["DF_API_URL"] = req.chat_api_url

#     project_root: Path = get_project_root()
#     tmps_dir: Path = project_root / "dataflow_agent" / "tmps"

#     # Perform URL-safe base64 encoding on session_id once to ensure safe directory names
#     session_id_encoded = base64.urlsafe_b64encode(req.session_id.encode()).decode()
#     session_dir: Path = tmps_dir / session_id_encoded
#     session_dir.mkdir(parents=True, exist_ok=True)

#     python_file_path = session_dir / "pipeline.py"

#     df_req = DFRequest(
#         language="en",
#         chat_api_url=req.chat_api_url,
#         api_key=req.api_key,
#         model=req.model_name,
#         json_file=req.json_file,
#         target=req.target,
#         python_file_path=str(python_file_path),
#         need_debug=req.need_debug,
#         session_id=session_id_encoded,
#         max_debug_rounds=req.max_debug_rounds,
#         chat_api_url_for_embeddings=req.chat_api_url_for_embeddings,
#         embedding_model_name=req.embedding_model_name,
#         update_rag_content=req.update_rag_content,
#     )

#     state = DFState(request=df_req, messages=[])
#     state.temp_data["round"] = 0
#     state.debug_mode = True

#     graph = create_pipeline_graph().build()
#     final_state = await graph.ainvoke(state)

#     # Align with original implementation: execution_result uses debug_history
#     if isinstance(final_state, dict):
#         debug_history = dict(final_state.get("debug_history", {}) or {})
#         agent_results = dict(final_state.get("agent_results", {}) or {})
#     else:
#         debug_history = dict(getattr(final_state, "debug_history", {}) or {})
#         agent_results = dict(getattr(final_state, "agent_results", {}) or {})

#     return PipelineRecommendResponse(
#         success=True,
#         python_file=str(df_req.python_file_path),
#         execution_result=debug_history,
#         agent_results=agent_results,
#     )

# # ------------------- Paper2Video Workflow Encapsulation -------------------
# async def run_paper_to_video_api(
#     req: FeaturePaper2VideoRequest,
# ) -> FeaturePaper2VideoResponse:
#     """
#     Encapsulation based on wf_paper2video.create_paper2video_graph.

#     Aligns with run_paper2video_workflow in gradio_app.pages.paper2video.
#     """
#     # 设置环境变量
#     if req.api_key:
#         os.environ["DF_API_KEY"] = req.api_key
#     else:
#         req.api_key = os.getenv("DF_API_KEY", "sk-dummy")

#     # 构造 DFRequest / DFState
#     req = Paper2VideoRequest(
#         chat_api_url=req.chat_api_url,
#         api_key=req.api_key,
#         model=req.model,
#         paper_pdf_path=req.pdf_path,
#         user_imgs_path=req.img_path,
#         language=req.language,
#     )
#     state = Paper2VideoState(request=req, messages=[])

#     from workflow_engine.workflow.wf_paper2video import create_paper2video_graph
    
#     graph = create_paper2video_graph().build()
#     final_state: Paper2VideoState = await graph.ainvoke(state)

#     # Extract results
#     result = {
#         "success": True,
#         "final_state": final_state,
#     }
    
#     # Extract output PDF file
#     try:
#         if isinstance(final_state, dict):
#             ppt_path = final_state.get("ppt_path", [])
#         else:
#             ppt_path = getattr(final_state, "ppt_path", [])
            
#         result["ppt_path"] = ppt_path or []
#     except Exception as e:
#         if 'log' in locals():
#             log.warning(f"Failed to extract PDF-based PPT: {e}")
#         result["ppt_path"] = []
    
#     return FeaturePaper2VideoResponse(
#         success=result.get("success", False),
#         ppt_path=result.get("ppt_path", ""),
#     )

# # --------------------------Paper2Figure----------------------------

# # ====================== Common Utility Functions ====================== #
# def to_serializable(obj: Any):
#     """Recursively convert objects to JSON-serializable structures"""
#     if isinstance(obj, dict):
#         return {k: to_serializable(v) for k, v in obj.items()}
#     if isinstance(obj, list):
#         return [to_serializable(i) for i in obj]
#     if hasattr(obj, "__dict__"):
#         return to_serializable(obj.__dict__)
#     if isinstance(obj, (str, int, float, bool)) or obj is None:
#         return obj
#     return str(obj)

# def save_final_state_json(final_state: dict, out_dir: Path, filename: str = "final_state.json") -> None:
#     """
#     Directly save final_state using json.dump to <Project Root>/dataflow_agent/tmps/(session_id?)/final_state.json.
#     Fallback to str for non-serializable objects.
#     """
#     out_dir.mkdir(parents=True, exist_ok=True)
#     out_path = out_dir / filename
#     with out_path.open("w", encoding="utf-8") as f:
#         json.dump(final_state, f, ensure_ascii=False, indent=2, default=str)
#     print(f"final_state has been saved to {out_path}")

# # ====================== Main Function ====================== #
# async def run_paper2figure_wf_api(req: Paper2FigureRequest) -> Paper2FigureResponse:
#     """
#     Select different workflow based on graph_type and split output directories.

#     Input req typically mapped from frontend FormData in FastAPI route layer (e.g., paper2any.generate_paper2figure):
#       - input_type: "PDF" / "TEXT" / "FIGURE"
#       - input_content: File path or plain text
#       - graph_type: "model_arch" | "tech_route" | "exp_data"
#     """
#     # -------- Base Paths and Output Directory -------- #
#     project_root: Path = get_project_root()
#     tmps_dir: Path = project_root / "dataflow_agent" / "tmps"
#     tmps_dir.mkdir(parents=True, exist_ok=True)

#     # -------- Mapping to dataflow_agent.state.Paper2FigureRequest -------- #
#     # df_req = DF_Paper2FigureRequest(
#     #     language=req.language,
#     #     chat_api_url=req.chat_api_url,
#     #     api_key=req.api_key or req.chat_api_key,
#     #     model=req.model,
#     # )
#     # Transparently pass extra fields
#     # df_req.input_type = req.input_type
#     # df_req.chat_api_key = req.chat_api_key
#     # df_req.input_content = req.input_content
#     # df_req.gen_fig_model = req.gen_fig_model
#     # df_req.bg_rm_model = req.bg_rm_model
#     # df_req["graph_type"] = req.graph_type
#     # df_req["style"] = req.style

#     state = Paper2FigureState(request=req, messages=[])
#     state.temp_data["round"] = 0

#     # Set specific input based on input_type / input_content
#     if req.input_type == "PDF":
#         state.paper_file = req.input_content
#     elif req.input_type == "TEXT":
#         state.paper_idea = req.input_content
#     elif req.input_type == "FIGURE":
#         state.fig_draft_path = req.input_content
#     else:
#         raise TypeError("Invalid input type. Available input type: PDF, TEXT, FIGURE.")

#     # Other control parameters
#     state.aspect_ratio = req.aspect_ratio

#     # -------- Determine Workflow and Output Root based on graph_type -------- #
#     ts = time.strftime("%Y%m%d_%H%M%S")
#     graph_type = req.graph_type

#     if graph_type == "model_arch":
#         wf_name = "paper2fig_with_sam"
#         result_root =  project_root / "outputs" / req.invite_code / "paper2fig" / ts
#     elif graph_type == "tech_route":
#         wf_name = "paper2technical"
#         result_root = project_root / "outputs" / req.invite_code / "paper2tec" / ts
#     elif graph_type == "exp_data":
#         # TODO: Integrate paper2exp workflow later
#         wf_name = "paper2fig_with_sam"
#         result_root = project_root / "outputs" / req.invite_code / "paper2exp" / ts
#     else:
#         wf_name = "paper2fig_with_sam"
#         result_root = project_root / "outputs" / req.invite_code / "paper2fig" / ts

#     result_root.mkdir(parents=True, exist_ok=True)
#     state.result_path = str(result_root)
#     log.critical(f"[paper2figure] result_path: {state.result_path} !!!!!!!!\n")
#     state.mask_detail_level = 2

#     # -------- Asynchronous Execution -------- #
#     log.critical(f"[paper2figure] req: {req} !!!!!!!!\n")
#     final_state: Paper2FigureState = await run_workflow(wf_name, state)

#     # -------- Save Final State -------- #
#     serializable_state = to_serializable(final_state)
#     save_final_state_json(
#         final_state=serializable_state,
#         out_dir=tmps_dir / ts,
#     )

#     log.info(f"[paper2figure] Results saved in directory: {state.result_path}")
#     log.info(f"[paper2figure]: {final_state['ppt_path']}")

#     # -------- Construct Response: Return different fields based on graph_type -------- #
#     ppt_filename = str(final_state["ppt_path"])

#     # Default empty string to avoid frontend issues with None
#     svg_filename = ""
#     svg_image_filename = ""

#     try:
#         # final_state could be State or dict, consider both
#         if isinstance(final_state, dict):
#             svg_filename = str(final_state.get("svg_file_path", "") or "")
#             svg_image_filename = str(final_state.get("svg_img_path", "") or "")
#         else:
#             svg_filename = str(getattr(final_state, "svg_file_path", "") or "")
#             svg_image_filename = str(getattr(final_state, "svg_img_path", "") or "")
#     except Exception as e:  # pragma: no cover - Logging fallback only
#         log.warning(f"[paper2figure] Failed to extract SVG path: {e}")
#         svg_filename = ""
#         svg_image_filename = ""

#     # Collect absolute paths for all PPTX / PNG / SVG files in this task's output directory
#     all_output_files: list[str] = []
#     try:
#         result_root_path = Path(state.result_path)
#         if result_root_path.exists():
#             for p in result_root_path.rglob("*"):
#                 if p.is_file() and p.suffix.lower() in {".pptx", ".png", ".svg"}:
#                     all_output_files.append(str(p))
#     except Exception as e:  # pragma: no cover
#         log.warning(f"[paper2figure] Failed to collect output file list: {e}")

#     return Paper2FigureResponse(
#         success=True,
#         ppt_filename=ppt_filename,
#         svg_filename=svg_filename,
#         svg_image_filename=svg_image_filename,
#         all_output_files=all_output_files,
#     )
