import logging
import json
import re
from typing import Any, Literal

from langgraph.types import Command
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage, RemoveMessage
from langchain_core.callbacks.manager import adispatch_custom_event

from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import apply_prompt_template
from src.core.workflow.state import State
from src.core.workflow.step_v2 import capability_from_any, normalize_step_v2, plan_steps_for_ui

logger = logging.getLogger(__name__)

MAX_MESSAGES = 40
KEEP_LAST_MESSAGES = 10
MAX_ARTIFACTS = 20
MAX_RETHINK_PER_TASK = 2
MAX_RETHINK_PER_TURN = 6
CAPABILITY_TO_DESTINATION = {
    "writer": "writer",
    "researcher": "researcher",
    "visualizer": "visualizer",
    "data_analyst": "data_analyst",
}
SUPERVISOR_RETRY_HINT_MARKER = "[SUPERVISOR_RETRY_HINT]"


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text")
                if isinstance(value, str):
                    parts.append(value)
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    if isinstance(content, dict):
        value = content.get("text")
        if isinstance(value, str):
            return value
    return ""


def _extract_latest_user_text(state: State) -> str:
    messages = state.get("messages", []) or []
    for msg in reversed(messages):
        msg_type = getattr(msg, "type", None)
        if msg_type == "human":
            return _extract_text_from_content(getattr(msg, "content", ""))
        if isinstance(msg, dict) and str(msg.get("role", "")) == "user":
            return _extract_text_from_content(msg.get("content", ""))
    return ""


def _is_regenerate_request(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in text for keyword in ("作り直", "再生成", "やり直し")) or "regenerate" in lowered


def _detect_intent(text: str) -> str:
    lowered = text.lower()
    if _is_regenerate_request(text):
        return "regenerate"
    if any(keyword in text for keyword in ("修正", "変更", "調整", "直して", "改善")) or any(
        keyword in lowered for keyword in ("fix", "refine", "update")
    ):
        return "refine"
    return "new"


def _detect_target_scope(text: str) -> dict[str, Any]:
    scope: dict[str, Any] = {}
    slide_numbers = [int(m) for m in re.findall(r"(\d+)\s*(?:枚目|スライド)", text)]
    page_numbers = [int(m) for m in re.findall(r"(\d+)\s*ページ", text)]
    panel_numbers = [int(m) for m in re.findall(r"(\d+)\s*コマ", text)]
    character_ids = [
        m.strip()
        for m in re.findall(r"(?:キャラ|キャラクター)\s*([A-Za-z0-9_\-ぁ-んァ-ン一-龥]+)", text)
    ]
    explicit_asset_unit_ids = [
        m.strip()
        for m in re.findall(r"asset[_\s-]?unit[:：]?\s*([A-Za-z0-9:_\-]+)", text, flags=re.IGNORECASE)
    ]

    if slide_numbers:
        scope["slide_numbers"] = sorted(set(slide_numbers))
    if page_numbers:
        scope["page_numbers"] = sorted(set(page_numbers))
    if panel_numbers:
        scope["panel_numbers"] = sorted(set(panel_numbers))
    if character_ids:
        scope["character_ids"] = sorted(set(character_ids))

    asset_units: list[dict[str, Any]] = []
    asset_unit_ids: list[str] = []

    for number in sorted(set(slide_numbers)):
        unit_id = f"slide:{number}"
        asset_units.append({"unit_id": unit_id, "unit_kind": "slide", "unit_index": number})
        asset_unit_ids.append(unit_id)
    for number in sorted(set(page_numbers)):
        unit_id = f"page:{number}"
        asset_units.append({"unit_id": unit_id, "unit_kind": "page", "unit_index": number})
        asset_unit_ids.append(unit_id)
    for number in sorted(set(panel_numbers)):
        unit_id = f"panel:{number}"
        asset_units.append({"unit_id": unit_id, "unit_kind": "panel", "unit_index": number})
        asset_unit_ids.append(unit_id)
    for unit_id in explicit_asset_unit_ids:
        if unit_id not in asset_unit_ids:
            asset_unit_ids.append(unit_id)
            asset_units.append({"unit_id": unit_id, "unit_kind": "image", "unit_index": None})

    if asset_unit_ids:
        scope["asset_unit_ids"] = asset_unit_ids
    if asset_units:
        scope["asset_units"] = asset_units

    return scope


def _hydrate_target_scope_from_ledger(
    scope: dict[str, Any],
    asset_unit_ledger: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(scope, dict):
        return {}
    ledger = asset_unit_ledger or {}
    if not isinstance(ledger, dict) or not ledger:
        return scope

    next_scope = dict(scope)
    unit_ids: list[str] = list(next_scope.get("asset_unit_ids") or [])

    for number in next_scope.get("slide_numbers") or []:
        if isinstance(number, int):
            unit_ids.append(f"slide:{number}")
    for number in next_scope.get("page_numbers") or []:
        if isinstance(number, int):
            unit_ids.append(f"page:{number}")
    for number in next_scope.get("panel_numbers") or []:
        if isinstance(number, int):
            unit_ids.append(f"panel:{number}")

    if not unit_ids and len(ledger) == 1:
        only_id = next(iter(ledger.keys()))
        if isinstance(only_id, str) and only_id:
            unit_ids = [only_id]

    deduped_ids: list[str] = []
    for unit_id in unit_ids:
        if isinstance(unit_id, str) and unit_id and unit_id not in deduped_ids:
            deduped_ids.append(unit_id)

    if deduped_ids:
        next_scope["asset_unit_ids"] = deduped_ids

    asset_units: list[dict[str, Any]] = []
    existing_units = next_scope.get("asset_units")
    if isinstance(existing_units, list):
        for unit in existing_units:
            if isinstance(unit, dict):
                asset_units.append(dict(unit))

    existing_ids = {str(unit.get("unit_id")) for unit in asset_units if isinstance(unit.get("unit_id"), str)}
    for unit_id in deduped_ids:
        entry = ledger.get(unit_id)
        if isinstance(entry, dict):
            unit = dict(entry)
            unit.setdefault("unit_id", unit_id)
            if unit_id not in existing_ids:
                asset_units.append(unit)
                existing_ids.add(unit_id)

    if asset_units:
        next_scope["asset_units"] = asset_units

    return next_scope


def _next_step_id(plan: list[dict[str, Any]]) -> int:
    max_id = 0
    for step in plan:
        value = step.get("id") if isinstance(step, dict) else None
        if isinstance(value, int):
            max_id = max(max_id, value)
    return max_id + 1

def _normalize_plan_statuses(plan: list[dict]) -> None:
    """Normalize statuses in-place to canonical values."""
    for step in plan:
        status = step.get("status")
        if status not in {"pending", "in_progress", "completed", "blocked"}:
            step["status"] = "pending"


def _looks_like_error_text(text: str | None) -> bool:
    if not isinstance(text, str):
        return False
    lowered = text.lower()
    return "error" in lowered or "失敗" in text or "エラー" in text or "failed" in lowered


def _result_summary_indicates_failure(text: str | None) -> bool:
    if not isinstance(text, str):
        return False
    trimmed = text.strip()
    if not trimmed:
        return False
    if _looks_like_error_text(trimmed):
        return True

    lowered = trimmed.lower()
    keyword_groups = (
        "failure",
        "exception",
        "traceback",
        "timeout",
        "timed out",
        "not found",
        "missing",
        "unable to",
        "cannot",
        "invalid",
        "forbidden",
        "要修正",
        "未完了",
        "見つかりません",
        "不足",
        "生成でき",
        "作成でき",
        "実行でき",
        "中断",
        "リトライ",
        "再試行",
    )
    return any(keyword in lowered or keyword in trimmed for keyword in keyword_groups)


def _resolve_origin_step_id(step: dict) -> int:
    origin_step_id = step.get("origin_step_id", step.get("id"))
    if isinstance(origin_step_id, int):
        return origin_step_id
    return int(step.get("id") or 0)


def _strip_supervisor_retry_hint(instruction: str) -> str:
    marker_index = instruction.find(SUPERVISOR_RETRY_HINT_MARKER)
    if marker_index >= 0:
        return instruction[:marker_index].rstrip()
    return instruction.strip()


def _build_retry_instruction(
    *,
    instruction: str | None,
    result_summary: str | None,
    failed_checks: list[str],
    step_retry_count: int,
) -> str:
    base_instruction = _strip_supervisor_retry_hint(instruction or "")
    if not base_instruction:
        base_instruction = "タスクを実行する"

    notes: list[str] = []
    if isinstance(result_summary, str) and result_summary.strip():
        notes.append(f"前回結果: {result_summary.strip()}")
    if failed_checks:
        notes.append(f"失敗チェック: {', '.join(sorted(set(failed_checks)))}")
    if not notes:
        notes.append("前回結果: 出力が要件を満たしませんでした。")

    retries_left = max(MAX_RETHINK_PER_TASK - step_retry_count, 0)
    guidance = (
        "修正指示: 上記の失敗要因を解消して同じ成果物を再生成してください。"
        "出力が不完全な場合も完了扱いにしないでください。"
    )
    return (
        f"{base_instruction}\n\n"
        f"{SUPERVISOR_RETRY_HINT_MARKER}\n"
        f"{' / '.join(notes)}\n"
        f"{guidance}\n"
        f"残り再試行回数: {retries_left}"
    )


def _resolve_worker_destination(step: dict) -> str | None:
    capability = step.get("capability")
    if isinstance(capability, str):
        return CAPABILITY_TO_DESTINATION.get(capability)
    return None


def _artifact_suffix_for_step(step: dict) -> str:
    capability = step.get("capability")
    if capability == "writer":
        return "story"
    if capability == "visualizer":
        return "visual"
    if capability == "researcher":
        return "research"
    if capability == "data_analyst":
        return "data"
    return "output"


def _extract_failure_metadata(current_step: dict, artifact_value: object) -> tuple[bool, list[str], str | None]:
    failed = False
    failed_checks: list[str] = []
    notes: str | None = None

    result_summary = current_step.get("result_summary")
    if _result_summary_indicates_failure(result_summary if isinstance(result_summary, str) else None):
        failed = True
        notes = result_summary if isinstance(result_summary, str) else notes

    if artifact_value is None:
        if failed and not failed_checks:
            failed_checks = ["worker_execution"]
        return failed, failed_checks, notes

    parsed = artifact_value
    if isinstance(artifact_value, str):
        if _looks_like_error_text(artifact_value):
            failed = True
            notes = artifact_value
        try:
            parsed = json.loads(artifact_value)
        except Exception:
            parsed = artifact_value

    if isinstance(parsed, dict):
        if parsed.get("error"):
            failed = True
            notes = str(parsed.get("notes") or parsed.get("error"))
        raw_checks = parsed.get("failed_checks")
        if isinstance(raw_checks, list):
            normalized_checks = [str(item) for item in raw_checks if isinstance(item, str)]
            if normalized_checks:
                failed = True
                failed_checks.extend(normalized_checks)
        execution_summary = parsed.get("execution_summary")
        if _result_summary_indicates_failure(execution_summary if isinstance(execution_summary, str) else None):
            failed = True
            if not notes and isinstance(execution_summary, str):
                notes = execution_summary
        analysis_report = parsed.get("analysis_report")
        if _result_summary_indicates_failure(analysis_report if isinstance(analysis_report, str) else None):
            failed = True
            if not notes and isinstance(analysis_report, str):
                notes = analysis_report

    if failed and not failed_checks:
        failed_checks = ["worker_execution"]
    failed_checks = sorted(set(failed_checks))
    return failed, failed_checks, notes

def _merge_updates(*updates: dict) -> dict:
    """Merge update dicts while concatenating messages."""
    merged: dict = {}
    for update in updates:
        if not update:
            continue
        for key, value in update.items():
            if key == "messages":
                merged.setdefault("messages", []).extend(value)
            elif key == "artifacts":
                prev = merged.get("artifacts", {})
                merged["artifacts"] = {**prev, **value}
            else:
                merged[key] = value
    return merged

def _format_messages_for_summary(messages: list) -> str:
    lines = []
    for m in messages:
        if getattr(m, "type", None) in ("human", "ai", "system"):
            lines.append(f"{m.type}: {m.content}")
    return "\n".join(lines)

async def _compact_state_if_needed(state: State, config: RunnableConfig) -> dict | None:
    """Summarize and delete old messages using RemoveMessage."""
    try:
        messages = state.get("messages", [])
        if len(messages) <= MAX_MESSAGES:
            return None

        old_messages = messages[:-KEEP_LAST_MESSAGES]
        removable = [m for m in old_messages if getattr(m, "id", None)]
        if not removable:
            return None

        summary_source = _format_messages_for_summary(old_messages)
        if not summary_source:
            return None

        previous_summary = state.get("summary") or ""
        prompt = (
            "Summarize the following conversation briefly in Japanese, focusing on "
            "user intent, decisions, and produced artifacts.\n\n"
            f"Existing summary (if any):\n{previous_summary}\n\n"
            f"New conversation to summarize:\n{summary_source}"
        )

        llm = get_llm_by_type("basic")
        stream_config = config.copy()
        stream_config["run_name"] = "supervisor_summarizer"

        summary_response = await llm.ainvoke([SystemMessage(content=prompt)], config=stream_config)
        summary_text = (summary_response.content or "").strip()
        if not summary_text:
            return None

        # Remove any prior summary messages that are old enough to be in the removable set
        removal_ids = {
            m.id
            for m in old_messages
            if getattr(m, "id", None) and getattr(m, "name", "") == "summary"
        }
        removal_ids.update({m.id for m in removable})
        remove_ops = [RemoveMessage(id=mid) for mid in removal_ids]

        return {
            "messages": remove_ops + [
                SystemMessage(content=f"Conversation Summary:\n{summary_text}", name="summary")
            ],
            "summary": summary_text
        }
    except Exception as e:
        logger.warning(f"State compaction failed: {e}")
        return None

def _prune_artifacts_if_needed(state: State) -> dict | None:
    """Remove oldest artifacts by setting value=None (see reducer)."""
    artifacts = state.get("artifacts", {})
    if len(artifacts) <= MAX_ARTIFACTS:
        return None
    keys = list(artifacts.keys())
    to_remove = keys[:-MAX_ARTIFACTS]
    if not to_remove:
        return None
    return {"artifacts": {k: None for k in to_remove}}

async def _generate_supervisor_report(
    state: State,
    config: RunnableConfig,
    is_final: bool = False,
    report_event: str = "step_completed",
) -> str:
    """Generate a dynamic status report using the basic LLM."""
    try:
        plan = state.get("plan", [])
        _normalize_plan_statuses(plan)
        
        prompt_name = "supervisor"
        enriched_state = state.copy()

        if is_final:
            prompt_name = "supervisor_final"
            # Summarize plan
            plan_lines = []
            for step in plan:
                status_emoji = "✅" if step.get("status") == "completed" else "⏳"
                plan_lines.append(f"- {status_emoji} {step.get('title')}: {step.get('result_summary', '完了')}")
            enriched_state["PLAN_SUMMARY"] = "\n".join(plan_lines)
            
            # Summarize artifacts (just keys/types to avoid token bloom)
            artifacts = state.get("artifacts", {})
            artifact_keys = [k for k in artifacts.keys() if artifacts[k] is not None]
            enriched_state["ARTIFACTS_SUMMARY"] = ", ".join(artifact_keys) if artifact_keys else "なし"
        else:
            # Identify last achievement
            last_step = None
            for step in reversed(plan):
                if step.get("status") == "completed":
                    last_step = step
                    break
            
            # Identify next objective
            next_step = None
            for step in plan:
                if step.get("status") == "in_progress":
                    next_step = step
                    break
            
            # Default fallback values
            last_achievement = "制作の準備と計画の立案"
            if last_step:
                summary = last_step.get("result_summary") or last_step.get("description", "")
                last_achievement = f"{last_step.get('title', '前の工程')}: {summary}"
                
            next_objective = "全体構成の検討"
            if next_step:
                next_objective = f"{next_step.get('title', '次の工程')}: {next_step.get('instruction', '')}"

            # Enrich state with context variables for the prompt
            enriched_state["REPORT_EVENT"] = report_event
            enriched_state["LAST_ACHIEVEMENT"] = last_achievement
            enriched_state["NEXT_OBJECTIVE"] = next_objective

        # Generate messages using only the specific context (no message history)
        # to prevent the "basic" model from hallucinating or summarizing the entire plan.
        # Use HumanMessage because Gemini API requires at least one user-role message.
        messages = [HumanMessage(content=apply_prompt_template(prompt_name, enriched_state)[0].content)]
        # Use basic model for status reports to save cost/latency
        llm = get_llm_by_type("basic")
        
        # Use astream to ensure events are emitted
        response_content = ""
        # Add run_name for better visibility in stream events
        stream_config = config.copy()
        stream_config["run_name"] = "supervisor"
        
        async for chunk in llm.astream(messages, config=stream_config):
            if chunk.content:
                if isinstance(chunk.content, list):
                    for part in chunk.content:
                        if isinstance(part, dict) and "text" in part:
                            response_content += part["text"]
                        elif isinstance(part, str):
                            response_content += part
                else:
                    response_content += str(chunk.content)
            
        return response_content
    except Exception as e:
        logger.error(f"Failed to generate supervisor report: {e}")
        return "進捗を確認しました。続いて次の制作工程に進みます。"

async def _dispatch_plan_update(plan: list[dict], config: RunnableConfig) -> None:
    """Emit the latest plan to the frontend."""
    try:
        await adispatch_custom_event(
            "plan_update",
            {
                "plan": plan_steps_for_ui(plan),
                "ui_type": "plan_update",
                "title": "Execution Plan",
                "description": "The updated execution plan."
            },
            config=config
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch plan update: {e}")


async def _dispatch_plan_step_started(step: dict, config: RunnableConfig) -> None:
    """Emit step-start event for timeline grouping."""
    try:
        await adispatch_custom_event(
            "data-plan_step_started",
            {
                "step_id": step.get("id"),
                "title": step.get("title"),
                "status": "in_progress",
            },
            config=config,
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch plan step started: {e}")


async def _dispatch_plan_step_ended(step: dict, status: str, config: RunnableConfig) -> None:
    """Emit step-end event for timeline grouping."""
    try:
        await adispatch_custom_event(
            "data-plan_step_ended",
            {
                "step_id": step.get("id"),
                "title": step.get("title"),
                "status": status,
            },
            config=config,
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch plan step ended: {e}")


async def retry_or_alt_mode_node(
    state: State, config: RunnableConfig
) -> Command[Literal["researcher", "writer", "visualizer", "data_analyst", "supervisor", "__end__"]]:
    """
    Retry policy:
      - first retry: same mode
      - second retry: append fallback step
      - exceed limits: end
    """
    product_type = state.get("product_type") if isinstance(state.get("product_type"), str) else None
    plan = [
        normalize_step_v2(
            dict(step),
            product_type=product_type,
            fallback_capability=capability_from_any(dict(step)),
            fallback_instruction=str(dict(step).get("instruction") or "タスクを実行する"),
            fallback_title=str(dict(step).get("title") or dict(step).get("description") or "タスク"),
        )
        for step in (state.get("plan", []) or [])
        if isinstance(step, dict)
    ]
    blocked_index = -1
    blocked_step: dict[str, Any] | None = None
    for idx in range(len(plan) - 1, -1, -1):
        step = plan[idx]
        if step.get("status") == "blocked":
            blocked_index = idx
            blocked_step = step
            break

    if blocked_step is None:
        return Command(goto="supervisor", update={})

    origin_step_id = blocked_step.get("origin_step_id", blocked_step.get("id"))
    if not isinstance(origin_step_id, int):
        origin_step_id = int(blocked_step.get("id") or 0)

    rethink_used_by_step = dict(state.get("rethink_used_by_step", {}) or {})
    rethink_used_turn = int(state.get("rethink_used_turn", 0) or 0)
    step_retry_count = int(rethink_used_by_step.get(origin_step_id, 0) or 0)

    if rethink_used_turn >= MAX_RETHINK_PER_TURN or step_retry_count >= MAX_RETHINK_PER_TASK:
        return Command(goto="__end__", update={})

    destination = _resolve_worker_destination(blocked_step)
    if destination is None:
        return Command(goto="supervisor", update={})

    quality_reports = dict(state.get("quality_reports", {}) or {})
    report = quality_reports.get(origin_step_id)
    failed_checks = report.get("failed_checks") if isinstance(report, dict) else None
    if isinstance(failed_checks, list) and any(str(item) == "missing_research" for item in failed_checks):
        return Command(goto="__end__", update={})

    rethink_used_by_step[origin_step_id] = step_retry_count + 1
    rethink_used_turn += 1

    if step_retry_count == 0:
        plan[blocked_index]["status"] = "in_progress"
        plan[blocked_index]["result_summary"] = None
        return Command(
            goto=destination,  # type: ignore[arg-type]
            update={
                "plan": plan,
                "rethink_used_turn": rethink_used_turn,
                "rethink_used_by_step": rethink_used_by_step,
            },
        )

    next_id = _next_step_id(plan)
    fallback_step = dict(blocked_step)
    fallback_step["id"] = next_id
    fallback_step["status"] = "pending"
    fallback_step["origin_step_id"] = origin_step_id
    fallback_step["instruction"] = f"代替アプローチで実行: {blocked_step.get('instruction', '')}"
    fallback_step["description"] = f"{blocked_step.get('description', 'タスク')}（代替）"
    fallback_step["result_summary"] = None
    plan.append(
        normalize_step_v2(
            fallback_step,
            product_type=product_type,
            fallback_capability=capability_from_any(fallback_step) or "writer",
            fallback_instruction=str(fallback_step.get("instruction") or "代替アプローチを実行する"),
            fallback_title=str(fallback_step.get("title") or fallback_step.get("description") or "代替タスク"),
        )
    )

    return Command(
        goto="supervisor",
        update={
            "plan": plan,
            "rethink_used_turn": rethink_used_turn,
            "rethink_used_by_step": rethink_used_by_step,
        },
    )

async def supervisor_node(state: State, config: RunnableConfig) -> Command:
    """
    Supervisor Node (Orchestrator).
    """
    logger.info("Supervisor evaluating state")
    
    plan = state.get("plan", [])
    _normalize_plan_statuses(plan)
    
    current_step_index = -1
    current_step = None
    
    # Check for in-progress step
    for i, step in enumerate(plan):
        if step.get("status") == "in_progress":
            current_step_index = i
            current_step = step
            break
            
    # If no step is in progress, find the first pending step
    if current_step is None:
        for i, step in enumerate(plan):
            if step.get("status") == "pending":
                current_step_index = i
                current_step = step
                break
    
    if current_step is None:
        logger.info("All steps completed. Generating final report.")
        
        # Check if we've already sent the final report to avoid duplication
        # We can use a custom flag in messages or just rely on the fact that this is the last call.
        report = await _generate_supervisor_report(state, config, is_final=True)
        
        return Command(
            goto="__end__",
            update={"messages": [AIMessage(content=report, name="supervisor")]}
        )
        
    destination = _resolve_worker_destination(current_step)
    
    if current_step.get("status") == "in_progress":
        suffix = _artifact_suffix_for_step(current_step)
        artifact_key = f"step_{current_step['id']}_{suffix}"
        
        artifacts = state.get("artifacts", {})
        artifact_exists = artifact_key in artifacts
        artifact_value = artifacts.get(artifact_key) if artifact_exists else None
        has_result_summary = isinstance(current_step.get("result_summary"), str) and bool(
            str(current_step.get("result_summary")).strip()
        )
        failed, failed_checks, failure_notes = _extract_failure_metadata(current_step, artifact_value)

        if failed and (artifact_exists or has_result_summary):
            plan[current_step_index]["status"] = "blocked"
            step_retry_count = int(
                (state.get("rethink_used_by_step", {}) or {}).get(_resolve_origin_step_id(current_step), 0) or 0
            )
            plan[current_step_index]["instruction"] = _build_retry_instruction(
                instruction=str(current_step.get("instruction") or ""),
                result_summary=failure_notes or current_step.get("result_summary"),
                failed_checks=failed_checks,
                step_retry_count=step_retry_count,
            )
            await _dispatch_plan_step_ended(current_step, "blocked", config)
            quality_reports = dict(state.get("quality_reports", {}) or {})
            step_id = current_step.get("id")
            if isinstance(step_id, int):
                quality_reports[step_id] = {
                    "step_id": step_id,
                    "passed": False,
                    "failed_checks": failed_checks,
                    "notes": failure_notes or current_step.get("result_summary") or "Worker output indicates failure.",
                }
            logger.warning(
                "Step %s (%s) marked blocked by supervisor result_summary decision.",
                current_step_index,
                destination or "unknown",
            )
            return Command(
                goto="retry_or_alt_mode",
                update={"plan": plan, "quality_reports": quality_reports},
            )

        if artifact_exists:

            plan[current_step_index]["status"] = "completed"
            await _dispatch_plan_step_ended(current_step, "completed", config)
            logger.info(f"Step {current_step_index} ({destination or 'unknown'}) completed. Marking as completed.")

            await _dispatch_plan_update(plan, config)
            
            # Generate report after completion
            report = await _generate_supervisor_report(state, config, report_event="step_completed")

            compact_update = await _compact_state_if_needed(state, config)
            prune_update = _prune_artifacts_if_needed(state)

            return Command(
                goto="supervisor",
                update=_merge_updates(
                    {"plan": plan, "messages": [AIMessage(content=report, name="supervisor")]},
                    compact_update,
                    prune_update
                )
            )
        else:
             if destination is None:
                 logger.error(f"Step {current_step_index} has no resolvable destination.")
                 plan[current_step_index]["status"] = "blocked"
                 return Command(
                     goto="retry_or_alt_mode",
                     update={"plan": plan}
                 )
             logger.info(f"Step {current_step_index} ({destination}) in progress but no artifact. Re-assigning.")
             return Command(goto=destination)

    elif current_step.get("status") == "pending":
        if destination is None:
            logger.error(f"Pending step {current_step_index} has no resolvable destination.")
            plan[current_step_index]["status"] = "blocked"
            return Command(
                goto="retry_or_alt_mode",
                update={"plan": plan}
            )

        logger.info(f"Starting Step {current_step_index} ({destination})")
        
        plan[current_step_index]["status"] = "in_progress"
        await _dispatch_plan_step_started(current_step, config)

        await _dispatch_plan_update(plan, config)
        
        # Generate report for next step
        report = await _generate_supervisor_report(state, config, report_event="step_started")

        compact_update = await _compact_state_if_needed(state, config)
        prune_update = _prune_artifacts_if_needed(state)

        return Command(
            goto=destination,
            update=_merge_updates(
                {"plan": plan, "messages": [AIMessage(content=report, name="supervisor")]},
                compact_update,
                prune_update
            )
        )
        
    return Command(goto="__end__")
