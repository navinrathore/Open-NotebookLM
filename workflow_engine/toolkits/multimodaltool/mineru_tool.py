# Before Using, do these:

# hf download opendatalab/MinerU2.5-2509-1.2B --local-dir opendatalab/MinerU2.5-2509-1.2B

# With vllm>=0.10.1, you can use following command to serve the model. The logits processor is used to support no_repeat_ngram_size sampling param, which can help the model to avoid generating repeated content.

# vllm serve opendatalab/MinerU2.5-2509-1.2B --host 127.0.0.1 --port <port> \
#   --logits-processors mineru_vl_utils:MinerULogitsProcessor
# If you are using vllm<0.10.1, no_repeat_ngram_size sampling param is not supported. You still can serve the model without logits processor:

# vllm serve models/MinerU2.5-2509-1.2B \
#     --host 127.0.0.1 \
#     --port 8010 \
#     --logits-processors mineru_vl_utils:MinerULogitsProcessor \
#     --gpu-memory-utilization 0.4

# vllm serve opendatalab/MinerU2.5-2509-1.2B --host 127.0.0.1 --port <port>


from pathlib import Path
from typing import Any, Dict, List, Sequence, Union, Optional
import os
import shutil
import subprocess
import re
import random
from PIL import Image
from mineru_vl_utils import MinerUClient


# ---------------------------------------
# 1. two_step_extract (sync)
# ---------------------------------------
def run_two_step_extract(image_path: str, port: int):
    """Synchronously calls MinerU two_step_extract, processes a single image and returns structured results."""
    image = Image.open(image_path)
    client = MinerUClient(
        backend="http-client",
        server_url=f"http://127.0.0.1:{port}"
    )
    return client.two_step_extract(image)


# ---------------------------------------
# 2. batch_two_step_extract (sync)
# ---------------------------------------
def run_batch_two_step_extract(image_paths: list[str], port: int):
    """Synchronously batch calls MinerU two_step_extract, processes multiple images and returns a list of results."""
    images = [Image.open(p) for p in image_paths]
    client = MinerUClient(
        backend="http-client",
        server_url=f"http://127.0.0.1:{port}"
    )
    return client.batch_two_step_extract(images)


# ---------------------------------------
# 3. aio_two_step_extract (async)
# ---------------------------------------
async def run_aio_two_step_extract(image_path: str, port: int):
    """Asynchronously calls MinerU two_step_extract, processes a single image and returns structured results."""
    image = Image.open(image_path)
    client = MinerUClient(
        backend="http-client",
        server_url=f"http://127.0.0.1:{port}"
    )
    return await client.aio_two_step_extract(image)


# ---------------------------------------
# 4. aio_batch_two_step_extract (async)
# ---------------------------------------
async def run_aio_batch_two_step_extract(image_paths: list[str], port: int):
    """Asynchronously batch calls MinerU two_step_extract, processes multiple images and returns a list of results."""
    images = [Image.open(p) for p in image_paths]
    client = MinerUClient(
        backend="http-client",
        server_url=f"http://127.0.0.1:{port}"
    )
    return await client.aio_batch_two_step_extract(images)


# ---------------------------------------
# 5. Crop original image based on MinerU bbox & type
# ---------------------------------------
def crop_mineru_blocks_by_type(
    image_path: str,
    blocks: List[Dict[str, Any]],
    target_type: Optional[Union[str, Sequence[str]]] = None,
    output_dir: str = "",
    prefix: str = "",
) -> List[str]:
    """
    Crops sub-images from the full image according to the bbox of specified type(s)
    based on structured results from MinerU two_step_extract / aio_two_step_extract
    and saves them to the output directory.

    Arguments:
        image_path: Original image path (e.g., technical roadmap PNG)
        blocks: list[dict] results returned by MinerU
        target_type: Type of blocks to crop, e.g., "title" / "text" / "image" / "footer"
        output_dir: Output directory path; will be created automatically if it doesn't exist
        prefix: Optional prefix for output filenames

    Returns:
        A list of absolute paths for all successfully saved cropped images
    """
    img = Image.open(image_path)
    width, height = img.size

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: List[str] = []

    # target_type is None means no filtering, return all blocks
    if target_type is None:
        target_types = None
    elif isinstance(target_type, str):
        target_types = {target_type}
    else:
        target_types = set(target_type)

    for idx, block in enumerate(blocks):
        block_type = block.get("type")
        # Only filter when target_type is explicitly specified
        if target_types is not None and block_type not in target_types:
            continue

        bbox = block.get("bbox")
        if not bbox or len(bbox) != 4:
            continue

        x1_norm, y1_norm, x2_norm, y2_norm = bbox

        # Convert normalized coordinates [0,1] to pixel coordinates and perform boundary clipping
        left = max(0, min(width, int(round(x1_norm * width))))
        top = max(0, min(height, int(round(y1_norm * height))))
        right = max(0, min(width, int(round(x2_norm * width))))
        bottom = max(0, min(height, int(round(y2_norm * height))))

        # Skip invalid bbox
        if right <= left or bottom <= top:
            continue

        cropped = img.crop((left, top, right, bottom))

        # Use actual block_type for naming to help distinguish between types
        safe_block_type = block_type or "unknown"
        filename = f"{prefix}{safe_block_type}_{idx}.png"
        out_path = out_dir / filename
        cropped.save(out_path)

        saved_paths.append(str(out_path.resolve()))

    return saved_paths

def run_mineru_pdf_extract(
    pdf_path: str,
    output_dir: str = "",
    source: str = "modelscope",
    mineru_executable: Optional[str] = None,
    backend: Optional[str] = None,
):
    """
    Extract structured content from PDF using MinerU command line.

    Arguments:
        pdf_path: PDF file path
        output_dir: Output directory path; will be created automatically if it doesn't exist
        source: Source for downloading models, e.g., modelscope, huggingface
        mineru_executable: Path to mineru executable,
            - If not provided: Priority is given to MINERU_CMD environment variable,
              otherwise it searches for 'mineru' in PATH
            - If absolute path is provided: Uses that path directly
        backend: Parsing backend. If "pipeline" is passed, it uses the pipeline backend (does not rely on vLLM,
            avoiding incompatibilities with newer vLLM versions like ParallelConfig.world_size);
            if not passed, it uses MinerU default (usually hybrid-auto-engine, which relies on vLLM).
            Can also be specified via MINERU_BACKEND environment variable (e.g., MINERU_BACKEND=pipeline).

    Returns:
        All extracted images and markdown content
    """
    # 1. Resolve mineru executable path
    if mineru_executable is None:
        mineru_executable = (
            os.environ.get("MINERU_CMD")  # Env var priority
            or shutil.which("mineru")     # Command in current env
        )
        if mineru_executable is None:
            raise RuntimeError(
                "mineru executable not found, please ensure:\n"
                "1) MinerU is installed in the current environment and `mineru` is in PATH; or\n"
                "2) MINERU_CMD environment variable is set to the mineru executable path; or\n"
                "3) Explicitly pass mineru_executable argument when calling run_mineru_pdf_extract."
            )

    backend = backend or os.environ.get("MINERU_BACKEND", "").strip() or None

    mineru_cmd = [
        str(mineru_executable),
        "-p",
        str(pdf_path),
        "-o",
        str(output_dir),
        "--source",
        source,
    ]
    if backend:
        mineru_cmd.extend(["--backend", backend])

    # 2. Optional: Auto-create output_dir
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 3. Simple Load Balancing for GPU
    #    Read list of available devices from MINERU_DEVICES environment variable (default "5,6")
    #    Randomly select a device ID to assign to the current child process
    available_devices_str = os.environ.get("MINERU_DEVICES", "4,5,6")
    # Clean and split string, removing whitespace
    available_devices = [d.strip() for d in available_devices_str.split(",") if d.strip()]
    
    env = os.environ.copy()
    if available_devices:
        selected_device = random.choice(available_devices)
        env["CUDA_VISIBLE_DEVICES"] = selected_device
        print(f"[MinerU] Assigned GPU: {selected_device} (from pool: {available_devices})")
    else:
        print("[MinerU] No GPU devices configured in MINERU_DEVICES, using system default.")

    # 4. Execute command
    subprocess.run(
        mineru_cmd,
        shell=False,
        check=True,
        text=True,
        stderr=None,
        stdout=None,
        env=env,
    )



def crop_mineru_blocks_with_meta(
    image_path: str,
    blocks: List[Dict[str, Any]],
    target_type: Optional[Union[str, Sequence[str]]] = None,
    output_dir: str = "",
    prefix: str = "",
) -> List[Dict[str, Any]]:
    """
    Similar to ``crop_mineru_blocks_by_type``, but returns a list containing metadata,
    facilitating the restoration of layouts in PPT proportionally according to MinerU's bbox.

    Each element returned contains:
        - block_index: Index in the original blocks list
        - type: MinerU block type
        - bbox: Original normalized bbox [x1, y1, x2, y2]
        - png_path: Absolute path of the cropped small PNG image
    """
    img = Image.open(image_path)
    width, height = img.size

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []

    # No filtering when target_type is None, return all blocks
    if target_type is None:
        target_types = None
    elif isinstance(target_type, str):
        target_types = {target_type}
    else:
        target_types = set(target_type)

    for idx, block in enumerate(blocks):
        block_type = block.get("type")
        # Only filter when target_type is explicitly specified
        if target_types is not None and block_type not in target_types:
            continue

        bbox = block.get("bbox")
        if not bbox or len(bbox) != 4:
            continue

        x1_norm, y1_norm, x2_norm, y2_norm = bbox

        # Convert normalized coordinates [0,1] to pixel coordinates and perform boundary clipping
        left = max(0, min(width, int(round(x1_norm * width))))
        top = max(0, min(height, int(round(y1_norm * height))))
        right = max(0, min(width, int(round(x2_norm * width))))
        bottom = max(0, min(height, int(round(y2_norm * height))))

        if right <= left or bottom <= top:
            continue

        cropped = img.crop((left, top, right, bottom))

        safe_block_type = block_type or "unknown"
        filename = f"{prefix}{safe_block_type}_{idx}.png"
        out_path = out_dir / filename
        cropped.save(out_path)

        results.append(
            {
                "block_index": idx,
                "type": block_type,
                "bbox": bbox,
                "png_path": str(out_path.resolve()),
            }
        )

    return results


def svg_to_emf(svg_path: str, emf_path: str, dpi: int = 600) -> str:
    """
    Converts SVG file into EMF vector image using Inkscape, returns generated EMF path.

    Dependencies
    ----
    - System must have Inkscape installed, and `inkscape` must be directly callable in PATH.

    Parameters
    ----
    svg_path:
        Input SVG file path.
    emf_path:
        Output EMF file path.

    Returns
    -------
    str
        Absolute path of generated EMF file.

    Exceptions
    -------
    FileNotFoundError
        When input SVG file does not exist.
    RuntimeError
        When Inkscape call fails or output file is not generated.
    """
    svg_p = Path(svg_path)
    if not svg_p.exists():
        raise FileNotFoundError(f"Input SVG does not exist: {svg_p}")

    emf_p = Path(emf_path)
    emf_p.parent.mkdir(parents=True, exist_ok=True)

    try:
        # inkscape input.svg --export-filename=output.emf
        result = subprocess.run(
            [
                "inkscape",
                str(svg_p),
                "--export-filename",
                str(emf_p),
                "--export-text-to-path",
                f"--export-dpi={dpi}"
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "Calling Inkscape failed: `inkscape` executable might not be installed in the system, "
            "please install Inkscape first and ensure it is in the PATH."
        ) from e

    if result.returncode != 0:
        raise RuntimeError(
            f"Inkscape conversion failed, return code {result.returncode}:\n"
            f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        )

    if not emf_p.exists():
        raise RuntimeError(f"Output EMF file not found after Inkscape run: {emf_p}")

    return str(emf_p.resolve())


# ---------------------------------------
# 6. Recursive MinerU block splitting + Coordinate mapping (HTTP Version)
# ---------------------------------------
def _crop_image_by_norm_bbox(
    image_path: str,
    bbox: Sequence[float],
    output_dir: Union[str, Path],
    prefix: str = "",
    index: int = 0,
) -> str:
    """
    Crops a sub-image from image_path according to normalized bbox [x1, y1, x2, y2]
    and saves it, returning the absolute path.
    """
    img = Image.open(image_path)
    width, height = img.size

    x1_norm, y1_norm, x2_norm, y2_norm = bbox
    left = max(0, min(width, int(round(x1_norm * width))))
    top = max(0, min(height, int(round(y1_norm * height))))
    right = max(0, min(width, int(round(x2_norm * width))))
    bottom = max(0, min(height, int(round(y2_norm * height))))

    if right <= left or bottom <= top:
        raise ValueError(f"Invalid bbox after clamp: {bbox}")

    cropped = img.crop((left, top, right, bottom))

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = Path(image_path).stem
    filename = f"{prefix}{stem}_{index}.png"
    out_path = out_dir / filename
    cropped.save(out_path)

    return str(out_path.resolve())


async def recursive_mineru_layout(
    image_path: str,
    port: int,
    max_depth: int = 2,
    current_depth: int = 0,
    output_dir: Optional[Union[str, Path]] = None,
    block_types_for_subimage: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Recursively split image using MinerU HTTP two_step_extract and map all bottom-level
    blocks to normalized coordinate system of the top-level image.

    Each element returned is like:
        {
            "type": str,
            "bbox": [x1, y1, x2, y2],   # Normalized coordinates relative to the top-level image
            "png_path": str | None,     # Path to corresponding sub-image (image/table etc.)
            "text": str | None,         # Text content (if any)
            "depth": int,               # Recursion depth
        }
    """
    if current_depth > max_depth:
        return []

    # Default to create a mineru_recursive subdirectory under the original image directory
    if output_dir is None:
        base = Path(image_path).with_suffix("")
        output_dir = base.parent / f"{base.stem}_mineru_recursive"
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Default block types to continue splitting into sub-images
    if block_types_for_subimage is None:
        block_types_for_subimage = ["image", "img", "table", "figure"]

    # 1. Current layer MinerU call
    blocks = await run_aio_two_step_extract(image_path=image_path, port=port)

    leaf_items: List[Dict[str, Any]] = []

    # Assume blocks structure as List[Dict], containing type / bbox / text etc.
    for idx, blk in enumerate(blocks):
        blk_type = blk.get("type")
        bbox = blk.get("bbox")
        if not bbox or len(bbox) != 4:
            continue

        # Ensure normalized bbox is within [0,1], rough cropping
        x1, y1, x2, y2 = bbox
        x1 = max(0.0, min(1.0, float(x1)))
        y1 = max(0.0, min(1.0, float(y1)))
        x2 = max(0.0, min(1.0, float(x2)))
        y2 = max(0.0, min(1.0, float(y2)))
        if x2 <= x1 or y2 <= y1:
            continue
        norm_bbox = [x1, y1, x2, y2]

        # If it's a block type that needs further splitting, crop sub-image and recurse
        if blk_type in block_types_for_subimage and current_depth < max_depth:
            try:
                sub_img_path = _crop_image_by_norm_bbox(
                    image_path=image_path,
                    bbox=norm_bbox,
                    output_dir=out_dir / "sub_images",
                    prefix=f"depth{current_depth}_blk{idx}_",
                    index=idx,
                )
            except Exception:
                # Handle as leaf block if cropping fails
                leaf_items.append(
                    {
                        "type": blk_type,
                        "bbox": norm_bbox,
                        "png_path": None,
                        "text": blk.get("text") or blk.get("content"),
                        "depth": current_depth,
                    }
                )
                continue

            # Sub-image internal coordinate system is full [0,1], need to map back to current image norm_bbox
            sub_items = await recursive_mineru_layout(
                image_path=sub_img_path,
                port=port,
                max_depth=max_depth,
                current_depth=current_depth + 1,
                output_dir=out_dir,
                block_types_for_subimage=block_types_for_subimage,
            )

            pw = norm_bbox[2] - norm_bbox[0]
            ph = norm_bbox[3] - norm_bbox[1]
            for si in sub_items:
                sb = si.get("bbox")
                if not sb or len(sb) != 4:
                    continue
                sx1, sy1, sx2, sy2 = sb
                nx1 = norm_bbox[0] + sx1 * pw
                ny1 = norm_bbox[1] + sy1 * ph
                nx2 = norm_bbox[0] + sx2 * pw
                ny2 = norm_bbox[1] + sy2 * ph
                si["bbox"] = [nx1, ny1, nx2, ny2]
                leaf_items.append(si)
        else:
            # Type that no longer drills down, treat directly as leaf
            leaf_items.append(
                {
                    "type": blk_type,
                    "bbox": norm_bbox,
                    "png_path": None,
                    "text": blk.get("text") or blk.get("content"),
                    "depth": current_depth,
                }
            )

    return leaf_items


def _shrink_markdown(md: str, max_h1: int = 6, max_chars: int = 10_000) -> str:
    """
    Shrink a long markdown string before passing to downstream LLM agents.

    Default strategy:
    - pick content under the first `max_h1` level-1 headings (lines starting with '# ')
    - if picked content shorter than `max_chars`, append remaining original content
      (in original order) until reaching `max_chars`
    - fallback to pure char truncation if no H1 found

    Notes:
    - This is a best-effort heuristic (no heavy markdown parser required).
    """
    if not md:
        return ""

    if max_chars is not None and max_chars > 0 and len(md) <= max_chars:
        return md

    # find H1 headings (allow leading spaces; require '# ' style)
    h1_re = re.compile(r"^\s*#\s+.+$")
    lines = md.splitlines(keepends=True)
    h1_indices = [i for i, line in enumerate(lines) if h1_re.match(line)]

    # no H1 -> fallback to char truncation
    if not h1_indices:
        if max_chars and max_chars > 0:
            return md[:max_chars]
        return md

    # build sections for first max_h1 headings
    picked_parts: List[str] = []
    for j, start_i in enumerate(h1_indices[:max_h1]):
        end_i = h1_indices[j + 1] if (j + 1) < len(h1_indices) else len(lines)
        picked_parts.append("".join(lines[start_i:end_i]))

    picked = "".join(picked_parts)

    # If picked already too long, truncate
    if max_chars and max_chars > 0 and len(picked) >= max_chars:
        return picked[:max_chars]

    # Otherwise, append original content (skipping already picked substrings by simple rule:
    # we only append from the beginning of the doc, but avoid duplicating the picked segments
    # by appending only those parts not present in picked when scanning in order).
    #
    # Practical approach: take the full md, then append characters from full md that are
    # not already in picked by position; easiest is to append from original start,
    # but that may duplicate. Instead, we fill from the original md excluding
    # the picked H1 blocks.
    keep = picked
    if not (max_chars and max_chars > 0):
        return keep

    # mark picked line ranges to exclude when appending
    exclude = [False] * len(lines)
    for j, start_i in enumerate(h1_indices[:max_h1]):
        end_i = h1_indices[j + 1] if (j + 1) < len(h1_indices) else len(lines)
        for i in range(start_i, end_i):
            exclude[i] = True

    # append non-excluded lines in original order until max_chars
    for i, line in enumerate(lines):
        if exclude[i]:
            continue
        if len(keep) >= max_chars:
            break
        remain = max_chars - len(keep)
        keep += line[:remain]

    return keep
