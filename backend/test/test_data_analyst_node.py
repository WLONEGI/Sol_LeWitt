import asyncio
import json
from pathlib import Path

from langchain_core.messages import AIMessage

from src.core.workflow.nodes import data_analyst as data_analyst_module
from src.core.workflow.nodes import common as common_module
from src.shared.schemas import DataAnalystOutput


class FakeLLM:
    def __init__(self, responses):
        self._responses = list(responses)
        self._index = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages, config=None):
        if self._index >= len(self._responses):
            return AIMessage(content="")
        response = self._responses[self._index]
        self._index += 1
        return response


def _base_state():
    return {
        "plan": [
            {
                "id": 1,
                "status": "in_progress",
                "capability": "data_analyst",
                "instruction": "process inputs",
                "title": "Data Analyst Task"
            }
        ],
        "artifacts": {},
        "messages": []
    }


def _output_payload():
    return {
        "implementation_code": "print('done')",
        "execution_log": "ok",
        "output_value": {"status": "done"},
        "failed_checks": [],
        "output_files": [],
    }


def test_data_analyst_node_outputs_json(monkeypatch):
    events = []

    async def fake_dispatch(name, data, config=None):
        events.append((name, data))

    payload = _output_payload()
    fake_llm = FakeLLM([AIMessage(content=json.dumps(payload))])

    monkeypatch.setattr(data_analyst_module, "get_llm_by_type", lambda _: fake_llm)
    monkeypatch.setattr(data_analyst_module, "adispatch_custom_event", fake_dispatch)
    monkeypatch.setattr(common_module.settings, "RESPONSE_FORMAT", "{role}:{content}")

    cmd = asyncio.run(data_analyst_module.data_analyst_node(_base_state(), {}))

    assert cmd.goto == "supervisor"
    assert any(name == "data-analyst-start" for name, _ in events)
    assert any(name == "data-analyst-output" for name, _ in events)
    assert any(name == "data-analyst-complete" for name, _ in events)
    start_payload = next(data for name, data in events if name == "data-analyst-start")
    assert start_payload["input"]["mode"] == "python_pipeline"
    assert "auto_task" not in start_payload["input"]

    artifact_id = "step_1_data"
    assert artifact_id in cmd.update["artifacts"]
    stored = json.loads(cmd.update["artifacts"][artifact_id])
    assert stored["implementation_code"] == "print('done')"
    assert stored["execution_log"] == "ok"
    assert stored["output_value"]["status"] == "done"
    assert stored["failed_checks"] == []


def test_data_analyst_node_streams_code_and_log(monkeypatch):
    events = []

    async def fake_dispatch(name, data, config=None):
        events.append((name, data))

    payload = _output_payload()
    responses = [
        AIMessage(content="", tool_calls=[{
            "name": "python_repl_tool",
            "args": {"code": "print('hi')"},
            "id": "call-1"
        }]),
        AIMessage(content=json.dumps(payload))
    ]
    fake_llm = FakeLLM(responses)

    monkeypatch.setattr(data_analyst_module, "get_llm_by_type", lambda _: fake_llm)
    monkeypatch.setattr(data_analyst_module, "adispatch_custom_event", fake_dispatch)
    monkeypatch.setattr(common_module.settings, "RESPONSE_FORMAT", "{role}:{content}")

    class _FakePythonTool:
        async def ainvoke(self, args, config=None):
            return "ok"

    monkeypatch.setattr(data_analyst_module, "python_repl_tool", _FakePythonTool())

    cmd = asyncio.run(data_analyst_module.data_analyst_node(_base_state(), {}))

    assert cmd.goto == "supervisor"
    code_deltas = [data for name, data in events if name == "data-analyst-code-delta"]
    log_deltas = [data for name, data in events if name == "data-analyst-log-delta"]

    assert any("print('hi')" in (d.get("delta") or "") for d in code_deltas)
    assert any("ok" in (d.get("delta") or "") for d in log_deltas)


def test_data_analyst_partial_success_is_treated_as_failure(monkeypatch):
    events = []

    async def fake_dispatch(name, data, config=None):
        events.append((name, data))

    payload = _output_payload()
    responses = [
        AIMessage(content="", tool_calls=[{
            "name": "python_repl_tool",
            "args": {"code": "print('boom')"},
            "id": "call-1"
        }]),
        AIMessage(content=json.dumps(payload))
    ]
    fake_llm = FakeLLM(responses)

    monkeypatch.setattr(data_analyst_module, "get_llm_by_type", lambda _: fake_llm)
    monkeypatch.setattr(data_analyst_module, "adispatch_custom_event", fake_dispatch)
    monkeypatch.setattr(common_module.settings, "RESPONSE_FORMAT", "{role}:{content}")

    class _FailingPythonTool:
        async def ainvoke(self, args, config=None):
            raise RuntimeError("repl failed")

    monkeypatch.setattr(data_analyst_module, "python_repl_tool", _FailingPythonTool())

    cmd = asyncio.run(data_analyst_module.data_analyst_node(_base_state(), {}))
    assert cmd.goto == "supervisor"

    artifact_id = "step_1_data"
    stored = json.loads(cmd.update["artifacts"][artifact_id])
    assert "Error executing python_repl" in stored["execution_log"]
    assert "tool_execution" in stored["failed_checks"]
    assert stored["output_files"] == []


def test_upload_result_files_rewrites_local_path_to_gcs(monkeypatch, tmp_path):
    output_path = tmp_path / "deck.pdf"
    output_path.write_bytes(b"%PDF-1.4 mock")

    result = DataAnalystOutput(
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
