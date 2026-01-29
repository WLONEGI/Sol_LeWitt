import logging
import json
from typing import Literal

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.types import Command, Send
from langgraph.graph import StateGraph, START
from langchain_core.runnables import RunnableConfig

from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import load_prompt_markdown
from src.shared.schemas import (
    ResearchTask,
    ResearchResult,
    ResearchTaskList
)
from src.core.workflow.state import ResearchSubgraphState
from .common import _update_artifact

logger = logging.getLogger(__name__)

async def research_worker_node(state: ResearchSubgraphState, config: RunnableConfig) -> dict:
    """
    Worker node for executing a single research task.
    """
    task_data = state.get("task")
    if not task_data:
        logger.warning("Research Worker received empty task")
        return {"internal_research_results": []}

    if isinstance(task_data, dict):
        try:
            task = ResearchTask.model_validate(task_data)
        except Exception as e:
            logger.error(f"Failed to validate task data: {e}")
            return {"internal_research_results": []}
    else:
        task = task_data

    task_id = getattr(task, "id", "unknown")
    logger.info(f"Worker executing task {task_id}: {task.perspective}")
    
    try:
        from src.resources.prompts.template import load_prompt_markdown
        from langchain_core.callbacks.manager import adispatch_custom_event
        
        system_prompt = load_prompt_markdown("researcher")
        
        # Dispatch start event
        await adispatch_custom_event(
            "research-worker-start",
            {
                "task_id": task_id,
                "perspective": task.perspective,
                "instruction": task.expected_output
            },
            config=config # Pass config to propagate run_id
        )
        
        instruction = (
            f"You are investigating: '{task.perspective}'.\n"
            f"Requirement: {task.expected_output}\n"
        )
        if task.query_hints:
            instruction += f"Suggested Queries: {', '.join(task.query_hints)}"
            
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=instruction, name="dispatcher")
        ]
        
        # Use Basic Model as requested
        llm = get_llm_by_type("basic")
        grounding_tool = {'google_search': {}}
        llm_with_search = llm.bind(
            tools=[grounding_tool],
            generation_config={"response_modalities": ["TEXT"]}
        )
        
        accumulated_content = ""
        
        # Stream the response
        async for chunk in llm_with_search.astream(messages, config=config):
            content = chunk.content
            if content:
                # Handle list content (rare in streaming but possible)
                if isinstance(content, list):
                    text_chunk = ""
                    for part in content:
                        if isinstance(part, dict) and "text" in part:
                            text_chunk += part["text"]
                        elif isinstance(part, str):
                            text_chunk += part
                    content = text_chunk
                
                accumulated_content += content
                
                # Dispatch delta
                await adispatch_custom_event(
                    "research-worker-delta",
                    {
                        "task_id": task_id,
                        "delta": content
                    },
                    config=config
                )

        # Dispatch end event
        await adispatch_custom_event(
            "research-worker-end",
            {
                "task_id": task_id,
            },
            config=config
        )
        
        res = ResearchResult(
            task_id=task.id,
            perspective=task.perspective,
            report=accumulated_content,
            sources=[], 
            confidence=1.0
        )
        return {"internal_research_results": [res]}
        
    except Exception as e:
        logger.error(f"Worker failed task {task.id}: {e}")
        err_res = ResearchResult(
            task_id=task.id,
            perspective=task.perspective,
            report=f"## Error\nInvestigation failed: {str(e)}",
            sources=[],
            confidence=0.0
        )
        return {"internal_research_results": [err_res]}


def research_manager_node(state: ResearchSubgraphState) -> Command[Literal["research_worker", "__end__"]]:
    """
    Manager Node (Orchestrator).
    """
    logger.info(f"Research Manager active. Decomposed: {state.get('is_decomposed', False)}")

    try:
        step_index, current_step = next(
            (i, step) for i, step in enumerate(state["plan"]) 
            if step["status"] == "in_progress" and step["role"] == "researcher"
        )
    except StopIteration:
        logger.error("Research Manager called but no in_progress step found.")
        return Command(goto="__end__", update={})
    internal_tasks = state.get("internal_research_tasks", [])
    results = state.get("internal_research_results", [])

    if not state.get("is_decomposed"):
        logger.info("Manager: Decomposing research step...")
        
        base_prompt = load_prompt_markdown("research_topic_analyzer")
        full_content = f"{base_prompt}\n\nUser Instruction: {current_step['instruction']}"
        
        llm = get_llm_by_type("reasoning")
        structured_llm = llm.with_structured_output(ResearchTaskList)
        
        try:
            qa_result: ResearchTaskList = structured_llm.invoke(full_content)
            tasks = qa_result.tasks
            if not tasks:
                 raise ValueError("No tasks generated")
        except Exception as e:
            logger.warning(f"Decomposition failed: {e}. Fallback to single task.")
            tasks = [
                ResearchTask(
                   id=1, 
                   perspective="General Investigation", 
                   query_hints=[], 
                   priority="high", 
                   expected_output="Detailed report."
                )
            ]

        logger.info(f"Manager: Generated {len(tasks)} parallel tasks.")
        
        sends = [Send("research_worker", {"task": t.model_dump()}) for t in tasks]
        return Command(
             update={"internal_research_tasks": tasks, "is_decomposed": True, "internal_research_results": []},
             goto=sends
        )

    if len(results) >= len(internal_tasks):
        logger.info("Manager: All tasks completed. Aggregating.")
        results.sort(key=lambda x: x.task_id)
        
        aggregated_content = {
            "tasks": [t.model_dump() for t in internal_tasks],
            "results": [r.model_dump() for r in results]
        }
        content_json = json.dumps(aggregated_content, ensure_ascii=False)
        
        summary_text = f"以下の項目について詳細に調査し、分析レポートを作成しました: {', '.join([r.perspective for r in results])}"
        current_step["result_summary"] = summary_text

        logger.info(f"Research Manager finished. Aggregated {len(results)} results.")
        
        return Command(
            goto="supervisor",
            update={
                "artifacts": _update_artifact(state, f"step_{current_step['id']}_research", content_json),
                "messages": [
                    AIMessage(
                        content=summary_text,
                        additional_kwargs={
                            "ui_type": "worker_result",
                            "role": "researcher", 
                            "status": "completed",
                            "result_summary": summary_text
                        },
                        name="researcher_ui"
                    ),
                    AIMessage(
                        content="Research Report",
                        additional_kwargs={
                            "ui_type": "artifact_view",
                            "artifact_id": f"step_{current_step['id']}_research",
                            "title": "Research Report",
                            "icon": "BookOpen"
                        },
                        name="researcher_artifact"
                    )
                ],
                "internal_research_tasks": [], # Reset
                "internal_research_results": [],
                "is_decomposed": False,
                "plan": state["plan"]
            }
        )
    
    logger.info(f"Manager: Waiting for workers. {len(results)}/{len(internal_tasks)} completed.")
    return Command(update={})


def build_researcher_subgraph():
    """Builds the encapsulated researcher subgraph."""
    workflow = StateGraph(ResearchSubgraphState)
    
    workflow.add_node("manager", research_manager_node)
    workflow.add_node("research_worker", research_worker_node)
    
    workflow.add_edge(START, "manager")
    workflow.add_edge("research_worker", "manager")
    
    return workflow.compile()
