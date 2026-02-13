import logging
import json
import re
from typing import Any, Literal
from pydantic import BaseModel, Field

from langgraph.types import Command
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.callbacks.manager import adispatch_custom_event

from src.infrastructure.llm.llm import astream_with_retry, get_llm_by_type
from src.resources.prompts.template import apply_prompt_template
from src.core.workflow.state import State
from src.core.workflow.step_v2 import capability_from_any, plan_steps_for_ui
from .common import run_structured_output, resolve_step_dependency_context, build_step_asset_pool

logger = logging.getLogger(__name__)

CAPABILITY_TO_DESTINATION = {
    "writer": "writer",
    "researcher": "researcher",
    "visualizer": "visualizer",
    "data_analyst": "data_analyst",
}
MAX_SELECTED_ASSETS_PER_STEP = 8


class StepAssetSelection(BaseModel):
    selected_asset_ids: list[str] = Field(default_factory=list, description="選択したasset_id一覧")
    reason: str | None = Field(default=None, description="選択理由")


class RequirementAssetBinding(BaseModel):
    role: str = Field(description="asset requirement role")
    asset_ids: list[str] = Field(default_factory=list, description="選択したasset_id一覧")
    reason: str | None = Field(default=None, description="選択理由")


class StepAssetBindingSelection(BaseModel):
    bindings: list[RequirementAssetBinding] = Field(default_factory=list, description="roleごとの選択結果")


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


def _build_failure_instruction(
    *,
    instruction: str | None,
    result_summary: str | None,
    failed_checks: list[str],
) -> str:
    base_instruction = (instruction or "").strip()
    if not base_instruction:
        base_instruction = "タスクを実行する"

    notes: list[str] = []
    if isinstance(result_summary, str) and result_summary.strip():
        notes.append(f"前回結果: {result_summary.strip()}")
    if failed_checks:
        notes.append(f"失敗チェック: {', '.join(sorted(set(failed_checks)))}")
    if not notes:
        notes.append("前回結果: 出力が要件を満たしませんでした。")

    guidance = (
        "上記の失敗要因を解消したうえで再リクエストしてください。"
        "現在の実行は失敗として終了します。"
    )
    return (
        f"{base_instruction}\n\n[SUPERVISOR_FAILURE]\n"
        f"{' / '.join(notes)}\n"
        f"{guidance}"
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


def _extract_visualizer_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows: list[dict[str, Any]] = []

    for key in ("prompts", "slides"):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    rows.append(item)

    for page_key in ("design_pages", "comic_pages", "pages"):
        pages = payload.get(page_key)
        if not isinstance(pages, list):
            continue
        for item in pages:
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            if "slide_number" not in normalized and isinstance(normalized.get("page_number"), int):
                normalized["slide_number"] = normalized.get("page_number")
            rows.append(normalized)

    characters = payload.get("characters")
    if isinstance(characters, list):
        for item in characters:
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            if "slide_number" not in normalized and isinstance(normalized.get("character_number"), int):
                normalized["slide_number"] = normalized.get("character_number")
            rows.append(normalized)

    return rows


def _extract_generated_visual_image_url(item: dict[str, Any]) -> str | None:
    for key in ("generated_image_url", "image_url"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_failure_metadata(current_step: dict, artifact_value: object) -> tuple[bool, list[str], str | None]:
    failed = False
    failed_checks: list[str] = []
    notes: str | None = None
    capability = current_step.get("capability")

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
        if capability == "data_analyst":
            execution_log = parsed.get("execution_log")
            if _result_summary_indicates_failure(execution_log if isinstance(execution_log, str) else None):
                failed = True
                if not notes and isinstance(execution_log, str):
                    notes = execution_log
        else:
            execution_summary = parsed.get("execution_summary")
            if _result_summary_indicates_failure(execution_summary if isinstance(execution_summary, str) else None):
                failed = True
                if not notes and isinstance(execution_summary, str):
                    notes = execution_summary

        if capability == "visualizer":
            rows = _extract_visualizer_rows(parsed)
            if rows:
                generated_count = 0
                for item in rows:
                    image_url = _extract_generated_visual_image_url(item)
                    if isinstance(image_url, str) and image_url.strip():
                        generated_count += 1
                if generated_count == 0:
                    failed = True
                    failed_checks.append("all_images_failed")
                    if not notes:
                        notes = "Visualizer produced no generated_image_url in output rows."

    if failed and not failed_checks:
        failed_checks = ["worker_execution"]
    failed_checks = sorted(set(failed_checks))
    return failed, failed_checks, notes

def _normalize_step_asset_requirements(step: dict[str, Any]) -> list[dict[str, Any]]:
    raw = step.get("asset_requirements")
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen_roles: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        if not role or role in seen_roles:
            continue
        seen_roles.add(role)
        scope = str(item.get("scope") or "global").strip()
        if scope not in {"global", "per_unit"}:
            scope = "global"
        mime_allow = [str(v).strip() for v in (item.get("mime_allow") or []) if isinstance(v, str) and str(v).strip()]
        source_preference = [
            str(v).strip() for v in (item.get("source_preference") or []) if isinstance(v, str) and str(v).strip()
        ]
        max_items = item.get("max_items")
        if not isinstance(max_items, int):
            max_items = 3
        max_items = max(1, min(max_items, MAX_SELECTED_ASSETS_PER_STEP))
        normalized.append(
            {
                "role": role,
                "required": bool(item.get("required")) if isinstance(item.get("required"), bool) else False,
                "scope": scope,
                "mime_allow": mime_allow,
                "source_preference": source_preference,
                "max_items": max_items,
                "instruction": str(item.get("instruction") or "").strip() or None,
            }
        )
    return normalized


def _asset_hints(item: dict[str, Any]) -> list[str]:
    hints = item.get("role_hints")
    if isinstance(hints, list):
        return [str(v).strip().lower() for v in hints if isinstance(v, str) and str(v).strip()]
    return []


def _mime_matches(asset: dict[str, Any], pattern: str) -> bool:
    mime_type = str(asset.get("mime_type") or "").lower()
    uri = str(asset.get("uri") or "").lower()
    is_image = bool(asset.get("is_image"))
    candidate = pattern.strip().lower()
    if not candidate:
        return False
    if candidate == "*/*":
        return True
    if candidate == "image/*":
        return is_image or mime_type.startswith("image/")
    if candidate.endswith("/*"):
        prefix = candidate[:-1]
        return mime_type.startswith(prefix)
    if mime_type == candidate:
        return True
    if candidate == "application/pdf":
        return uri.endswith(".pdf")
    if candidate == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
        return uri.endswith(".pptx")
    if candidate == "text/csv":
        return uri.endswith(".csv")
    if candidate == "application/json":
        return uri.endswith(".json")
    return False


def _matches_role_semantics(asset: dict[str, Any], role: str) -> bool:
    role_l = role.lower()
    is_image = bool(asset.get("is_image"))
    mime_type = str(asset.get("mime_type") or "").lower()
    uri = str(asset.get("uri") or "").lower()
    hints = set(_asset_hints(asset))

    if role_l in {"style_reference", "reference_image", "character_reference", "base_image", "mask_image"}:
        return is_image or mime_type.startswith("image/")
    if role_l == "layout_reference":
        return is_image or mime_type.startswith("image/") or mime_type == "application/pdf" or uri.endswith(".pdf")
    if role_l == "template_source":
        return (
            "template_source" in hints
            or uri.endswith(".pptx")
            or mime_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            or mime_type == "application/pdf"
            or is_image
        )
    if role_l == "data_source":
        return "data_source" in hints or (not is_image)
    if role_l == "reference_document":
        return mime_type.startswith("text/") or mime_type == "application/pdf" or (not is_image)
    return True


def _matches_source_preference(asset: dict[str, Any], source_preference: list[str]) -> bool:
    if not source_preference:
        return True
    blob = " ".join(
        [
            str(asset.get("source_type") or "").lower(),
            str(asset.get("producer_mode") or "").lower(),
            str(asset.get("producer_capability") or "").lower(),
            str(asset.get("label") or "").lower(),
            str(asset.get("title") or "").lower(),
            " ".join(_asset_hints(asset)),
        ]
    )
    for pref in source_preference:
        token = str(pref or "").strip().lower()
        if token and token in blob:
            return True
    return False


def _filter_assets_by_requirement(
    requirement: dict[str, Any],
    asset_pool: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    role = str(requirement.get("role") or "")
    mime_allow = [str(v) for v in (requirement.get("mime_allow") or []) if isinstance(v, str)]
    source_preference = [str(v) for v in (requirement.get("source_preference") or []) if isinstance(v, str)]

    candidates: list[dict[str, Any]] = []
    for item in asset_pool.values():
        if not isinstance(item, dict):
            continue
        if mime_allow and not any(_mime_matches(item, pattern) for pattern in mime_allow):
            continue
        if not _matches_role_semantics(item, role):
            continue
        if source_preference and not _matches_source_preference(item, source_preference):
            continue
        candidates.append(item)

    if candidates:
        return candidates

    # source_preferenceで該当ゼロなら、前段の制約を緩めて再取得する
    if source_preference:
        for item in asset_pool.values():
            if not isinstance(item, dict):
                continue
            if mime_allow and not any(_mime_matches(item, pattern) for pattern in mime_allow):
                continue
            if not _matches_role_semantics(item, role):
                continue
            candidates.append(item)
    return candidates


def _asset_rank_score(asset: dict[str, Any], requirement: dict[str, Any]) -> int:
    score = 0
    role = str(requirement.get("role") or "").lower()
    hints = set(_asset_hints(asset))
    source_type = str(asset.get("source_type") or "").lower()
    producer_step_id = int(asset.get("producer_step_id") or 0)

    if role in hints:
        score += 7
    if role in {"style_reference", "reference_image"} and source_type in {"user_upload", "selected_image_input"}:
        score += 5
    if role in {"layout_reference", "template_source"} and (
        "template_source" in hints or source_type in {"user_upload", "dependency_artifact"}
    ):
        score += 5
    if role == "data_source" and ("data_source" in hints or not bool(asset.get("is_image"))):
        score += 4
    if bool(asset.get("is_image")) and role in {"style_reference", "layout_reference", "character_reference"}:
        score += 2
    score += max(min(producer_step_id, 100), 0)
    return score


def _sort_candidates_for_requirement(
    requirement: dict[str, Any],
    asset_pool: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = _filter_assets_by_requirement(requirement, asset_pool)
    return sorted(
        candidates,
        key=lambda item: (
            _asset_rank_score(item, requirement),
            int(item.get("producer_step_id") or 0),
        ),
        reverse=True,
    )


def _fallback_asset_bindings(
    requirements: list[dict[str, Any]],
    asset_pool: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not requirements:
        return []
    bindings: list[dict[str, Any]] = []
    for requirement in requirements:
        role = str(requirement.get("role") or "").strip()
        if not role:
            continue
        max_items = int(requirement.get("max_items") or 3)
        sorted_candidates = _sort_candidates_for_requirement(requirement, asset_pool)
        selected_ids: list[str] = []
        for item in sorted_candidates:
            asset_id = item.get("asset_id")
            if isinstance(asset_id, str) and asset_id not in selected_ids:
                selected_ids.append(asset_id)
            if len(selected_ids) >= max_items:
                break
        bindings.append(
            {
                "role": role,
                "asset_ids": selected_ids,
                "reason": "rule_based_fallback",
            }
        )
    return bindings


def _fallback_selected_asset_ids(
    step: dict[str, Any],
    asset_pool: dict[str, dict[str, Any]],
) -> list[str]:
    capability = capability_from_any(step)
    items = list(asset_pool.values())
    if capability == "visualizer":
        items = [item for item in items if bool(item.get("is_image"))]
    elif capability == "writer":
        items = [item for item in items if not bool(item.get("is_image")) or item.get("source_type") == "user_upload"] or items

    # Prefer newer upstream artifacts when producer_step_id is available.
    items.sort(key=lambda item: int(item.get("producer_step_id") or 0), reverse=True)
    selected: list[str] = []
    for item in items:
        asset_id = item.get("asset_id")
        if isinstance(asset_id, str) and asset_id not in selected:
            selected.append(asset_id)
        if len(selected) >= MAX_SELECTED_ASSETS_PER_STEP:
            break
    return selected


def _asset_candidate_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": item.get("asset_id"),
        "source_type": item.get("source_type"),
        "mime_type": item.get("mime_type"),
        "is_image": bool(item.get("is_image")),
        "producer_step_id": item.get("producer_step_id"),
        "producer_capability": item.get("producer_capability"),
        "producer_mode": item.get("producer_mode"),
        "label": item.get("label"),
        "title": item.get("title"),
        "role_hints": item.get("role_hints") if isinstance(item.get("role_hints"), list) else [],
    }


async def _select_assets_for_step(
    *,
    state: State,
    step: dict[str, Any],
    dependency_context: dict[str, Any],
    config: RunnableConfig,
) -> tuple[dict[str, dict[str, Any]], list[str], list[dict[str, Any]]]:
    asset_pool = build_step_asset_pool(state, current_step=step, dependency_context=dependency_context)
    if not asset_pool:
        return asset_pool, [], []

    step_id = step.get("id")
    requirements = _normalize_step_asset_requirements(step)
    candidate_assets = [_asset_candidate_payload(item) for item in asset_pool.values()]

    if requirements:
        sorted_candidates_by_role: dict[str, list[dict[str, Any]]] = {}
        requirement_candidates: dict[str, list[dict[str, Any]]] = {}
        for requirement in requirements:
            role = str(requirement.get("role") or "").strip()
            if not role:
                continue
            sorted_candidates = _sort_candidates_for_requirement(requirement, asset_pool)
            sorted_candidates_by_role[role] = sorted_candidates
            requirement_candidates[role] = [_asset_candidate_payload(item) for item in sorted_candidates[:12]]

        selector_input = {
            "step_id": step_id,
            "capability": step.get("capability"),
            "mode": step.get("mode"),
            "instruction": step.get("instruction"),
            "description": step.get("description"),
            "inputs": step.get("inputs") or [],
            "depends_on": step.get("depends_on") or [],
            "asset_requirements": requirements,
            "candidate_assets_by_role": requirement_candidates,
            "candidate_assets": candidate_assets,
        }

        selector_messages = [
            SystemMessage(
                content=(
                    "あなたはSupervisor配下のアセット解決器です。"
                    "asset_requirementsごとに適切なasset_idを選択してください。"
                    "各roleはmax_items以内、required=trueのroleは可能な限り空にしないでください。"
                    "出力はStepAssetBindingSelectionスキーマに厳密準拠してください。"
                )
            ),
            HumanMessage(content=json.dumps(selector_input, ensure_ascii=False), name="supervisor"),
        ]

        selected_bindings: list[dict[str, Any]] = []
        try:
            llm = get_llm_by_type("reasoning")
            stream_config = config.copy()
            stream_config["run_name"] = "supervisor_asset_requirement_resolver"
            selection = await run_structured_output(
                llm=llm,
                schema=StepAssetBindingSelection,
                messages=selector_messages,
                config=stream_config,
                repair_hint="Schema: StepAssetBindingSelection. No extra text.",
            )
            role_to_requirement = {
                str(req.get("role")): req for req in requirements if isinstance(req.get("role"), str)
            }
            for row in selection.bindings:
                role = str(row.role).strip()
                if not role or role not in role_to_requirement:
                    continue
                requirement = role_to_requirement[role]
                max_items = int(requirement.get("max_items") or 3)
                valid_candidates = sorted_candidates_by_role.get(role) or _sort_candidates_for_requirement(
                    requirement, asset_pool
                )
                valid_ids = {
                    str(item.get("asset_id"))
                    for item in valid_candidates
                    if isinstance(item.get("asset_id"), str)
                }
                deduped_ids: list[str] = []
                for asset_id in row.asset_ids:
                    if not isinstance(asset_id, str):
                        continue
                    if asset_id not in asset_pool:
                        continue
                    if valid_ids and asset_id not in valid_ids:
                        continue
                    if asset_id in deduped_ids:
                        continue
                    deduped_ids.append(asset_id)
                    if len(deduped_ids) >= max_items:
                        break
                selected_bindings.append(
                    {
                        "role": role,
                        "asset_ids": deduped_ids,
                        "reason": row.reason,
                    }
                )
        except Exception as e:
            logger.warning("Supervisor requirement-based asset selection failed, fallback is applied: %s", e)

        if not selected_bindings:
            selected_bindings = _fallback_asset_bindings(requirements, asset_pool)

        # required roleが空ならfallbackで補完
        existing_roles = {str(row.get("role")) for row in selected_bindings if isinstance(row, dict)}
        for requirement in requirements:
            role = str(requirement.get("role") or "").strip()
            if not role or role in existing_roles:
                continue
            selected_bindings.append(
                {
                    "role": role,
                    "asset_ids": [],
                    "reason": "missing_in_llm_response",
                }
            )

        role_to_binding = {
            str(row.get("role")): row
            for row in selected_bindings
            if isinstance(row, dict) and isinstance(row.get("role"), str)
        }
        for requirement in requirements:
            role = str(requirement.get("role") or "").strip()
            if not role or not requirement.get("required"):
                continue
            binding = role_to_binding.get(role)
            asset_ids = binding.get("asset_ids") if isinstance(binding, dict) else None
            if isinstance(asset_ids, list) and asset_ids:
                continue
            fallback_row = _fallback_asset_bindings([requirement], asset_pool)
            if fallback_row and fallback_row[0].get("asset_ids"):
                role_to_binding[role] = fallback_row[0]
            elif binding is None:
                role_to_binding[role] = {"role": role, "asset_ids": [], "reason": "required_but_not_found"}

        finalized_bindings = list(role_to_binding.values())
        selected_ids: list[str] = []
        for row in finalized_bindings:
            asset_ids = row.get("asset_ids")
            if not isinstance(asset_ids, list):
                continue
            for asset_id in asset_ids:
                if not isinstance(asset_id, str):
                    continue
                if asset_id not in asset_pool or asset_id in selected_ids:
                    continue
                selected_ids.append(asset_id)
                if len(selected_ids) >= MAX_SELECTED_ASSETS_PER_STEP:
                    break
            if len(selected_ids) >= MAX_SELECTED_ASSETS_PER_STEP:
                break

        if not selected_ids:
            selected_ids = _fallback_selected_asset_ids(step, asset_pool)

        return asset_pool, selected_ids, finalized_bindings

    selector_input = {
        "step_id": step_id,
        "capability": step.get("capability"),
        "mode": step.get("mode"),
        "instruction": step.get("instruction"),
        "description": step.get("description"),
        "inputs": step.get("inputs") or [],
        "depends_on": step.get("depends_on") or [],
        "candidate_assets": candidate_assets,
    }

    selector_messages = [
        SystemMessage(
            content=(
                "あなたは実行ステップに渡すアセット選択器です。"
                "候補から必要なasset_idだけ選び、JSONで返してください。"
                "capabilityとmodeに応じて必要な形式を選択し、不要なアセットは除外してください。"
                "visualizerは画像を優先し、writer/data_analystは指示に必要なファイルを優先してください。"
                "出力はStepAssetSelectionスキーマに厳密準拠してください。"
            )
        ),
        HumanMessage(content=json.dumps(selector_input, ensure_ascii=False), name="supervisor"),
    ]

    selected_ids: list[str] = []
    try:
        llm = get_llm_by_type("reasoning")
        stream_config = config.copy()
        stream_config["run_name"] = "supervisor_asset_selector"
        selection = await run_structured_output(
            llm=llm,
            schema=StepAssetSelection,
            messages=selector_messages,
            config=stream_config,
            repair_hint="Schema: StepAssetSelection. No extra text.",
        )
        valid_ids = [
            asset_id
            for asset_id in selection.selected_asset_ids
            if isinstance(asset_id, str) and asset_id in asset_pool
        ]
        deduped: list[str] = []
        for asset_id in valid_ids:
            if asset_id not in deduped:
                deduped.append(asset_id)
        selected_ids = deduped[:MAX_SELECTED_ASSETS_PER_STEP]
    except Exception as e:
        logger.warning("Supervisor asset selection failed, fallback selection is applied: %s", e)

    if not selected_ids:
        selected_ids = _fallback_selected_asset_ids(step, asset_pool)

    return asset_pool, selected_ids, []

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
        
        async for chunk in astream_with_retry(
            lambda: llm.astream(messages, config=stream_config),
            operation_name="supervisor.astream",
        ):
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


def _find_current_step(plan: list[dict[str, Any]]) -> tuple[int, dict[str, Any] | None]:
    for index, step in enumerate(plan):
        if step.get("status") == "in_progress":
            return index, step
    for index, step in enumerate(plan):
        if step.get("status") == "pending":
            return index, step
    return -1, None


async def supervisor_node(state: State, config: RunnableConfig) -> Command:
    """
    Supervisor Node (Orchestrator).
    """
    logger.info("Supervisor evaluating state")
    
    plan = state.get("plan", [])
    _normalize_plan_statuses(plan)
    
    current_step_index, current_step = _find_current_step(plan)
    
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

        if artifact_exists:

            plan[current_step_index]["status"] = "completed"
            await _dispatch_plan_step_ended(current_step, "completed", config)
            logger.info(f"Step {current_step_index} ({destination or 'unknown'}) completed. Marking as completed.")

            await _dispatch_plan_update(plan, config)
            
            # Generate report after completion
            report = await _generate_supervisor_report(state, config, report_event="step_completed")

            return Command(
                goto="supervisor",
                update={
                    "plan": plan,
                    "messages": [AIMessage(content=report, name="supervisor")],
                },
            )
        else:
             if destination is None:
                 logger.error(f"Step {current_step_index} has no resolvable destination.")
                 plan[current_step_index]["status"] = "blocked"
                 return Command(
                     goto="__end__",
                     update={"plan": plan},
                 )
             logger.info(f"Step {current_step_index} ({destination}) in progress but no artifact. Re-assigning.")
             return Command(goto=destination)

    elif current_step.get("status") == "pending":
        if destination is None:
            logger.error(f"Pending step {current_step_index} has no resolvable destination.")
            plan[current_step_index]["status"] = "blocked"
            return Command(
                goto="__end__",
                update={"plan": plan},
            )

        logger.info(f"Starting Step {current_step_index} ({destination})")

        dependency_context = resolve_step_dependency_context(state, current_step)
        step_asset_pool, selected_asset_ids, selected_asset_bindings = await _select_assets_for_step(
            state=state,
            step=current_step,
            dependency_context=dependency_context,
            config=config,
        )
        asset_catalog = dict(state.get("asset_catalog") or {})
        asset_catalog.update(step_asset_pool)
        candidate_assets_by_step = dict(state.get("candidate_assets_by_step") or {})
        selected_assets_by_step = dict(state.get("selected_assets_by_step") or {})
        asset_bindings_by_step = dict(state.get("asset_bindings_by_step") or {})
        step_id = current_step.get("id")
        if isinstance(step_id, int):
            candidate_assets_by_step[str(step_id)] = list(step_asset_pool.keys())
            selected_assets_by_step[str(step_id)] = selected_asset_ids
            asset_bindings_by_step[str(step_id)] = selected_asset_bindings

        plan[current_step_index]["status"] = "in_progress"
        await _dispatch_plan_step_started(current_step, config)
        try:
            await adispatch_custom_event(
                "data-step-assets-selected",
                {
                    "step_id": current_step.get("id"),
                    "capability": current_step.get("capability"),
                    "mode": current_step.get("mode"),
                    "selected_asset_ids": selected_asset_ids,
                    "asset_bindings": selected_asset_bindings,
                },
                config=config,
            )
        except Exception as e:
            logger.warning("Failed to dispatch selected assets event: %s", e)

        await _dispatch_plan_update(plan, config)
        
        # Generate report for next step
        report = await _generate_supervisor_report(state, config, report_event="step_started")

        return Command(
            goto=destination,
            update={
                "plan": plan,
                "messages": [AIMessage(content=report, name="supervisor")],
                "asset_catalog": asset_catalog,
                "candidate_assets_by_step": candidate_assets_by_step,
                "selected_assets_by_step": selected_assets_by_step,
                "asset_bindings_by_step": asset_bindings_by_step,
            },
        )
        
    return Command(goto="__end__")
