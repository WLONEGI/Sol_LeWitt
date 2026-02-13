import io
import posixpath
import re
import zipfile
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

SLIDE_LIMIT = 30
TEXTS_PER_SLIDE_LIMIT = 8
TEXT_LENGTH_LIMIT = 160

_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}
_RELS_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
_REL_TYPE_SLIDE_LAYOUT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
_REL_TYPE_SLIDE_MASTER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster"


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


def _rels_path_for_part(part_path: str) -> str:
    part = PurePosixPath(part_path)
    return str(part.parent / "_rels" / f"{part.name}.rels")


def _normalize_archive_target_path(base_part_path: str, target: str | None) -> str | None:
    if not isinstance(target, str) or not target.strip():
        return None
    raw = target.strip().replace("\\", "/")
    if raw.startswith("/"):
        normalized = posixpath.normpath(raw.lstrip("/"))
    else:
        base_dir = str(PurePosixPath(base_part_path).parent)
        normalized = posixpath.normpath(posixpath.join(base_dir, raw))
    if not normalized or normalized.startswith("../"):
        return None
    return normalized


def _read_relationship_target(
    archive: zipfile.ZipFile,
    *,
    part_path: str,
    rel_type: str,
) -> str | None:
    rels_path = _rels_path_for_part(part_path)
    if rels_path not in archive.namelist():
        return None
    try:
        rels_xml = archive.read(rels_path)
        rels_root = ET.fromstring(rels_xml)
    except Exception:
        return None

    for rel in rels_root.findall("./rel:Relationship", _RELS_NS):
        if rel.attrib.get("Type") != rel_type:
            continue
        target = _normalize_archive_target_path(part_path, rel.attrib.get("Target"))
        if target:
            return target
    return None


def _extract_layout_placeholders(layout_root: ET.Element) -> list[str]:
    placeholders: list[str] = []
    seen: set[str] = set()
    for node in layout_root.findall(".//p:ph", _NS):
        raw = str(node.attrib.get("type") or "body").strip().lower()
        value = re.sub(r"[^a-z0-9_]+", "_", raw).strip("_") or "body"
        if value in seen:
            continue
        seen.add(value)
        placeholders.append(value)
        if len(placeholders) >= 8:
            break
    return placeholders


def _classify_layout_kind(
    *,
    layout_name: str | None,
    layout_type: str | None,
    placeholders: list[str],
) -> str:
    name = (layout_name or "").strip().lower()
    type_hint = (layout_type or "").strip().lower()
    merged = f"{name} {type_hint}".strip()
    placeholder_set = {item.lower() for item in placeholders if isinstance(item, str)}

    if "blank" in merged:
        return "blank"
    if any(token in merged for token in ("title slide", "cover", "title only", "表紙")):
        return "cover"
    if any(token in merged for token in ("section", "セクション")):
        return "section_header"
    if any(token in merged for token in ("comparison", "比較")):
        return "comparison"

    body_count = sum(1 for item in placeholders if item == "body")
    has_image = bool({"pic", "obj", "media", "chart", "tbl"} & placeholder_set)
    has_title = bool({"title", "ctrtitle", "subtitle"} & placeholder_set)

    if body_count >= 2:
        return "two_content"
    if has_image and (body_count >= 1 or has_title):
        return "content_with_image"
    if has_image and body_count == 0:
        return "image_focus"
    if body_count >= 1 or "body" in merged or "content" in merged:
        return "content"
    if has_title:
        return "title_only"
    return "other"


def _extract_slide_layout_master_meta(
    archive: zipfile.ZipFile,
    *,
    slide_part_path: str,
) -> dict[str, Any]:
    layout_part_path = _read_relationship_target(
        archive,
        part_path=slide_part_path,
        rel_type=_REL_TYPE_SLIDE_LAYOUT,
    )
    if not layout_part_path or layout_part_path not in archive.namelist():
        return {
            "layout_name": None,
            "layout_type": None,
            "layout_kind": None,
            "layout_placeholders": [],
            "master_name": None,
            "master_texts": [],
        }

    layout_name: str | None = None
    layout_type: str | None = None
    layout_placeholders: list[str] = []
    try:
        layout_xml = archive.read(layout_part_path)
        layout_root = ET.fromstring(layout_xml)
        layout_node = layout_root if layout_root.tag.endswith("sldLayout") else None
        if layout_node is not None:
            raw_layout_type = layout_node.attrib.get("type")
            if isinstance(raw_layout_type, str) and raw_layout_type.strip():
                layout_type = raw_layout_type.strip()
        c_sld = layout_root.find("./p:cSld", _NS)
        if c_sld is not None:
            raw_name = c_sld.attrib.get("name")
            if isinstance(raw_name, str):
                normalized_name = _normalize_text(raw_name)
                layout_name = normalized_name or None
        layout_placeholders = _extract_layout_placeholders(layout_root)
    except Exception:
        return {
            "layout_name": None,
            "layout_type": None,
            "layout_kind": None,
            "layout_placeholders": [],
            "master_name": None,
            "master_texts": [],
        }

    master_name: str | None = None
    master_texts: list[str] = []
    master_part_path = _read_relationship_target(
        archive,
        part_path=layout_part_path,
        rel_type=_REL_TYPE_SLIDE_MASTER,
    )
    if master_part_path and master_part_path in archive.namelist():
        try:
            master_xml = archive.read(master_part_path)
            master_root = ET.fromstring(master_xml)
            c_sld = master_root.find("./p:cSld", _NS)
            if c_sld is not None:
                raw_name = c_sld.attrib.get("name")
                if isinstance(raw_name, str):
                    normalized_name = _normalize_text(raw_name)
                    master_name = normalized_name or None
            master_texts = _parse_slide_texts(master_xml)
        except Exception:
            master_name = None
            master_texts = []

    layout_kind = _classify_layout_kind(
        layout_name=layout_name,
        layout_type=layout_type,
        placeholders=layout_placeholders,
    )
    return {
        "layout_name": layout_name,
        "layout_type": layout_type,
        "layout_kind": layout_kind,
        "layout_placeholders": layout_placeholders,
        "master_name": master_name,
        "master_texts": master_texts,
    }


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
                layout_meta = _extract_slide_layout_master_meta(archive, slide_part_path=path)
            except Exception:
                texts = []
                layout_meta = {
                    "layout_name": None,
                    "layout_type": None,
                    "layout_kind": None,
                    "layout_placeholders": [],
                    "master_name": None,
                    "master_texts": [],
                }
            slide_number = _slide_sort_key(path)
            title = texts[0] if texts else None
            slides.append(
                {
                    "slide_number": slide_number,
                    "title": title,
                    "texts": texts,
                    "layout_name": layout_meta.get("layout_name"),
                    "layout_type": layout_meta.get("layout_type"),
                    "layout_kind": layout_meta.get("layout_kind"),
                    "layout_placeholders": layout_meta.get("layout_placeholders") or [],
                    "master_name": layout_meta.get("master_name"),
                    "master_texts": layout_meta.get("master_texts") or [],
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
