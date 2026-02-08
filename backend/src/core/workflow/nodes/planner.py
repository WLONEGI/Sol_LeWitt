import logging
import json
from copy import deepcopy
from typing import Any, Literal

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import apply_prompt_template
from src.shared.schemas import PlannerOutput
from src.core.workflow.state import State
from src.core.workflow.step_v2 import capability_from_any, normalize_plan_v2, plan_steps_for_ui
from .common import run_structured_output, extract_first_json, split_content_parts

logger = logging.getLogger(__name__)

RESEARCH_REQUIREMENT_KEYWORDS = (
    "調査",
    "出典",
    "根拠",
    "裏取り",
    "reference",
    "citation",
    "source",
    "ライセンス",
    "史実",
    "資料",
)

COMIC_REQUIRED_SEQUENCE: tuple[tuple[str, str], ...] = (
    ("writer", "story_framework"),
    ("writer", "character_sheet"),
    ("visualizer", "character_sheet_render"),
    ("writer", "comic_script"),
    ("visualizer", "comic_page_render"),
)

FIXED_FALLBACK = [
    "retry_with_tighter_constraints",
    "reduce_scope_to_target_units",
    "switch_mode_minimal_safe_output",
]


def _step_signature(step: dict[str, Any]) -> tuple[str, str]:
    return capability_from_any(step), str(step.get("mode") or "")


def _build_comic_required_step(capability: str, mode: str) -> dict[str, Any]:
    if (capability, mode) == ("writer", "story_framework"):
        return {
            "capability": "writer",
            "mode": "story_framework",
            "instruction": "漫画の世界観と物語の骨子を定義する",
            "title": "物語フレーム設計",
            "description": "世界観・背景・物語の核を定義する",
            "inputs": ["user_request"],
            "outputs": ["story_framework"],
            "preconditions": ["ユーザー要件を確認済み"],
            "validation": ["物語の核と世界観が定義されている"],
            "success_criteria": ["物語の核と世界観が定義されている"],
            "fallback": list(FIXED_FALLBACK),
            "depends_on": [],
            "status": "pending",
        }
    if (capability, mode) == ("writer", "character_sheet"):
        return {
            "capability": "writer",
            "mode": "character_sheet",
            "instruction": "主要キャラクターの設定を作成する",
            "title": "キャラクター設定作成",
            "description": "主要キャラクターの外見と性格を定義する",
            "inputs": ["story_framework"],
            "outputs": ["character_sheet"],
            "preconditions": ["物語フレームが定義されている"],
            "validation": ["主要キャラクターの設定が定義されている"],
            "success_criteria": ["主要キャラクターの設定が定義されている"],
            "fallback": list(FIXED_FALLBACK),
            "depends_on": [],
            "status": "pending",
        }
    if (capability, mode) == ("visualizer", "character_sheet_render"):
        return {
            "capability": "visualizer",
            "mode": "character_sheet_render",
            "instruction": "キャラクターシート画像を生成する",
            "title": "キャラクターシート画像生成",
            "description": "主要キャラクターの見た目を画像で可視化する",
            "inputs": ["character_sheet"],
            "outputs": ["character_sheet_images"],
            "preconditions": ["キャラクター設定が定義されている"],
            "validation": ["キャラクターの見た目一貫性が保たれている"],
            "success_criteria": ["キャラクターの見た目一貫性が保たれている"],
            "fallback": list(FIXED_FALLBACK),
            "depends_on": [],
            "status": "pending",
        }
    if (capability, mode) == ("writer", "comic_script"):
        return {
            "capability": "writer",
            "mode": "comic_script",
            "instruction": "キャラクターシートを参照して漫画脚本を作成する",
            "title": "漫画脚本作成",
            "description": "ページ・コマ詳細を含む脚本を作成する",
            "inputs": ["story_framework", "character_sheet", "character_sheet_images"],
            "outputs": ["comic_script"],
            "preconditions": ["キャラクターシート画像が生成済みである"],
            "validation": ["ページとコマの脚本が定義されている"],
            "success_criteria": ["ページとコマの脚本が定義されている"],
            "fallback": list(FIXED_FALLBACK),
            "depends_on": [],
            "status": "pending",
        }
    if (capability, mode) == ("visualizer", "comic_page_render"):
        return {
            "capability": "visualizer",
            "mode": "comic_page_render",
            "instruction": "漫画ページ画像を生成する",
            "title": "漫画ページ画像生成",
            "description": "脚本に基づいて漫画ページ画像を生成する",
            "inputs": ["comic_script", "character_sheet_images"],
            "outputs": ["comic_pages"],
            "preconditions": ["漫画脚本が定義されている"],
            "validation": ["脚本と画像内容が整合している"],
            "success_criteria": ["脚本と画像内容が整合している"],
            "fallback": list(FIXED_FALLBACK),
            "depends_on": [],
            "status": "pending",
        }
    return {
        "capability": capability,
        "mode": mode,
        "instruction": "タスクを実行する",
        "title": "タスク",
        "description": "タスクを実行する",
        "inputs": ["user_request"],
        "outputs": ["artifact"],
        "preconditions": ["なし"],
        "validation": ["出力が生成されている"],
        "success_criteria": ["出力が生成されている"],
        "fallback": list(FIXED_FALLBACK),
        "depends_on": [],
        "status": "pending",
    }


def _enforce_comic_required_sequence(plan_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not plan_steps:
        plan_steps = []

    required_set = set(COMIC_REQUIRED_SEQUENCE)
    steps: list[dict[str, Any]] = []
    for idx, raw in enumerate(plan_steps, start=1):
        step = dict(raw)
        original_id = step.get("id")
        if not isinstance(original_id, int):
            original_id = idx
        step["_orig_id"] = original_id
        steps.append(step)

    consumed_indices: set[int] = set()
    required_steps: list[dict[str, Any]] = []
    matched_indices: list[int] = []
    inserted_seed = -1

    for capability, mode in COMIC_REQUIRED_SEQUENCE:
        matched_idx: int | None = None
        matched_step: dict[str, Any] | None = None
        for idx, step in enumerate(steps):
            if idx in consumed_indices:
                continue
            if _step_signature(step) == (capability, mode):
                matched_idx = idx
                matched_step = dict(step)
                break

        if matched_step is None:
            matched_step = _build_comic_required_step(capability, mode)
            matched_step["_orig_id"] = inserted_seed
            inserted_seed -= 1
        else:
            consumed_indices.add(matched_idx)
            matched_indices.append(matched_idx)
        required_steps.append(matched_step)

    insert_pos = min(matched_indices) if matched_indices else 0
    remaining_steps = [
        dict(step)
        for idx, step in enumerate(steps)
        if idx not in consumed_indices and _step_signature(step) not in required_set
    ]
    reordered = remaining_steps[:insert_pos] + required_steps + remaining_steps[insert_pos:]

    old_to_new: dict[int, int] = {}
    for new_id, step in enumerate(reordered, start=1):
        orig_id = step.get("_orig_id")
        if isinstance(orig_id, int):
            old_to_new[orig_id] = new_id
        step["id"] = new_id

    for step in reordered:
        step_id = int(step.get("id", 0))
        raw_depends = step.get("depends_on")
        remapped: list[int] = []
        if isinstance(raw_depends, list):
            for dep in raw_depends:
                if not isinstance(dep, int):
                    continue
                mapped = old_to_new.get(dep)
                if not mapped or mapped == step_id or mapped in remapped:
                    continue
                remapped.append(mapped)
        step["depends_on"] = remapped

    required_ids: list[int] = []
    for capability, mode in COMIC_REQUIRED_SEQUENCE:
        matched = next(
            (
                int(step["id"])
                for step in reordered
                if _step_signature(step) == (capability, mode)
            ),
            None,
        )
        if matched is not None:
            required_ids.append(matched)

    for idx in range(1, len(required_ids)):
        prev_id = required_ids[idx - 1]
        current_id = required_ids[idx]
        step = reordered[current_id - 1]
        depends = step.get("depends_on")
        if not isinstance(depends, list):
            depends = []
        if prev_id not in depends:
            depends.append(prev_id)
        step["depends_on"] = depends

    for step in reordered:
        step.pop("_orig_id", None)

    return normalize_plan_v2(reordered, product_type="comic")


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text")
                if isinstance(value, str):
                    texts.append(value)
            elif isinstance(item, str):
                texts.append(item)
        return "".join(texts)
    if isinstance(content, dict):
        value = content.get("text")
        return value if isinstance(value, str) else ""
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


def _normalize_plan_steps(plan_data: list[dict], product_type: str | None) -> list[dict]:
    """Normalize planner output to canonical V2 steps."""
    normalized = normalize_plan_v2(plan_data, product_type=product_type)
    if product_type == "comic":
        return _enforce_comic_required_sequence(normalized)
    return normalized


def _step_text_blob(step: dict[str, Any]) -> str:
    chunks: list[str] = []
    for key in ("instruction", "description", "title", "mode"):
        value = step.get(key)
        if isinstance(value, str):
            chunks.append(value)
    for key in ("inputs", "outputs", "validation", "success_criteria"):
        value = step.get(key)
        if isinstance(value, list):
            chunks.extend(str(item) for item in value if isinstance(item, str))
    return " ".join(chunks)


def _contains_research_requirement(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in text or keyword in lowered for keyword in RESEARCH_REQUIREMENT_KEYWORDS)


def _has_explicit_research_step(plan_steps: list[dict[str, Any]]) -> bool:
    for step in plan_steps:
        if capability_from_any(step) == "researcher":
            return True
    return False


def _missing_required_research_step(
    plan_steps: list[dict[str, Any]],
    latest_user_text: str,
) -> tuple[bool, str]:
    requires_research = _contains_research_requirement(latest_user_text)
    if not requires_research:
        for step in plan_steps:
            if _contains_research_requirement(_step_text_blob(step)):
                requires_research = True
                break

    if not requires_research:
        return False, ""

    if _has_explicit_research_step(plan_steps):
        return False, ""

    return True, "Research requirement was detected but no explicit researcher step is included."


async def planner_node(state: State, config: RunnableConfig) -> Command[Literal["supervisor", "__end__"]]:
    """Planner node - uses structured output for reliable JSON execution plan."""
    logger.info("Planner creating execution plan")
    
    context_state = deepcopy(state)
    context_state["plan"] = json.dumps(state.get("plan", []), ensure_ascii=False, indent=2)
    
    messages = apply_prompt_template("planner", context_state)
    logger.debug(f"[DEBUG] Planner Input Messages: {messages}")
    
    llm = get_llm_by_type("reasoning", streaming=True)
    
    try:
        logger.info("Planner: Calling LLM for structured output (streaming=True)")
        
        # Add run_name for better visibility in stream events
        stream_config = config.copy()
        stream_config["run_name"] = "planner"
        
        # Stream tokens via on_chat_model_stream; keep final JSON in-buffer
        full_text = ""
        async for chunk in llm.astream(messages, config=stream_config):
            if not getattr(chunk, "content", None):
                continue
            thinking_text, text = split_content_parts(chunk.content)
            if text:
                full_text += text

        try:
            json_text = extract_first_json(full_text) or full_text
            planner_output = PlannerOutput.model_validate_json(json_text)
        except Exception as parse_error:
            logger.warning(f"Planner streaming JSON parse failed: {parse_error}. Falling back to repair.")
            planner_output = await run_structured_output(
                llm=llm,
                schema=PlannerOutput,
                messages=messages,
                config=stream_config,
                repair_hint="Schema: PlannerOutput. No extra text."
            )
        
        logger.debug(f"[DEBUG] Planner Output: {planner_output}")
        plan_data = [step.model_dump(exclude_none=True) for step in planner_output.steps]
        plan_data = _normalize_plan_steps(plan_data, product_type=state.get("product_type"))

        latest_user_text = _extract_latest_user_text(state)
        missing_research, reason = _missing_required_research_step(plan_data, latest_user_text)
        if missing_research:
            logger.error("Planner output missing explicit researcher step: %s", reason)
            return Command(
                update={
                    "messages": [
                        AIMessage(
                            content=(
                                "Researchが必要な要件ですが、Plannerに明示的なResearcherステップがありません。"
                                "要件を明示して再依頼してください（例: 出典調査を含める）。"
                            ),
                            name="planner",
                        )
                    ]
                },
                goto="__end__",
            )

        logger.info(f"Plan generated successfully with {len(plan_data)} steps.")
        
        return Command(
            update={
                "messages": [
                    AIMessage(
                        content="Plan Created",
                        additional_kwargs={
                            "ui_type": "plan_update",
                            "plan": plan_steps_for_ui(plan_data),
                            "title": "Execution Plan",
                            "description": "The updated execution plan."
                        },
                        name="planner_ui"
                    )
                ],
                "plan": plan_data,
                "artifacts": {}
            },
            goto="supervisor",
        )
    except Exception as e:
        logger.error(f"[CRITICAL] Planner structured output failed. Error type: {type(e).__name__}, Message: {e}")
        # If possible, we'd want raw output here, but with_structured_output hides it on error.
        # For now, let's just log the context.
        return Command(
            update={"messages": [AIMessage(content=f"プランの生成に失敗しました (形式エラー)。詳細: {e}", name="planner")]},
            goto="__end__"
        )
