import ast
from json import JSONDecodeError, JSONDecoder
import json
import re
from typing import Any, Dict, Union, List
from pathlib import Path
from workflow_engine.logger import get_logger
log = get_logger(__name__)

import ast
from json import JSONDecodeError, JSONDecoder
import json
import re
from typing import Any, Dict, Union, List
from pathlib import Path
import asyncio
import logging
from typing import List, Dict, Any, Optional


from math import ceil
import time
import os
import math
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

import fitz  # PyMuPDF

from PIL import Image
import pdfplumber
import uuid

from workflow_engine.toolkits.multimodaltool.mineru_tool import run_aio_batch_two_step_extract, run_aio_two_step_extract

def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent

def robust_parse_json(
    text: str,
    *,
    merge_dicts: bool = False,
    strip_double_braces: bool = False
) -> Union[Dict[str, Any], List[Any]]:
    """
    Tries to extract valid JSON from LLM / logs / jsonl / Markdown fragments.

    Parameters
    ----------
    text : str
        Original input text
    merge_dicts : bool, default False
        Whether to merge with dict.update if multiple objects are extracted and all are dicts
    strip_double_braces : bool, default False
        Replace '{{' / '}}' with '{' / '}' (some template languages add double curly braces)

    Returns
    -------
    Dict / List / List[Dict | List]
    """
    s = text.strip()

    # ---------- Preprocessing: Strip outer wrappers ----------
    s = _remove_markdown_fence(s)          # ```json ... ```
    s = _remove_outer_triple_quotes(s)     # ''' ... ''' / """ ... """
    s = _remove_leading_json_word(s)       # Leading json/JSON marker

    if strip_double_braces:
        s = s.replace("{{", "{").replace("}}", "}")

    # ---------- Clean comments & trailing commas ----------
    s = _strip_json_comments(s)

    # ---------- NEW: Clean illegal control characters ----------
    # Remove all ASCII control characters not allowed by JSON spec.
    # Essential \n, \r, \t, and \f, \b, \" are not removed, but this target non-printable control codes.
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', s)

    # ---------- NEW: Escape unescaped backslashes (fixes LaTeX formulas, etc.) ----------
    # This converts all single backslashes to double backslashes while preserving correctly escaped sequences.
    # First protect already escaped sequences (e.g., \\n, \\t, \\", \\\\)
    s = s.replace('\\\\', '\x00DOUBLE_BACKSLASH\x00')  # 临时标记
    s = s.replace('\\n', '\x00NEWLINE\x00')
    s = s.replace('\\r', '\x00RETURN\x00')
    s = s.replace('\\t', '\x00TAB\x00')
    s = s.replace('\\"', '\x00QUOTE\x00')
    s = s.replace('\\/', '\x00SLASH\x00')
    s = s.replace('\\b', '\x00BACKSPACE\x00')
    s = s.replace('\\f', '\x00FORMFEED\x00')
    
    # Now escape all remaining single backslashes
    s = s.replace('\\', '\\\\')
    
    # Restore previously protected sequences
    s = s.replace('\x00DOUBLE_BACKSLASH\x00', '\\\\')
    s = s.replace('\x00NEWLINE\x00', '\\n')
    s = s.replace('\x00RETURN\x00', '\\r')
    s = s.replace('\x00TAB\x00', '\\t')
    s = s.replace('\x00QUOTE\x00', '\\"')
    s = s.replace('\x00SLASH\x00', '\\/')
    s = s.replace('\x00BACKSPACE\x00', '\\b')
    s = s.replace('\x00FORMFEED\x00', '\\f')

    log.debug(f'Content after cleaning is: {s}')

    # ---------- Step-1: Overall Parsing ----------
    # Step-1
    try:
        result = json.loads(s)
        log.info(f"Overall parsing successful, type: {type(result)}")
        return result
    except JSONDecodeError as e:
        log.warning(f"Overall parsing failed: {e}")

    # ---------- Step-2: Try JSON Lines ----------
    objs = _parse_json_lines(s)
    if objs is not None:
        return _maybe_merge(objs, merge_dicts)

    # ---------- Step-3: Stream extracted multiple objects ----------
    objs = _extract_json_objects(s)
    log.warning(f"Extracted {len(objs)} objects")
    if not objs:
        raise ValueError("Unable to locate any valid JSON fragment.")

    return _maybe_merge(objs, merge_dicts)


# ======================================================================
#                            Utility Functions
# ======================================================================

_fence_pat = re.compile(r'```[\w-]*\s*([\s\S]*?)```', re.I)
# Match only outer-wrapped code blocks (entire content wrapped in ```)
_outer_fence_pat = re.compile(r'^\s*```[\w-]*\s*([\s\S]*?)```\s*$', re.I)


def _remove_markdown_fence(src: str) -> str:
    """Extracts only the text inside an outer-wrapped ``` ... ``` block; returns as-is if not wrapped."""
    # Only process cases where the entire content is wrapped in a code block to avoid extracting nested code blocks within JSON
    match = _outer_fence_pat.match(src)
    if match:
        return match.group(1).strip()
    return src


def _remove_outer_triple_quotes(src: str) -> str:
    if (src.startswith("'''") and src.endswith("'''")) or (
        src.startswith('"""') and src.endswith('"""')
    ):
        return src[3:-3].strip()
    return src


def _remove_leading_json_word(src: str) -> str:
    return src[4:].lstrip() if src.lower().startswith("json") else src


def _strip_json_comments(src: str) -> str:
    # /* ... */  Block comment
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    # // ...     Line comment, excluding :// in URLs and // inside strings
    src = re.sub(r'(?<![:\"\'])//.*', '', src)
    # Trailing comma ,}
    src = re.sub(r',\s*([}\]])', r'\1', src)
    return src.strip()


# ----------------  JSON Lines ----------------
def _parse_json_lines(src: str) -> Union[List[Any], None]:
    lines = [ln.strip() for ln in src.splitlines() if ln.strip()]
    if len(lines) <= 1:          # JSONL requires more than 1 line
        return None

    objs: List[Any] = []
    for ln in lines:
        try:
            objs.append(json.loads(ln))
        except JSONDecodeError:
            return None  # If any line is not valid JSON, skip JSONL approach
    return objs


# ------------  Multi-object extraction (improved version) ------------
def _extract_json_objects(src: str) -> List[Any]:
    dec = JSONDecoder()
    idx, n = 0, len(src)
    objs: List[Any] = []

    while idx < n:
        m = re.search(r'[{\[]', src[idx:])
        if not m:
            break
        idx += m.start()
        try:
            obj, end = dec.raw_decode(src, idx)
            # ========== Strictness check ==========
            tail = src[end:].lstrip()
            # Allow end, comma, newline, right brace, right bracket
            if tail and tail[0] not in ',]}>\n\r':
                idx += 1  # Might be false identification, e.g., {"a":1 <-- missing }
                continue
            objs.append(obj)
            idx = end
        except JSONDecodeError:
            idx += 1
    return objs


def _maybe_merge(objs: List[Any], merge_dicts: bool) -> Union[Any, List[Any]]:
    if len(objs) == 1:
        return objs[0]
    if merge_dicts and all(isinstance(o, dict) for o in objs):
        merged: Dict[str, Any] = {}
        for o in objs:
            merged.update(o)
        return merged
    return objs


# ========================================================================

#                           For Paper2Figure

# ========================================================================

async def run_mineru(image_path: Path, output_dir: Path) -> bool:
    """Calls mineru and returns whether it succeeded"""
    cmd = [
        "mineru",
        "-p", str(image_path),
        "--backend", "vlm-transformers",
        "--source", "local",
        "-o", str(output_dir)
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        log.warning(f"[mineru] Run failed: {stderr.decode(errors='ignore')}")
        return False
    
    log.info("[mineru] Execution successful")
    return True

async def replace_item_with_sub_items(
    items: List[Dict[str, Any]], 
    sub_items: List[Dict[str, Any]], 
    sub_img_path: str
) -> List[Dict[str, Any]]:
    """
    Processes each sub_item, performing coordinate transformation and replacing the original item.
    """
    # Load image and get dimensions
    with Image.open(sub_img_path) as sub_img:
        sub_img_width, sub_img_height = sub_img.size

    expanded_items = []  # Stores expanded sub_items
    items_to_remove = []  # Tracks items to remove by index

    log.info(f"[replace_item_with_sub_items] Starting image replacement: {sub_img_path}")

    for i, item in enumerate(items):
        log.info(f"item[type]: {item['type']}")
        if item["type"] in ["image", "table"]:
            log.info(f"item['img_path']: {item['img_path']}")
            log.info(f"sub_img_path: {sub_img_path}") 
            if item["img_path"] == sub_img_path: # Match sub_img_path with original image's img_path
                # Get target image's bbox
                target_bbox = item["bbox"]
                xmin, ymin, xmax, ymax = target_bbox
                # Calculate ratio
                width_ratio = (xmax - xmin) / sub_img_width
                height_ratio = (ymax - ymin) / sub_img_height

                log.info(f"[replace_item_with_sub_items] Found matching item, replacing bbox: {target_bbox} -> expanded into {len(sub_items)} sub_items")

                # Replace image info in original item and expand sub_items
                for sub_item in sub_items:
                    # Get original sub_item bbox coordinates
                    sub_item_bbox = sub_item["bbox"]
                    sub_xmin, sub_ymin, sub_xmax, sub_ymax = sub_item_bbox

                    # Linear coordinate transformation
                    transformed_bbox = [
                        int(sub_xmin * width_ratio + xmin),  # x transformation
                        int(sub_ymin * height_ratio + ymin),  # y transformation
                        int(sub_xmax * width_ratio + xmin),  # x transformation
                        int(sub_ymax * height_ratio + ymin)  # y transformation
                    ]

                    # Update sub_item bbox
                    sub_item["bbox"] = transformed_bbox

                    # Add transformed sub_item to expanded_items list
                    expanded_items.append(sub_item)

                # Record original item index to remove
                items_to_remove.append(i)

                break

    # Replace original item, deleting original
    log.info(f"[replace_item_with_sub_items] Deleting original item, replacing with {len(expanded_items)} sub_items")

    for index in sorted(items_to_remove, reverse=True):  # Reverse delete to avoid index issues
        del items[index]

    # Extend sub_items into items
    items.extend(expanded_items)

    log.info(f"[replace_item_with_sub_items] Replacement complete, current items length: {len(items)}")

    return items

async def recursive_run_mineru(
    img_path: Path, 
    out_dir: Path, 
    max_depth: int = 2, 
    current_depth: int = 0
) -> List[Dict[str, Any]]:
    """Recursively runs mineru, processing subgraphs and updating fig_mask"""
    
    if current_depth > max_depth:
        return []  # Stop recursion at maximum depth
    
    log.info(f"[recursive_run_mineru] Current depth {current_depth}, processing image: {img_path}")
    
    # Call mineru to process current image
    ok = await run_mineru(img_path, out_dir)
    if not ok:
        return []  # If failed, return empty result

    # Find and read intermediate result JSON
    content_json = locate_content_json(out_dir / img_path.stem)
    if content_json is None:
        return []  # No content file found

    items = load_and_fix_items(content_json, out_dir)

    log.info(f"[recursive_run_mineru] Current items length: {len(items)}")

    # Find subgraph directory and recurse
    vlm_images_dir = out_dir / img_path.stem / 'vlm' / 'images'
    sub_images = list(vlm_images_dir.glob("*.jpg"))  # Assume subgraphs are .jpg

    if(current_depth != max_depth):
        for sub_img_path in sub_images:  # sub_img_path is image path
            log.info(f"[recursive_run_mineru] Processing subgraph: {sub_img_path}")

            # Get sub_items for current sub_img_path
            sub_items = await recursive_run_mineru(sub_img_path, out_dir, max_depth, current_depth + 1)

            # Handle replacement and coordinate mapping
            items = await replace_item_with_sub_items(items, sub_items, str(sub_img_path))

            log.info(f"[recursive_run_mineru] Replacement complete, current items length: {len(items)}")

    return items

def locate_content_json(output_dir: Path) -> Path | None:
    """Finds *_middle.json file"""
    files = list(output_dir.rglob("*_middle.json"))
    if not files:
        log.warning(f"[mineru] Not found *_middle.json in {output_dir}")
        return None
    return files[0]


def load_and_fix_items(content_json: Path, output_dir: Path) -> List[Dict[str, Any]]:
    """
    Reads JSON and extracts all text and image elements, fixing image paths to absolute paths
    """
    try:
        data = json.loads(content_json.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"[mineru] JSON read failed: {e}")
        return []

    # Extract base name
    stem = content_json.stem  # e.g. "paper1_middle"
    base_name = stem.replace("_middle", "") or stem
    
    results = []
    
    # Traverse para_blocks in pdf_info
    if "pdf_info" in data and isinstance(data["pdf_info"], list):
        for pdf_info in data["pdf_info"]:
            if "para_blocks" in pdf_info and isinstance(pdf_info["para_blocks"], list):
                for block in pdf_info["para_blocks"]:
                    block_type = block.get("type", "")
                    
                    # Handle title and normal text
                    if block_type in ["title", "text", "paragraph"]:
                        # Extract text content
                        text_content = extract_text_from_block(block)
                        if text_content:
                            results.append({
                                "type": "text",
                                "text": text_content,
                                "bbox": block.get("bbox", []),
                                "text_level": 1 if block_type == "title" else None,
                                "page_idx": 0
                            })
                    
                    # Handle image blocks
                    elif block_type in ["list", "image", "table"]:
                        # Extract image and related caption
                        image_elements = extract_image_elements(block, base_name, output_dir)
                        results.extend(image_elements)
    
    return results


def extract_text_from_block(block: Dict) -> str:
    """Extracts text content from block"""
    text_parts = []
    
    # If lines field exists, traverse and extract
    if "lines" in block and isinstance(block["lines"], list):
        for line in block["lines"]:
            if "spans" in line and isinstance(line["spans"], list):
                for span in line["spans"]:
                    if span.get("type") == "text" and "content" in span:
                        text_parts.append(span["content"])
    
    # If no lines field, try to get content directly
    elif "content" in block:
        text_parts.append(block["content"])
    
    return " ".join(text_parts) if text_parts else ""


def extract_image_elements(block: Dict, base_name: str, output_dir: Path) -> List[Dict]:
    """Extracts image and related text elements from image block"""
    elements = []
    
    if "blocks" in block and isinstance(block["blocks"], list):
        for sub_block in block["blocks"]:
            sub_type = sub_block.get("type", "")
            
            # Handle image caption
            if sub_type in ["title", "text", "paragraph","image_caption", "table_caption"]:
                caption_text = extract_text_from_block(sub_block)
                if caption_text:
                    elements.append({
                        "type": "text",
                        "text": caption_text,
                        "bbox": sub_block.get("bbox", []),
                        "text_level": None,  # Caption as normal text
                        "page_idx": 0
                    })
            
            # Handle image body
            elif sub_type in ["image_body", "table_body"]:
                image_path = extract_image_path(sub_block, base_name, output_dir)
                if image_path:
                    elements.append({
                        "type": "image",
                        "img_path": str(image_path),
                        "bbox": sub_block.get("bbox", []),
                        "image_caption": [],
                        "image_footnote": [],
                        "page_idx": 0
                    })
    
    return elements


def extract_image_path(block: Dict, base_name: str, output_dir: Path) -> Optional[Path]:
    """Extracts image path from block and converts to absolute path"""
    if "lines" in block and isinstance(block["lines"], list):
        for line in block["lines"]:
            if "spans" in line and isinstance(line["spans"], list):
                for span in line["spans"]:
                    if span.get("type") in ["image", "table"] and "image_path" in span:
                        rel_path = span["image_path"]
                        if rel_path:
                            # Build absolute path
                            abs_path = output_dir / base_name / "vlm/images" / rel_path
                            return abs_path
    return None

def build_output_directory(image_path: Path) -> Path:
    """Constructs <image_no_ext>_mineru output directory"""
    base = image_path.with_suffix("")
    out_dir = Path(f"{base}_mineru")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


# -------------------- NEW UTILS FUNCTIONS ---------------------------------

import asyncio
from pathlib import Path
from PIL import Image
from mineru_vl_utils import MinerUClient


# -----------------------------
# Tool: relative bbox → pixel bbox
# -----------------------------
def rel_bbox_to_pixel(bbox, width, height):
    x1, y1, x2, y2 = bbox
    return [
        int(x1 * width),
        int(y1 * height),
        int(x2 * width),
        int(y2 * height),
    ]


# -----------------------------
# Tool: Crop and save image
# -----------------------------
def crop_and_save(img: Image.Image, bbox_pixel, save_path: Path, margin=3):
    W, H = img.size
    x1, y1, x2, y2 = bbox_pixel

    log.info(f"[crop_and_save] Image size={img.size}, bbox={bbox_pixel}")

    # --- 1. Out of bounds check ---
    if x1 < 0 or y1 < 0 or x2 > W or y2 > H or x2 <= x1 or y2 <= y1:
        log.info("[crop_and_save] BBOX out of range → return original path")
        return None  # Or return str(original_image_path)

    # --- 2. Check if all four sides are "tight against edge" ---
    touch_left   = x1 <= margin
    touch_top    = y1 <= margin
    touch_right  = x2 >= W - margin
    touch_bottom = y2 >= H - margin

    if touch_left and touch_top and touch_right and touch_bottom:
        log.info("[crop_and_save] BBOX covers almost entire image → skip crop, return original")
        return None  # Or return str(original_image_path)

    # --- 3. Normal crop ---
    try:
        crop_img = img.crop(bbox_pixel)
        crop_img.save(save_path)
        log.info(f"[crop_and_save] Cropped size={crop_img.size}, saved={save_path}")
        return str(save_path)

    except Exception as e:
        log.info(f"[crop_and_save] ERROR during crop: {e}")
        return None

def transform_sub_bbox(sub_bbox, parent_bbox):
    """Maps bbox inside sub-image back to original image coordinates"""
    px1, py1, px2, py2 = parent_bbox
    sx1, sy1, sx2, sy2 = sub_bbox

    return [
        px1 + sx1,
        py1 + sy1,
        px1 + sx2,
        py1 + sy2
    ]

# -----------------------------
# Main function: HTTP Asynchronous Recursive MinerU
# -----------------------------
async def recursive_run_mineru_http(
    image_path: Path,
    out_dir: Path,
    port: int = None,
    max_depth: int = 2,
    current_depth: int = 0,
):
    """
    Executes asynchronous MinerU extraction using aio_two_step_extract.
    In-memory results, no intermediate JSON dependency.
    Automatically crops image/table/list etc. for next recursion layer.
    """
    # Read port from environment
    if port is None:
        import os
        port = int(os.getenv("LOCAL_MINERU_PORT", "26215"))

    # ---- Depth management ----
    if current_depth > max_depth:
        return []

    out_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"[recursive_http] ─ Depth={current_depth}, Image={image_path}")

    # ---- Load image ----
    img = Image.open(image_path)
    W, H = img.size
    log.info(f"[recursive_http] Image size: W={W}, H={H}")

    # ---- Call MinerU async interface ----
    try:
        blocks = await run_aio_two_step_extract(image_path, port)
        log.info(f"[recursive_http] MinerU returned {len(blocks)} blocks")
    except Exception as e:
        log.info(f"[recursive_http] MinerU error: {e}")
        return []

    results = []
    sub_images_paths = []  # Paths for next layer recursion

    # -----------------------------
    # Parse block and handle types
    # -----------------------------
    for idx, blk in enumerate(blocks):

        btype = blk.get("type")
        bbox_rel = blk.get("bbox", [0, 0, 1, 1])
        content = blk.get("content")

        log.info(f"  Block[{idx}] type={btype}, bbox_rel={bbox_rel}, "
                 f"content={str(content)[:30] if content else None}")

        bbox_pixel = rel_bbox_to_pixel(bbox_rel, W, H)
        log.info(f"  → bbox_pixel={bbox_pixel}")

        # ---- Text blocks: Save directly ----
        if btype in ["title", "text", "paragraph", "caption", "image_caption", "table_caption"]:
            results.append({
                "type": "text",
                "text": content or "",
                "bbox": bbox_pixel,
            })
            log.info(f"    Added TEXT block, content preview: {str(content)[:30]}")

        # ---- Image blocks: Crop as next level input ----
        elif btype in ["image", "table", "list"]:

            sub_img_name = f"sub_{current_depth}_{uuid.uuid4()}.png"
            sub_img_path = out_dir / sub_img_name
            
            log.info(f"Try to crop img: {image_path}")
            cropped_path = crop_and_save(img, bbox_pixel, sub_img_path) 
            sub_img_path = cropped_path if cropped_path else image_path
            log.info(f"    Cropped IMAGE block → {sub_img_path}")

            results.append({
                "type": "image",
                "img_path": str(sub_img_path),
                "bbox": bbox_pixel,
            })

            sub_images_paths.append(sub_img_path)

    log.info(f"[recursive_http] Depth={current_depth} → Parsed {len(results)} items, {len(sub_images_paths)} sub-images")

    # ----------------------------------------------
    # Process subgraphs recursively, replacing image elements with results
    # ----------------------------------------------
    if current_depth < max_depth and len(sub_images_paths) > 0:

        tasks = [
            recursive_run_mineru_http(
                sub_img_path,
                out_dir,
                port=port,
                max_depth=max_depth,
                current_depth=current_depth + 1
            )
            for sub_img_path in sub_images_paths
        ]

        sub_results_list = await asyncio.gather(*tasks)

        new_results = []

        sub_map = {
            str(path): sub_results_list[i]
            for i, path in enumerate(sub_images_paths)
        }

        for item in results:
            img_path = item.get("img_path")

            # Only perform replacement for subgraphs generated at current level
            if item["type"] in ["image", 'table', 'list'] and img_path in sub_map:
                parent_bbox = item["bbox"]
                sub_items = sub_map[img_path]

                log.info(f"    Replacing sub-image {img_path} with {len(sub_items)} items")

                for si in sub_items:
                    new_item = si.copy()
                    new_item["bbox"] = transform_sub_bbox(si["bbox"], parent_bbox)
                    new_results.append(new_item)
            else:
                new_results.append(item)

        results = new_results

    return results

# -------------------------------------------------------------------------------------

def get_font_size_for_text(bbox, text, max_font_size=48, min_font_size=10):
    """
    Infers font size based on text box bbox and text length
    bbox: [xmin, ymin, xmax, ymax]
    text: Text to insert
    """
    box_height = bbox[3] - bbox[1]  # Calculation of box height
    max_chars_per_line = 30         # Maximum characters per line
    lines = ceil(len(text) / max_chars_per_line)  # Calculation of needed lines

    font_size = min(box_height // lines, max_font_size)
    return max(font_size, min_font_size)

def generate_ppt_filename(output_path):
    """
    Generates a unique PPT filename based on current timestamp
    """
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return f"{output_path}/presentation_{timestamp}.pptx"

def pixels_to_inches(pixels: int, dpi: int = 96) -> float:
    """Converts pixels to inches"""
    return pixels / dpi


def calculate_font_size(text: str, bbox: List[int], text_level: int = None) -> int:
    """
    Calculates appropriate font size based on text box size, content, and text level
    """
    # Calculation of box width and height (pixels)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    
    # Set base font size according to text level
    if text_level == 1:  # Main title
        base_size = min(height * 0.8, 44)
    elif text_level == 2:  # Subtitle
        base_size = min(height * 0.7, 32)
    else:  # Body
        base_size = min(height * 0.6, 24)
    
    # Adjust according to text length
    char_count = len(text)
    if char_count > 0:
        chars_per_line = max(1, width / (base_size * 0.6))
        lines_needed = math.ceil(char_count / chars_per_line)
        
        max_lines = max(1, height / (base_size * 1.1))
        if lines_needed > max_lines:
            base_size = base_size * (max_lines / lines_needed)
    
    # Constrain font size range
    font_size = max(8, min(base_size, 72))
    
    return int(font_size)


def setup_presentation_size(prs, slide_width_px: int = 1024, slide_height_px: int = 1024):
    """Sets PPT size"""
    prs.slide_width = Inches(pixels_to_inches(slide_width_px))
    prs.slide_height = Inches(pixels_to_inches(slide_height_px))
    
    return slide_width_px, slide_height_px


def add_text_element(slide, element: Dict):
    """Adds text element to slide"""
    bbox = element.get('bbox', [0, 0, 100, 50])
    text = element.get('text', '')
    text_level = element.get('text_level')
    
    # Calculations for location and size
    left = pixels_to_inches(bbox[0])
    top = pixels_to_inches(bbox[1])
    width = pixels_to_inches(bbox[2] - bbox[0])
    height = pixels_to_inches(bbox[3] - bbox[1])
    
    # Calculation of font size
    font_size = calculate_font_size(text, bbox, text_level)
    
    log.info(f"Adding text box:")
    log.info(f"  Position: [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}] pixels")
    log.info(f"  Inch coordinates: left={left:.2f}, top={top:.2f}, width={width:.2f}, height={height:.2f}")
    log.info(f"  Text content: {text[:30]}{'...' if len(text) > 30 else ''}")
    log.info(f"  Text level: {text_level}, font size: {font_size}pt")
    
    # Add text box
    textbox = slide.shapes.add_textbox(
        Inches(left), Inches(top), Inches(width) * 1.2, Inches(height)
    )
    text_frame = textbox.text_frame
    text_frame.word_wrap = True
    
    # Set text content
    paragraph = text_frame.paragraphs[0]
    paragraph.text = text
    
    # Set font style
    paragraph.font.size = Pt(font_size)
    paragraph.font.name = "Comic Sans MS"
    
    # Set style according to text level
    if text_level == 1:
        paragraph.font.bold = True
        paragraph.alignment = PP_ALIGN.CENTER
        log.info("  Style: Title (Bold, Centered)")
    elif text_level == 2:
        paragraph.font.bold = True
        log.info("  Style: Subtitle (Bold)")
    else:
        log.info("  Style: Body")
    
    return textbox


def add_image_element(slide, element: Dict):
    """Adds image element to slide"""
    bbox = element.get('bbox', [0, 0, 100, 100])
    img_path = element.get('img_path', '')
    
    # Calculations for location and size
    left = pixels_to_inches(bbox[0])
    top = pixels_to_inches(bbox[1])
    width = pixels_to_inches(bbox[2] - bbox[0])
    height = pixels_to_inches(bbox[3] - bbox[1])
    
    log.info(f"Adding image:")
    log.info(f"  Position: [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}] pixels")
    log.info(f"  Inch coordinates: left={left:.2f}, top={top:.2f}, width={width:.2f}, height={height:.2f}")
    log.info(f"  Image path: {img_path}")
    log.info(f"  Image dimensions: {bbox[2]-bbox[0]}x{bbox[3]-bbox[1]} pixels")
    
    # Check if image file exists
    if os.path.exists(img_path):
        try:
            log.info("  Image file exists, adding...")
            result = slide.shapes.add_picture(
                img_path,
                Inches(left), Inches(top), Inches(width), Inches(height)
            )
            log.info("  Image added successfully")
            return result
        except Exception as e:
            log.error(f"  Error adding image: {e}")
            return add_image_placeholder(slide, bbox, f"Error: {str(e)}")
    else:
        log.warning("  Image file does not exist, using placeholder")
        return add_image_placeholder(slide, bbox, "Image not found")


def add_image_placeholder(slide, bbox: List[int], message: str):
    """Adds image placeholder"""
    left = pixels_to_inches(bbox[0])
    top = pixels_to_inches(bbox[1])
    width = pixels_to_inches(bbox[2] - bbox[0])
    height = pixels_to_inches(bbox[3] - bbox[1])
    
    # Add rectangle as placeholder
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor(240, 240, 240)
    shape.line.color.rgb = RGBColor(200, 200, 200)
    
    # Add status message text
    textbox = slide.shapes.add_textbox(
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    text_frame = textbox.text_frame
    text_frame.text = message
    text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    text_frame.paragraphs[0].font.size = Pt(10)
    text_frame.paragraphs[0].font.name = "Comic Sans MS"
    text_frame.paragraphs[0].font.color.rgb = RGBColor(128, 128, 128)
    
    return shape

# def robust_parse_json(
#         s: str,
#         merge_dicts: bool = False,          # Explicitly enable when merging is desired
#         strip_double_braces: bool = False   # Optional: {{ }} → { }
# ) -> Union[Dict[str, Any], List[Any]]:
#     """
#     Infers pure JSON and can also extract multiple objects from mixed text.
    
#     - Supports // and /* */ comments, trailing commas
#     - Automatically removes Markdown code blocks ```json … ```, triple quotes ''' … '''
#     - Returns original dict / list structure by default
#     - If multiple independent objects are extracted, can be merged with merge_dicts=True
#     """

#     # ---------- Preprocessing ----------
#     # 1) Strip ```xxx code fences
#     s = re.sub(r'```[\w]*\s*', '', s)      # Start fence
#     s = re.sub(r'```', '', s)              # End fence
#     # 2) Strip paired triple quotes ''' or """
#     s = re.sub(r"^'''|'''$|^\"\"\"|\"\"\"$", '', s.strip())
#     # 3) Optional: {{ }} → { }
#     if strip_double_braces:
#         s = s.replace('{{', '{').replace('}}', '}')
#     # 4) Strip comments + trailing commas
#     s = _strip_json_comments(s)

#     # ---------- Step 1: Overall Parsing ----------
#     try:
#         return json.loads(s)              
#     except JSONDecodeError:
#         pass                              

#     # ---------- Step 2: Multi-object extraction ----------
#     objs: List[Any] = _extract_json_objects(s)
#     if not objs:
#         raise ValueError("No valid JSON found.")

#     # Single object
#     if len(objs) == 1:
#         return objs[0]

#     # Multi-object: depends on parameters
#     if merge_dicts and all(isinstance(o, dict) for o in objs):
#         merged: Dict[str, Any] = {}
#         for o in objs:
#             merged.update(o)
#         return merged
#     return objs

# def _strip_json_comments(s: str) -> str:
#     # s = re.sub(r'/\*.*?\*/', '', s, flags=re.S)          # Block comment
#     # s = re.sub(r'//.*?$',    '', s, flags=re.M)          # Line comment
#     s = re.sub(r',\s*([}\]])', r'\1', s)                 # Trailing comma
#     return s

# def _extract_json_objects(s: str) -> List[Any]:
#     dec = JSONDecoder()
#     idx, n = 0, len(s)
#     objs = []
#     while idx < n:
#         # Look for next { or [
#         m = re.search(r'[{\[]', s[idx:])
#         if not m:
#             break
#         idx += m.start()
#         try:
#             obj, end = dec.raw_decode(s, idx)
#             objs.append(obj)
#             idx = end
#         except JSONDecodeError:
#             idx += 1
#     return objs


# ========================================================================

#                           For Paper2ExpFigure

# ========================================================================

def pdf_to_pil_images(
    pdf_path: Union[str, Path],
    dpi: int = 300
) -> List[Image.Image]:
    """
    Converts each page of a PDF file to a PIL Image object.
    Fixed issues with white/corrupted images caused by CMYK/Grayscale/Transparent backgrounds.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file does not exist: {pdf_path}")

    # Calculations for scaling ratio
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    images: List[Image.Image] = []
    
    # flags here are used for handling complex rendering cases (optional, but useful in some chart PDFs)
    # fitz.pdf.Page.get_pixmap automatically handles most cases by default
    
    doc = fitz.open(pdf_path)
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # 1. Get initial Pixmap
            # alpha=False: force opaque background (default white), solves transparent backgrounds turning black/white
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            # 2. Critical fix: Check color space and convert
            # pix.n is the channel count. Force convert to RGB if not 3 (RGB)
            if pix.n != 3:
                # fitz.csRGB is PyMuPDF's built-in RGB color space definition
                temp_pix = fitz.Pixmap(fitz.csRGB, pix)
                pix = temp_pix  # Replace with converted RGB pixmap
                # Note: temp_pix is just a reference, subsequent logic is consistent and memory managed

            # 3. Safely convert to PIL
            # Now we are 100% sure the data is in RGB format
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            images.append(img)

            log.info(f"[pdf_to_pil_images] Converted page {page_num + 1} (Mode: {pix.n} channels), Size: {pix.width}x{pix.height}")

    except Exception as e:
        log.error(f"[pdf_to_pil_images] Error during transformation: {e}")
        raise e
    finally:
        doc.close()

    log.info(f"[pdf_to_pil_images] Complete, total {len(images)} images generated")
    return images


def _parse_html_table(html_content: str) -> tuple[List[str], List[List[str]]]:
    """
    Parses HTML table content, extracting headers and data rows.
    
    Parameters
    ----------
    html_content : str
        HTML table string, e.g., <table>...</table>
    
    Returns
    -------
    tuple[List[str], List[List[str]]]
        (headers, rows) - Table column names and data rows
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log.warning("[_parse_html_table] BeautifulSoup not installed, using simple parsing")
        return _parse_html_table_simple(html_content)
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        table = soup.find('table')
        
        if not table:
            log.warning("[_parse_html_table] tag table not found")
            return [], []
        
        # Extract all rows
        rows_data = []
        for tr in table.find_all('tr'):
            row = []
            for cell in tr.find_all(['td', 'th']):
                # Handle colspan
                colspan = int(cell.get('colspan', 1))
                cell_text = cell.get_text(strip=True)
                row.append(cell_text)
                # Add empty cells if colspan exists
                for _ in range(colspan - 1):
                    row.append('')
            if row:  # Add non-empty rows only
                rows_data.append(row)
        
        if not rows_data:
            return [], []
        
        # Use first row as header
        headers = rows_data[0]
        data_rows = rows_data[1:] if len(rows_data) > 1 else []
        
        return headers, data_rows
        
    except Exception as e:
        log.error(f"[_parse_html_table] Parsing failed: {e}")
        return _parse_html_table_simple(html_content)


def _parse_html_table_simple(html_content: str) -> tuple[List[str], List[List[str]]]:
    """
    Simple HTML table parsing (no BeautifulSoup dependency).
    Fallback only, may not be robust.
    """
    try:
        # Simple regex extraction for all <tr>...</tr> content
        import re
        tr_pattern = re.compile(r'<tr>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
        td_pattern = re.compile(r'<t[dh][^>]*>(.*?)</t[dh]>', re.DOTALL | re.IGNORECASE)
        
        rows_data = []
        for tr_match in tr_pattern.finditer(html_content):
            tr_content = tr_match.group(1)
            row = []
            for td_match in td_pattern.finditer(tr_content):
                cell_text = td_match.group(1).strip()
                # Strip HTML tags
                cell_text = re.sub(r'<[^>]+>', '', cell_text)
                row.append(cell_text)
            if row:
                rows_data.append(row)
        
        if not rows_data:
            return [], []
        
        headers = rows_data[0]
        data_rows = rows_data[1:] if len(rows_data) > 1 else []
        
        return headers, data_rows
        
    except Exception as e:
        log.error(f"[_parse_html_table_simple] Simple parsing failed: {e}")
        return [], []


def extract_tables_from_mineru_results(
    mineru_items: List[Dict[str, Any]],
    min_rows: int = 2,
    min_cols: int = 2,
) -> List[Dict[str, Any]]:
    """
    Extracts table data from MinerU识别 results.

    Parameters
    ----------
    mineru_items : List[Dict[str, Any]]
        List of items returned by MinerU, each item containing type, bbox, content fields etc.
    min_rows : int, default 2
        Minimum row count, tables with fewer rows will be filtered
    min_cols : int, default 2
        Minimum column count, tables with fewer columns will be filtered

    Returns
    -------
    List[Dict[str, Any]]
        List of extracted tables, each in format:
        {
            "table_id": str,           # Unique identifier for table
            "headers": List[str],       # Table header column names
            "rows": List[List[str]],    # Data rows
            "caption": str,             # Table title/description
            "bbox": List[int],          # Original coordinates
            "content": str,             # Original HTML content (if it's an HTML table)
        }
    """
    tables = []
    table_idx = 0

    # Temporary storage for associating caption and table
    pending_caption = ""

    for item in mineru_items:
        item_type = item.get("type", "")
        content = item.get("content", "")
        bbox = item.get("bbox", [])

        # Handle table_caption
        if item_type == "table_caption" and content:
            pending_caption = content
            continue

        # Handle table
        if item_type == "table" and content:
            # MinerU returns content as HTML string (e.g., <table>...</table>)
            headers, rows = _parse_html_table(content)
            
            # Filter small tables
            if len(headers) < min_cols or len(rows) < min_rows:
                log.debug(f"[extract_tables] Skipping small table: {len(headers)} columns, {len(rows)} rows")
                continue

            table_id = f"table_{table_idx}"
            table_idx += 1

            tables.append({
                "table_id": table_id,
                "headers": headers,
                "rows": rows,
                "caption": pending_caption,
                "bbox": bbox,
                "content": content,  # 保留原始 HTML
            })

            pending_caption = ""  # Reset
            log.info(f"[extract_tables] Extracted table {table_id}: {len(headers)} columns, {len(rows)} rows, caption: {pending_caption[:50] if pending_caption else 'N/A'}")

    log.info(f"[extract_tables] Total {len(tables)} tables extracted")
    return tables


def extract_text_from_mineru_results(
    mineru_items: List[Dict[str, Any]],
    max_chars: int = 10000,
) -> str:
    """
    Extracts plain text content from MinerU识别 results (used for paper_idea_extractor).

    Parameters
    ----------
    mineru_items : List[Dict[str, Any]]
        List of items returned by MinerU
    max_chars : int, default 10000
        Maximum character count for extraction to avoid excessive length

    Returns
    -------
    str
        Extracted text content
    """
    text_parts = []
    total_chars = 0

    for item in mineru_items:
        if total_chars >= max_chars:
            break

        item_type = item.get("type", "")
        content = item.get("content", "")

        # Extract text-typed content (text, title, table_caption etc.)
        if item_type in ["text", "title", "table_caption"] and content:
            text_parts.append(content)
            total_chars += len(content)

    result = "\n\n".join(text_parts)
    
    if total_chars > max_chars:
        result = result[:max_chars] + "..."

    log.info(f"[extract_text] Extracted {len(text_parts)} text segments, total {len(result)} characters")
    return result


def execute_matplotlib_code(
    code: str,
    output_path: Union[str, Path],
    timeout: int = 30,
    allowed_modules: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Safely executes matplotlib code and saves chart.

    Parameters
    ----------
    code : str
        The matplotlib Python code to execute
    output_path : str | Path
        Output path for chart (including filename, e.g., /tmp/chart.png)
    timeout : int, default 30
        Execution timeout (seconds)
    allowed_modules : List[str], optional
        List of modules allowed to be imported, defaults to ["matplotlib", "numpy", "pandas"]

    Returns
    -------
    Dict[str, Any]
        {
            "success": bool,
            "output_path": str,      # Image path returned on success
            "error": str,            # Error message returned on failure
        }
    """
    import subprocess
    import tempfile

    if allowed_modules is None:
        allowed_modules = ["matplotlib", "numpy", "pandas", "math"]

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Security check: Prohibit dangerous operations
    dangerous_patterns = [
        r'\bos\.system\b',
        r'\bsubprocess\b',
        r'\beval\b',
        r'\bexec\b',
        r'\bopen\s*\(',
        r'\b__import__\b',
        r'\bimport\s+os\b',
        r'\bimport\s+sys\b',
        r'\bimport\s+subprocess\b',
        r'\bfrom\s+os\b',
        r'\bfrom\s+sys\b',
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, code):
            return {
                "success": False,
                "output_path": "",
                "error": f"Dangerous operation detected: {pattern}",
            }

    # Build complete execution code
#     full_code = f'''
# import matplotlib
# matplotlib.use('Agg')  # Non-interactive backend
# import matplotlib.pyplot as plt
# import numpy as np

# # User code
# {code}

# # Save chart
# plt.tight_layout()
# plt.savefig(r"{str(output_path)}", dpi=150, bbox_inches='tight')
# plt.close('all')
# print("SUCCESS")
# '''
    full_code = f'''
{code}
'''

    # Write to temporary file and execute
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(full_code)
            temp_script = f.name

        result = subprocess.run(
            ['python', temp_script],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(output_path.parent),
        )

        # Cleanup temporary file
        try:
            os.unlink(temp_script)
        except Exception:
            pass

        # Determine success: status code 0 and image exists
        if result.returncode == 0:
            if output_path.exists():
                log.info(f"[execute_matplotlib] Chart generated successfully: {output_path}")
                return {
                    "success": True,
                    "output_path": str(output_path),
                    "error": "",
                }
            else:
                log.warning(f"[execute_matplotlib] Code executed successfully but image not generated")
                return {
                    "success": False,
                    "output_path": "",
                    "error": "Code executed successfully but image not generated",
                }
        else:
            error_msg = result.stderr or result.stdout or "Unknown error"
            log.warning(f"[execute_matplotlib] Execution failed (Status: {result.returncode}): {error_msg}")
            return {
                "success": False,
                "output_path": "",
                "error": error_msg[:500],  # Truncate long error messages
            }

    except subprocess.TimeoutExpired:
        log.warning(f"[execute_matplotlib] Execution timeout ({timeout}s)")
        return {
            "success": False,
            "output_path": "",
            "error": f"Code execution timeout ({timeout} seconds)",
        }
    except Exception as e:
        log.error(f"[execute_matplotlib] Execution exception: {e}")
        return {
            "success": False,
            "output_path": "",
            "final_code": full_code,
            "error": str(e),
        }
