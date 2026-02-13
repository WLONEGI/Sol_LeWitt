import asyncio
import json
from pathlib import Path

from src.core.workflow.nodes import data_analyst as data_analyst_module


def _base_state(mode: str, instruction: str = "process inputs"):
    return {
        "plan": [
            {
                "id": 1,
                "status": "in_progress",
                "capability": "data_analyst",
                "mode": mode,
                "instruction": instruction,
                "title": "Data Analyst Task",
            }
        ],
        "artifacts": {},
        "messages": [],
    }


def test_data_analyst_template_manifest_extract(monkeypatch):
    events = []

    async def fake_dispatch(name, data, config=None):
        events.append((name, data))

    monkeypatch.setattr(data_analyst_module, "adispatch_custom_event", fake_dispatch)

    state = _base_state("template_manifest_extract", "テンプレートのメタ情報を抽出して")
    state["pptx_context"] = {
        "template_count": 1,
        "primary": {
            "filename": "template.pptx",
            "slide_count": 3,
            "theme": {"name": "Corp"},
        },
    }

    cmd = asyncio.run(data_analyst_module.data_analyst_node(state, {}))
    assert cmd.goto == "supervisor"

    artifact_id = "step_1_data"
    assert artifact_id in cmd.update["artifacts"]
    stored = json.loads(cmd.update["artifacts"][artifact_id])
    assert stored["failed_checks"] == []
    assert stored["output_value"]["template_count"] == 1
    assert len(stored["output_value"]["templates"]) == 1

    start_payload = next(data for name, data in events if name == "data-analyst-start")
    assert start_payload["input"]["mode"] == "template_manifest_extract"
    assert any(name == "data-analyst-output" for name, _ in events)
    assert any(name == "data-analyst-complete" for name, _ in events)


def test_data_analyst_images_to_package_success(monkeypatch):
    events = []

    async def fake_dispatch(name, data, config=None):
        events.append((name, data))

    def fake_download(url: str):
        if url.endswith(".png"):
            return b"png-bytes"
        return None

    class FakePackageTool:
        async def ainvoke(self, args, config=None):
            work_dir = Path(args["work_dir"])
            out_dir = work_dir / "outputs" / "packaged_assets"
            out_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = out_dir / "deck.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 mock")
            return json.dumps({"status": "ok", "pdf_path": str(pdf_path)})

    def fake_upload(file_data, content_type, session_id=None, slide_number=None, object_name=None):
        assert file_data.startswith(b"%PDF")
        return "https://example.com/generated/deck.pdf"

    monkeypatch.setattr(data_analyst_module, "adispatch_custom_event", fake_dispatch)
    monkeypatch.setattr(data_analyst_module, "download_blob_as_bytes", fake_download)
    monkeypatch.setattr(data_analyst_module, "package_visual_assets_tool", FakePackageTool())
    monkeypatch.setattr(data_analyst_module, "upload_to_gcs", fake_upload)

    state = _base_state("images_to_package", "画像をpdf/pptx/zip化して")
    state["attachments"] = [
        {
            "id": "img1",
            "filename": "slide01.png",
            "mime_type": "image/png",
            "url": "https://example.com/slide01.png",
            "kind": "image",
        }
    ]

    cmd = asyncio.run(data_analyst_module.data_analyst_node(state, {}))
    assert cmd.goto == "supervisor"

    stored = json.loads(cmd.update["artifacts"]["step_1_data"])
    assert stored["failed_checks"] == []
    assert any(item["url"] == "https://example.com/generated/deck.pdf" for item in stored["output_files"])
    assert "Upload Trace" in stored["execution_log"]
    code_deltas = [data for name, data in events if name == "data-analyst-code-delta"]
    log_deltas = [data for name, data in events if name == "data-analyst-log-delta"]
    assert code_deltas
    assert any("package_visual_assets_tool" in str(item.get("delta") or "") for item in code_deltas)
    assert log_deltas
    assert any("status\": \"ok\"" in str(item.get("delta") or "") for item in log_deltas)
    assert any(name == "data-analyst-output" and data.get("status") == "completed" for name, data in events)


def test_data_analyst_images_to_package_without_images_fails(monkeypatch):
    async def fake_dispatch(name, data, config=None):
        return None

    monkeypatch.setattr(data_analyst_module, "adispatch_custom_event", fake_dispatch)

    state = _base_state("images_to_package", "画像をpdf/pptx/zip化して")
    cmd = asyncio.run(data_analyst_module.data_analyst_node(state, {}))
    assert cmd.goto == "supervisor"

    stored = json.loads(cmd.update["artifacts"]["step_1_data"])
    assert "missing_dependency" in stored["failed_checks"]
    assert stored["output_files"] == []
    assert stored["output_value"] is None


def test_upload_result_files_rewrites_local_path_to_gcs(monkeypatch, tmp_path):
    output_path = tmp_path / "deck.pdf"
    output_path.write_bytes(b"%PDF-1.4 mock")

    result = data_analyst_module.DataAnalystOutput(
        implementation_code="print('done')",
        execution_log="ok",
        output_value=None,
        failed_checks=[],
        output_files=[{"url": "deck.pdf", "title": "Deck", "mime_type": "application/pdf"}],
    )

    def _fake_upload(file_data, content_type, session_id=None, slide_number=None, object_name=None):
        assert file_data.startswith(b"%PDF")
        assert content_type == "application/pdf"
        assert isinstance(object_name, str)
        return "https://example.com/generated/deck.pdf"

    monkeypatch.setattr(data_analyst_module, "upload_to_gcs", _fake_upload)

    trace = asyncio.run(
        data_analyst_module._upload_result_files_to_gcs(
            result=result,
            workspace_dir=str(Path(tmp_path)),
            output_prefix="generated_assets/session/title",
        )
    )

    assert result.output_files[0].url == "https://example.com/generated/deck.pdf"
    assert trace and "uploaded deck.pdf" in trace[0]


def test_resolve_data_analyst_mode_prefers_template_images_when_package_intent_is_implicit() -> None:
    mode = data_analyst_module._resolve_data_analyst_mode(
        {
            "mode": "images_to_package",
            "instruction": "PPTXテンプレートを解析してマスタースライドを画像化する",
        }
    )
    assert mode == "pptx_master_to_images"


def test_filter_output_files_for_pptx_mode_keeps_only_images() -> None:
    result = data_analyst_module.DataAnalystOutput(
        implementation_code="",
        execution_log="ok",
        output_value={"mode": "pptx_master_to_images"},
        failed_checks=[],
        output_files=[
            {"url": "outputs/master_images/template_master_01.png", "title": "slide1", "mime_type": "image/png"},
            {"url": "outputs/master_images/template.pdf", "title": "tmp-pdf", "mime_type": "application/pdf"},
            {"url": "outputs/master_images/template.pptx", "title": "tmp-pptx", "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"},
        ],
    )

    data_analyst_module._filter_output_files_for_mode(
        mode="pptx_master_to_images",
        result=result,
    )

    assert len(result.output_files) == 1
    assert result.output_files[0].url.endswith(".png")


def test_build_pptx_render_output_files_includes_slide_metadata() -> None:
    output_files = data_analyst_module._build_pptx_render_output_files(
        mode="pptx_slides_to_images",
        image_paths=[
            "/tmp/workspace/outputs/slide_images/template_master_01.png",
            "/tmp/workspace/outputs/slide_images/template_master_02.png",
        ],
        slide_rows=[
            {
                "slide_number": 1,
                "title": "現状分析",
                "texts": ["高齢化率 34.2%", "移動困難者 1.8万人"],
                "layout_name": "Title and Content",
                "layout_placeholders": ["title", "body"],
                "master_name": "Corporate Master",
                "master_texts": ["年度方針", "重点施策"],
            },
            {
                "slide_number": 2,
                "title": "施策案",
                "texts": ["デマンド交通", "MaaS連携"],
                "layout_name": "Picture with Caption",
                "layout_placeholders": ["title", "pic", "body"],
                "master_name": "Corporate Master",
                "master_texts": ["年度方針", "重点施策"],
            },
        ],
    )

    assert len(output_files) == 2
    assert output_files[0]["source_title"] == "現状分析"
    assert output_files[0]["source_texts"] == ["高齢化率 34.2%", "移動困難者 1.8万人"]
    assert output_files[0]["source_layout_name"] == "Title and Content"
    assert output_files[0]["source_layout_placeholders"] == ["title", "body"]
    assert output_files[0]["source_master_name"] == "Corporate Master"
    assert output_files[0]["source_master_texts"] == ["年度方針", "重点施策"]
    assert output_files[0]["source_mode"] == "pptx_slides_to_images"
    assert "source_slide_number" not in output_files[0]
    assert "source_layout_type" not in output_files[0]
    assert "source_layout_kind" not in output_files[0]


def test_extract_visualizer_generated_image_urls_supports_pages_and_characters() -> None:
    dependency_context = {
        "resolved_dependency_artifacts": [
            {
                "producer_capability": "visualizer",
                "content": json.dumps(
                    {
                        "product_type": "design",
                        "design_pages": [
                            {
                                "page_number": 2,
                                "generated_image_url": "https://example.com/page-2.png",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
            {
                "producer_capability": "visualizer",
                "content": json.dumps(
                    {
                        "product_type": "comic",
                        "mode": "character_sheet_render",
                        "characters": [
                            {
                                "character_number": 1,
                                "image_url": "https://example.com/character-1.png",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ]
    }

    urls = data_analyst_module._extract_visualizer_generated_image_urls(dependency_context)

    assert urls == [
        "https://example.com/character-1.png",
        "https://example.com/page-2.png",
    ]
