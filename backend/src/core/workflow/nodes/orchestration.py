import hashlib
import json
import logging
import re
from typing import Any, Literal

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.core.workflow.state import State
from src.core.workflow.step_v2 import (
    capability_from_any,
    destination_for_capability,
    default_mode_for_capability,
    normalize_step_v2,
)

logger = logging.getLogger(__name__)

MAX_RETHINK_PER_TASK = 2
MAX_RETHINK_PER_TURN = 6
ALLOWED_PATCH_OPS = {"edit_pending", "split_pending", "append_tail"}
TARGET_SCOPE_ALLOWED_KEYS = {
    "asset_unit_ids",
    "asset_units",
    "slide_numbers",
    "page_numbers",
    "panel_numbers",
    "character_ids",
    "artifact_ids",
}
MAX_TARGET_SCOPE_UNITS = 10
CANONICAL_ASSET_UNIT_PATTERN = re.compile(r"^(slide|page|panel):\d+$", flags=re.IGNORECASE)
EDITABLE_PENDING_FIELDS = {
    "capability",
    "mode",
    "instruction",
    "title",
    "description",
    "inputs",
    "outputs",
    "preconditions",
    "validation",
    "success_criteria",
    "target_scope",
    "fallback",
    "depends_on",
    "design_direction",
}
EDIT_PENDING_ALLOWED_PAYLOAD_KEYS = set(EDITABLE_PENDING_FIELDS)
SPLIT_PENDING_ALLOWED_PAYLOAD_KEYS = {"new_steps", "steps"}
APPEND_TAIL_ALLOWED_PAYLOAD_KEYS = {"steps", "step"}
WORKER_DESTINATIONS = {"researcher", "writer", "visualizer", "data_analyst"}
SPLIT_HINT_KEYWORDS = ("分割", "分け", "別々", "それぞれ", "split")
VISUALIZER_HINT_KEYWORDS = (
    "画像", "イラスト", "ビジュアル", "色", "配色", "トーン", "レイアウト", "構図", "デザイン", "コマ",
)
WRITER_HINT_KEYWORDS = (
    "ストーリー", "物語", "構成", "アウトライン", "設定", "キャラクター", "脚本", "セリフ", "文章",
)
RESEARCHER_HINT_KEYWORDS = ("調査", "検索", "出典", "根拠", "裏取り", "リファレンス")
DATA_ANALYST_HINT_KEYWORDS = ("pdf", "tar", "集約", "パッケージ", "変換", "python", "計算")


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


def _detect_intent(text: str) -> str:
    lowered = text.lower()
    if _is_regenerate_request(text):
        return "regenerate"
    if any(k in text for k in ("修正", "変更", "調整", "直して", "改善")) or any(
        k in lowered for k in ("fix", "refine", "update")
    ):
        return "refine"
    return "new"


def _is_regenerate_request(text: str) -> bool:
    lowered = text.lower()
    return any(k in text for k in ("作り直", "再生成", "やり直し")) or "regenerate" in lowered


def _detect_target_scope(text: str) -> dict[str, Any]:
    scope: dict[str, Any] = {}
    slide_numbers = [int(m) for m in re.findall(r"(\d+)\s*(?:枚目|スライド)", text)]
    page_numbers = [int(m) for m in re.findall(r"(\d+)\s*ページ", text)]
    panel_numbers = [int(m) for m in re.findall(r"(\d+)\s*コマ", text)]
    character_ids = [m.strip() for m in re.findall(r"(?:キャラ|キャラクター)\s*([A-Za-z0-9_\-ぁ-んァ-ン一-龥]+)", text)]
    explicit_asset_unit_ids = [m.strip() for m in re.findall(r"asset[_\s-]?unit[:：]?\s*([A-Za-z0-9:_\-]+)", text, flags=re.IGNORECASE)]

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

    for n in sorted(set(slide_numbers)):
        unit_id = f"slide:{n}"
        asset_units.append({"unit_id": unit_id, "unit_kind": "slide", "unit_index": n})
        asset_unit_ids.append(unit_id)
    for n in sorted(set(page_numbers)):
        unit_id = f"page:{n}"
        asset_units.append({"unit_id": unit_id, "unit_kind": "page", "unit_index": n})
        asset_unit_ids.append(unit_id)
    for n in sorted(set(panel_numbers)):
        unit_id = f"panel:{n}"
        asset_units.append({"unit_id": unit_id, "unit_kind": "panel", "unit_index": n})
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


def _hash_plan(plan: list[dict[str, Any]]) -> str:
    payload = json.dumps(plan, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _next_step_id(plan: list[dict[str, Any]]) -> int:
    max_id = 0
    for step in plan:
        sid = step.get("id")
        if isinstance(sid, int) and sid > max_id:
            max_id = sid
    return max_id + 1


def _resolve_worker_destination(step: dict[str, Any]) -> str | None:
    capability = _capability_for_step(step)
    if capability is not None:
        destination = destination_for_capability(capability)
        if destination in WORKER_DESTINATIONS:
            return destination
    return None


def _capability_for_step(step: dict[str, Any]) -> str | None:
    capability = capability_from_any(step)
    return capability if isinstance(capability, str) else None


def _infer_target_capability(text: str, product_type: str | None) -> str:
    lowered = text.lower()
    if any(k in text for k in RESEARCHER_HINT_KEYWORDS):
        return "researcher"
    if any(k in text for k in DATA_ANALYST_HINT_KEYWORDS):
        return "data_analyst"
    if any(k in text for k in VISUALIZER_HINT_KEYWORDS):
        return "visualizer"
    if any(k in text for k in WRITER_HINT_KEYWORDS):
        return "writer"
    if product_type in ("slide_infographic", "document_design", "comic"):
        return "visualizer" if ("修正" in text or "変更" in text or _is_regenerate_request(text)) else "writer"
    return "writer"


def _find_pending_step(plan: list[dict[str, Any]], capability: str) -> dict[str, Any] | None:
    for step in plan:
        if step.get("status") != "pending":
            continue
        step_capability = _capability_for_step(step)
        if step_capability == capability:
            return step
    return None


def _build_append_step(
    *,
    capability: str,
    text: str,
    product_type: str | None,
    target_scope: dict[str, Any] | None,
) -> dict[str, Any]:
    mode = default_mode_for_capability(capability, product_type, text)
    return {
        "capability": capability,
        "mode": mode,
        "instruction": f"以下の追加修正指示を反映してください: {text}",
        "title": "修正反映",
        "description": "ユーザー追加依頼への追従タスク",
        "inputs": ["existing_artifacts", "user_patch_instruction"],
        "outputs": ["patched_artifact"],
        "preconditions": ["既存成果物が参照可能であること"],
        "validation": ["ユーザー指示が反映されている"],
        "success_criteria": ["ユーザー指示が反映されている"],
        "fallback": ["不足情報をResearcherで補完して再実行する"],
        "depends_on": [],
        "target_scope": target_scope or {},
    }


def _patch_gate_reject(code: str, message: str) -> Command:
    return Command(
        goto="__end__",
        update={
            "messages": [
                AIMessage(
                    content=message,
                    name="patch_gate",
                    additional_kwargs={"result_code": code},
                )
            ]
        },
    )


def _normalize_int_list(values: Any) -> tuple[list[int], str | None]:
    if values is None:
        return [], None
    if not isinstance(values, list):
        return [], "must be a list of integers"
    deduped: list[int] = []
    for item in values:
        if not isinstance(item, int):
            return [], "must be a list of integers"
        if item <= 0:
            return [], "must contain positive integers"
        if item not in deduped:
            deduped.append(item)
    return sorted(deduped), None


def _normalize_string_list(values: Any) -> tuple[list[str], str | None]:
    if values is None:
        return [], None
    if not isinstance(values, list):
        return [], "must be a list of strings"
    deduped: list[str] = []
    for item in values:
        if not isinstance(item, str):
            return [], "must be a list of strings"
        trimmed = item.strip()
        if not trimmed:
            continue
        if trimmed not in deduped:
            deduped.append(trimmed)
    return deduped, None


def _normalize_target_scope_for_patch(
    raw_scope: Any,
    asset_unit_ledger: dict[str, Any] | None,
) -> tuple[dict[str, Any], str | None, str | None]:
    if raw_scope is None:
        return {}, None, None
    if not isinstance(raw_scope, dict):
        return {}, "invalid_target_scope", "target_scope は object 形式である必要があります。"

    unknown_keys = sorted(set(raw_scope.keys()) - TARGET_SCOPE_ALLOWED_KEYS)
    if unknown_keys:
        return (
            {},
            "invalid_target_scope_key",
            f"target_scope に未許可キーがあります: {', '.join(unknown_keys)}",
        )

    normalized: dict[str, Any] = {}

    for key in ("slide_numbers", "page_numbers", "panel_numbers"):
        numbers, err = _normalize_int_list(raw_scope.get(key))
        if err:
            return {}, "invalid_target_scope", f"target_scope.{key} {err}"
        if numbers:
            normalized[key] = numbers

    character_ids, err = _normalize_string_list(raw_scope.get("character_ids"))
    if err:
        return {}, "invalid_target_scope", f"target_scope.character_ids {err}"
    if character_ids:
        normalized["character_ids"] = character_ids

    artifact_ids, err = _normalize_string_list(raw_scope.get("artifact_ids"))
    if err:
        return {}, "invalid_target_scope", f"target_scope.artifact_ids {err}"
    if artifact_ids:
        normalized["artifact_ids"] = artifact_ids

    explicit_unit_ids, err = _normalize_string_list(raw_scope.get("asset_unit_ids"))
    if err:
        return {}, "invalid_target_scope", f"target_scope.asset_unit_ids {err}"

    derived_unit_ids = list(explicit_unit_ids)
    for number in normalized.get("slide_numbers", []):
        derived_unit_ids.append(f"slide:{number}")
    for number in normalized.get("page_numbers", []):
        derived_unit_ids.append(f"page:{number}")
    for number in normalized.get("panel_numbers", []):
        derived_unit_ids.append(f"panel:{number}")

    deduped_unit_ids: list[str] = []
    for unit_id in derived_unit_ids:
        if unit_id not in deduped_unit_ids:
            deduped_unit_ids.append(unit_id)

    if len(deduped_unit_ids) > MAX_TARGET_SCOPE_UNITS:
        return (
            {},
            "target_scope_too_wide",
            f"target_scope.asset_unit_ids は最大 {MAX_TARGET_SCOPE_UNITS} 件までです。",
        )

    ledger = asset_unit_ledger if isinstance(asset_unit_ledger, dict) else {}
    if ledger and deduped_unit_ids:
        invalid_ids = [
            unit_id
            for unit_id in deduped_unit_ids
            if unit_id not in ledger and not CANONICAL_ASSET_UNIT_PATTERN.match(unit_id)
        ]
        if invalid_ids:
            return (
                {},
                "invalid_target_scope_asset_unit",
                f"target_scope.asset_unit_ids に不正な unit_id があります: {', '.join(invalid_ids)}",
            )

    if deduped_unit_ids:
        normalized["asset_unit_ids"] = deduped_unit_ids

    asset_units: list[dict[str, Any]] = []
    raw_units = raw_scope.get("asset_units")
    if raw_units is not None and not isinstance(raw_units, list):
        return {}, "invalid_target_scope", "target_scope.asset_units は list 形式である必要があります。"
    if isinstance(raw_units, list):
        for unit in raw_units:
            if not isinstance(unit, dict):
                return {}, "invalid_target_scope", "target_scope.asset_units の要素は object である必要があります。"
            unit_id = unit.get("unit_id")
            if not isinstance(unit_id, str) or not unit_id.strip():
                return {}, "invalid_target_scope", "target_scope.asset_units[].unit_id は必須です。"
            asset_units.append(dict(unit))

    existing_unit_ids = {
        str(unit.get("unit_id"))
        for unit in asset_units
        if isinstance(unit.get("unit_id"), str)
    }
    for unit_id in deduped_unit_ids:
        entry = ledger.get(unit_id)
        if isinstance(entry, dict) and unit_id not in existing_unit_ids:
            hydrated = dict(entry)
            hydrated.setdefault("unit_id", unit_id)
            asset_units.append(hydrated)
            existing_unit_ids.add(unit_id)

    if asset_units:
        normalized["asset_units"] = asset_units

    provided_scope_keys = [key for key in TARGET_SCOPE_ALLOWED_KEYS if key in raw_scope]
    if provided_scope_keys and not normalized:
        return {}, "invalid_target_scope_empty", "target_scope が空です。対象を指定してください。"

    return normalized, None, None


def _normalize_depends_on_field(step: dict[str, Any]) -> tuple[list[int], str | None]:
    depends_on = step.get("depends_on")
    if depends_on is None:
        step["depends_on"] = []
        return [], None
    if not isinstance(depends_on, list):
        return [], "depends_on は int の配列である必要があります。"
    deduped: list[int] = []
    for dep in depends_on:
        if not isinstance(dep, int):
            return [], "depends_on は int の配列である必要があります。"
        if dep not in deduped:
            deduped.append(dep)
    step["depends_on"] = deduped
    return deduped, None


async def plan_manager_node(
    state: State, config: RunnableConfig
) -> Command[Literal["planner", "patch_planner", "patch_gate", "supervisor"]]:
    """
    Keep plan frozen by default and route only patch operations
    to patch_gate.
    """
    product_type = state.get("product_type") if isinstance(state.get("product_type"), str) else None
    raw_plan = state.get("plan", []) or []
    plan = [
        normalize_step_v2(
            dict(step),
            product_type=product_type,
            fallback_capability=capability_from_any(dict(step)),
            fallback_instruction=str(dict(step).get("instruction") or "タスクを実行する"),
            fallback_title=str(dict(step).get("title") or dict(step).get("description") or "タスク"),
        )
        for step in raw_plan
        if isinstance(step, dict)
    ]
    latest_text = _extract_latest_user_text(state)
    latest_intent = _detect_intent(latest_text)
    interrupt_intent = bool(state.get("interrupt_intent"))
    if interrupt_intent and plan and latest_intent == "new":
        latest_intent = "refine"

    updates: dict[str, Any] = {
        "plan_status": "frozen",
        "request_intent": latest_intent,
        "interrupt_intent": interrupt_intent,
        "rethink_used_turn": int(state.get("rethink_used_turn", 0) or 0),
        "rethink_used_by_step": dict(state.get("rethink_used_by_step", {}) or {}),
    }
    if plan != raw_plan:
        updates["plan"] = plan
    latest_scope = _detect_target_scope(latest_text)
    if latest_scope:
        updates["target_scope"] = _hydrate_target_scope_from_ledger(
            latest_scope,
            state.get("asset_unit_ledger"),
        )

    if not plan:
        logger.info("PlanManager: no existing plan -> planner")
        return Command(goto="planner", update=updates)

    if not state.get("plan_baseline_hash"):
        updates["plan_baseline_hash"] = _hash_plan(plan)

    patch_ops = state.get("plan_patch_log") or []
    if patch_ops:
        logger.info("PlanManager: patch log detected -> patch_gate")
        return Command(goto="patch_gate", update=updates)

    if latest_intent in {"refine", "regenerate"}:
        logger.info("PlanManager: %s intent detected -> patch_planner", latest_intent)
        return Command(goto="patch_planner", update=updates)

    logger.info("PlanManager: frozen plan loaded -> supervisor")
    return Command(goto="supervisor", update=updates)


async def patch_gate_node(
    state: State, config: RunnableConfig
) -> Command[Literal["supervisor", "__end__"]]:
    """
    Apply patch operations with minimal hard validation.
    Hard errors are limited to structural type breaks; other issues are downgraded to warnings.
    """
    product_type = state.get("product_type") if isinstance(state.get("product_type"), str) else None
    raw_plan = state.get("plan", []) or []
    plan = [
        normalize_step_v2(
            dict(step),
            product_type=product_type,
            fallback_capability=capability_from_any(dict(step)),
            fallback_instruction=str(dict(step).get("instruction") or "タスクを実行する"),
            fallback_title=str(dict(step).get("title") or dict(step).get("description") or "タスク"),
        )
        for step in raw_plan
        if isinstance(step, dict)
    ]
    patch_ops = state.get("plan_patch_log") or []

    if not patch_ops:
        return Command(goto="supervisor", update={})

    asset_unit_ledger = state.get("asset_unit_ledger")
    latest_user_text = _extract_latest_user_text(state)
    warnings: list[str] = []

    def _warn(message: str) -> None:
        warnings.append(message)

    def _find_step_index_by_id(step_id: Any) -> int | None:
        if not isinstance(step_id, int):
            return None
        for index, step in enumerate(plan):
            if step.get("id") == step_id:
                return index
        return None

    def _normalize_target_scope_for_apply(raw_scope: Any) -> tuple[dict[str, Any] | None, str | None]:
        normalized_scope, scope_code, scope_message = _normalize_target_scope_for_patch(
            raw_scope,
            asset_unit_ledger if isinstance(asset_unit_ledger, dict) else None,
        )
        if scope_code is None:
            return normalized_scope, None
        if scope_code == "invalid_target_scope":
            return None, scope_message or "target_scope が不正です。"
        _warn(scope_message or "target_scope が不正なため無視しました。")
        return None, None

    def _apply_step_common(step: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        step_candidate = dict(step)
        if "target_scope" in step:
            normalized_scope, scope_error = _normalize_target_scope_for_apply(step.get("target_scope"))
            if scope_error:
                return None, scope_error
            if normalized_scope is None:
                step_candidate.pop("target_scope", None)
            else:
                step_candidate["target_scope"] = normalized_scope
        depends_on, depends_err = _normalize_depends_on_field(step_candidate)
        if depends_err:
            return None, depends_err
        step_candidate["depends_on"] = depends_on

        normalized_step = normalize_step_v2(
            step_candidate,
            product_type=product_type,
            fallback_capability=_capability_for_step(step_candidate) or "writer",
            fallback_instruction=str(step_candidate.get("instruction") or "追加作業を実行する"),
            fallback_title=str(step_candidate.get("title") or step_candidate.get("description") or "タスク"),
        )
        return normalized_step, None

    def _append_pending_step(step: dict[str, Any], *, anchor_step_id: int | None = None) -> int:
        next_id = _next_step_id(plan)
        if not isinstance(step.get("id"), int):
            step["id"] = next_id
        step["status"] = "pending"
        step["result_summary"] = None
        if not step.get("depends_on") and isinstance(anchor_step_id, int):
            step["depends_on"] = [anchor_step_id]
        plan.append(step)
        return int(step["id"])

    def _build_fallback_append_step(payload: dict[str, Any]) -> dict[str, Any]:
        payload_capability = payload.get("capability")
        capability = (
            payload_capability
            if isinstance(payload_capability, str) and payload_capability in {"writer", "researcher", "visualizer", "data_analyst"}
            else _infer_target_capability(latest_user_text, product_type)
        )
        instruction = str(
            payload.get("instruction")
            or latest_user_text
            or "追加修正を反映する"
        )
        fallback_step = _build_append_step(
            capability=capability,
            text=instruction,
            product_type=product_type,
            target_scope={},
        )
        for key in EDITABLE_PENDING_FIELDS:
            if key in {"target_scope", "depends_on"}:
                continue
            if key in payload:
                fallback_step[key] = payload[key]
        if "target_scope" in payload:
            fallback_step["target_scope"] = payload["target_scope"]
        if "depends_on" in payload:
            fallback_step["depends_on"] = payload["depends_on"]
        return fallback_step

    for raw_op in patch_ops:
        if not isinstance(raw_op, dict):
            _warn("Plan Patch op の形式が不正なためスキップしました。")
            continue
        op = dict(raw_op)
        op_type = op.get("op")
        if op_type not in ALLOWED_PATCH_OPS:
            _warn(f"未対応の patch op をスキップしました: {op_type}")
            continue

        payload = op.get("payload")
        if not isinstance(payload, dict):
            return _patch_gate_reject(
                "invalid_payload",
                "Plan Patch payload の形式が不正です。",
            )

        if op_type == "edit_pending":
            unknown_payload_keys = sorted(set(payload.keys()) - EDIT_PENDING_ALLOWED_PAYLOAD_KEYS)
        elif op_type == "split_pending":
            unknown_payload_keys = sorted(set(payload.keys()) - SPLIT_PENDING_ALLOWED_PAYLOAD_KEYS)
        else:
            unknown_payload_keys = sorted(set(payload.keys()) - APPEND_TAIL_ALLOWED_PAYLOAD_KEYS)
        if unknown_payload_keys:
            _warn(f"未許可キーを無視しました: {', '.join(unknown_payload_keys)}")
            payload = {key: value for key, value in payload.items() if key not in unknown_payload_keys}

        target_step_id = op.get("target_step_id")
        target_index = _find_step_index_by_id(target_step_id)
        target_step = plan[target_index] if target_index is not None else None
        target_is_pending = bool(target_step and target_step.get("status") == "pending")

        if op_type == "edit_pending":
            if not target_is_pending:
                _warn("編集対象stepがpendingでないため append_tail に変換しました。")
                fallback_step = _build_fallback_append_step(payload)
                prepared_step, step_err = _apply_step_common(fallback_step)
                if step_err:
                    return _patch_gate_reject("invalid_target_scope", step_err)
                existing_step_ids = [int(step.get("id")) for step in plan if isinstance(step.get("id"), int)]
                anchor_step_id = max(existing_step_ids) if existing_step_ids else None
                _append_pending_step(prepared_step or fallback_step, anchor_step_id=anchor_step_id)
                continue

            target_step = plan[target_index]  # type: ignore[index]
            for key, value in payload.items():
                if key in EDITABLE_PENDING_FIELDS:
                    if key == "target_scope":
                        normalized_scope, scope_error = _normalize_target_scope_for_apply(value)
                        if scope_error:
                            return _patch_gate_reject("invalid_target_scope", scope_error)
                        if normalized_scope is None:
                            target_step.pop("target_scope", None)
                        else:
                            target_step[key] = normalized_scope
                    elif key == "depends_on":
                        target_step[key] = value
                    else:
                        target_step[key] = value

            prepared_step, step_err = _apply_step_common(target_step)
            if step_err:
                return _patch_gate_reject("invalid_depends_on", step_err)
            if prepared_step is not None:
                plan[target_index] = prepared_step  # type: ignore[index]
            continue

        if op_type == "split_pending":
            new_steps = payload.get("new_steps") or payload.get("steps")
            if not isinstance(new_steps, list):
                return _patch_gate_reject(
                    "invalid_split_payload",
                    "split_pending の new_steps は list 形式である必要があります。",
                )
            if not new_steps:
                _warn("split_pending の new_steps が空のためスキップしました。")
                continue

            if not target_is_pending and target_step_id is not None:
                _warn("split対象stepがpendingでないため append_tail 相当で追加します。")

            fallback_instruction = (
                str(target_step.get("instruction", "追加作業を実行する"))
                if isinstance(target_step, dict)
                else "追加作業を実行する"
            )
            fallback_description = (
                str(target_step.get("description", "追加タスク"))
                if isinstance(target_step, dict)
                else "追加タスク"
            )
            last_new_step_id: int | None = None
            for raw_step in new_steps:
                if not isinstance(raw_step, dict):
                    _warn("split_pending の非object要素を無視しました。")
                    continue
                fallback_capability = (
                    _capability_for_step(target_step) if isinstance(target_step, dict) else "writer"
                ) or "writer"
                step = normalize_step_v2(
                    dict(raw_step),
                    product_type=product_type,
                    fallback_capability=fallback_capability,
                    fallback_instruction=fallback_instruction,
                    fallback_title=fallback_description,
                )
                if not step.get("depends_on"):
                    if isinstance(last_new_step_id, int):
                        step["depends_on"] = [last_new_step_id]
                    elif target_is_pending and isinstance(target_step_id, int):
                        step["depends_on"] = [target_step_id]

                prepared_step, step_err = _apply_step_common(step)
                if step_err:
                    return _patch_gate_reject("invalid_depends_on", step_err)
                sid = _append_pending_step(prepared_step or step)
                last_new_step_id = sid
            continue

        if op_type == "append_tail":
            steps = payload.get("steps")
            if steps is None:
                one_step = payload.get("step")
                steps = [one_step] if one_step is not None else []
            if not isinstance(steps, list):
                return _patch_gate_reject(
                    "invalid_append_payload",
                    "append_tail の steps は list 形式である必要があります。",
                )
            if not steps:
                _warn("append_tail の steps が空のためスキップしました。")
                continue

            existing_step_ids = [
                int(step.get("id"))
                for step in plan
                if isinstance(step.get("id"), int)
            ]
            anchor_step_id = max(existing_step_ids) if existing_step_ids else None
            last_new_step_id: int | None = None
            for raw_step in steps:
                if not isinstance(raw_step, dict):
                    _warn("append_tail の非object要素を無視しました。")
                    continue
                step = normalize_step_v2(
                    dict(raw_step),
                    product_type=product_type,
                    fallback_capability=_capability_for_step(raw_step) or "writer",
                    fallback_instruction=str(raw_step.get("instruction") or "追加作業を実行する"),
                    fallback_title=str(raw_step.get("title") or raw_step.get("description") or "追加タスク"),
                )
                if not step.get("depends_on"):
                    if isinstance(last_new_step_id, int):
                        step["depends_on"] = [last_new_step_id]
                    elif isinstance(anchor_step_id, int):
                        step["depends_on"] = [anchor_step_id]

                prepared_step, step_err = _apply_step_common(step)
                if step_err:
                    return _patch_gate_reject("invalid_depends_on", step_err)
                sid = _append_pending_step(prepared_step or step)
                last_new_step_id = sid

    message_content = "修正指示を実行計画に反映しました。"
    result_code = "patch_applied"
    additional_kwargs: dict[str, Any] = {"result_code": result_code}
    if warnings:
        message_content = "修正指示を実行計画に反映しました（一部警告あり）。"
        additional_kwargs = {
            "result_code": "patch_applied_with_warnings",
            "warnings": warnings,
        }

    return Command(
        goto="supervisor",
        update={
            "plan": plan,
            "plan_patch_log": [],
            "plan_baseline_hash": _hash_plan(plan),
            "messages": [
                AIMessage(
                    content=message_content,
                    name="patch_gate",
                    additional_kwargs=additional_kwargs,
                )
            ],
        },
    )


async def patch_planner_node(
    state: State, config: RunnableConfig
) -> Command[Literal["patch_gate", "supervisor"]]:
    """
    Translate user refinement/regeneration requests into structured PlanPatchOp list.
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
    if not plan:
        return Command(goto="supervisor", update={})

    user_text = _extract_latest_user_text(state)
    intent = str(state.get("request_intent") or _detect_intent(user_text))
    if intent not in {"refine", "regenerate"}:
        return Command(goto="supervisor", update={})

    target_scope = _detect_target_scope(user_text)
    if not target_scope:
        existing_scope = state.get("target_scope")
        if isinstance(existing_scope, dict):
            target_scope = dict(existing_scope)
    target_scope = _hydrate_target_scope_from_ledger(
        target_scope or {},
        state.get("asset_unit_ledger"),
    )

    target_capability = _infer_target_capability(user_text, product_type)
    pending_step = _find_pending_step(plan, target_capability)
    patch_ops: list[dict[str, Any]] = []

    force_append_tail = intent == "regenerate"

    if not force_append_tail and pending_step is not None and isinstance(pending_step.get("id"), int):
        pending_step_id = int(pending_step["id"])
        updated_instruction = (
            f"{pending_step.get('instruction', '')}\n"
            f"追加修正指示: {user_text}"
        ).strip()
        payload: dict[str, Any] = {
            "instruction": updated_instruction,
            "title": str(pending_step.get("title") or "修正反映"),
            "description": str(pending_step.get("description") or "ユーザー修正反映"),
            "mode": str(pending_step.get("mode") or default_mode_for_capability(target_capability, product_type, user_text)),
            "success_criteria": ["ユーザー修正指示を反映している"],
            "validation": ["ユーザー修正指示を反映している"],
        }
        if target_scope:
            payload["target_scope"] = target_scope

        if any(keyword in user_text for keyword in SPLIT_HINT_KEYWORDS):
            split_steps = [
                _build_append_step(
                    capability=target_capability,
                    text=f"修正案を検討: {user_text}",
                    product_type=product_type,
                    target_scope=target_scope,
                ),
                _build_append_step(
                    capability=target_capability,
                    text=f"修正を実反映: {user_text}",
                    product_type=product_type,
                    target_scope=target_scope,
                ),
            ]
            patch_ops.append(
                {
                    "op": "split_pending",
                    "target_step_id": pending_step_id,
                    "payload": {"new_steps": split_steps},
                }
            )
        else:
            patch_ops.append(
                {
                    "op": "edit_pending",
                    "target_step_id": pending_step_id,
                    "payload": payload,
                }
            )
    else:
        append_text = user_text if intent == "refine" else f"再生成指示: {user_text}"
        append_steps = [
            _build_append_step(
                capability=target_capability,
                text=append_text,
                product_type=product_type,
                target_scope=target_scope,
            )
        ]
        if intent == "regenerate":
            append_steps[0]["title"] = "再生成"
            append_steps[0]["description"] = "既存成果物を参照して再生成"
            append_steps[0]["success_criteria"] = ["既存成果物との差分を反映して再生成されている"]
            append_steps[0]["validation"] = ["再生成結果がユーザー意図に沿っている"]
        if target_capability == "visualizer":
            append_steps.append(
                _build_append_step(
                    capability="data_analyst",
                    text="更新画像の再パッケージング",
                    product_type=product_type,
                    target_scope=target_scope,
                )
            )
        patch_ops.append({"op": "append_tail", "payload": {"steps": append_steps}})

    if not patch_ops:
        return Command(goto="supervisor", update={})

    return Command(
        goto="patch_gate",
        update={
            "plan_patch_log": patch_ops,
            "messages": [
                AIMessage(
                    content=f"修正指示を構造化しました（{patch_ops[0]['op']}）。",
                    name="patch_planner",
                )
            ],
        },
    )


async def retry_or_alt_mode_node(
    state: State, config: RunnableConfig
) -> Command[Literal["researcher", "writer", "visualizer", "data_analyst", "supervisor", "__end__"]]:
    """
    Retry policy:
      - first retry: same mode
      - second retry: append fallback step
      - exceed limits: ask user clarification
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
        return Command(
            goto="__end__",
            update={},
        )

    destination = _resolve_worker_destination(blocked_step)
    if destination is None:
        return Command(goto="supervisor", update={})

    quality_reports = dict(state.get("quality_reports", {}) or {})
    report = quality_reports.get(origin_step_id)
    failed_checks = report.get("failed_checks") if isinstance(report, dict) else None
    if isinstance(failed_checks, list) and any(str(item) == "missing_research" for item in failed_checks):
        return Command(
            goto="__end__",
            update={},
        )

    rethink_used_by_step[origin_step_id] = step_retry_count + 1
    rethink_used_turn += 1

    if step_retry_count == 0:
        plan[blocked_index]["status"] = "in_progress"
        return Command(
            goto=destination,  # type: ignore[arg-type]
            update={
                "plan": plan,
                "rethink_used_turn": rethink_used_turn,
                "rethink_used_by_step": rethink_used_by_step,
            },
        )

    # step_retry_count == 1 -> append one fallback task and let supervisor continue
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
            fallback_capability=_capability_for_step(fallback_step) or "writer",
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
