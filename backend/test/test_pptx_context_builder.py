import base64
import io
import zipfile

import pytest

from src.app.app import _build_pptx_context


def _build_minimal_pptx_bytes() -> bytes:
    slide_1 = """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>Template Title</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/slides/slide1.xml", slide_1)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_build_pptx_context_from_attachment(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _build_minimal_pptx_bytes()

    def _fake_download(_: str) -> bytes:
        return payload

    monkeypatch.setattr("src.app.app.download_blob_as_bytes", _fake_download)

    context = await _build_pptx_context(
        attachments=[
            {
                "kind": "pptx",
                "filename": "template.pptx",
                "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "url": "https://example.com/template.pptx",
            }
        ],
        pptx_template_base64=None,
    )

    assert context is not None
    assert context["template_count"] == 1
    assert context["primary"]["filename"] == "template.pptx"
    assert context["primary"]["slide_count"] == 1


@pytest.mark.asyncio
async def test_build_pptx_context_from_legacy_base64() -> None:
    payload = _build_minimal_pptx_bytes()
    encoded = base64.b64encode(payload).decode("utf-8")

    context = await _build_pptx_context(
        attachments=[],
        pptx_template_base64=encoded,
    )

    assert context is not None
    assert context["template_count"] == 1
    assert context["primary"]["filename"] == "legacy_template.pptx"
    assert context["primary"]["slide_count"] == 1
