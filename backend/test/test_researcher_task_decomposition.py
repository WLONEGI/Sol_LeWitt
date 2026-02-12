from src.core.workflow.nodes.researcher import (
    _build_fallback_research_tasks,
    _ensure_minimum_task_diversity,
    _extract_instruction_perspectives,
)
from src.shared.schemas import ResearchTask


def test_extract_instruction_perspectives_from_bullet_section() -> None:
    instruction = (
        "SaaS向けQBR資料を作るために調査する。\n\n"
        "調査観点:\n"
        "- 主要KPIの定義と計算式\n"
        "- 役員向け可視化の先行事例\n"
        "- 市場トレンドの変化と影響\n"
    )

    perspectives = _extract_instruction_perspectives(instruction)
    assert perspectives == [
        "主要KPIの定義と計算式",
        "役員向け可視化の先行事例",
        "市場トレンドの変化と影響",
    ]


def test_build_fallback_research_tasks_creates_multiple_perspectives() -> None:
    instruction = (
        "調査観点:\n"
        "- 観点A\n"
        "- 観点B\n"
        "- 観点C\n"
    )
    tasks = _build_fallback_research_tasks(instruction, step_mode="text_search")

    assert len(tasks) >= 2
    assert tasks[0].perspective == "観点A"
    assert tasks[1].perspective == "観点B"
    assert all(task.search_mode == "text_search" for task in tasks)


def test_ensure_minimum_task_diversity_expands_single_task() -> None:
    single = [
        ResearchTask(
            id=1,
            perspective="単一観点",
            search_mode="text_search",
            query_hints=["単一観点"],
            priority="high",
            expected_output="単一観点レポート",
        )
    ]
    instruction = "調査観点:\n- 観点A\n- 観点B\n- 観点C"

    diversified = _ensure_minimum_task_diversity(single, instruction, step_mode="text_search")
    assert len(diversified) >= 2
    assert diversified[0].perspective != "単一観点"
