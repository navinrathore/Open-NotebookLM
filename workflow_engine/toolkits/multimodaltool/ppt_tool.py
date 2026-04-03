# -*- coding: utf-8 -*-
"""
ppt_tool

This module identifies a sequence of images as editable text via PaddleOCR, automatically analyzes line height, layout, and color, generates a PPTX with a "clean background + overlay text boxes", and optionally exports a PDF simultaneously.
It provides multiple parameters to control background inpaint strength (INPAINT_METHOD/INPAINT_RADIUS, SIMPLE_BG_VAR_THRESH, MASK_DILATE_ITER, USE_ADAPTIVE_MASK),
OCR resolution and sharpening (UPSCALE_LONG_SIDE_TO, UPSCALE_INTERP, ENABLE_SHARPEN, SHARPEN_AMOUNT),
text filtering threshold (DROP_SCORE), and font size amplification and the ratio of title/subtitle to body (BASE_BODY_PT, FONT_SCALE_FACTOR, TITLE_RATIO_*/SUBTITLE_RATIO_*/BODY_RATIO_*).
It balances "restoring visual effects" with "editability/aesthetics" and performance by controlling whether to overlay background images, remove original text, and estimate text color based on the original image through ADD_BACKGROUND_IMAGE / CLEAN_BACKGROUND / EXTRACT_TEXT_COLOR.

Feature Overview:
- Read images in natural order from a specified directory
- Generate a PDF file containing all image pages
- Use PaddleOCR to perform OCR on pages and identify text lines
- Automatically estimate font size and color based on recognition results and overlay text on PPTX
- Optionally inpaint the original page to generate a "clean background without text" as the PPT background

Typical Usage:
- Used as a post-processing tool from image pages to editable PPT documents in the image processing workflow of DataFlow-Agent
- Can also be directly called via external functions in other components or scripts
"""

# Function Overview:
# natural_key(s): Generates a key for "natural sorting" of filenames, comparing numeric parts as integers.
# list_images_in_dir(d): Lists all image file paths in a directory in natural order.
# read_bgr(path): Reads an image in a way compatible with non-ASCII paths and returns standard BGR uint8 format.
# debug_dump(img, tag): Writes intermediate images to a debug directory and logs basic statistics.
# images_to_pdf(image_paths, output_pdf_path): Exports a set of images sequentially as a single PDF file.
# pdf_to_images(pdf_path, out_dir, dpi): Renders each page of a PDF as a PNG at a specified resolution and returns a list of image paths.
# upscale_if_needed(bgr, long_side_to, interp): Enlarges the image by the long side if the resolution is low, returning the enlarged image and scale ratio.
# sharpen(bgr, amount): Gently sharpens the image using the "unsharp mask" method.
# preprocess_for_ocr(bgr): Enlarges and optionally sharpens the full-page image, generating a version suitable for OCR and its scale ratio.
# is_cjk(s): Determines if a string contains CJK (Chinese, Japanese, Korean) characters.
# iou(a, b): Calculates the Intersection over Union (IoU) of two bounding boxes.
# merge_lines(lines, y_tol, x_gap): Merges OCR short lines/words into sentence-level text lines based on line direction and spacing.
# text_score(lines): Estimates the overall score of a set of text lines based on characters, average confidence, and CJK presence.
# paddle_ocr(bgr, drop_score): Calls PaddleOCR to perform OCR on a full-page BGR image and filters results by confidence threshold.
# paddle_ocr_page_with_layout(img_path): Performs preprocessing + OCR + line merging + line height/background color estimation for a single page image and returns layout info.
# extract_text_color(bgr, bbox, bg_color): Estimates main text color from a given text area, trying to exclude colors close to the background.
# estimate_background_color(bgr, lines): Inverts text mask to select background area and estimates the main background color of the page.
# px_to_emu(px, emu_per_px): Converts pixel values to EMU units used by PPT according to a given ratio.
# analyze_line_heights(lines): Researches the distribution of OCR line box heights and estimates the median line height of the body.
# classify_line_role(bbox, img_h_px, body_h_px): Roughly distinguishes between title, subtitle, and body based on line height and vertical position.
# estimate_font_pt(bbox, img_h_px, body_h_px, slide_h_in): Estimates font size in PPT based on the line height ratio of the original image.
# add_background(slide, bgr, slide_w_emu, slide_h_emu, tmp_path): Adds full-page background image to a PPT slide and deletes temp files.
# build_text_mask_from_lines(bgr, lines): Generates a rough binary mask of text areas based on OCR line boxes.
# build_adaptive_mask(bgr, lines): Generates a finer main text mask by combining local contrast and adaptive thresholding.
# is_simple_background_region(bgr, mask): Determines if the background of text area neighborhood is approximately solid (low variance).
# fill_with_neighbor(bgr, mask): Roughly fills text areas of complex backgrounds with neighborhood pixels to alleviate inpaint artifacts.
# make_clean_background(bgr, lines): Generates a "clean background without text" based on text mask and inpaint.
# ocr_images_to_ppt(image_paths, output_pptx, add_background_image, clean_background, use_text_color): Converts a sequence of images into an editable PPT with background and overlay text boxes via OCR.
# images_to_pdf_and_ppt(image_paths, output_pdf_path, output_pptx_path, add_background_image, clean_background, extract_text_color): One-stop conversion of a given image list to PDF and PPTX and returns paths.
# convert_images_dir_to_pdf_and_ppt(input_dir, output_pdf_path, output_pptx_path, add_background_image, clean_background, extract_text_color): Reads images from a directory and generates corresponding PDF + PPTX.
# convert_images_dir_to_pdf_and_ppt_api(input_dir, output_pdf_path, output_pptx_path, api_url, api_key, model, use_api_inpaint, add_background_image, clean_background, use_text_color): Async version of directory to PDF/PPTX conversion, prioritizes image editing API for inpainting, falls back to local inpaint on failure.

import os
import re
from typing import Sequence, Optional, Dict, Any, List, Tuple
import requests
import random
from collections import Counter

import fitz  # PyMuPDF
from pathlib import Path

import numpy as np
from PIL import Image
import cv2
from paddleocr import PaddleOCR

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from workflow_engine.utils import get_project_root
from workflow_engine.logger import get_logger
from typing import Union

log = get_logger(__name__)

# ----------------------------
# Config (Default configuration, can be partially overridden via external function parameters)
# ----------------------------
ADD_BACKGROUND_IMAGE = True
CLEAN_BACKGROUND = True  # Whether to try removing text, generate a clean background and overlay OCR text
EXTRACT_TEXT_COLOR = True  # Whether to extract original text color
INPAINT_METHOD = cv2.INPAINT_TELEA  # or cv2.INPAINT_NS
INPAINT_RADIUS = 7  # Increase inpaint radius (from 3 to 7)
SIMPLE_BG_VAR_THRESH = 50.0  # Relax threshold (from 12 to 50)
MASK_DILATE_ITER = 2  # Increase dilation iterations (from 1 to 2)
USE_ADAPTIVE_MASK = True  # Use adaptive mask generation

# Output PPT ratio (16:9)
SLIDE_W_IN = 13.333
SLIDE_H_IN = 7.5

# Debug: Dump images sent to OCR to easily manually confirm content/resolution/corruption
DEBUG_DUMP_FIRST_N = 2
DEBUG_DIR = f"{get_project_root()}/tests/debug_frames"

# ---------- Core fix: OCR pre-enhancement for low-resolution pages ----------
UPSCALE_LONG_SIDE_TO = 2200  # Recommend 2000~3200, larger is slower
UPSCALE_INTERP = cv2.INTER_CUBIC
ENABLE_SHARPEN = True  # Gentle sharpening to enhance edge contrast
SHARPEN_AMOUNT = 0.8  # Between 0.0~1.5

# Recognition filtering threshold
DROP_SCORE = 30  # PaddleOCR score is 0-1, here multiplied by 100 and filtered by 0-100

# Font size optimization configuration (enlarge overall font size, significantly differentiate titles from body)
BASE_BODY_PT = 16.0  # Body baseline font size
FONT_SCALE_FACTOR = 1.0  # Global font size scale factor
TITLE_RATIO_MIN = 2.0  # Title minimum multiplier
TITLE_RATIO_MAX = 3.5  # Title maximum multiplier
SUBTITLE_RATIO_MIN = 1.4  # Subtitle minimum multiplier
SUBTITLE_RATIO_MAX = 2.0  # Subtitle maximum multiplier
BODY_RATIO_MIN = 0.9  # Body minimum multiplier
BODY_RATIO_MAX = 1.1  # Body maximum multiplier

# PaddleOCR configuration (initialized only once globally)
PADDLE_OCR = PaddleOCR(
    use_angle_cls=True,  # Angle classification, handles horizontal/vertical mixing
    lang="ch",  # Chinese + English
    det_db_unclip_ratio=1.2 ,
    det_db_box_thresh=0.5
)

# ----------------------------
# Font Size Clustering
# ----------------------------

class FontSizeClustering:
    """
    Adaptive font size clusterer: maps continuous, noisy font size estimates to K discrete "standard font sizes".
    Supports global clustering (uniform across all documents) or single-page clustering.
    Depends on sklearn.cluster.KMeans, falls back to a simple mode/quantile strategy if missing.
    """
    def __init__(self, n_clusters: int = 4, merge_tol: float = 2.0):
        self.n_clusters = n_clusters
        self.merge_tol = merge_tol
        self.centroids = []
        self.has_sklearn = False
        try:
            from sklearn.cluster import KMeans
            self._KMeans = KMeans
            self.has_sklearn = True
        except ImportError:
            pass

    def fit(self, font_sizes: List[float]) -> "FontSizeClustering":
        """
        Input raw font size list (pt), calculate cluster centroids.
        """
        # Filter invalid values
        data = [x for x in font_sizes if x > 0]
        if not data:
            self.centroids = [12.0] # Default fallback
            return self

        # 1. If data size is too small, use original values (deduplicated and sorted)
        if len(data) < self.n_clusters:
            self.centroids = sorted(list(set(data)))
            return self

        # 2. If sklearn is not available, fall back to simple histogram statistics (take top K high-frequency values)
        if not self.has_sklearn:
            # Simple stats: take K most frequent, or simple quantiles
            # Frequency stats fit the intuition of "standard font sizes" better here
            counts = Counter([round(x) for x in data])
            top_k = counts.most_common(self.n_clusters)
            self.centroids = sorted([float(x[0]) for x in top_k])
            return self

        # 3. K-Means clustering
        import numpy as np
        X = np.array(data).reshape(-1, 1)
        
        # Dynamically adjust K: cannot exceed number of unique values in samples
        n_unique = len(set([round(x, 1) for x in data]))
        real_k = min(self.n_clusters, n_unique)
        
        kmeans = self._KMeans(n_clusters=real_k, n_init=10, random_state=42)
        kmeans.fit(X)
        centers = sorted(kmeans.cluster_centers_.flatten())

        # 4. 后处理：合并过近的中心 (Merge close centers)
        merged_centers = []
        if centers:
            curr = centers[0]
            for next_c in centers[1:]:
                if (next_c - curr) < self.merge_tol:
                    # Too close, merge (take average)
                    curr = (curr + next_c) / 2.0
                else:
                    merged_centers.append(curr)
                    curr = next_c
            merged_centers.append(curr)
        
        # Round to 0.5 pt
        self.centroids = [round(c * 2) / 2.0 for c in merged_centers]
        log.info(f"[FontSizeClustering] Fitted centroids: {self.centroids}")
        return self

    def map(self, pt: float) -> float:
        """
        Map original font size to the nearest centroid.
        """
        if not self.centroids:
            return pt
        
        # Find nearest neighbor
        closest = min(self.centroids, key=lambda c: abs(c - pt))
        return closest


# ----------------------------
# IO helpers
# ----------------------------


def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def list_images_in_dir(d: str) -> List[str]:
    """
    Lists all image file paths in a directory in natural order.
    """
    exts = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
    files = [f for f in os.listdir(d) if f.lower().endswith(exts)]
    files.sort(key=natural_key)
    return [os.path.join(d, f) for f in files]


def read_bgr(path: str) -> np.ndarray:
    """
    Robust image reader:
    - supports non-ascii paths (np.fromfile + imdecode)
    - returns BGR uint8 HxWx3
    """
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Failed to read image: {path}")

    # Normalize to BGR uint8
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.ndim == 3 and img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    if img.dtype != np.uint8:
        img = np.clip(img, 0, 255).astype(np.uint8)

    return img


def debug_dump(img: np.ndarray, tag: str = "dbg") -> None:
    """
    Writes intermediate images to DEBUG_DIR for easier debugging.
    """
    os.makedirs(DEBUG_DIR, exist_ok=True)

    log.info(f"{tag} type: {type(img)}")
    if isinstance(img, np.ndarray):
        log.info(
            f"{tag} shape: {img.shape}, dtype: {img.dtype}, "
            f"min/max: {int(img.min())}/{int(img.max())}"
        )

    out_path = os.path.join(DEBUG_DIR, f"{tag}.png")
    ok = cv2.imwrite(out_path, img)
    log.info(f"{tag} saved: {out_path}, ok: {ok}")


# ----------------------------
# PDF / Page helpers
# ----------------------------


def images_to_pdf(image_paths: Sequence[str], output_pdf_path: str) -> str:
    """
    Exports a set of images as a single PDF file.
    """
    imgs: List[Image.Image] = []
    for p in image_paths:
        im = Image.open(p)
        if im.mode != "RGB":
            im = im.convert("RGB")
        imgs.append(im)
    if not imgs:
        raise ValueError("No images for PDF.")
    imgs[0].save(output_pdf_path, save_all=True, append_images=imgs[1:])
    return output_pdf_path


def pdf_to_images(pdf_path: str, out_dir: str, dpi: int = 220) -> List[str]:
    """
    Renders each page of a PDF as a PNG image and returns a list of image paths (in page order).

    Parameters
    ----------
    pdf_path:
        Input PDF file path.
    out_dir:
        Directory for output images; created automatically if it doesn't exist.
    dpi:
        Rendering resolution (pixels per inch), default 220.

    Returns
    -------
    List[str]
        List of absolute paths to PNG images in page order.
    """
    doc = fitz.open(pdf_path)
    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    image_paths: List[str] = []
    for page_index in range(len(doc)):
        page = doc.load_page(page_index)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        img_path = out_dir_path / f"page_{page_index + 1:03d}.png"
        pix.save(str(img_path))
        image_paths.append(str(img_path))

    doc.close()
    log.info(f"[pdf_to_images] rendered {len(image_paths)} pages from {pdf_path}")
    return image_paths


# ----------------------------
# Preprocess
# ----------------------------


def upscale_if_needed(
    bgr: np.ndarray,
    long_side_to: int = UPSCALE_LONG_SIDE_TO,
    interp: int = UPSCALE_INTERP,
):
    h, w = bgr.shape[:2]
    long_side = max(h, w)
    if long_side >= long_side_to:
        return bgr, 1.0

    scale = long_side_to / float(long_side)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    up = cv2.resize(bgr, (new_w, new_h), interpolation=interp)
    return up, scale


def sharpen(bgr: np.ndarray, amount: float = SHARPEN_AMOUNT) -> np.ndarray:
    """
    Unsharp mask style: sharpen = img*(1+a) - blur*a
    """
    if amount <= 0:
        return bgr
    blur = cv2.GaussianBlur(bgr, (0, 0), sigmaX=1.2, sigmaY=1.2)
    out = cv2.addWeighted(bgr, 1.0 + amount, blur, -amount, 0)
    return np.clip(out, 0, 255).astype(np.uint8)


def preprocess_for_ocr(bgr: np.ndarray):
    """
    Make a "det-friendly" version of the page:
    - upscale to a reasonable working resolution
    - optional sharpen
    """
    up, scale = upscale_if_needed(bgr)
    if ENABLE_SHARPEN:
        up = sharpen(up, amount=SHARPEN_AMOUNT)
    return up, scale


# ----------------------------
# OCR helpers
# ----------------------------


def is_cjk(s: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


def iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter + 1e-6)


def merge_lines(
    lines: Sequence[Tuple[Sequence[float], str, float]], y_tol: int = 12, x_gap: int = 18
):
    """
    Merges OCR words/short lines into sentence-level lines.
    """
    if not lines:
        return []
    lines = sorted(lines, key=lambda x: (x[0][1], x[0][0]))

    def union(b1, b2):
        return [
            min(b1[0], b2[0]),
            min(b1[1], b2[1]),
            max(b1[2], b2[2]),
            max(b1[3], b2[3]),
        ]

    merged = []
    cur_bbox, cur_text, cur_conf_sum, cur_n = (
        lines[0][0],
        lines[0][1],
        lines[0][2],
        1,
    )

    for bbox, text, conf in lines[1:]:
        cy1 = (cur_bbox[1] + cur_bbox[3]) / 2
        cy2 = (bbox[1] + bbox[3]) / 2
        same_line = abs(cy1 - cy2) <= y_tol
        near_x = (bbox[0] - cur_bbox[2]) <= x_gap

        if same_line and near_x:
            cur_bbox = union(cur_bbox, bbox)
            if (not is_cjk(cur_text)) and (not is_cjk(text)):
                cur_text = (cur_text + " " + text).strip()
            else:
                cur_text = (cur_text + text).strip()
            cur_conf_sum += conf
            cur_n += 1
        else:
            merged.append((cur_bbox, cur_text, cur_conf_sum / cur_n))
            cur_bbox, cur_text, cur_conf_sum, cur_n = bbox, text, conf, 1

    merged.append((cur_bbox, cur_text, cur_conf_sum / cur_n))
    return merged


def text_score(lines) -> float:
    if not lines:
        return 0.0
    total_chars = sum(len(t) for (_, t, _) in lines)
    avg_conf = sum(conf for (_, _, conf) in lines) / max(1, len(lines))
    cjk_bonus = 1.1 if any(is_cjk(t) for (_, t, _) in lines) else 1.0
    return total_chars * (avg_conf / 100.0) * cjk_bonus  # normalize confidence to 0-1


def paddle_ocr(bgr: np.ndarray, drop_score: int = DROP_SCORE):
    """
    Recognize full-page images using PaddleOCR
    Return format: [(bbox, text, confidence), ...]
    bbox: [x1, y1, x2, y2]
    Note: Runs directly on BGR image; PaddleOCR handles color space internally.
    """
    h, w = bgr.shape[:2]

    # ocr_result: List[List[ [box, (text, score)], ... ]]
    ocr_result = PADDLE_OCR.ocr(bgr, cls=True)
    lines = []

    if not ocr_result:
        return lines

    # Usually one page corresponds to ocr_result[0]
    for line in ocr_result[0]:
        box, (text, score) = line
        if not text:
            continue
        if score * 100.0 < drop_score:
            continue

        # box is a four-point polygon: [ [x1,y1], [x2,y2], [x3,y3], [x4,y4] ]
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)

        # Boundary clipping
        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h, y2))
        if x2 <= x1 or y2 <= y1:
            continue

        bbox = [float(x1), float(y1), float(x2), float(y2)]
        # Maintain 0-100 confidence range, compatible with original Tesseract logic
        lines.append((bbox, text.strip(), float(score * 100.0)))

    return lines


def paddle_ocr_page_with_layout(img_path: str) -> Dict[str, Any]:
    """
    Performs on a single page image:
    - Read + Preprocess (Upscale + Sharpen)
    - PaddleOCR recognition
    - Map coordinates from OCR resolution back to original image
    - Line merging
    - Body line height estimation
    - Background color estimation

    Returns:
    {
        "image_size": (w, h),
        "lines": [(bbox, text, conf), ...],  # bbox is original image pixel coordinates
        "body_h_px": float or None,
        "bg_color": (r,g,b) or None,
    }
    """
    bgr = read_bgr(img_path)
    h0, w0 = bgr.shape[:2]

    # Preprocessing
    ocr_img, scale = preprocess_for_ocr(bgr)
    h1, w1 = ocr_img.shape[:2]

    log.info(f"[paddle_ocr_page_with_layout] {os.path.basename(img_path)} up-scale={scale:.3f}")

    # OCR
    raw_lines = paddle_ocr(ocr_img)

    # Map back to original image pixel coordinates
    if raw_lines and (w1 != w0 or h1 != h0):
        sx = w0 / float(w1)
        sy = h0 / float(h1)
        raw_lines = [
            ([b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy], t, c)
            for (b, t, c) in raw_lines
        ]

    # 合并行
    y_tol = max(12, int(h0 * 0.008))
    x_gap = max(18, int(w0 * 0.01))
    lines = merge_lines(raw_lines, y_tol=y_tol, x_gap=x_gap)

    # Body line height estimation
    body_h_px = analyze_line_heights(lines)

    if not lines:
        log.warning(f"[paddle_ocr_page_with_layout] no text detected: {img_path}")
        bg_color = None
    else:
        log.info(
            f"[paddle_ocr_page_with_layout] detected {len(lines)} text boxes, body_h_px={body_h_px}"
        )
        bg_color = estimate_background_color(bgr, lines) if EXTRACT_TEXT_COLOR else None

    return {
        "image_size": (w0, h0),
        "lines": lines,
        "body_h_px": body_h_px,
        "bg_color": bg_color,
    }


def paddle_ocr_page_with_layout_server(
    img_path: str,
    server_urls: Union[str, List[str]],
) -> Dict[str, Any]:
    """
    Performs remote OCR processing on a single page image.

    Parameters:
        img_path: image path
        server_urls: OCR server URL or list of URLs

    Returns:
        Same as paddle_ocr_page_with_layout
    """
    if isinstance(server_urls, str):
        urls = [server_urls]
    else:
        urls = list(server_urls)
    
    if not urls:
        raise ValueError("No server URLs provided")
    
    base_url = random.choice(urls)
    api_url = f"{base_url.rstrip('/')}/predict"
    
    abs_img_path = os.path.abspath(img_path)
    payload = {"image_path": abs_img_path}
    
    try:
        response = requests.post(api_url, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()
        
        # Transform lines back to tuples if needed, though list is fine
        # lines: [[bbox, text, conf], ...] -> [(bbox, text, conf), ...]
        lines = []
        for line_obj in data.get("lines", []):
            lines.append((
                line_obj.get("bbox"),
                line_obj.get("text"),
                line_obj.get("conf")
            ))
            
        return {
            "image_size": tuple(data.get("image_size", [0, 0])),
            "lines": lines,
            "body_h_px": data.get("body_h_px"),
            "bg_color": tuple(data.get("bg_color")) if data.get("bg_color") else None
        }
        
    except Exception as e:
        raise RuntimeError(f"Failed to call OCR server at {api_url}: {e}")


# ----------------------------
# Color extraction
# ----------------------------


def extract_text_color(
    bgr: np.ndarray, bbox, bg_color=None
) -> Tuple[int, int, int]:
    """
    Extracts the main color tone from the text area.
    Returns (r, g, b) tuple.
    """
    x1, y1, x2, y2 = [int(round(v)) for v in bbox]
    h, w = bgr.shape[:2]

    # Boundary check
    x1 = max(0, min(w - 1, x1))
    x2 = max(0, min(w, x2))
    y1 = max(0, min(h - 1, y1))
    y2 = max(0, min(h, y2))

    if x2 <= x1 or y2 <= y1:
        return (0, 0, 0)  # Default black

    # Extract text area
    region = bgr[y1:y2, x1:x2]
    if region.size == 0:
        return (0, 0, 0)

    # Convert to RGB
    region_rgb = cv2.cvtColor(region, cv2.COLOR_BGR2RGB)
    pixels = region_rgb.reshape(-1, 3)

    # If pixels are too few, return median color directly
    if len(pixels) < 10:
        median_color = np.median(pixels, axis=0).astype(int)
        return tuple(int(x) for x in median_color)

    # Use K-means clustering to find main color tone (2-3 clusters)
    try:
        from sklearn.cluster import KMeans

        n_clusters = min(3, len(pixels))
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        kmeans.fit(pixels)

        # Get cluster centers and pixel counts per cluster
        centers = kmeans.cluster_centers_
        labels = kmeans.labels_
        counts = np.bincount(labels)

        # If background color provided, exclude clusters close to background color
        if bg_color is not None:
            bg_array = np.array(bg_color)
            valid_centers = []
            valid_counts = []

            for i, center in enumerate(centers):
                # 计算与背景色的距离
                dist = np.linalg.norm(center - bg_array)
                if dist > 30:  # Distance threshold
                    valid_centers.append(center)
                    valid_counts.append(counts[i])

            if valid_centers:
                centers = np.array(valid_centers)
                counts = np.array(valid_counts)

        # Select the most frequent color
        dominant_idx = np.argmax(counts)
        dominant_color = centers[dominant_idx].astype(int)

        return tuple(int(x) for x in dominant_color)
    except Exception:
        # If sklearn unavailable or error, use simple median method
        median_color = np.median(pixels, axis=0).astype(int)
        return tuple(int(x) for x in median_color)


def estimate_background_color(bgr: np.ndarray, lines):
    """
    Estimates the main color tone of the background, used to exclude background during color extraction.
    """
    h, w = bgr.shape[:2]

    # Create text mask
    mask = np.ones((h, w), dtype=np.uint8) * 255
    for bbox, _, _ in lines:
        x1, y1, x2, y2 = [int(round(v)) for v in bbox]
        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h, y2))
        if x2 > x1 and y2 > y1:
            mask[y1:y2, x1:x2] = 0

    # Extract background area pixels
    bg_pixels = bgr[mask > 0]
    if bg_pixels.size == 0:
        return None

    # Convert to RGB and calculate median
    bg_rgb = cv2.cvtColor(
        bg_pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2RGB
    ).reshape(-1, 3)
    median_bg = np.median(bg_rgb, axis=0).astype(int)

    return tuple(int(x) for x in median_bg)


# ----------------------------
# PPT helpers
# ----------------------------


def px_to_emu(px: float, emu_per_px: float) -> int:
    return int(px * emu_per_px)


def analyze_line_heights(lines) -> Optional[float]:
    """
    Statistics of line height distribution, estimates "body line height"
    """
    if not lines:
        return None
    hs = [max(1, b[3] - b[1]) for (b, _, _) in lines]
    return float(np.median(hs))


def classify_line_role(bbox, img_h_px: int, body_h_px: Optional[float]) -> str:
    """
    Roughly distinguish: title / subtitle / body
    """
    x1, y1, x2, y2 = bbox
    h = max(1, y2 - y1)
    if body_h_px is None or body_h_px <= 0:
        return "body"
    ratio = h / float(body_h_px)

    # Position help: near top of page + taller lines
    y_center = (y1 + y2) / 2.0
    top_region = img_h_px * 0.3

    if ratio > 1.7 and y_center < top_region:
        return "title"
    if ratio > 1.3:
        return "subtitle"
    return "body"


def estimate_font_pt(
    bbox, img_h_px: int, body_h_px: Optional[float], slide_h_in: float = SLIDE_H_IN
):
    """
    Estimate font size proportionally based on line height (improved version: removed hard-coded multiplier constraints)
    
    Core Idea:
    1. Calculate pixel height of the line in original image
    2. Map to PPT points (pt) proportionally
    3. No longer forcibly limit title/subtitle multiplier ranges
    """
    x1, y1, x2, y2 = bbox
    h_px = max(1, y2 - y1)
    
    # Method: Convert pixel height to PPT points according to image height ratio
    # PPT height = 7.5 inches = 540pt (1 inch = 72pt)
    slide_h_pt = slide_h_in * 72.0
    
    # Proportion of line height to image height
    height_ratio = h_px / float(img_h_px)
    
    # Map to PPT points, 0.7 is an empirical coefficient (as line height is usually larger than font size)
    pt = slide_h_pt * height_ratio * 0.7
    
    # Apply global scale factor
    pt *= FONT_SCALE_FACTOR
    
    # Only apply reasonable range limits, no longer force role-based multipliers
    return Pt(max(8, min(96, pt)))


def add_background(
    slide, bgr: np.ndarray, slide_w_emu: int, slide_h_emu: int, tmp_path: str
) -> None:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    pil.save(tmp_path)
    slide.shapes.add_picture(tmp_path, 0, 0, width=slide_w_emu, height=slide_h_emu)
    os.remove(tmp_path)


def build_text_mask_from_lines(bgr: np.ndarray, lines) -> np.ndarray:
    """
    Generates initial mask from OCR line boxes (rough rectangles)
    """
    h, w = bgr.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)

    for bbox, text, conf in lines:
        x1, y1, x2, y2 = [int(round(v)) for v in bbox]
        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h, y2))
        if x2 <= x1 or y2 <= y1:
            continue
        mask[y1:y2, x1:x2] = 255

    if MASK_DILATE_ITER > 0:
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=MASK_DILATE_ITER)

    return mask


def build_adaptive_mask(bgr: np.ndarray, lines) -> np.ndarray:
    """
    Generates a finer main text mask using an adaptive method
    Combines OCR bbox and actual text shapes (internal edges + threshold)
    """
    h, w = bgr.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    for bbox, text, conf in lines:
        x1, y1, x2, y2 = [int(round(v)) for v in bbox]
        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h, y2))
        if x2 <= x1 or y2 <= y1:
            continue

        region = gray[y1:y2, x1:x2]
        if region.size == 0:
            continue

        try:
            # Check local contrast first
            if np.var(region) < 100:
                # Contrast is very low, prioritize using Canny edges to find strokes
                edges = cv2.Canny(region, 50, 150)
                kernel = np.ones((2, 2), np.uint8)
                binary = cv2.dilate(edges, kernel, iterations=1)
            else:
                # Normal contrast, use thresholding
                if region.shape[0] < 20 or region.shape[1] < 20:
                    _, binary = cv2.threshold(
                        region, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
                    )
                    binary = 255 - binary  # Invert: text becomes white
                else:
                    binary = cv2.adaptiveThreshold(
                        region,
                        255,
                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                        cv2.THRESH_BINARY_INV,
                        11,
                        2,
                    )
                kernel = np.ones((2, 2), np.uint8)
                binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

            mask[y1:y2, x1:x2] = cv2.bitwise_or(mask[y1:y2, x1:x2], binary)
        except Exception:
            mask[y1:y2, x1:x2] = 255

    if MASK_DILATE_ITER > 0:
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=MASK_DILATE_ITER)

    return mask


def is_simple_background_region(bgr: np.ndarray, mask: np.ndarray) -> bool:
    """
    Simple determination: whether the background near the mask area is approximately solid (low variance)
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Expand range slightly to get neighborhood
    dilated = cv2.dilate((mask > 0).astype(np.uint8), np.ones((5, 5), np.uint8), iterations=1)
    region = gray[dilated > 0]
    if region.size == 0:
        return False
    var = float(np.var(region))
    return var < SIMPLE_BG_VAR_THRESH


def fill_with_neighbor(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """
    For complex backgrounds, prioritize rough filling with neighborhood pixels, then hand over to inpaint for smoothing,
    avoiding strange textures generated by NS/TELEA in large areas.
    """
    result = bgr.copy()
    h, w = mask.shape
    for y in range(h):
        xs = np.where(mask[y] > 0)[0]
        if len(xs) == 0:
            continue
        x_min, x_max = xs[0], xs[-1]
        left_src = max(0, x_min - 3)
        right_src = min(w - 1, x_max + 3)
        fill_color = (
            (bgr[y, left_src].astype(np.int32) + bgr[y, right_src].astype(np.int32))
            // 2
        ).astype(np.uint8)
        result[y, x_min : x_max + 1] = fill_color
    return result


def make_clean_background(bgr: np.ndarray, lines) -> np.ndarray:
    """
    Generates a "clean background version" using improved inpaint:
    - Adaptive main text mask
    - Expanded shadow/glow area mask used only for inpaint
    - Direct inpaint for simple backgrounds, neighborhood fill then small-radius inpaint for complex backgrounds
    """
    if not lines:
        return bgr

    # Use adaptive or simple mask (main text area)
    if USE_ADAPTIVE_MASK:
        main_mask = build_adaptive_mask(bgr, lines)
    else:
        main_mask = build_text_mask_from_lines(bgr, lines)

    # Expand shadow/glow area, use this large mask during inpaint
    shadow_mask = cv2.dilate(main_mask, np.ones((7, 7), np.uint8), iterations=2)

    is_simple = is_simple_background_region(bgr, shadow_mask)

    if is_simple:
        # Simple background: direct inpaint + slight blur
        clean = cv2.inpaint(bgr, shadow_mask, INPAINT_RADIUS, cv2.INPAINT_TELEA)
    else:
        # Complex background: rough fill with neighborhood pixels, then fine-tune with small-radius NS
        prefilled = fill_with_neighbor(bgr, shadow_mask)
        clean = cv2.inpaint(
            prefilled, shadow_mask, max(3, INPAINT_RADIUS // 2), cv2.INPAINT_NS
        )

    clean = cv2.GaussianBlur(clean, (3, 3), 0.5)

    # Apply inpaint result only to shadow_mask area
    result = bgr.copy()
    mask_3ch = cv2.cvtColor(shadow_mask, cv2.COLOR_GRAY2BGR) / 255.0
    result = (clean * mask_3ch + bgr * (1 - mask_3ch)).astype(np.uint8)

    return result


def ocr_images_to_ppt(
    image_paths: Sequence[str],
    output_pptx: str,
    add_background_image: bool = ADD_BACKGROUND_IMAGE,
    clean_background: bool = CLEAN_BACKGROUND,
    use_text_color: bool = EXTRACT_TEXT_COLOR,
) -> str:
    """
    Converts images to PPT with editable text via OCR (Optimized version)

    Note: This function is an internal implementation; recommended to call indirectly via
    images_to_pdf_and_ppt / convert_images_dir_to_pdf_and_ppt.
    """
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W_IN)
    prs.slide_height = Inches(SLIDE_H_IN)

    slide_w_emu = prs.slide_width
    slide_h_emu = prs.slide_height

    for idx, img_path in enumerate(image_paths, start=1):
        log.info(f"Processing slide #{idx}: {os.path.basename(img_path)}")

        bgr = read_bgr(img_path)

        # Preprocessing: upscale and sharpen
        ocr_img, scale = preprocess_for_ocr(bgr)

        if idx <= DEBUG_DUMP_FIRST_N:
            debug_dump(bgr, f"before_ocr_raw_{idx}")
            debug_dump(ocr_img, f"before_ocr_up_{idx}")
            log.info(f"slide#{idx} upscale scale={scale:.3f}")

        h0, w0 = bgr.shape[:2]  # Original size
        h1, w1 = ocr_img.shape[:2]  # OCR input size

        # Create slide
        slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank layout

        # OCR recognition (PaddleOCR handles BGR images directly)
        lines = paddle_ocr(ocr_img)

        # Scale bbox from OCR image coordinates back to original image coordinates
        if lines and (w1 != w0 or h1 != h0):
            sx = w0 / float(w1)
            sy = h0 / float(h1)
            lines = [
                ([b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy], t, c)
                for (b, t, c) in lines
            ]

        # Merge lines again
        y_tol = max(12, int(h0 * 0.008))
        x_gap = max(18, int(w0 * 0.01))
        lines = merge_lines(lines, y_tol=y_tol, x_gap=x_gap)

        # Statistics of body line height for subsequent font size estimation
        body_h_px = analyze_line_heights(lines)

        if not lines:
            log.warning(f"slide#{idx} no text detected")
        else:
            log.info(f"slide#{idx} detected {len(lines)} text boxes")

        # Estimate background color (for color extraction)
        bg_color = None
        if use_text_color and lines:
            bg_color = estimate_background_color(bgr, lines)
            if bg_color:
                log.info(f"slide#{idx} estimated background color: RGB{bg_color}")

        # Background processing: optional inpaint to generate "clean background"
        bg_for_slide = bgr
        if add_background_image:
            if clean_background and lines:
                log.info(f"slide#{idx} applying inpainting...")
                bg_for_slide = make_clean_background(bgr, lines)
                if idx <= DEBUG_DUMP_FIRST_N:
                    debug_dump(bg_for_slide, f"clean_bg_{idx}")
            tmp = f"__ppt_bg_{idx}.png"
            add_background(slide, bg_for_slide, slide_w_emu, slide_h_emu, tmp)

        scale_x = slide_w_emu / w0
        scale_y = slide_h_emu / h0

        for bbox, text, conf in lines:
            x1, y1, x2, y2 = bbox
            if (x2 - x1) < 6 or (y2 - y1) < 6:
                continue

            # 计算字号
            font_size = estimate_font_pt(bbox, img_h_px=h0, body_h_px=body_h_px)

            # 文本框尺寸：直接使用OCR检测到的bbox尺寸
            bbox_width_emu = px_to_emu((x2 - x1), scale_x)
            bbox_height_emu = px_to_emu((y2 - y1), scale_y)

            width = bbox_width_emu
            height = bbox_height_emu

            left = px_to_emu(x1, scale_x)
            top = px_to_emu(y1, scale_y)

            # Add transparent textbox
            tb = slide.shapes.add_textbox(left, top, int(width), int(height))
            tf = tb.text_frame
            tf.clear()
            tf.word_wrap = False  # Disable auto-wrap

            # Vertical center (optional)
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE

            # Set textbox transparency
            tb.fill.background()  # No fill
            tb.line.fill.background()  # No border

            p = tf.paragraphs[0]
            p.text = text

            # Use native distributed alignment: distributed for multi-character, centered for single
            if len(text) > 1:
                p.alignment = PP_ALIGN.DISTRIBUTE
            else:
                p.alignment = PP_ALIGN.CENTER

            # No longer rely on font.spacing for distribution, uniformly set to 0
            p.font.size = font_size
            p.font.spacing = Pt(0)

            # Extract and set text color
            if use_text_color:
                text_color = extract_text_color(bgr, bbox, bg_color)
                p.font.color.rgb = RGBColor(*text_color)
            else:
                # Default black
                p.font.color.rgb = RGBColor(0, 0, 0)

    prs.save(output_pptx)
    return output_pptx


# ----------------------------
# Public API
# ----------------------------


def images_to_pdf_and_ppt(
    image_paths: Sequence[str],
    output_pdf_path: Optional[str] = None,
    output_pptx_path: Optional[str] = None,
    add_background_image: bool = ADD_BACKGROUND_IMAGE,
    clean_background: bool = CLEAN_BACKGROUND,
    extract_text_color: bool = EXTRACT_TEXT_COLOR,
) -> Dict[str, Optional[str]]:
    """
    Converts a given sequence of images to PDF and editable PPTX.

    Parameters:
        image_paths: List of image paths in page order.
        output_pdf_path: Output PDF file path; no PDF generated if None.
        output_pptx_path: Output PPTX file path; no PPT generated if None.
        add_background_image: Whether to add full-page background images to PPT.
        clean_background: Whether to perform inpaint on background (effective when add_background_image is True).
        extract_text_color: Whether to estimate text color based on the original image for PPT text coloring.

    Returns:
        Dictionary containing generated file paths, e.g.:
        {
            "pdf": "/path/to/output.pdf" or None,
            "pptx": "/path/to/output_editable.pptx" or None,
        }
    """
    result: Dict[str, Optional[str]] = {"pdf": None, "pptx": None}

    if output_pdf_path is not None:
        result["pdf"] = images_to_pdf(image_paths, output_pdf_path)

    if output_pptx_path is not None:
        result["pptx"] = ocr_images_to_ppt(
            image_paths=image_paths,
            output_pptx=output_pptx_path,
            add_background_image=add_background_image,
            clean_background=clean_background,
            use_text_color=extract_text_color,
        )

    return result


def convert_images_dir_to_pdf_and_ppt(
    input_dir: str,
    output_pdf_path: Optional[str] = None,
    output_pptx_path: Optional[str] = None,
    add_background_image: bool = ADD_BACKGROUND_IMAGE,
    clean_background: bool = CLEAN_BACKGROUND,
    extract_text_color: bool = EXTRACT_TEXT_COLOR,
) -> Dict[str, Optional[str]]:
    """
    Automatically reads all images from a directory and generates PDF + PPTX.

    Parameters:
        input_dir: Directory containing images, naturally sorted by filename internally.
        Other parameters same as images_to_pdf_and_ppt.

    Returns:
        Same as images_to_pdf_and_ppt.
    """
    image_paths = list_images_in_dir(input_dir)
    if not image_paths:
        raise ValueError(f"No images found in {input_dir!r}")

    return images_to_pdf_and_ppt(
        image_paths=image_paths,
        output_pdf_path=output_pdf_path,
        output_pptx_path=output_pptx_path,
        add_background_image=add_background_image,
        clean_background=clean_background,
        extract_text_color=extract_text_color,
    )


async def convert_images_dir_to_pdf_and_ppt_api(
    input_dir: str,
    output_pdf_path: Optional[str] = None,
    output_pptx_path: Optional[str] = None,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    use_api_inpaint: bool = True,
    add_background_image: bool = ADD_BACKGROUND_IMAGE,
    clean_background: bool = CLEAN_BACKGROUND,
    use_text_color: bool = EXTRACT_TEXT_COLOR,
) -> Dict[str, Optional[str]]:
    """
    Image to PDF/PPTX conversion with API inpainting support (async version)
    
    Difference from convert_images_dir_to_pdf_and_ppt:
    - Supports using image editing API for inpainting (priority)
    - Automatically falls back to traditional OpenCV inpaint when API fails
    - Supports retry mechanism (up to 3 times)
    
    Parameters:
        input_dir: Directory containing images, naturally sorted by filename internally
        output_pdf_path: Output PDF file path; no PDF generated if None
        output_pptx_path: Output PPTX file path; no PPT generated if None
        api_url: URL for image editing API
        api_key: API Key
        model: Model name to use
        use_api_inpaint: Whether to enable API inpainting (default True)
        add_background_image: Whether to add full-page background images to PPT
        clean_background: Whether to perform inpaint on background
        extract_text_color: Whether to estimate text color based on original image
    
    Returns:
        Dictionary containing generated file paths
    """
    import asyncio
    from workflow_engine.toolkits.multimodaltool.req_img import generate_or_edit_and_save_image_async

    image_paths = list_images_in_dir(input_dir)

    # Filter out versioned history files (e.g., page_000_v001.png), keep only the current version (page_000.png)
    # Versioned filename pattern: page_XXX_vYYY.png
    version_pattern = re.compile(r'_v\d+\.(png|jpg|jpeg|bmp|tif|tiff)$', re.IGNORECASE)
    image_paths = [p for p in image_paths if not version_pattern.search(os.path.basename(p))]

    if not image_paths:
        raise ValueError(f"No images found in {input_dir!r}")

    result: Dict[str, Optional[str]] = {"pdf": None, "pptx": None}
    
    # Generate PDF
    if output_pdf_path is not None:
        result["pdf"] = images_to_pdf(image_paths, output_pdf_path)
    
    # Generate PPTX (with API inpainting support)
    if output_pptx_path is not None:
        prs = Presentation()
        prs.slide_width = Inches(SLIDE_W_IN)
        prs.slide_height = Inches(SLIDE_H_IN)
        
        slide_w_emu = prs.slide_width
        slide_h_emu = prs.slide_height
        
        for idx, img_path in enumerate(image_paths, start=1):
            log.info(f"Processing slide #{idx}: {os.path.basename(img_path)}")
            
            bgr = read_bgr(img_path)
            ocr_img, scale = preprocess_for_ocr(bgr)
            
            h0, w0 = bgr.shape[:2]
            h1, w1 = ocr_img.shape[:2]
            
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            
            # OCR Recognition
            lines = paddle_ocr(ocr_img)
            
            # Coordinate mapping
            if lines and (w1 != w0 or h1 != h0):
                sx = w0 / float(w1)
                sy = h0 / float(h1)
                lines = [
                    ([b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy], t, c)
                    for (b, t, c) in lines
                ]
            
            # Merge lines
            y_tol = max(12, int(h0 * 0.008))
            x_gap = max(18, int(w0 * 0.01))
            lines = merge_lines(lines, y_tol=y_tol, x_gap=x_gap)
            
            body_h_px = analyze_line_heights(lines)
            bg_color = estimate_background_color(bgr, lines) if use_text_color and lines else None
            
            # Background processing: prioritise using API inpainting
            bg_for_slide = bgr
            if add_background_image:
                if clean_background and lines and use_api_inpaint and api_url and api_key and model:
                    # Use API inpainting (with retry)
                    async def _call_inpaint_api_with_retry(retries: int = 3, delay: float = 1.0) -> bool:
                        last_err: Optional[Exception] = None
                        for attempt in range(1, retries + 1):
                            try:
                                await generate_or_edit_and_save_image_async(
                                    prompt=inpaint_prompt,
                                    save_path=clean_bg_path,
                                    aspect_ratio="16:9",
                                    api_url=api_url,
                                    api_key=api_key,
                                    model=model,
                                    image_path=temp_img_path,
                                    use_edit=True,
                                )
                                return True
                            except Exception as e:
                                last_err = e
                                log.error(f"[convert_images_dir_to_pdf_and_ppt_api] slide#{idx} inpainting attempt {attempt}/{retries} failed: {e}")
                                if attempt < retries:
                                    try:
                                        await asyncio.sleep(delay)
                                    except Exception:
                                        pass
                        log.error(f"[convert_images_dir_to_pdf_and_ppt_api] slide#{idx} inpainting failed after {retries} attempts: {last_err}")
                        return False
                    
                    try:
                        # Generate text mask
                        text_mask = build_adaptive_mask(bgr, lines)
                        
                        # Save temporary files
                        import tempfile
                        with tempfile.TemporaryDirectory() as tmpdir:
                            temp_img_path = os.path.join(tmpdir, f"temp_{idx}.png")
                            clean_bg_path = os.path.join(tmpdir, f"clean_{idx}.png")
                            cv2.imwrite(temp_img_path, bgr)
                            
                            # Construct inpainting prompt
                            inpaint_prompt = "Please intelligently repair the area after text is removed from the image, maintaining continuity, consistency, and natural transition of the background, so that the repaired image looks complete, and you should try to preserve the icons involved in the original image as much as possible;"
                            
                            log.info(f"[convert_images_dir_to_pdf_and_ppt_api] slide#{idx} Starting to call image editing API for inpainting (max 3 retries)...")
                            
                            api_success = await _call_inpaint_api_with_retry(retries=3, delay=1.0)
                            
                            if api_success and os.path.exists(clean_bg_path):
                                bg_for_slide = read_bgr(clean_bg_path)
                                log.info(f"[convert_images_dir_to_pdf_and_ppt_api] slide#{idx} API inpainting successful")
                            else:
                                log.warning(f"[convert_images_dir_to_pdf_and_ppt_api] slide#{idx} API inpainting failed, using local inpaint")
                                bg_for_slide = make_clean_background(bgr, lines)
                    except Exception as e:
                        log.error(f"[convert_images_dir_to_pdf_and_ppt_api] slide#{idx} inpainting process failed: {e}, using local inpaint")
                        try:
                            bg_for_slide = make_clean_background(bgr, lines)
                        except Exception as e2:
                            log.error(f"[convert_images_dir_to_pdf_and_ppt_api] slide#{idx} local inpaint also failed: {e2}, using original image")
                            bg_for_slide = bgr
                elif clean_background and lines:
                    # Not using API, use local inpaint directly
                    log.info(f"slide#{idx} applying local inpainting...")
                    bg_for_slide = make_clean_background(bgr, lines)
                
                tmp = f"__ppt_bg_{idx}.png"
                add_background(slide, bg_for_slide, slide_w_emu, slide_h_emu, tmp)
            
            # Add textboxes (same logic as main function)
            scale_x = slide_w_emu / w0
            scale_y = slide_h_emu / h0
            
            for bbox, text, conf in lines:
                x1, y1, x2, y2 = bbox
                if (x2 - x1) < 6 or (y2 - y1) < 6:
                    continue

                font_size = estimate_font_pt(bbox, img_h_px=h0, body_h_px=body_h_px)

                bbox_width_emu = px_to_emu((x2 - x1), scale_x)
                bbox_height_emu = px_to_emu((y2 - y1), scale_y)
                width = bbox_width_emu
                height = bbox_height_emu
                left = px_to_emu(x1, scale_x)
                top = px_to_emu(y1, scale_y)

                tb = slide.shapes.add_textbox(left, top, int(width), int(height))
                tf = tb.text_frame
                tf.clear()
                tf.word_wrap = False
                tb.fill.background()
                tb.line.fill.background()

                # Vertical center (optional)
                tf.vertical_anchor = MSO_ANCHOR.MIDDLE

                p = tf.paragraphs[0]
                p.text = text

                # Use native distributed alignment
                if len(text) > 1:
                    p.alignment = PP_ALIGN.DISTRIBUTE
                else:
                    p.alignment = PP_ALIGN.CENTER

                p.font.size = font_size
                p.font.spacing = Pt(0)

                if use_text_color:
                    text_color = extract_text_color(bgr, bbox, bg_color)
                    p.font.color.rgb = RGBColor(*text_color)
                else:
                    p.font.color.rgb = RGBColor(0, 0, 0)
        
        prs.save(output_pptx_path)
        result["pptx"] = output_pptx_path
    
    return result


if __name__ == "__main__":
    """
    Simple local test entry:
    - Run this file directly to test PaddleOCR recognition on specified images
    - Recognition results will be printed to terminal, and images with bounding boxes will be saved to specified path
    """
    # Test image path (also visualization output path)
    img_path = f"{get_project_root()}/tests/fig_1767604887.png"

    if not os.path.exists(img_path):
        raise FileNotFoundError(f"Test image does not exist: {img_path}")

    # Call encapsulated single-page interface
    info = paddle_ocr_page_with_layout(img_path)

    print("=== PaddleOCR Test Results ===")
    print(f"image_size: {info['image_size']}")
    print(f"body_h_px: {info['body_h_px']}")
    print(f"bg_color: {info['bg_color']}")
    print(f"Number of text boxes detected: {len(info['lines'])}")

    for i, (bbox, text, conf) in enumerate(info["lines"], start=1):
        print(f"[{i:02d}] conf={conf:.1f} bbox={bbox} text={text}")

    # Draw bounding boxes on the image and save to file instead of popping up a window
    try:
        bgr = read_bgr(img_path)
        vis = bgr.copy()
        for bbox, text, conf in info["lines"]:
            x1, y1, x2, y2 = map(int, bbox)
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)

        save_path = f"{get_project_root()}/tests/test_01_paddle_frame.png"
        ok = cv2.imwrite(save_path, vis)
        if ok:
            log.info(f"PaddleOCR visualization result saved to: {save_path}")
        else:
            log.warning(f"Failed to save PaddleOCR visualization result: {save_path}")
    except Exception as e:
        log.warning(f"Visualization failed: {e}")
        # Does not affect plain text printing results
