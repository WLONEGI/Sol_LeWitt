import io
import re
import zipfile
from typing import Any
from xml.etree import ElementTree as ET

SLIDE_LIMIT = 30
TEXTS_PER_SLIDE_LIMIT = 8
TEXT_LENGTH_LIMIT = 160

_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


def _slide_sort_key(path: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", path)
    if not match:
        return 10**9
    return int(match.group(1))


def _normalize_text(value: str) -> str:
    compact = re.sub(r"\s+", " ", value or "").strip()
    if len(compact) <= TEXT_LENGTH_LIMIT:
        return compact
    return compact[: TEXT_LENGTH_LIMIT - 1] + "…"


def _parse_slide_texts(xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(xml_bytes)
    texts: list[str] = []
    for node in root.findall(".//a:t", _NS):
        if node.text is None:
            continue
        normalized = _normalize_text(node.text)
        if not normalized:
            continue
        texts.append(normalized)
        if len(texts) >= TEXTS_PER_SLIDE_LIMIT:
            break
    return texts


def _parse_theme(theme_xml_bytes: bytes) -> dict[str, Any]:
    root = ET.fromstring(theme_xml_bytes)
    theme_name = root.attrib.get("name")

    accent_colors: list[str] = []
    for accent_name in ("accent1", "accent2", "accent3", "accent4", "accent5", "accent6"):
        accent = root.find(f".//a:clrScheme/a:{accent_name}", _NS)
        if accent is None:
            continue
        srgb = accent.find("./a:srgbClr", _NS)
        sys_clr = accent.find("./a:sysClr", _NS)
        if srgb is not None and srgb.attrib.get("val"):
            accent_colors.append(f"#{srgb.attrib['val']}")
        elif sys_clr is not None:
            fallback = sys_clr.attrib.get("lastClr") or sys_clr.attrib.get("val")
            if fallback:
                accent_colors.append(f"#{fallback}")

    major_font = None
    minor_font = None
    major_font_node = root.find(".//a:fontScheme/a:majorFont/a:latin", _NS)
    minor_font_node = root.find(".//a:fontScheme/a:minorFont/a:latin", _NS)
    if major_font_node is not None:
        major_font = major_font_node.attrib.get("typeface")
    if minor_font_node is not None:
        minor_font = minor_font_node.attrib.get("typeface")

    return {
        "name": theme_name,
        "accent_colors": accent_colors,
        "major_font": major_font,
        "minor_font": minor_font,
    }


def extract_pptx_context(
    file_bytes: bytes,
    *,
    filename: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    """
    Extract a lightweight context from a PPTX binary.
    The output is intentionally compact for prompt injection safety.
    """
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
        slide_paths = sorted(
            [
                name for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            ],
            key=_slide_sort_key,
        )[:SLIDE_LIMIT]

        slides: list[dict[str, Any]] = []
        for path in slide_paths:
            try:
                slide_xml = archive.read(path)
                texts = _parse_slide_texts(slide_xml)
            except Exception:
                texts = []
            slide_number = _slide_sort_key(path)
            title = texts[0] if texts else None
            slides.append(
                {
                    "slide_number": slide_number,
                    "title": title,
                    "texts": texts,
                }
            )

        theme = None
        if "ppt/theme/theme1.xml" in archive.namelist():
            try:
                theme = _parse_theme(archive.read("ppt/theme/theme1.xml"))
            except Exception:
                theme = None

    return {
        "filename": filename,
        "source_url": source_url,
        "slide_count": len(slides),
        "slides": slides,
        "theme": theme,
    }
