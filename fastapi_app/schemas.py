from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal
from workflow_engine.utils import get_project_root
from pydantic import BaseModel, Field
from fastapi_app.config import settings

# ===================== General Base Models =====================


class APIError(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Unified error response model"""
    error: str
    code: str = "INTERNAL_ERROR"  # Error code, e.g., VALIDATION_ERROR, WORKFLOW_ERROR, etc.
    details: Optional[Dict] = None


# ===================== paper2video Related =====================


class FeaturePaper2VideoRequest(BaseModel):
    model: str = settings.PAPER2VIDEO_DEFAULT_MODEL
    chat_api_url: str = settings.DEFAULT_LLM_API_URL
    api_key: str = ""
    pdf_path: str = ""
    img_path: str = ""
    language: str = ""


class FeaturePaper2VideoResponse(BaseModel):
    success: bool
    ppt_path: str


# ===================== LLM Verification =====================


class VerifyLlmRequest(BaseModel):
    api_url: str
    api_key: str
    model: str = settings.MODEL_GPT_4O


class VerifyLlmResponse(BaseModel):
    success: bool
    error: Optional[str] = None


# ===================== paper2figure Related =====================


class Paper2FigureRequest(BaseModel):
    """
    Request parameter definition for Paper2Figure.

    Note:
    - To maintain compatibility with internal dataflow_agent access to state.request,
      an extra language field is provided here, with a simple get method
      allowing both attribute access (.language) and dict-style access (.get).
    """

    # ---------------------- Base LLM Settings ----------------------
    language: str = settings.DEFAULT_LANGUAGE
    # Internal workflow roles access state.request.language

    chat_api_url: str = settings.DEFAULT_LLM_API_URL
    # API URL for LLM interaction

    # ---------------------- Graph Type & Difficulty Settings ----------------------
    figure_complex: str = "easy"
    # Drawing complexity: only effective when graph_type == "model_arch", passed from frontend as easy/mid/hard

    chat_api_key: str = "fill the key"
    # API KEY for chat_api_url; used to access backend LLM services

    api_key: str = ""
    # External API Key if using third-party services (e.g., OpenAI); uses internal service if empty

    model: str = settings.PAPER2FIGURE_TEXT_MODEL
    # Text model name for understanding, abstraction, and description generation

    gen_fig_model: str = settings.PAPER2FIGURE_IMAGE_MODEL
    # Image model name for illustration / composition sketch generation

    bg_rm_model: str = f"{get_project_root()}/models/RMBG-2.0"

    # New model parameters
    vlm_model: str = settings.PAPER2FIGURE_VLM_MODEL
    tec_vlm_desc_model: str = settings.PAPER2FIGURE_REF_IMG_DESC_MODEL
    chart_model: str = settings.PAPER2FIGURE_CHART_MODEL
    fig_desc_model: str = settings.PAPER2FIGURE_DESC_MODEL
    technical_model: str = settings.PAPER2FIGURE_TECHNICAL_MODEL
    tech_route_template: str = ""
    tech_route_palette: str = ""

    # ---------------------- Input Type Settings ----------------------
    input_type: Literal["PDF", "TEXT", "FIGURE"] = "PDF"
    # Specifies the form of input content:
    # - "PDF": Input is a PDF file path
    # - "TEXT": Input is plain text content
    # - "FIGURE": Input is an image file path (e.g., JPG/PNG), for parsing or conversion

    input_content: str = ""
    # Input content body (string), meaning determined by input_type:
    # - input_type = "PDF": input_content is the PDF **file path**
    # - input_type = "FIGURE": input_content is the image **file path**
    # - input_type = "TEXT": input_content is the **plain text content itself**
    # Note: This parameter is always a string and does not change types.

    # ---------------------- Output Aspect Ratio Settings ----------------------
    aspect_ratio: Literal["1:1", "16:9", "9:16", "4:3", "3:4", "21:9"] = "16:9"
    # Graph type: Model architecture / Technical roadmap / Experimental data
    graph_type: Literal["model_arch", "tech_route", "exp_data"] = "model_arch"
    # Style: Cartoon / Realistic (exact values passed from frontend)
    style: str = "cartoon"
    # Specifies the aspect ratio of the generated image, e.g.:
    # 1:1 (square), 16:9 (widescreen), 9:16 (vertical), 4:3, 3:4, and 21:9 ultra-wide.

    email: str = ""

    # ---------------------- Regeneration/Editing Related ----------------------
    edit_prompt: str = ""
    # Prompt provided by user for regeneration

    prev_image: str = ""
    # Path to the previously generated image (used for image-to-image or edit mode)

    # ---------------------- Technical Roadmap Reference Image Related ----------------------
    reference_image_path: str = ""
    # Reference image path (used for VLM to generate tech roadmap in a similar style)

    tech_route_edit_prompt: str = ""
    # Second edit prompt for technical roadmap

    # ---------------------- Compatible with dict-style access ----------------------
    def get(self, key: str, default=None):
        """
        Compatibility for internal dataflow_agent usage using dict.get("key") on requests.
        Returns default if attribute not found.
        """
        return getattr(self, key, default)


class Paper2FigureResponse(BaseModel):
    success: bool
    ppt_filename: str = ""  # Generated PPT path
    drawio_filename: str = ""  # DrawIO source file path (valid for model_arch image2drawio)
    svg_filename: str = ""  # Tech roadmap SVG source file path (valid for graph_type=tech_route)
    svg_image_filename: str = ""  # Tech roadmap PNG render path (valid for graph_type=tech_route)
    svg_bw_filename: str = ""  # Tech roadmap B&W SVG source file path (valid when selecting color schemes)
    svg_bw_image_filename: str = ""  # Tech roadmap B&W PNG render path (valid when selecting color schemes)
    svg_color_filename: str = ""  # Tech roadmap color SVG source file path (valid when selecting color schemes)
    svg_color_image_filename: str = ""  # Tech roadmap color PNG render path (valid when selecting color schemes)
    all_output_files: List[str] = []  # All output file paths generated by this task (later converted to URL in router layer)


# ===================== paper2ppt Related =====================

class PageContentRequest(BaseModel):
    """Request model specifically for pagecontent generation"""
    chat_api_url: str
    api_key: str
    email: Optional[str] = None
    input_type: Literal["text", "pdf", "pptx", "topic"]
    file: Optional[Any] = None  # UploadFile handled at router layer, Any is used as a placeholder here
    text: Optional[str] = None
    model: str = settings.PAPER2PPT_OUTLINE_MODEL
    language: str = settings.DEFAULT_LANGUAGE
    style: str = ""
    reference_img: Optional[Any] = None
    gen_fig_model: str = Field(...)
    page_count: int = 5
    use_long_paper: str = "false"
    pdf_as_slides: str = "false"
    render_dpi: Optional[int] = None


class OutlineRefineRequest(BaseModel):
    """Refine outline based on user feedback without re-parsing input."""
    chat_api_url: str
    api_key: str
    email: Optional[str] = None
    model: str = settings.PAPER2PPT_OUTLINE_MODEL
    language: str = settings.DEFAULT_LANGUAGE
    result_path: Optional[str] = None
    outline_feedback: str
    pagecontent: str


class PPTGenerationRequest(BaseModel):
    """Request model specifically for PPT generation/editing"""
    img_gen_model_name: str
    chat_api_url: str
    api_key: str
    email: Optional[str] = None
    style: str = ""
    reference_img: Optional[Any] = None
    aspect_ratio: str = "16:9"
    language: str = settings.DEFAULT_LANGUAGE
    model: str = settings.PAPER2PPT_CONTENT_MODEL
    get_down: str = "false"
    all_edited_down: str = "false"
    result_path: str
    pagecontent: Optional[str] = None
    page_id: Optional[int] = None
    edit_prompt: Optional[str] = None
    image_resolution: Optional[str] = None


class FullPipelineRequest(BaseModel):
    """Request model specifically for full pipeline"""
    img_gen_model_name: str
    chat_api_url: str
    api_key: str
    email: Optional[str] = None
    input_type: Literal["text", "pdf", "pptx"]
    file: Optional[Any] = None
    text: Optional[str] = None
    language: str = settings.DEFAULT_LANGUAGE
    aspect_ratio: str = "16:9"
    style: str = ""
    model: str = settings.PAPER2PPT_DEFAULT_MODEL
    use_long_paper: str = "false"


class Paper2PPTRequest(BaseModel):
    """
    Request parameter definition for Paper2PPT.

    Currently reuses Paper2FigureRequest field semantics, only name differs
    to decouple from specific workflows at FastAPI layer.
    """

    # ---------------------- Base LLM Settings ----------------------
    language: str = settings.DEFAULT_LANGUAGE
    chat_api_url: str = settings.DEFAULT_LLM_API_URL

    # ---------------------- Graph Type & Difficulty Settings ----------------------
    chat_api_key: str = "fill the key"
    api_key: str = ""
    # Model used for chat
    model: str = settings.PAPER2PPT_DEFAULT_MODEL

    ref_img : str = ""

    gen_fig_model: str = settings.PAPER2PPT_IMAGE_GEN_MODEL
    # bg_rm_model: str = f"{get_project_root()}/models/RMBG-2.0"

    # New model parameters
    vlm_model: str = settings.PAPER2PPT_VLM_MODEL
    chart_model: str = settings.PAPER2PPT_CHART_MODEL
    fig_desc_model: str = settings.PAPER2PPT_DESC_MODEL
    technical_model: str = settings.PAPER2PPT_TECHNICAL_MODEL

    # ---------------------- Input Type Settings ----------------------
    input_type: Literal["PDF", "TEXT", "PPT", "TOPIC", "FIGURE"] = "PDF"
    input_content: str = ""
    render_dpi: Optional[int] = None

    # ---------------------- Output Aspect Ratio Settings ----------------------
    aspect_ratio: Literal["1:1", "16:9", "9:16", "4:3", "3:4", "21:9"] = "16:9"
    style: str = " "
    use_long_paper: bool = False  # Do not use long paper    image_resolution: str = "2K"

    email: str = ""
    # Number of generated PPT pages;
    page_count: int = 5

    all_edited_down: bool = False
    use_ai_edit: bool = False

    def get(self, key: str, default=None):
        """
        Compatibility for internal dataflow_agent usage using dict.get("key") on requests.
        Returns default if attribute not found.
        """
        return getattr(self, key, default)


class Paper2PPTResponse(BaseModel):
    """
    Response model for Paper2PPT.

    workflow_adapters.paper2ppt returns these fields (or a subset):
    - pagecontent: Structured result of paper2page_content
    - result_path: Task output directory (internal backend path; usually converted to URL at router layer)
    - ppt_pdf_path / ppt_pptx_path: Final file paths exported by paper2ppt
    - all_output_files: Scanned relevant files in the task output directory (returned after converting to URL at router layer)
    """
    success: bool = True

    ppt_pdf_path: str = ""
    ppt_pptx_path: str = ""
    pagecontent: List[Dict[str, Any]] = []
    result_path: str = ""
    all_output_files: List[str] = []


# ===================== Flashcard Related =====================

class Flashcard(BaseModel):
    """Single Flashcard"""
    id: str
    question: str
    answer: str
    type: str = "qa"
    difficulty: Optional[str] = None
    source_file: Optional[str] = None
    source_excerpt: Optional[str] = None
    tags: List[str] = []
    created_at: Optional[str] = None


class GenerateFlashcardsRequest(BaseModel):
    """Generate flashcards request"""
    file_paths: List[str]
    email: str
    user_id: str
    notebook_id: Optional[str] = None
    api_url: str
    api_key: str
    model: str = "deepseek-v3.2"
    language: str = settings.DEFAULT_LANGUAGE
    card_count: int = 20


class GenerateFlashcardsResponse(BaseModel):
    """Generate flashcards response"""
    success: bool
    flashcards: List[Flashcard] = []
    total_count: int = 0
    result_path: str = ""


# ===================== Quiz Related Models =====================

class QuizOption(BaseModel):
    """Quiz Option"""
    label: str
    text: str


class QuizQuestion(BaseModel):
    """Quiz Question"""
    id: str
    question: str
    options: List[QuizOption]
    correct_answer: str
    explanation: str
    source_excerpt: Optional[str] = None
    difficulty: Optional[str] = None
    category: Optional[str] = None


class GenerateQuizRequest(BaseModel):
    """Generate Quiz request"""
    file_paths: List[str]
    email: str
    user_id: str
    notebook_id: Optional[str] = None
    api_url: str
    api_key: str
    model: str = "deepseek-v3.2"
    language: str = settings.DEFAULT_LANGUAGE
    question_count: int = 10


class GenerateQuizResponse(BaseModel):
    """Generate Quiz response"""
    success: bool
    questions: List[QuizQuestion] = []
    quiz_id: str = ""
    total_count: int = 0
    result_path: str = ""
