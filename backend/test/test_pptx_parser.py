import io
import zipfile

from src.domain.designer.pptx_parser import extract_pptx_context


def _build_minimal_pptx_bytes() -> bytes:
    slide_1 = """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>Title One</a:t></a:r></a:p>
          <a:p><a:r><a:t>Body A</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
"""
    slide_2 = """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>Second Slide</a:t></a:r></a:p>
          <a:p><a:r><a:t>Body B</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
"""
    theme = """<?xml version="1.0" encoding="UTF-8"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Custom Theme">
  <a:themeElements>
    <a:clrScheme name="Custom Colors">
      <a:accent1><a:srgbClr val="112233"/></a:accent1>
      <a:accent2><a:srgbClr val="445566"/></a:accent2>
      <a:accent3><a:srgbClr val="778899"/></a:accent3>
    </a:clrScheme>
    <a:fontScheme name="Custom Fonts">
      <a:majorFont><a:latin typeface="Aptos Display"/></a:majorFont>
      <a:minorFont><a:latin typeface="Aptos"/></a:minorFont>
    </a:fontScheme>
  </a:themeElements>
</a:theme>
"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/slides/slide1.xml", slide_1)
        archive.writestr("ppt/slides/slide2.xml", slide_2)
        archive.writestr("ppt/theme/theme1.xml", theme)
    return buffer.getvalue()


def _build_pptx_with_layout_metadata() -> bytes:
    slide_1 = """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>Cover Title</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
"""
    slide_2 = """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>Body Slide</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
"""
    slide_1_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>
"""
    slide_2_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout2.xml"/>
</Relationships>
"""
    slide_layout_1 = """<?xml version="1.0" encoding="UTF-8"?>
<p:sldLayout xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
             type="title">
  <p:cSld name="Title Slide">
    <p:spTree>
      <p:sp><p:nvSpPr><p:nvPr><p:ph type="ctrTitle"/></p:nvPr></p:nvSpPr></p:sp>
      <p:sp><p:nvSpPr><p:nvPr><p:ph type="subTitle"/></p:nvPr></p:nvSpPr></p:sp>
    </p:spTree>
  </p:cSld>
</p:sldLayout>
"""
    slide_layout_2 = """<?xml version="1.0" encoding="UTF-8"?>
<p:sldLayout xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
             type="picTx">
  <p:cSld name="Picture with Caption">
    <p:spTree>
      <p:sp><p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr></p:sp>
      <p:sp><p:nvSpPr><p:nvPr><p:ph type="pic"/></p:nvPr></p:nvSpPr></p:sp>
      <p:sp><p:nvSpPr><p:nvPr><p:ph type="body"/></p:nvPr></p:nvSpPr></p:sp>
    </p:spTree>
  </p:cSld>
</p:sldLayout>
"""
    layout_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>
"""
    slide_master = """<?xml version="1.0" encoding="UTF-8"?>
<p:sldMaster xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
             xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld name="Corporate Master">
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:p><a:r><a:t>Master Header</a:t></a:r></a:p>
          <a:p><a:r><a:t>Master Footer</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sldMaster>
"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/slides/slide1.xml", slide_1)
        archive.writestr("ppt/slides/slide2.xml", slide_2)
        archive.writestr("ppt/slides/_rels/slide1.xml.rels", slide_1_rels)
        archive.writestr("ppt/slides/_rels/slide2.xml.rels", slide_2_rels)
        archive.writestr("ppt/slideLayouts/slideLayout1.xml", slide_layout_1)
        archive.writestr("ppt/slideLayouts/slideLayout2.xml", slide_layout_2)
        archive.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", layout_rels)
        archive.writestr("ppt/slideLayouts/_rels/slideLayout2.xml.rels", layout_rels)
        archive.writestr("ppt/slideMasters/slideMaster1.xml", slide_master)
    return buffer.getvalue()


def test_extract_pptx_context_reads_slides_and_theme() -> None:
    context = extract_pptx_context(
        _build_minimal_pptx_bytes(),
        filename="sample.pptx",
        source_url="https://example.com/sample.pptx",
    )

    assert context["filename"] == "sample.pptx"
    assert context["source_url"] == "https://example.com/sample.pptx"
    assert context["slide_count"] == 2
    assert context["slides"][0]["slide_number"] == 1
    assert context["slides"][0]["title"] == "Title One"
    assert context["slides"][1]["title"] == "Second Slide"
    assert context["theme"]["name"] == "Custom Theme"
    assert context["theme"]["major_font"] == "Aptos Display"
    assert context["theme"]["minor_font"] == "Aptos"
    assert context["theme"]["accent_colors"][:2] == ["#112233", "#445566"]


def test_extract_pptx_context_includes_layout_and_master_metadata() -> None:
    context = extract_pptx_context(_build_pptx_with_layout_metadata())

    assert context["slide_count"] == 2
    assert context["slides"][0]["layout_name"] == "Title Slide"
    assert context["slides"][0]["layout_type"] == "title"
    assert context["slides"][0]["layout_kind"] == "cover"
    assert context["slides"][0]["layout_placeholders"] == ["ctrtitle", "subtitle"]
    assert context["slides"][0]["master_name"] == "Corporate Master"
    assert context["slides"][0]["master_texts"] == ["Master Header", "Master Footer"]

    assert context["slides"][1]["layout_name"] == "Picture with Caption"
    assert context["slides"][1]["layout_type"] == "picTx"
    assert context["slides"][1]["layout_kind"] == "content_with_image"
    assert context["slides"][1]["layout_placeholders"] == ["title", "pic", "body"]
    assert context["slides"][1]["master_name"] == "Corporate Master"
    assert context["slides"][1]["master_texts"] == ["Master Header", "Master Footer"]
