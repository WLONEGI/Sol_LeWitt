import asyncio
import json

from langchain_core.messages import AIMessage
import langchain_experimental.tools as lc_tools

from src.core.workflow.nodes import data_analyst as data_analyst_module
from src.core.workflow.nodes import common as common_module


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
        "execution_summary": "done",
        "analysis_report": "report",
        "failed_checks": [],
        "output_files": [
            {
                "url": "https://example.com/output.pdf",
                "title": "output",
                "mime_type": "application/pdf"
            }
        ],
        "blueprints": [],
        "visualization_code": None,
        "data_sources": []
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
    assert stored["output_files"][0]["url"] == "https://example.com/output.pdf"
    assert "## 入力" in stored["analysis_report"]
    assert "## 処理" in stored["analysis_report"]
    assert "## 結果" in stored["analysis_report"]
    assert "## 未解決" in stored["analysis_report"]


def test_data_analyst_node_streams_code_and_log(monkeypatch):
    events = []

    async def fake_dispatch(name, data, config=None):
        events.append((name, data))

    payload = _output_payload()
    responses = [
        AIMessage(content="", tool_calls=[{
            "name": "python_repl",
            "args": {"query": "print('hi')"},
            "id": "call-1"
        }]),
        AIMessage(content=json.dumps(payload))
    ]
    fake_llm = FakeLLM(responses)

    monkeypatch.setattr(data_analyst_module, "get_llm_by_type", lambda _: fake_llm)
    monkeypatch.setattr(data_analyst_module, "adispatch_custom_event", fake_dispatch)
    monkeypatch.setattr(common_module.settings, "RESPONSE_FORMAT", "{role}:{content}")
    monkeypatch.setattr(
        lc_tools.PythonREPLTool,
        "invoke",
        lambda self, args, config=None: "ok"
    )

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
            "name": "python_repl",
            "args": {"query": "print('boom')"},
            "id": "call-1"
        }]),
        AIMessage(content=json.dumps(payload))
    ]
    fake_llm = FakeLLM(responses)

    monkeypatch.setattr(data_analyst_module, "get_llm_by_type", lambda _: fake_llm)
    monkeypatch.setattr(data_analyst_module, "adispatch_custom_event", fake_dispatch)
    monkeypatch.setattr(common_module.settings, "RESPONSE_FORMAT", "{role}:{content}")

    def _raise_error(self, args, config=None):
        raise RuntimeError("repl failed")

    monkeypatch.setattr(lc_tools.PythonREPLTool, "invoke", _raise_error)

    cmd = asyncio.run(data_analyst_module.data_analyst_node(_base_state(), {}))
    assert cmd.goto == "supervisor"

    artifact_id = "step_1_data"
    stored = json.loads(cmd.update["artifacts"][artifact_id])
    assert stored["execution_summary"].startswith("Error:")
    assert "tool_execution" in stored["failed_checks"]
    assert stored["output_files"] == []
