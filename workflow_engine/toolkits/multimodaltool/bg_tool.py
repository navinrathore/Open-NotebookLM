# ================================================================
# 图像相关工具汇总：
# - ensure_model: 确保本地存在 RMBG-2.0 模型权重（无则从 ModelScope 下载）
# - BriaRMBG2Remover: 使用 RMBG-2.0 进行高质量背景抠图
# - local_tool_for_bg_remove: 统一接口，基于 RMBG-2.0 去除图片背景
# - get_bg_remove_desc: 返回背景抠图工具的说明文本
# - convert_image_to_svg: 使用 vtracer 将位图图像转换为 SVG 矢量图
# - local_tool_for_raster_to_svg: 统一接口，位图→SVG 矢量化
# - get_raster_to_svg_desc: 返回位图→SVG 工具的说明文本
# - render_svg_to_image: 使用 CairoSVG 将 SVG 渲染为 PNG/PDF/PS 等文件
# - local_tool_for_svg_render: 统一接口，SVG（文件或源码）→图片/文档
# - get_svg_render_desc: 返回 SVG 渲染工具的说明文本
# ================================================================
# BRIA-RMBG 2.0 高质量抠图工具
# - 模型：RMBG 2.0（ONNX）
# - 依赖：onnxruntime, pillow, numpy
# ================================================================

from __future__ import annotations

import os
import subprocess
from pathlib import Path
import platform

import numpy as np
from PIL import Image, ImageFilter
import torch
from torchvision import transforms
from transformers import AutoModelForImageSegmentation

CURRENT_DIR = Path(__file__).resolve().parent
MODEL_PATH = CURRENT_DIR / "onnx" / "model.onnx"
OUTPUT_DIR = CURRENT_DIR

# Process-level background removal model cache: reuse BriaRMBG2Remover instances by model_path
_BG_RMBG_MODEL_CACHE: dict[str, "BriaRMBG2Remover"] = {}


def ensure_model(model_path: Path) -> None:
    """
    确保本地存在 RMBG-2.0 模型权重。

    若 ``model_path`` 对应的文件不存在，则通过 ModelScope 下载
    ``AI-ModelScope/RMBG-2.0`` 模型到该路径所在目录。

    参数
    ----
    model_path:
        本地模型文件路径（通常为 ONNX 或 transformers 权重）。

    异常
    ----
    FileNotFoundError
        当下载结束后仍未在 ``model_path`` 处找到模型文件时抛出。
    """
    if model_path.exists():
        print(f"Model already exists: {model_path}")
        return

    print("Model file not detected, downloading RMBG-2.0 weights...")

    # Ensure directory exists
    model_path.parent.mkdir(parents=True, exist_ok=True)
    # Check if current system is Windows
    is_windows = platform.system().lower() == "windows"
    # Use double quotes for paths on Windows, single quotes on Linux/macOS (keep original logic)
    quote = '"' if is_windows else "'"
    # Download directly to target directory
    cmd = (
        f"modelscope download "
        f"--model AI-ModelScope/RMBG-2.0 "
        f"--local_dir {quote}{model_path}{quote} "
    )
    os.system(cmd)

    # 检查下载是否成功
    if not model_path.exists():
        raise FileNotFoundError(
            f"模型下载失败：未找到 {model_path}。\n"
            "请检查 ModelScope 或手动下载。"
        )

    print(f"模型已成功下载到: {model_path}")


class BriaRMBG2Remover:
    """
    使用 BRIA-RMBG 2.0 模型进行高质量背景抠图的封装类。

    该类会在初始化时确保本地存在 RMBG-2.0 模型权重，并自动选择
    CUDA 或 CPU 设备进行推理。提供 ``remove_background`` 方法，对
    输入图像进行前景分割并生成带透明通道的 PNG 图片。
    """

    def __init__(self, model_path: Path | None = None, output_dir: Path | None = None):
        """
        初始化抠图器。

        参数
        ----
        model_path:
            本地 RMBG-2.0 模型路径。若为 None，则使用默认 ``MODEL_PATH``。
        output_dir:
            输出目录。若为 None，则使用当前文件所在目录。
        """
        self.model_path = Path(model_path) if model_path else MODEL_PATH
        self.output_dir = Path(output_dir) if output_dir else OUTPUT_DIR

        ensure_model(self.model_path)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device

        print(f"加载本地权重: {self.model_path}")
        self.model = AutoModelForImageSegmentation.from_pretrained(
            self.model_path,
            trust_remote_code=True,
        ).eval().to(device)

        # Transform pipeline
        self.image_size = (1024, 1024)
        self.transform_image = transforms.Compose(
            [
                transforms.Resize(self.image_size),
                transforms.ToTensor(),
                transforms.Normalize(
                    [0.485, 0.456, 0.406],
                    [0.229, 0.224, 0.225],
                ),
            ]
        )

    def remove_background(self, image_path: str) -> str:
        """
        对输入图像进行背景抠图，并保存到 ``output_dir``。

        参数
        ----
        image_path:
            输入图片路径（支持 JPG/PNG/WebP 等常见格式）。

        返回
        ----
        str
            输出抠图结果 PNG 文件的绝对路径。
        """
        image_path = Path(image_path)
        print(f"Starting background removal: {image_path}")

        # Load image
        image = Image.open(image_path).convert("RGB")
        input_tensor = self.transform_image(image).unsqueeze(0).to(self.device)

        # Predict mask
        with torch.no_grad():
            preds = self.model(input_tensor)[-1].sigmoid().cpu()

        pred = preds[0].squeeze()
        pred_pil = transforms.ToPILImage()(pred)

        # Resize mask back to original size
        mask = pred_pil.resize(image.size)

        # Apply alpha mask
        out = image.copy()
        out.putalpha(mask)

        # Save output
        out_path = self.output_dir / f"{image_path.stem}_bg_removed.png"
        out.save(out_path)

        print(f"抠图完成: {out_path}")
        return str(out_path)

    def remove_background_batch(self, image_paths: list[str]) -> list[str]:
        """
        Batch background removal (load model once, process one by one)
        Returns list of output file paths
        """
        results = []

        for image_path in image_paths:
            image_path = Path(image_path)
            print(f"[Batch] Starting background removal: {image_path}")

            # Load image
            image = Image.open(image_path).convert("RGB")
            input_tensor = self.transform_image(image).unsqueeze(0).to(self.device)

            # Predict mask
            with torch.no_grad():
                preds = self.model(input_tensor)[-1].sigmoid().cpu()

            pred = preds[0].squeeze()
            pred_pil = transforms.ToPILImage()(pred)

            # Resize mask back to original size
            mask = pred_pil.resize(image.size)

            # Apply alpha mask
            out = image.copy()
            out.putalpha(mask)

            # Save output
            out_path = self.output_dir / f"{image_path.stem}_bg_removed.png"
            out.save(out_path)

            print(f"[Batch] 抠图完成: {out_path}")
            results.append(str(out_path))

        return results


# class BriaRMBG2Remover:
#     """High-quality background removal using BRIA-RMBG 2.0 model"""
#
#     def __init__(self, model_path: str | None = None, output_dir: str | None = None):
#         self.model_path = Path(model_path) if model_path else MODEL_PATH
#         self.output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
#
#         ensure_model(self.model_path)
#
#         # Prefer GPU, fallback to CPU
#         providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
#         self.session = ort.InferenceSession(str(self.model_path), providers=providers)
#
#     def remove_background(self, image_path: str) -> str:
#         img = Image.open(image_path).convert("RGB")
#         orig_w, orig_h = img.size
#
#         side = 1024
#         img_rs = img.resize((side, side), Image.BICUBIC)
#         arr = np.asarray(img_rs).astype(np.float32) / 255.0
#         arr = arr.transpose(2, 0, 1)[None, ...]
#
#         input_name = self.session.get_inputs()[0].name
#         pred = self.session.run(None, {input_name: arr})[0]
#
#         mask = np.clip(pred[0, 0], 0, 1)
#         mask = (mask * 255).astype(np.uint8)
#         m = Image.fromarray(mask, "L").resize((orig_w, orig_h), Image.BICUBIC)
#
#         rgba = img.convert("RGBA")
#         r, g, b, _ = rgba.split()
#         out = Image.merge("RGBA", (r, g, b, m)).filter(ImageFilter.SMOOTH_MORE)
#
#         out_path = self.output_dir / f"{Path(image_path).stem}_bg_removed.png"
#         out.save(out_path)
#         print(f"Background removal complete: {out_path}")
#         return str(out_path)


def get_bg_rm_remover(
    model_path: str | None = None,
    output_dir: str | None = None,
) -> BriaRMBG2Remover:
    """
    获取/创建进程级抠图模型单例，避免重复加载占用显存。

    - 按 model_path 作为 key 进行缓存；
    - output_dir 可在已有实例上动态更新。
    """
    global _BG_RMBG_MODEL_CACHE

    key = str(model_path) if model_path else str(MODEL_PATH)
    if key in _BG_RMBG_MODEL_CACHE:
        remover = _BG_RMBG_MODEL_CACHE[key]
        # 允许调用方调整输出目录
        if output_dir is not None:
            remover.output_dir = Path(output_dir)
            remover.output_dir.mkdir(parents=True, exist_ok=True)
        return remover

    remover = BriaRMBG2Remover(model_path=model_path, output_dir=output_dir)
    _BG_RMBG_MODEL_CACHE[key] = remover
    return remover


def free_bg_rm_model(model_path: str | None = None) -> None:
    """
    显式释放 RMBG-2.0 模型占用的显存。

    - model_path 为 None 时：释放所有已缓存的抠图模型；
    - 否则：仅释放对应 model_path 的实例。
    """
    import gc

    global _BG_RMBG_MODEL_CACHE

    def _del_model(m: BriaRMBG2Remover) -> None:
        try:
            if hasattr(m, "model"):
                try:
                    # Migration model to CPU first, then delete reference
                    m.model.to("cpu")
                except Exception:
                    pass
            del m
        except Exception:
            pass

    if model_path is None:
        for _, m in list(_BG_RMBG_MODEL_CACHE.items()):
            _del_model(m)
        _BG_RMBG_MODEL_CACHE.clear()
    else:
        key = str(model_path)
        m = _BG_RMBG_MODEL_CACHE.pop(key, None)
        if m is not None:
            _del_model(m)

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def local_tool_for_bg_remove(req: dict) -> str:
    """
    使用 BRIA-RMBG 2.0 模型进行背景抠图的统一接口。

    参数
    ----
    req:
        配置字典，支持字段：
        - ``image_path``: str，必需，输入图片路径。
        - ``model_path``: str，可选，自定义模型路径。
        - ``output_dir``: str，可选，自定义输出目录。

    返回
    ----
    str
        抠图结果图片的绝对路径。
    """
    remover = get_bg_rm_remover(
        model_path=req.get("model_path"),
        output_dir=req.get("output_dir"),
    )
    return remover.remove_background(req["image_path"])


def local_tool_for_bg_remove_batch(req: dict) -> list[str]:
    """Batch background removal using process-level singleton model"""
    remover = get_bg_rm_remover(
        model_path=req.get("model_path"), output_dir=req.get("output_dir")
    )
    return remover.remove_background_batch(req["image_path_list"])


def get_bg_remove_desc(lang: str = "zh") -> str:
    """
    获取背景抠图工具的说明文本。

    参数
    ----
    lang:
        语言代码，目前仅支持 "zh"（中文）。

    返回
    ----
    str
        工具功能说明。
    """
    return (
        "Performs high-quality background removal using BRIA-RMBG 2.0 model, automatically removing backgrounds and outputting PNG files with alpha channel. "
        "Supports multiple input formats (JPG/PNG/WebP), output files are saved in the bg_removed/ directory of the input image by default."
    )


# ======================================================================
# vtracer: Raster -> SVG vectorization
# ======================================================================


def convert_image_to_svg(
    input_path: str,
    output_path: str,
    colormode: str = "color",
    hierarchical: str = "stacked",
    mode: str = "spline",
    filter_speckle: int = 4,
    color_precision: int = 6,
    layer_difference: int = 16,
    corner_threshold: int = 60,
    length_threshold: int = 10,
    max_iterations: int = 10,
    splice_threshold: int = 45,
    path_precision: int = 3,
) -> str:
    """
    使用 vtracer 将光栅图像转换为 SVG 矢量图。

    本函数是对 ``vtracer.convert_image_to_svg_py`` 的轻量封装，
    主要用于在 DataFlow-Agent 的工具体系中提供统一的位图→SVG 能力。

    Parameters
    ----
    input_path:
        Input image path (supports common formats like PNG/JPEG).
    output_path:
        Output SVG file path.
    colormode:
        Color mode:
        - "color": Color vectorization.
        - "binary": Black and white vectorization (default).
    hierarchical:
        Hierarchy mode:
        - "stacked": Stacked scan (recommended, default).
        - "cutout": Cutout effect.
    mode:
        Path mode:
        - "spline": Fit paths using smooth curves (default).
        - "polygon": Approximate paths using polygons.
    filter_speckle:
        Speckle filtering threshold (regions with pixel area smaller than this value are removed).
    color_precision:
        Color precision, the smaller the value, the more colors are merged, fewer colors in output.
    layer_difference:
        Layer difference parameter, used to control split sensitivity of adjacent layers.
    corner_threshold:
        Corner threshold, determines strictness of treating corner points as corners (angle threshold).
    length_threshold:
        Length threshold, used to filter very short segments.
    max_iterations:
        Maximum iterations for curve fitting.
    splice_threshold:
        Path splice threshold, used to merge close path segments.
    path_precision:
        Path precision, controls fineness of output curves/polygons.

    返回
    ----
    str
        生成的 SVG 文件的绝对路径。

    异常
    ----
    FileNotFoundError
        当 ``input_path`` 对应的文件不存在时。
    RuntimeError
        当 vtracer 未安装或转换失败时。
    """
    from pathlib import Path

    input_p = Path(input_path)
    if not input_p.exists():
        raise FileNotFoundError(f"Input file not found: {input_p}")

    output_p = Path(output_path)
    output_p.parent.mkdir(parents=True, exist_ok=True)

    try:
        import vtracer
    except ModuleNotFoundError as e:
        raise RuntimeError("vtracer 未安装，请先运行 `pip install vtracer`") from e

    try:
        vtracer.convert_image_to_svg_py(
            str(input_p),
            str(output_p),
            colormode=colormode,
            hierarchical=hierarchical,
            mode=mode,
            filter_speckle=filter_speckle,
            color_precision=color_precision,
            layer_difference=layer_difference,
            corner_threshold=corner_threshold,
            length_threshold=length_threshold,
            max_iterations=max_iterations,
            splice_threshold=splice_threshold,
            path_precision=path_precision,
        )
    except Exception as e:
        raise RuntimeError(f"vtracer conversion failed: {e}") from e

    return str(output_p.resolve())


def local_tool_for_raster_to_svg(req: dict) -> str:
    """
    将位图图像转换为 SVG 矢量图的统一工具接口。

    本工具基于 vtracer 封装，适合作为 DataFlow-Agent 中的本地工具被调用。
    入参为包含配置项的字典，返回生成的 SVG 文件路径字符串。

    必需字段
    --------
    - ``image_path``: str
        输入位图图片路径。
    - ``output_svg``: str
        输出 SVG 文件路径。

    可选字段（对应 vtracer 参数）
    -------------------------------
    - ``colormode``: {"color", "binary"}，默认 "binary"
    - ``hierarchical``: {"stacked", "cutout"}，默认 "stacked"
    - ``mode``: {"spline", "polygon"}，默认 "spline"
    - ``filter_speckle``: int，默认 4
    - ``color_precision``: int，默认 6
    - ``layer_difference``: int，默认 16
    - ``corner_threshold``: int，默认 60
    - ``length_threshold``: int，默认 10
    - ``max_iterations``: int，默认 10
    - ``splice_threshold``: int，默认 45
    - ``path_precision``: int，默认 3

    返回
    ----
    str
        生成的 SVG 文件的绝对路径。
    """
    if "image_path" not in req:
        raise ValueError("Missing required field: image_path")
    if "output_svg" not in req:
        raise ValueError("Missing required field: output_svg")

    return convert_image_to_svg(
        input_path=req["image_path"],
        output_path=req["output_svg"],
        colormode=req.get("colormode", "binary"),
        hierarchical=req.get("hierarchical", "stacked"),
        mode=req.get("mode", "spline"),
        filter_speckle=req.get("filter_speckle", 4),
        color_precision=req.get("color_precision", 6),
        layer_difference=req.get("layer_difference", 16),
        corner_threshold=req.get("corner_threshold", 60),
        length_threshold=req.get("length_threshold", 10),
        max_iterations=req.get("max_iterations", 10),
        splice_threshold=req.get("splice_threshold", 45),
        path_precision=req.get("path_precision", 3),
    )


def get_raster_to_svg_desc(lang: str = "zh") -> str:
    """
    获取位图转 SVG 矢量化工具的文本说明。

    参数
    ----
    lang:
        语言代码，目前支持:
        - "zh": 返回中文描述。
        - 其它值: 返回英文说明。

    返回
    ----
    str
        工具功能说明字符串。
    """
    if lang == "zh":
        return (
            "使用 vtracer 将位图图像（PNG/JPEG 等）自动矢量化为 SVG 文件。"
            "支持彩色/黑白两种模式，并提供堆叠扫描（stacked）和 cutout 分层方式，"
            "适合将图标、插画甚至照片级图片转换为可缩放的矢量图。"
        )
    return (
        "Raster-to-SVG conversion tool based on vtracer. "
        "It converts raster images (e.g. PNG/JPEG) into SVG vectors, "
        "supporting color/binary modes and stacked/cutout hierarchies."
    )


# ======================================================================
# CairoSVG: SVG -> PNG/PDF/PS rendering
# ======================================================================


def render_svg_to_image(
    svg_source: str,
    output_path: str,
    *,
    from_string: bool = False,
    fmt: str | None = None,
    scale: float = 1.0,
) -> str:
    """
    使用 CairoSVG 将 SVG 渲染为图片或文档文件。

    该函数支持两种输入方式：
    1. ``from_string=False`` （默认）：``svg_source`` 视为 SVG 文件路径。
    2. ``from_string=True``：``svg_source`` 视为 SVG 源码字符串。

    参数
    ----
    svg_source:
        - 当 ``from_string=False`` 时，为 SVG 文件路径。
        - 当 ``from_string=True`` 时，为 SVG 源码字符串。
    output_path:
        输出文件路径，例如 ``output.png``、``output.pdf``。
    from_string:
        是否将 ``svg_source`` 视为 SVG 字符串而非文件路径。
    fmt:
        输出格式，通常由 ``output_path`` 的扩展名自动推断。
        如需强制指定，可传入:
        - "png"
        - "pdf"
        - "ps"
        - "svg"

    返回
    ----
    str
        生成文件的绝对路径。

    异常
    ----
    FileNotFoundError
        当 ``from_string=False`` 且指定的 SVG 文件不存在时。
    RuntimeError
        当 CairoSVG 未安装或渲染过程失败时。

    说明
    ----
    这是对 ``cairosvg.svg2*`` 系列函数的统一封装，用于在
    DataFlow-Agent 中以统一的方式完成 SVG 渲染任务。
    """
    from pathlib import Path

    try:
        import cairosvg
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "cairosvg not installed, please run `pip install cairosvg` first"
        ) from e

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    if fmt is None:
        ext = out_p.suffix.lower().lstrip(".")
        fmt = ext or "png"

    try:
        if from_string:
            # svg_source is SVG string
            data = svg_source.encode("utf-8")
            if fmt == "png":
                cairosvg.svg2png(bytestring=data, write_to=str(out_p), scale=scale)
            elif fmt == "pdf":
                cairosvg.svg2pdf(bytestring=data, write_to=str(out_p))
            elif fmt == "ps":
                cairosvg.svg2ps(bytestring=data, write_to=str(out_p))
            elif fmt == "svg":
                # Write to file directly
                out_p.write_text(svg_source, encoding="utf-8")
            else:
                raise ValueError(f"Unsupported output format: {fmt}")
        else:
            # svg_source is SVG file path
            in_p = Path(svg_source)
            if not in_p.exists():
                raise FileNotFoundError(f"Input SVG file not found: {in_p}")

            if fmt == "png":
                cairosvg.svg2png(url=str(in_p), write_to=str(out_p), scale=scale)
            elif fmt == "pdf":
                cairosvg.svg2pdf(url=str(in_p), write_to=str(out_p))
            elif fmt == "ps":
                cairosvg.svg2ps(url=str(in_p), write_to=str(out_p))
            elif fmt == "svg":
                # Copy original SVG
                out_p.write_text(in_p.read_text(encoding="utf-8"), encoding="utf-8")
            else:
                raise ValueError(f"Unsupported output format: {fmt}")
    except Exception as e:
        raise RuntimeError(f"SVG rendering failed: {e}") from e

    return str(out_p.resolve())


def local_tool_for_svg_render(req: dict) -> str:
    """
    将 SVG 源码或 SVG 文件渲染为图片/文档文件的统一接口。

    支持两种调用方式：
    1. 通过 SVG 文件路径渲染；
    2. 通过 SVG 源码字符串渲染。

    必需字段（二选一）
    ------------------
    - ``svg_path``: str
        SVG 文件路径。
    - ``svg_code``: str
        SVG 源码字符串。

    必需字段
    --------
    - ``output_path``: str
        输出文件路径，例如 ``output.png``、``output.pdf``。

    可选字段
    --------
    - ``fmt``: str
        输出格式，通常由 ``output_path`` 的扩展名自动推断。
        如需强制指定，可传 "png"、"pdf"、"ps"、"svg"。

    返回
    ----
    str
        生成文件的绝对路径。

    示例
    ----
    1. 从 SVG 文件渲染为 PNG::

        local_tool_for_svg_render({
            "svg_path": "icon.svg",
            "output_path": "icon.png",
        })

    2. 从 SVG 代码渲染为 PNG::

        local_tool_for_svg_render({
            "svg_code": "<svg ...>...</svg>",
            "output_path": "icon.png",
        })
    """
    svg_path = req.get("svg_path")
    svg_code = req.get("svg_code")
    scale = req.get("scale", 1.0)

    if not svg_path and not svg_code:
        raise ValueError("必须提供 svg_path 或 svg_code 其中之一。")

    if svg_path and svg_code:
        raise ValueError("svg_path 与 svg_code 只能同时提供一个，请二选一。")

    if "output_path" not in req:
        raise ValueError("缺少必需字段: output_path")

    if svg_code:
        return render_svg_to_image(
            svg_source=svg_code,
            output_path=req["output_path"],
            from_string=True,
            fmt=req.get("fmt"),
            scale=scale,
        )

    return render_svg_to_image(
        svg_source=svg_path,
        output_path=req["output_path"],
        from_string=False,
        fmt=req.get("fmt"),
        scale=scale,
    )


def get_svg_render_desc(lang: str = "zh") -> str:
    """
    获取 SVG 渲染工具的文本说明。

    参数
    ----
    lang:
        语言代码，目前支持:
        - "zh": 返回中文描述。
        - 其它值: 返回英文描述。

    返回
    ----
    str
        工具功能说明字符串。
    """
    if lang == "zh":
        return (
            "使用 CairoSVG 将 SVG 渲染为位图或文档文件（如 PNG、PDF、PS）。"
            "既支持从 SVG 文件路径渲染，也支持直接从 SVG 源码字符串渲染，"
            "适合在生成 SVG 后进一步导出为通用图片格式。"
        )
    return (
        "Render SVG into raster images or documents (PNG, PDF, PS) using CairoSVG. "
        "Supports both SVG file path and raw SVG string as input."
    )


# ======================================================================
# Inkscape: SVG -> EMF vector conversion
# ======================================================================


def svg_to_emf(svg_path: str, emf_path: str, dpi: int = 600) -> str:
    """
    使用 Inkscape 将 SVG 文件转换为 EMF 矢量图，返回生成的 EMF 路径。

    依赖
    ----
    - 系统需安装 Inkscape，并且 `inkscape` 在 PATH 中可直接调用。

    参数
    ----
    svg_path:
        输入 SVG 文件路径。
    emf_path:
        输出 EMF 文件路径。
    dpi:
        导出 DPI，默认 600。

    返回
    ----
    str
        生成的 EMF 文件的绝对路径。

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


def local_tool_for_svg_to_emf(req: dict) -> str:
    """
    Unified interface for converting SVG files to EMF vector images.

    Required Fields
    --------
    - ``svg_path``: str
        Input SVG file path.
    - ``emf_path``: str
        Output EMF file path.

    Optional Fields
    --------
    - ``dpi``: int
        Export DPI, default 600.

    Returns
    -------
    str
        Absolute path of generated EMF file.
    """
    if "svg_path" not in req:
        raise ValueError("Missing required field: svg_path")
    if "emf_path" not in req:
        raise ValueError("Missing required field: emf_path")

    return svg_to_emf(
        svg_path=req["svg_path"],
        emf_path=req["emf_path"],
        dpi=req.get("dpi", 600),
    )


def get_svg_to_emf_desc(lang: str = "zh") -> str:
    """
    Get text description for the SVG-to-EMF tool.

    Parameters
    ----------
    lang:
        Language code, currently supported:
        - "zh": Returns Chinese description.
        - Other: Returns English description.

    Returns
    -------
    str
        Tool functionality description.
    """
    if lang == "zh":
        return (
            "使用 Inkscape 将 SVG 矢量图转换为 EMF 格式。"
            "EMF 格式在 Windows 和 Office 应用中有更好的兼容性，"
            "特别适合在 PowerPoint 中使用矢量图形。"
        )
    return (
        "Convert SVG to EMF vector format using Inkscape. "
        "EMF format has better compatibility in Windows and Office applications, "
        "especially suitable for use in PowerPoint."
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="BRIA-RMBG 2.0 High-quality Background Removal, Vectorization, and Rendering Toolset")
    parser.add_argument("image_path", help="Input image path (for background removal example)")
    parser.add_argument("--model_path", default=None, help="Model path (optional)")
    parser.add_argument("--output_dir", default=None, help="Output directory (optional)")
    args = parser.parse_args()

    out = local_tool_for_bg_remove(
        {
            "image_path": args.image_path,
            "model_path": args.model_path,
            "output_dir": args.output_dir,
        }
    )
    print(out)
