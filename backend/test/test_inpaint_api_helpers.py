import asyncio
from unittest.mock import patch

import pytest

from src.app.app import _build_inpaint_instruction, _resolve_inpaint_reference


def test_build_inpaint_instruction_contains_constraints() -> None:
    prompt = "Replace the logo with a monochrome icon"
    instruction = _build_inpaint_instruction(prompt)

    assert "Image[1] = ORIGINAL" in instruction
    assert "Image[2] = MASK" in instruction
    assert "white = editable" in instruction
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
