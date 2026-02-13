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
