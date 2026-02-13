import asyncio
from unittest.mock import patch

import pytest

from src.app.app import (
    InpaintReferenceImage,
    _build_inpaint_instruction,
    _inpaint_source_kind,
    _resolve_inpaint_reference,
    _run_inpaint,
)


def test_build_inpaint_instruction_contains_constraints() -> None:
    prompt = "Replace the logo with a monochrome icon"
    instruction = _build_inpaint_instruction(prompt)

    assert "Image[1] = ORIGINAL" in instruction
    assert "Image[2] = MASK" in instruction
    assert "white = editable" in instruction
    assert prompt in instruction


def test_inpaint_source_kind_classifies_sources() -> None:
    assert _inpaint_source_kind("data:image/png;base64,AAAA") == "data_url"
    assert _inpaint_source_kind("gs://bucket/path.png") == "gcs_uri"
    assert _inpaint_source_kind("https://example.com/a.png") == "https_url"
    assert _inpaint_source_kind("http://example.com/a.png") == "http_url"


def test_build_inpaint_instruction_includes_optional_references() -> None:
    prompt = "Apply a hand-drawn marker texture"
    instruction = _build_inpaint_instruction(
        prompt,
        reference_images=[
            InpaintReferenceImage(image_url="https://example.com/ref-style.png", caption="style board"),
            InpaintReferenceImage(image_url="https://example.com/ref-logo.png"),
        ],
    )

    assert "Image[3..N] = OPTIONAL REFERENCE IMAGES" in instruction
    assert "Image[3] = REFERENCE (style board)" in instruction
    assert "Image[4] = REFERENCE" in instruction
    assert prompt in instruction


def test_resolve_inpaint_reference_accepts_data_url() -> None:
    data_url = "data:image/png;base64,aGVsbG8="
    result = asyncio.run(_resolve_inpaint_reference(data_url, field_name="mask_image_url"))
    assert isinstance(result, bytes)
    assert result == b"hello"


def test_resolve_inpaint_reference_accepts_gs_uri() -> None:
    source = "gs://demo-bucket/generated_assets/demo.png"
    result = asyncio.run(_resolve_inpaint_reference(source, field_name="image_url"))
    assert result == source


def test_resolve_inpaint_reference_downloads_storage_url() -> None:
    source = "https://storage.googleapis.com/demo-bucket/generated_assets/demo.webp"
    with patch("src.app.app.download_blob_as_bytes", return_value=b"storage-image") as mocked:
        result = asyncio.run(_resolve_inpaint_reference(source, field_name="image_url"))
    assert result == b"storage-image"
    mocked.assert_called_once_with(source)


def test_resolve_inpaint_reference_downloads_http_url() -> None:
    with patch("src.app.app.download_blob_as_bytes", return_value=b"image-bytes") as mocked:
        result = asyncio.run(
            _resolve_inpaint_reference("https://example.com/image.png", field_name="image_url")
        )

    assert isinstance(result, bytes)
    assert result == b"image-bytes"
    mocked.assert_called_once_with("https://example.com/image.png")


def test_resolve_inpaint_reference_rejects_invalid_data_url() -> None:
    with pytest.raises(ValueError) as exc_info:
        asyncio.run(_resolve_inpaint_reference("data:image/png;base64,@@@", field_name="mask_image_url"))

    assert "Invalid mask_image_url data URL" in str(exc_info.value)


def test_run_inpaint_passes_references_in_strict_order() -> None:
    references = [
        InpaintReferenceImage(
            image_url="https://storage.googleapis.com/demo-bucket/ref-1.webp",
            caption="logo",
            mime_type="image/webp",
        ),
        InpaintReferenceImage(
            image_url="https://example.com/ref-2.png",
            caption="palette",
            mime_type="image/jpeg",
        ),
    ]

    with patch(
        "src.app.app._resolve_inpaint_reference",
        side_effect=["gs://demo-bucket/source.jpg", b"mask-bytes", "gs://demo-bucket/ref-1.webp", b"ref-2-bytes"],
    ) as mocked_resolve, patch(
        "src.app.app.generate_image",
        return_value=(b"generated-bytes", None),
    ) as mocked_generate, patch(
        "src.app.app.upload_to_gcs",
        return_value="https://storage.googleapis.com/demo/output.png",
    ) as mocked_upload:
        output_url = asyncio.run(
            _run_inpaint(
                image_url="https://example.com/source.png",
                mask_image_url="data:image/png;base64,bWFzaw==",
                prompt="replace masked area",
                reference_images=references,
                session_id="session-1",
                slide_number=2,
            )
        )

    assert output_url == "https://storage.googleapis.com/demo/output.png"
    assert mocked_resolve.call_count == 4
    reference_image = mocked_generate.call_args.kwargs["reference_image"]
    assert reference_image == [
        {"uri": "gs://demo-bucket/source.jpg", "mime_type": "image/jpeg"},
        {"data": b"mask-bytes", "mime_type": "image/png"},
        {"uri": "gs://demo-bucket/ref-1.webp", "mime_type": "image/webp"},
        {"data": b"ref-2-bytes", "mime_type": "image/jpeg"},
    ]
    mocked_upload.assert_called_once()
