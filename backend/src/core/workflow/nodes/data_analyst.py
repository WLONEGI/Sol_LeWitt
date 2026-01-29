import logging
import json
import re
from typing import Literal

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from src.shared.config.settings import settings
from src.shared.config import AGENT_LLM_MAP
from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import apply_prompt_template
from src.shared.schemas import DataAnalystOutput
from src.core.workflow.state import State
from .common import create_worker_response
from langchain_core.runnables import RunnableConfig
import logging

logger = logging.getLogger(__name__)

def data_analyst_node(state: dict, config: RunnableConfig) -> Command[Literal["supervisor"]]:
    """
    Node for the Data Analyst agent.
    
    Uses Code Execution for calculations and proceeds to Supervisor.
    """
    logger.info("Data Analyst starting task")
    try:
        step_index, current_step = next(
            (i, step) for i, step in enumerate(state["plan"]) 
            if step["status"] == "in_progress" and step["role"] == "data_analyst"
        )
    except StopIteration:
        logger.error("Data Analyst called but no in_progress step found.")
        return Command(goto="supervisor", update={})

    context = f"Instruction: {current_step['instruction']}\n\nAvailable Artifacts: {json.dumps(state.get('artifacts', {}), default=str)}"

    messages = apply_prompt_template("data_analyst", state)
    messages.append(HumanMessage(content=context, name="supervisor"))

    from langchain_experimental.tools import PythonREPLTool
    
    llm = get_llm_by_type(AGENT_LLM_MAP["data_analyst"])
    
    # Use standard PythonREPLTool
    repl_tool = PythonREPLTool()
    
    # Bind tool to LLM
    llm_with_code_exec = llm.bind_tools([repl_tool])

    try:
        messages[-1].content += "\n\nIMPORTANT: After performing necessary calculations with code, you MUST output the final result in valid JSON format matching the DataAnalystOutput structure."
        
        response = llm_with_code_exec.invoke(messages, config=config)
        content = response.content
        
        # 0. Handle Empty Response (Safety/Recitation Block)
        if not content and not response.tool_calls:
            logger.warning("Data Analyst returned an empty response. Likely blocked by safety settings or recursion limit.")
            result_summary = "AIの回答が安全フィルター等の理由で制限されました。指示内容を調整して再試行してください。"
            content_json = json.dumps({"error": "Empty Response", "raw_output": ""}, ensure_ascii=False)
            raise ValueError("Model returned empty output.")

        # DEBUG LOGS (Keep for now)
        print(f"DEBUG_DATA_ANALYST: tool_calls={response.tool_calls}")
        
        content_json = ""
        result_summary = ""

        # 1. Handle Tool Calls (Code Execution)
        if response.tool_calls:
            logger.info(f"Data Analyst triggered tool calls: {len(response.tool_calls)}")
            tool_outputs = []
            
            for tool_call in response.tool_calls:
                if tool_call["name"] == "python_repl":
                    # Execute code
                    try:
                        # Pass config!
                        output = repl_tool.invoke(tool_call["args"], config=config)
                        tool_outputs.append(f"Output for {tool_call['name']}:\n{output}")
                    except Exception as e:
                        logger.error(f"Tool execution failed: {e}")
                        tool_outputs.append(f"Error executing {tool_call['name']}: {e}")
            
            # Combine outputs
            full_output = "\n".join(tool_outputs)
            result_summary = f"Pythonコードの実行を完了しました。結果:\n{full_output}"
            
            # Data Analyst often uses code results to then generate the JSON.
            # If it stops after tool call, we might need another turn, 
            # but for now we'll wrap the raw result.
            content_json = json.dumps({
                "execution_summary": result_summary,
                "analysis_report": f"Code Output:\n```\n{full_output}\n```",
                "blueprints": [],
                "visualization_code": str(response.tool_calls[0]["args"].get("query", ""))
            }, ensure_ascii=False)
            
        # 2. Handle Text Content (Fallback or standard JSON)
        else:
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        text_parts.append(part["text"])
                    elif isinstance(part, str):
                        text_parts.append(part)
                content = "".join(text_parts)
            
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                try:
                    result = DataAnalystOutput.model_validate_json(json_match.group(0))
                    content_json = result.model_dump_json() 
                    logger.info(f"✅ Data Analyst generated {len(result.blueprints)} blueprints")
                    result_summary = result.execution_summary
                except Exception as e:
                    logger.warning(f"Parsed JSON failed validation: {e}. Returning raw content.")
                    content_json = json.dumps({
                        "execution_summary": "Validation Failed",
                        "analysis_report": content,
                        "error": str(e)
                    }, ensure_ascii=False)
                    result_summary = f"分析データの構造化に失敗しました: {e}"
            else:
                 logger.warning("No JSON found in Data Analyst output. Returning raw content.")
                 content_json = json.dumps({
                     "execution_summary": "No JSON found",
                     "analysis_report": content
                 }, ensure_ascii=False)
                 result_summary = "分析は行われましたが、構造化されたデータ（JSON）が見つかりませんでした。"
                 
    except Exception as e:
        logger.error(f"Data Analyst failed: {e}")
        content_json = json.dumps({"error": str(e)}, ensure_ascii=False)
        result_summary = f"Error: {str(e)}"

    current_step["result_summary"] = result_summary
    
    # Determine error status based on result_summary content as a simple heuristic
    # since data_analyst captures errors in output text often
    is_error = "Error:" in result_summary or "Validation Failed" in content_json

    return create_worker_response(
        role="data_analyst",
        content_json=content_json,
        result_summary=result_summary,
        current_step_id=current_step['id'],
        state=state,
        artifact_key_suffix="data",
        artifact_title="Data Analysis Result",
        artifact_icon="BarChart",
        is_error=is_error
    )
