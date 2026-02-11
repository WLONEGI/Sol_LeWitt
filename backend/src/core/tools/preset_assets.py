import json
import logging
import os
import subprocess
import zipfile
from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool
from pdf2image import convert_from_path
from PIL import Image

from src.domain.designer.pdf import assemble_pdf_from_images

logger = logging.getLogger(__name__)


def _resolve_path(path: str, work_dir: str) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        return str(candidate)
    return str(Path(work_dir) / candidate)


def _ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _build_pptx_from_images(image_paths: list[str], output_path: str, title: str | None = None) -> None:
    try:
        from pptx import Presentation
        from pptx.util import Emu
    except Exception as exc:
        raise RuntimeError(f"python-pptx is required for PPTX packaging: {exc}") from exc

    if not image_paths:
        raise ValueError("image_paths is empty")

    with Image.open(image_paths[0]) as first_image:
        width_px, height_px = first_image.size
    if width_px <= 0 or height_px <= 0:
        raise ValueError("Invalid first image dimensions")

    prs = Presentation()
    blank_layout = prs.slide_layouts[6]

    slide_width = Emu(9144000)  # 10 inches
    slide_height = Emu(int(slide_width * height_px / width_px))
    prs.slide_width = slide_width
    prs.slide_height = slide_height

    if title:
        prs.core_properties.title = title

    for image_path in image_paths:
        slide = prs.slides.add_slide(blank_layout)
        slide.shapes.add_picture(image_path, 0, 0, width=prs.slide_width, height=prs.slide_height)

    prs.save(output_path)


@tool
def render_pptx_master_images_tool(
    pptx_path: Annotated[str, "Local path of PPTX file to render."],
    output_dir: Annotated[str, "Output directory for rendered images."] = "master_images",
    dpi: Annotated[int, "Rendering DPI (72-300)."] = 160,
    work_dir: Annotated[str, "Base working directory for relative paths."] = "/tmp",
):
    """
    Render PPTX into PNG files as local assets.
    This tool only handles local files. GCS I/O is handled by Data Analyst node.
    """
    try:
        safe_work_dir = os.path.abspath(work_dir or "/tmp")
        _ensure_dir(safe_work_dir)

        source_pptx = _resolve_path(pptx_path, safe_work_dir)
        if not os.path.isfile(source_pptx):
            return f"Error: PPTX file not found: {source_pptx}"

        out_dir = os.path.abspath(_resolve_path(output_dir, safe_work_dir))
        _ensure_dir(out_dir)

        dpi_value = max(72, min(300, int(dpi)))
        stem = Path(source_pptx).stem
        rendered_pdf = os.path.join(out_dir, f"{stem}.pdf")

        convert_cmd = [
            "soffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            out_dir,
            source_pptx,
        ]
        convert_result = subprocess.run(convert_cmd, capture_output=True, text=True, check=False, timeout=120)
        if convert_result.returncode != 0:
            return (
                "Error: Failed to render PPTX with LibreOffice.\n"
                f"stdout: {convert_result.stdout}\n"
                f"stderr: {convert_result.stderr}"
            )
        if not os.path.isfile(rendered_pdf):
            return f"Error: Converted PDF not found: {rendered_pdf}"

        pages = convert_from_path(rendered_pdf, dpi=dpi_value, fmt="png")
        image_paths: list[str] = []
        for idx, page in enumerate(pages, start=1):
            image_path = os.path.join(out_dir, f"{stem}_master_{idx:02d}.png")
            page.save(image_path, format="PNG")
            image_paths.append(image_path)

        return json.dumps(
            {
                "status": "ok",
                "pptx_path": source_pptx,
                "pdf_path": rendered_pdf,
                "image_paths": image_paths,
            },
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error("render_pptx_master_images_tool failed: %s", e)
        return f"Error: {e}"


@tool
def package_visual_assets_tool(
    image_paths: Annotated[list[str], "Local image paths to package in order."],
    output_basename: Annotated[str, "Base filename for pptx/pdf/zip outputs."] = "deck",
    output_dir: Annotated[str, "Output directory for packaged files."] = "packaged_assets",
    deck_title: Annotated[str, "Optional deck title embedded into PPTX metadata."] = "Generated Deck",
    work_dir: Annotated[str, "Base working directory for relative paths."] = "/tmp",
):
    """
    Package local images into PPTX, PDF, and ZIP files.
    This tool only handles local files. GCS I/O is handled by Data Analyst node.
    """
    try:
        safe_work_dir = os.path.abspath(work_dir or "/tmp")
        _ensure_dir(safe_work_dir)
        out_dir = os.path.abspath(_resolve_path(output_dir, safe_work_dir))
        _ensure_dir(out_dir)

        normalized_images: list[str] = []
        for raw_path in image_paths or []:
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            resolved = _resolve_path(raw_path.strip(), safe_work_dir)
            if os.path.isfile(resolved):
                normalized_images.append(resolved)

        if not normalized_images:
            return "Error: No valid local images found for packaging."

        safe_basename = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in output_basename).strip("_")
        safe_basename = safe_basename or "deck"

        pptx_path = os.path.join(out_dir, f"{safe_basename}.pptx")
        pdf_path = os.path.join(out_dir, f"{safe_basename}.pdf")
        zip_path = os.path.join(out_dir, f"{safe_basename}.zip")

        _build_pptx_from_images(normalized_images, pptx_path, title=deck_title)

        image_bytes_list: list[bytes] = []
        for image_path in normalized_images:
            with open(image_path, "rb") as fp:
                image_bytes_list.append(fp.read())
        pdf_bytes = assemble_pdf_from_images(image_bytes_list)
        with open(pdf_path, "wb") as fp:
            fp.write(pdf_bytes)

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(pptx_path, arcname=os.path.basename(pptx_path))
            archive.write(pdf_path, arcname=os.path.basename(pdf_path))
            for idx, image_path in enumerate(normalized_images, start=1):
                ext = Path(image_path).suffix or ".png"
                archive.write(image_path, arcname=f"slides/slide_{idx:02d}{ext}")

        return json.dumps(
            {
                "status": "ok",
                "image_paths": normalized_images,
                "pptx_path": pptx_path,
                "pdf_path": pdf_path,
                "zip_path": zip_path,
            },
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error("package_visual_assets_tool failed: %s", e)
        return f"Error: {e}"

