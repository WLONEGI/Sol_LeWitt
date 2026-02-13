import pytest
from fastapi import HTTPException

from src.app.app import (
    _infer_upload_kind,
    _normalize_display_filename,
    _sanitize_filename,
    _validate_upload_file,
)


def test_infer_upload_kind_detects_image() -> None:
    kind = _infer_upload_kind("image/png", "sample.png")
    assert kind == "image"


def test_infer_upload_kind_detects_pptx_from_extension() -> None:
    kind = _infer_upload_kind("application/octet-stream", "deck.pptx")
    assert kind == "pptx"


def test_infer_upload_kind_detects_csv() -> None:
    kind = _infer_upload_kind("text/csv", "dataset.csv")
    assert kind == "csv"


def test_infer_upload_kind_detects_text_file() -> None:
    kind = _infer_upload_kind("text/plain", "notes.txt")
    assert kind == "text"


def test_infer_upload_kind_marks_xlsx_as_unsupported() -> None:
    kind = _infer_upload_kind(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "sheet.xlsx",
    )
    assert kind == "xlsx_unsupported"


def test_validate_upload_file_rejects_oversized_image() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _validate_upload_file(
            content_type="image/png",
            filename="large.png",
            size_bytes=(10 * 1024 * 1024) + 1,
        )
    assert exc_info.value.status_code == 413


def test_validate_upload_file_rejects_unsupported_type() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _validate_upload_file(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="sheet.xlsx",
            size_bytes=100,
        )
    assert exc_info.value.status_code == 415


def test_validate_upload_file_accepts_pptx() -> None:
    kind = _validate_upload_file(
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename="template.pptx",
        size_bytes=1024,
    )
    assert kind == "pptx"


def test_sanitize_filename_preserves_pptx_extension_for_non_ascii_name() -> None:
    safe_name = _sanitize_filename("資料.pptx")
    assert safe_name.endswith(".pptx")
    assert safe_name == "upload.pptx"


def test_validate_upload_file_accepts_sanitized_non_ascii_pptx_name() -> None:
    safe_name = _sanitize_filename("テンプレート.pptx")
    kind = _validate_upload_file(
        content_type="application/octet-stream",
        filename=safe_name,
        size_bytes=1024,
    )
    assert kind == "pptx"


def test_validate_upload_file_accepts_pdf() -> None:
    kind = _validate_upload_file(
        content_type="application/pdf",
        filename="report.pdf",
        size_bytes=1024,
    )
    assert kind == "pdf"


def test_validate_upload_file_accepts_text_markdown_and_json() -> None:
    txt_kind = _validate_upload_file(
        content_type="text/plain",
        filename="notes.txt",
        size_bytes=1024,
    )
    md_kind = _validate_upload_file(
        content_type="text/markdown",
        filename="spec.md",
        size_bytes=1024,
    )
    json_kind = _validate_upload_file(
        content_type="application/json",
        filename="data.json",
        size_bytes=1024,
    )
    assert txt_kind == "text"
    assert md_kind == "text"
    assert json_kind == "json"


def test_validate_upload_file_accepts_csv() -> None:
    kind = _validate_upload_file(
        content_type="text/csv",
        filename="table.csv",
        size_bytes=1024,
    )
    assert kind == "csv"


def test_normalize_display_filename_keeps_original_basename() -> None:
    display_name = _normalize_display_filename("C:\\fakepath\\提案資料 v1.pptx")
    assert display_name == "提案資料 v1.pptx"


def test_normalize_display_filename_falls_back_for_invalid_name() -> None:
    display_name = _normalize_display_filename("../\u0000", fallback="upload.pptx")
    assert display_name == "upload.pptx"
