import logging
import json
import re
from copy import deepcopy
from typing import Any, Literal

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.infrastructure.llm.llm import astream_with_retry, get_llm_by_type
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

SUPPORTED_PRODUCT_TYPES = {"slide", "design", "comic"}

SLIDE_WRITER_DENSITY_CHECKS: tuple[str, ...] = (
    "非タイトルスライドに具体データ（数値・期間・比較軸・固有名詞）が含まれる",
    "主張と根拠の対応関係が確認できる",
)
SLIDE_VISUALIZER_DENSITY_CHECKS: tuple[str, ...] = (
    "Writerで定義した数値・列挙情報が画像で欠落していない",
    "非タイトルスライドが装飾過多でなく情報伝達を優先している",
)


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


def _detect_intent(text: str) -> str:
    lowered = text.lower()
    if any(keyword in text for keyword in ("再生成", "作り直", "やり直し")) or "regenerate" in lowered:
        return "regenerate"
    if any(keyword in text for keyword in ("修正", "変更", "調整", "直して")) or any(
        keyword in lowered for keyword in ("fix", "refine", "update")
    ):
        return "refine"
    return "new"


def _normalize_plan_steps(plan_data: list[dict], product_type: str | None) -> list[dict]:
    """Normalize planner output to canonical V2 steps.

    Hybrid policy:
    - Keep structural normalization hard.
    - Keep sequence/content decisions soft (AI judgment).
    """
    return normalize_plan_v2(plan_data, product_type=product_type)


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


def _has_multiple_research_perspectives(instruction: str) -> bool:
    if not instruction:
        return False
    lines = [line.strip() for line in instruction.splitlines() if line.strip()]
    bullet_count = 0
    for line in lines:
        if re.match(r"^(?:[-*・]|[0-9]+[.)、])\s*", line):
            bullet_count += 1
    if bullet_count >= 2:
        return True

    if "調査観点" in instruction:
        marker_index = instruction.find("調査観点")
        tail = instruction[marker_index:]
        candidate_count = 0
        for raw in re.split(r"[、,\n/]", tail):
            text = re.sub(r"^(?:[-*・]|[0-9]+[.)、])\s*", "", raw).strip()
            if not text:
                continue
            if text.startswith("調査観点"):
                continue
            if "分解" in text or "調査する" in text:
                continue
            candidate_count += 1
        return candidate_count >= 2

    return False


def _default_research_perspectives(product_type: str | None) -> list[str]:
    if product_type == "comic":
        return [
            "題材・時代背景の事実関係と参照可能な根拠",
            "近い作風・演出の先行事例と再現ポイント",
            "表現上のリスク・制約（権利/倫理/文化的配慮）",
        ]
    if product_type == "design":
        return [
            "業界動向・主要論点の最新情報",
            "類似ドキュメントの構成パターンとベストプラクティス",
            "意思決定時に注意すべき制約・リスク要因",
        ]
    return [
        "市場動向・背景データの最新情報",
        "先行事例・ベストプラクティスと示唆",
        "実行時に考慮すべきリスク・制約条件",
    ]


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword in text or keyword in lowered for keyword in keywords)


def _default_asset_requirements_for_step(step: dict[str, Any]) -> list[dict[str, Any]]:
    capability = capability_from_any(step)
    mode = str(step.get("mode") or "")
    text = _step_text_blob(step)

    if capability == "visualizer":
        requirements: list[dict[str, Any]] = [
            {
                "role": "style_reference",
                "required": False,
                "scope": "global",
                "mime_allow": ["image/*"],
                "source_preference": ["user_upload", "selected_image_input"],
                "max_items": 2,
            },
            {
                "role": "layout_reference",
                "required": False,
                "scope": "per_unit",
                "mime_allow": ["image/*", "application/pdf"],
                "source_preference": ["derived_template", "dependency_artifact"],
                "max_items": 1,
            },
        ]
        if _contains_any(text, ("inpaint", "in-paint", "マスク", "修正範囲")):
            requirements.extend(
                [
                    {
                        "role": "base_image",
                        "required": True,
                        "scope": "per_unit",
                        "mime_allow": ["image/*"],
                        "source_preference": [],
                        "max_items": 1,
                    },
                    {
                        "role": "mask_image",
                        "required": True,
                        "scope": "per_unit",
                        "mime_allow": ["image/*"],
                        "source_preference": [],
                        "max_items": 1,
                    },
                ]
            )
        if mode == "character_sheet_render":
            requirements.append(
                {
                    "role": "character_reference",
                    "required": False,
                    "scope": "global",
                    "mime_allow": ["image/*"],
                    "source_preference": ["dependency_artifact"],
                    "max_items": 3,
                }
            )
        if mode == "comic_page_render":
            requirements.append(
                {
                    "role": "character_reference",
                    "required": True,
                    "scope": "global",
                    "mime_allow": ["image/*"],
                    "source_preference": ["dependency_artifact"],
                    "max_items": 6,
                }
            )
        return requirements

    if capability == "data_analyst":
        template_required = _contains_any(text, ("pptx", "テンプレート", "master", "layout"))
        return [
            {
                "role": "template_source",
                "required": template_required,
                "scope": "global",
                "mime_allow": [
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "application/pdf",
                    "image/*",
                ],
                "source_preference": ["user_upload", "dependency_artifact"],
                "max_items": 3,
            },
            {
                "role": "data_source",
                "required": False,
                "scope": "global",
                "mime_allow": [
                    "text/csv",
                    "application/json",
                    "application/pdf",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ],
                "source_preference": ["dependency_artifact", "user_upload"],
                "max_items": 5,
            },
        ]

    if capability == "writer":
        return [
            {
                "role": "reference_document",
                "required": False,
                "scope": "global",
                "mime_allow": ["application/pdf", "text/*", "application/json", "image/*"],
                "source_preference": ["dependency_artifact", "user_upload"],
                "max_items": 4,
            }
        ]

    return []


def _ensure_asset_requirements(plan_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for step in plan_steps:
        next_step = dict(step)
        existing = next_step.get("asset_requirements")
        if isinstance(existing, list) and existing:
            updated.append(next_step)
            continue
        defaults = _default_asset_requirements_for_step(next_step)
        if defaults:
            next_step["asset_requirements"] = defaults
        updated.append(next_step)
    return updated


def _ensure_multi_perspective_research_steps(
    plan_steps: list[dict[str, Any]],
    product_type: str | None,
) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for step in plan_steps:
        next_step = dict(step)
        if capability_from_any(next_step) != "researcher":
            updated.append(next_step)
            continue

        instruction = str(next_step.get("instruction") or "").strip()
        if _has_multiple_research_perspectives(instruction):
            updated.append(next_step)
            continue

        perspectives = _default_research_perspectives(product_type)
        perspective_lines = "\n".join(f"- {item}" for item in perspectives)
        instruction_head = instruction if instruction else "依頼テーマを調査する"
        next_step["instruction"] = (
            f"{instruction_head}\n\n"
            "調査観点:\n"
            f"{perspective_lines}\n\n"
            "上記の観点を個別タスクに分解し、それぞれ根拠付きで調査する。"
        )

        description = next_step.get("description")
        if isinstance(description, str) and description.strip():
            if "複数観点" not in description:
                next_step["description"] = f"{description.strip()}（複数観点を分解して調査）"
        else:
            next_step["description"] = "複数観点を分解して調査する"

        updated.append(next_step)
    return updated


def _merge_required_strings(existing: Any, required: tuple[str, ...]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()

    if isinstance(existing, list):
        for item in existing:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)

    for item in required:
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        merged.append(text)

    return merged


def _append_instruction_block_if_missing(base_text: Any, block_title: str, block_body: str) -> str:
    text = str(base_text or "").strip()
    if block_title in text:
        return text
    if not text:
        return f"{block_title}\n{block_body}"
    return f"{text}\n\n{block_title}\n{block_body}"


def _enforce_slide_information_density_plan(plan_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for step in plan_steps:
        next_step = dict(step)
        capability = capability_from_any(next_step)
        mode = str(next_step.get("mode") or "")

        if capability == "writer" and mode in {"slide_outline", "infographic_spec"}:
            next_step["instruction"] = _append_instruction_block_if_missing(
                next_step.get("instruction"),
                "情報密度要件:",
                "- 非タイトルスライドに具体データ（数値・期間・比較軸・固有名詞）を含める。\n"
                "- 主張と根拠の対応を明示し、曖昧語だけの記述を避ける。",
            )
            next_step["validation"] = _merge_required_strings(
                next_step.get("validation"),
                SLIDE_WRITER_DENSITY_CHECKS,
            )
            next_step["success_criteria"] = _merge_required_strings(
                next_step.get("success_criteria"),
                SLIDE_WRITER_DENSITY_CHECKS,
            )

        if capability == "visualizer" and mode == "slide_render":
            next_step["instruction"] = _append_instruction_block_if_missing(
                next_step.get("instruction"),
                "情報反映要件:",
                "- Writerアウトラインの数値・比較軸・列挙情報を漏れなく反映する。\n"
                "- 装飾優先ではなく、情報伝達と可読性を優先する。",
            )
            next_step["validation"] = _merge_required_strings(
                next_step.get("validation"),
                SLIDE_VISUALIZER_DENSITY_CHECKS,
            )
            next_step["success_criteria"] = _merge_required_strings(
                next_step.get("success_criteria"),
                SLIDE_VISUALIZER_DENSITY_CHECKS,
            )

        updated.append(next_step)
    return updated


def _is_valid_request_intent(value: Any) -> bool:
    return isinstance(value, str) and value in {"new", "refine", "regenerate"}


def _plan_execution_snapshot(plan: Any) -> dict[str, Any]:
    snapshot = {
        "total": 0,
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "blocked": 0,
    }
    if not isinstance(plan, list):
        return snapshot

    for step in plan:
        if not isinstance(step, dict):
            continue
        snapshot["total"] += 1
        status = str(step.get("status") or "pending")
        if status in snapshot:
            snapshot[status] += 1
        else:
            snapshot["pending"] += 1
    return snapshot


def _unfinished_steps_snapshot(plan: Any) -> list[dict[str, Any]]:
    if not isinstance(plan, list):
        return []
    rows: list[dict[str, Any]] = []
    for step in plan:
        if not isinstance(step, dict):
            continue
        status = str(step.get("status") or "pending")
        if status == "completed":
            continue
        step_id = step.get("id")
        rows.append(
            {
                "id": int(step_id) if isinstance(step_id, int) else None,
                "status": status,
                "capability": capability_from_any(step),
                "mode": str(step.get("mode") or ""),
                "title": str(step.get("title") or ""),
                "depends_on": list(step.get("depends_on") or []) if isinstance(step.get("depends_on"), list) else [],
                "result_summary": str(step.get("result_summary") or ""),
            }
        )
    return rows


async def _invoke_planner_llm(
    *,
    llm: Any,
    messages: list[Any],
    stream_config: RunnableConfig,
) -> PlannerOutput:
    full_text = ""
    async for chunk in astream_with_retry(
        lambda: llm.astream(messages, config=stream_config),
        operation_name="planner.astream",
    ):
        if not getattr(chunk, "content", None):
            continue
        _, text = split_content_parts(chunk.content)
        if text:
            full_text += text

    try:
        json_text = extract_first_json(full_text) or full_text
        return PlannerOutput.model_validate_json(json_text)
    except Exception as parse_error:
        logger.warning("Planner streaming JSON parse failed: %s. Falling back to repair.", parse_error)
        return await run_structured_output(
            llm=llm,
            schema=PlannerOutput,
            messages=messages,
            config=stream_config,
            repair_hint="Schema: PlannerOutput. No extra text.",
        )


def _finalize_plan(
    *,
    raw_plan_steps: list[dict[str, Any]],
    product_type: str,
) -> list[dict[str, Any]]:
    plan_data = _normalize_plan_steps(raw_plan_steps, product_type=product_type)
    plan_data = _ensure_multi_perspective_research_steps(plan_data, product_type=product_type)
    plan_data = _ensure_asset_requirements(plan_data)
    if product_type == "slide":
        plan_data = _enforce_slide_information_density_plan(plan_data)
    return plan_data


def _planner_ui_message(plan_data: list[dict[str, Any]]) -> AIMessage:
    return AIMessage(
        content="Plan Created",
        additional_kwargs={
            "ui_type": "plan_update",
            "plan": plan_steps_for_ui(plan_data),
            "title": "Execution Plan",
            "description": "The updated execution plan.",
        },
        name="planner_ui",
    )


async def planner_node(state: State, config: RunnableConfig) -> Command[Literal["supervisor", "__end__"]]:
    """Planner node (single-turn optimized: always create a fresh plan)."""
    logger.info("Planner creating execution plan")

    product_type = state.get("product_type") if isinstance(state.get("product_type"), str) else None
    if product_type not in SUPPORTED_PRODUCT_TYPES:
        logger.warning("Planner aborted because product_type is invalid: %s", product_type)
        return Command(
            update={
                "messages": [
                    AIMessage(
                        content="プロダクト種別が未確定のため、slide/design/comic を指定してください。",
                        name="planner",
                    )
                ]
            },
            goto="__end__",
        )

    latest_user_text = _extract_latest_user_text(state)
    request_intent = state.get("request_intent") if _is_valid_request_intent(state.get("request_intent")) else _detect_intent(latest_user_text)
    planning_mode = "create"
    existing_plan: list[dict[str, Any]] = []
    target_scope = state.get("target_scope") if isinstance(state.get("target_scope"), dict) else {}

    context_state = deepcopy(state)
    context_state["product_type"] = product_type
    context_state["request_intent"] = str(request_intent)
    context_state["planning_mode"] = planning_mode
    context_state["latest_user_text"] = latest_user_text
    context_state["plan"] = json.dumps(existing_plan, ensure_ascii=False, indent=2)
    context_state["plan_execution_snapshot"] = json.dumps(
        _plan_execution_snapshot(existing_plan),
        ensure_ascii=False,
    )
    context_state["unfinished_steps"] = json.dumps(
        _unfinished_steps_snapshot(existing_plan),
        ensure_ascii=False,
    )
    context_state["target_scope"] = json.dumps(target_scope or {}, ensure_ascii=False)
    context_state["interrupt_intent"] = "true" if bool(state.get("interrupt_intent")) else "false"

    messages = apply_prompt_template("planner", context_state)
    logger.debug(f"[DEBUG] Planner Input Messages: {messages}")

    llm = get_llm_by_type("reasoning", streaming=True)

    try:
        logger.info("Planner: Calling LLM for structured output (streaming=True)")

        # Add run_name for better visibility in stream events
        stream_config = config.copy()
        stream_config["run_name"] = "planner"

        planner_output = await _invoke_planner_llm(
            llm=llm,
            messages=messages,
            stream_config=stream_config,
        )

        logger.debug(f"[DEBUG] Planner Output: {planner_output}")
        proposed_steps = [step.model_dump(exclude_none=True) for step in planner_output.steps]
        proposed_steps = _finalize_plan(
            raw_plan_steps=proposed_steps,
            product_type=product_type,
        )

        plan_data = proposed_steps

        missing_research, reason = _missing_required_research_step(plan_data, latest_user_text)
        if missing_research:
            logger.warning(
                "Planner output missing explicit researcher step (soft warning in hybrid mode): %s",
                reason,
            )

        logger.info(f"Plan generated successfully with {len(plan_data)} steps.")
        
        return Command(
            update={
                "messages": [_planner_ui_message(plan_data)],
                "request_intent": str(request_intent),
                "planning_mode": planning_mode,
                "plan": plan_data,
                # Single-turn optimization: reset per-request execution state.
                "artifacts": {},
                "interrupt_intent": False,
                # Top-level scope is short-lived; concrete scope stays on each plan step.
                "target_scope": {},
                "quality_reports": {},
                "asset_unit_ledger": {},
                "asset_catalog": {},
                "candidate_assets_by_step": {},
                "selected_assets_by_step": {},
                "asset_bindings_by_step": {},
                "coordinator_followup_options": [],
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
