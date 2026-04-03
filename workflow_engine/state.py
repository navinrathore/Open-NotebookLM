from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
current_file = Path(__file__).resolve()
PROJDIR = current_file.parent.parent
from typing_extensions import TypedDict, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


# ==================== Base Request ====================
@dataclass
class MainRequest:
    """Base class for all requests, containing only core fields"""
    # 1. User's preferred natural language
    language: str = "en"  # "en" | "zh" | ...

    # 2. LLM Interface (Locked to Free HuggingFace Inference)
    chat_api_url: str = os.getenv("DEFAULT_LLM_API_URL", "https://api-inference.huggingface.co/v1")
    api_key: str = os.getenv("HF_TOKEN", "test")
    chat_api_key: str = os.getenv("HF_TOKEN", "test") # No difference, but kept for legacy compatibility

    # 3. Selected LLM Name (Free Tier Default)
    model: str = "meta-llama/Meta-Llama-3-8B-Instruct"

    # 4. Requirement Description
    target: str = ""

    def get(self, key, default=None):
        return getattr(self, key, default)
    
    def __setitem__(self, key, value):
        setattr(self, key, value)


# ==================== Base State (Ancestor of all States) ====================
@dataclass
class MainState:
    """Base class for all states, containing only core fields"""
    request: MainRequest = field(default_factory=MainRequest)
    messages: Annotated[list[BaseMessage], add_messages] = field(default_factory=list)
    # Common fields
    agent_results: Dict[str, Any] = field(default_factory=dict)
    temp_data: Dict[str, Any] = field(default_factory=dict)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __setitem__(self, key, value):
        setattr(self, key, value)


# ==================== Main Process Request ====================
@dataclass
class DFRequest(MainRequest):
    """Request for the main process, inherits from MainRequest"""
    # 5. Test sample file (CLI batch runs only)
    json_file: str = ""

    # 6. Python code file location
    python_file_path: str = ""

    # 7. Debug related
    need_debug: bool = False
    max_debug_rounds: int = 3

    # 8. Local model related
    use_local_model: bool = False
    local_model_path: str = ""

    # 9. Cache and Session
    cache_dir: str = f"{PROJDIR}/cache_dir"
    session_id: str = "default_session"

    # embeddings url
    chat_api_url_for_embeddings : str = ""
    embedding_model_name: str = "text-embedding-3-small"
    update_rag_content: bool = True

# ==================== Main Process State ====================
@dataclass
class DFState(MainState):
    """State for the main process, inherits from MainState"""
    # Override request type with DFRequest
    request: DFRequest = field(default_factory=DFRequest)

    
    # Main process specific fields
    category: Dict[str, Any] = field(default_factory=dict)
    recommendation: Dict[str, Any] = field(default_factory=dict)
    matched_ops: list[str] = field(default_factory=list)
    debug_mode: bool = False
    pipeline_structure_code: Dict[str, Any] = field(default_factory=dict)
    execution_result: Dict[str, Any] = field(default_factory=dict)
    code_debug_result: Dict[str, Any] = field(default_factory=dict)
    debug_history: Dict[Any, Dict[str, Any]] = field(default_factory=dict)
    opname_and_params: List[Dict[str, Dict[str, Any]]] = field(default_factory=list)

# ==================== Paper2Video Generation Request ====================

@dataclass
class Paper2VideoRequest(MainRequest):
    paper_pdf_path: str = ""
    user_imgs_path: str = ""
    
    ref_audio_path: str = ""

# ==================== Paper2Video Generation State ======================
@dataclass
class Paper2VideoState(MainState):
    # Override request
    request: Paper2VideoRequest = field(default_factory=Paper2VideoRequest)
    
    # paper2video specific fields
    beamer_code_path: str = ""
    is_beamer_wrong: bool = False
    is_beamer_warning: bool = False
    code_debug_result: str = ""
    ppt_path: str = ""
    
    # Generated subtitles + cursor position info
    slide_img_dir: str = ""
    subtitle_and_cursor: List[str] = field(default_factory=list)
    subtitle_and_cursor_path: str = ""
    
    # Generated audio path
    speech_save_dir: str = ""



# ==================== Planning Agent Related State ====================
@dataclass
class PlanningRequest(MainRequest):
    """Request for Planning Agent"""
    # Planner configuration
    planner_model: Optional[str] = None
    planner_temperature: float = 0.0
    
    # Executor configuration
    executor_model: Optional[str] = None
    executor_as_react: bool = True
    
    # Replanner configuration (Plan-and-Execute mode only)
    replanner_model: Optional[str] = None
    max_replanning_rounds: int = 3
    
    # Human-in-the-Loop configuration
    require_plan_approval: bool = True      # Whether plan approval is required
    interrupt_before_step: bool = True      # Whether to interrupt before each step
    interrupt_after_step: bool = False      # Whether to interrupt after each step
    
    # Execution configuration
    max_plan_steps: int = 10
    planning_mode: str = "plan_solve"       # "plan_solve" | "plan_execute"


@dataclass
class PlanStep:
    """Single plan step"""
    index: int                              # Step index
    description: str                        # Step description
    status: str = "pending"                 # pending | running | completed | failed | skipped
    result: Optional[str] = None            # 执行结果
    error: Optional[str] = None             # 错误信息
    started_at: Optional[str] = None        # Start time
    completed_at: Optional[str] = None      # Completion time


@dataclass
class PlanningState(MainState):
    """
    State class for Planning Agent
    
    Supports two modes:
    - Plan-and-Solve: Generate plan once, execute in sequence
    - Plan-and-Execute (Replanning): Adjust plan dynamically
    """
    request: PlanningRequest = field(default_factory=PlanningRequest)
    
    # ===== Planning related =====
    plan: List[str] = field(default_factory=list)                    # List of plan steps (simple strings)
    plan_steps: List[Dict[str, Any]] = field(default_factory=list)   # Detailed plan steps
    current_step_index: int = 0                                       # Current step index
    past_steps: List[tuple] = field(default_factory=list)            # [(step_description, execution_result), ...]
    
    # ===== State control =====
    plan_approved: bool = False                     # Whether plan is approved
    is_replanning_needed: bool = False              # Whether replanning is needed
    replanning_count: int = 0                       # Replanning count
    final_response: str = ""                        # Final response
    is_finished: bool = False                       # Whether finished
    
    # ===== Human-in-the-Loop related =====
    awaiting_human_input: bool = False              # Whether awaiting human input
    human_feedback: Optional[str] = None            # Human feedback
    interrupt_reason: Optional[str] = None          # Interruption reason
    
    # ===== Execution context =====
    original_task: str = ""                         # Original task description
    executor_tools: List[str] = field(default_factory=list)  # Available tools list
    
    def get_current_step(self) -> Optional[str]:
        """Get the current step to be executed"""
        if 0 <= self.current_step_index < len(self.plan):
            return self.plan[self.current_step_index]
        return None
    
    def get_remaining_steps(self) -> List[str]:
        """Get the remaining unexecuted steps"""
        return self.plan[self.current_step_index:]
    
    def get_completed_steps(self) -> List[tuple]:
        """Get the completed steps and their results"""
        return self.past_steps
    
    def mark_step_complete(self, result: str):
        """Mark current step as complete"""
        if self.current_step_index < len(self.plan):
            step = self.plan[self.current_step_index]
            self.past_steps.append((step, result))
            self.current_step_index += 1
    
    def reset_plan(self):
        """Reset plan state (used for replanning)"""
        self.plan = []
        self.plan_steps = []
        self.current_step_index = 0
        self.is_replanning_needed = False
        # Retain past_steps because replanning needs history reference
    
    def to_planning_context(self) -> Dict[str, Any]:
        """Generate planning context (for LLM use)"""
        return {
            "original_task": self.original_task or self.request.target,
            "past_steps": [
                {"step": step, "result": result} 
                for step, result in self.past_steps
            ],
            "remaining_steps": self.get_remaining_steps(),
            "replanning_count": self.replanning_count,
            "available_tools": self.executor_tools,
        }

@dataclass
class Paper2FigureRequest(MainRequest):
    gen_fig_model: str = "gemini-2.5-flash-image-preview"
    # gen_fig_model: str = "gemini-3-pro-image-preview"
    sam2_model: str = "models/facebook/sam2.1-hiera-tiny"
    bg_rm_model: str = "models/RMBG-2.0"

    # New: VLM model for wf_pdf2ppt_qwenvl.py
    vlm_model: str = "qwen-vl-ocr-2025-11-20"
    
    # New: Chart related models for wf_paper2expfigure.py
    chart_model: str = "deepseek-v3.2"
    
    # New: Description generation model for wf_paper2figure_image_only.py
    fig_desc_model: str = "deepseek-v3.2"
    
    # New: Technology route generation model for wf_paper2technical.py
    technical_model: str = "deepseek-v3.2"
    # Technical route template/palette (optional)
    tech_route_template: str = ""
    tech_route_palette: str = ""

    input_type: str = "PDF"
    # Scientific drawing complexity    
    figure_complex: str = "hard"
    style: str = "kartoon"

    # Number of PPT pages 
    page_count: int = 10
    # Whether editing is complete, i.e., whether to re-generate the full PPT
    all_edited_down: bool = False

    # Whether pdf2ppt uses AI editing
    use_ai_edit: bool = False

    # Reference image path for paper2ppt:
    ref_img: str = ''

@dataclass
class Paper2FigureState(MainState):
    request: Paper2FigureRequest = field(default_factory=Paper2FigureRequest)
    fig_desc: str = ''
    aspect_ratio: str = '16:9'
    paper_file: str = ''
    # Original image path with content
    fig_draft_path: str = ''
    # Content elements extracted by MinerU (text / images / tables, etc.)
    fig_mask: List[Dict[str, Any]] = field(default_factory=list)
    # Secondary edited empty box template image (outer rectangles and arrows only)
    fig_layout_path: str = ''
    # Layout elements formed by SAM + SVG + EMF (background frame layer only)
    layout_items: List[Dict[str, Any]] = field(default_factory=list)
    result_path: str = ''
    ppt_path: str = ''
    mask_detail_level: int = 2
    paper_idea: str = ''
    input_type: str = 'PDF'

    # Technology route map attributes ==============================
    figure_tec_svg_content: str = ""
    figure_tec_svg_bw_content: str = ""
    figure_tec_svg_color_content: str = ""
    svg_img_path: str = ""
    mineru_port: int = 8010
    svg_file_path: str = ""  # Address for SVG text-inclusive image
    svg_bg_file_path: str = ""
    svg_bw_file_path: str = ""
    svg_bw_img_path: str = ""
    svg_color_file_path: str = ""
    svg_color_img_path: str = ""
    # SVG image with text version
    svg_full_img_path: str = ""
    # Background SVG code:
    svg_bg_code : str = ""
    
    # Experimental statistical chart attributes ==============================
    # ===== Input =====
    pre_tool_results: Dict[str, Any] = field(default_factory=dict)  # Pre-tool results injection

    # ===== Intermediate Results =====
    paper_idea: str = ''                                          # Paper core idea
    extracted_tables: List[Dict[str, Any]] = field(default_factory=list)  # Table list extracted from MinerU
    # Each table format: {"table_id": str, "headers": List[str], "rows": List[List[str]], "caption": str}

    chart_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)     # Chart configuration dictionary
    # Each config format: {table_id: {"table_id": str, "chart_type": str, "x_column": str, "y_columns": List[str], ...}}

    generated_codes: Dict[str, Dict[str, Any]] = field(default_factory=dict)   # Generated code dictionary
    # Each code format: {table_id: {"table_id": str, "code": str}}

    # ===== Output =====
    generated_charts: Dict[str, str] = field(default_factory=dict)             # Generated charts path dictionary
    stylize_results: Dict[str, list] = field(default_factory=dict)             # Stylized charts path dictionary

    svg_bg_code: str = ""

    # paper2ppt specific ==============================
    # Whether the first generation of the set of page images is complete; False for batch generation, True for page-by-page secondary editing
    gen_down: bool = False
    # 0-based: Page number for secondary editing
    edit_page_num: int = -1
    # Secondary editing prompt (for the page corresponding to edit_page_num)
    edit_page_prompt: str = ""
    # Paths of generated page images (0-based aligned with pagecontent)
    generated_pages: List[str] = field(default_factory=list)
    table_img_path: str = ""

    # pagecontent: Can be structured slide description or image list like [{"ppt_img_path": "..."}]
    pagecontent: list[dict] = field(default_factory=list)
    # KB workflow specific fields
    image_items: List[Dict[str, Any]] = field(default_factory=list)
    filtered_image_items: List[Dict[str, Any]] = field(default_factory=list)
    kb_query: str = ""
    kb_retrieval_text: str = ""
    kb_user_images: List[Dict[str, Any]] = field(default_factory=list)
    kb_md_images: List[str] = field(default_factory=list)
    kb_multi_source_text: str = ""  # Concatenated sources as "Source 1:\n...\n\nSource 2:\n...", outline prefers this
    minueru_output: str = ""
    mineru_root: str = ""
    text_content: str = ""
    outline_feedback: str = ""
    # Generated PPT PDF path
    ppt_pdf_path: str = ""

    # image2drawio specific ==============================
    ocr_items: List[Dict[str, Any]] = field(default_factory=list)
    no_text_path: str = ""
    clean_bg_path: str = ""
    drawio_elements: List[Dict[str, Any]] = field(default_factory=list)
    drawio_xml: str = ""
    drawio_output_path: str = ""
    ppt_pptx_path: str = ""

    # Long text PPT specific:
    long_text: str = ""
    target_pages: int = 60
    pages_per_batch: int = 10
    pages_to_generate: int = 12
    max_rounds: int = 1
    current_chunk: str = ""
    current_text: str = ""

    # pdf2ppt specific ==============================
    pdf_file: str = ""
    slide_images: List[str] = field(default_factory=list)
    ocr_pages: List[str] = field(default_factory=list)
    sam_pages: List[str] = field(default_factory=list)
    mineru_pages: List[Dict[str, Any]] = field(default_factory=list)
    # Whether pdf2ppt uses AI editing
    use_ai_edit: bool = False
    use_global_font_clustering: bool = False # Whether to use single-page clustering


    # img2ppt specific ==============================
    bbox_result: List[str] = field(default_factory=list)
    vlm_pages: List[Dict[str, Any]] = field(default_factory=list)

# ==================== Intelligent QA Related State ====================

@dataclass
class IntelligentQARequest(MainRequest):
    """
    Intelligent QA Request
    """
    file_ids: List[str] = field(default_factory=list)  # List of file IDs after ingestion layer processing
    query: str = ""  # User query
    history: List[Dict[str, str]] = field(default_factory=list)  # History records [{"role": "user", "content": "..."}]
    vector_store_base_dir: Optional[str] = None  # Optional, for RAG: Vector store root directory (consistent with kb_embedding convention)

@dataclass
class IntelligentQAState(MainState):
    """
    Intelligent QA State
    """
    request: IntelligentQARequest = field(default_factory=IntelligentQARequest)

    # Context content after parsing
    context_content: str = ""

    # New: Store analysis results for each file
    file_analyses: List[Dict[str, Any]] = field(default_factory=list)

    # RAG retrieved chunks (when using vector_store)
    retrieved_chunks: List[Dict[str, Any]] = field(default_factory=list)

    # Source mapping {1: "filename.md", 2: "doc.pdf", ...}
    source_mapping: Dict[int, str] = field(default_factory=dict)

    # Reference preview mapping {1: "chunk preview ...", 2: "chunk preview ..."}
    source_preview_mapping: Dict[int, str] = field(default_factory=dict)

    # Reference details mapping {1: {"fileName": "...", "filePath": "...", "preview": "...", "chunkIndex": 0}}
    source_reference_mapping: Dict[int, Dict[str, Any]] = field(default_factory=dict)

    # Final answer
    answer: str = ""

@dataclass
class KBPodcastRequest(MainRequest):
    """
    Knowledge Podcast Request
    """
    file_ids: List[str] = field(default_factory=list)  # List of file IDs after ingestion layer processing
    podcast_mode: str = "monologue"  # monologue | dialog
    tts_model: str = "gemini-2.5-pro-preview-tts"
    voice_name: str = "Kore"
    voice_name_b: str = "Puck"
    language: str = "zh"
    vector_store_base_dir: Optional[str] = None  # Vector store root directory (where manifest is located)

@dataclass
class KBPodcastState(MainState):
    """
    Knowledge Podcast State
    """
    request: KBPodcastRequest = field(default_factory=KBPodcastRequest)
    result_path: str = ""
    file_contents: List[Dict[str, Any]] = field(default_factory=list)
    podcast_script: str = ""
    audio_path: str = ""


# ==================== KBMindMap 相关 State ====================

@dataclass
class KBMindMapRequest(MainRequest):
    """
    Knowledge Base Mind Map Request
    """
    file_ids: List[str] = field(default_factory=list)  # List of file IDs after ingestion layer processing
    mindmap_style: str = "default"  # default | flowchart | tree
    max_depth: int = 3  # Maximum depth of mind map
    vector_store_base_dir: Optional[str] = None  # Vector store root directory (where manifest is located)

@dataclass
class KBMindMapState(MainState):
    """
    Knowledge Base Mind Map State
    """
    request: KBMindMapRequest = field(default_factory=KBMindMapRequest)
    result_path: str = ""
    file_contents: List[Dict[str, Any]] = field(default_factory=list)
    content_structure: str = ""  # Content structure extracted by LLM
    mermaid_code: str = ""  # Generated Mermaid code
    mindmap_svg_path: str = ""  # SVG output path (optional)


# ==================== Paper2Drawio Related State ====================

@dataclass
class Paper2DrawioRequest(MainRequest):
    """Paper2Drawio Request Parameters"""
    # Input type: "PDF" | "TEXT"
    input_type: str = "TEXT"

    # Diagram type: "flowchart" | "architecture" | "sequence" | "mindmap" | "er" | "auto"
    diagram_type: str = "auto"

    # Diagram style: "minimal" | "sketch" | "default"
    diagram_style: str = "default"

    # Whether to enable VLM validation
    enable_vlm_validation: bool = False

    # VLM model (optional, defaults to model)
    vlm_model: str = ""

    # VLM validation max retries
    vlm_validation_max_retries: int = 3

    # Max retries
    max_retries: int = 3

    # Current XML (for edit mode)
    current_xml: str = ""

    # Edit instruction (for edit mode)
    edit_instruction: str = ""

    # Chat history (for multi-turn conversation)
    chat_history: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class Paper2DrawioState(MainState):
    """Paper2Drawio Workflow State"""
    request: Paper2DrawioRequest = field(default_factory=Paper2DrawioRequest)

    # Input content
    paper_file: str = ""           # PDF file path
    text_content: str = ""         # Text content

    # Intermediate results
    paper_summary: str = ""        # Paper summary/core content
    diagram_plan: str = ""         # Diagram plan description

    # Diagram XML
    drawio_xml: str = ""           # Current draw.io XML
    drawio_xml_history: List[str] = field(default_factory=list)  # XML history
    validation_feedback: str = ""  # VLM validation feedback
    validation_png_path: str = ""  # PNG for VLM validation

    # Output path
    result_path: str = ""          # Result directory
    output_xml_path: str = ""      # XML file path
    output_png_path: str = ""      # PNG export path
    output_svg_path: str = ""      # SVG export path
