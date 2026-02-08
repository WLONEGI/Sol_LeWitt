from src.core.workflow.nodes.planner import _missing_required_research_step


def test_missing_required_research_step_when_user_request_demands_sources() -> None:
    plan_steps = [
        {
            "id": 1,
            "capability": "writer",
            "instruction": "スライド構成を作成する",
        },
        {
            "id": 2,
            "capability": "visualizer",
            "instruction": "画像生成を行う",
        },
    ]
    missing, reason = _missing_required_research_step(
        plan_steps,
        "中世情報の出典を調査してから漫画を作って",
    )
    assert missing is True
    assert "Research requirement" in reason


def test_missing_required_research_step_when_step_requires_reference() -> None:
    plan_steps = [
        {
            "id": 1,
            "capability": "writer",
            "instruction": "出典を併記した構成案を作る",
        }
    ]
    missing, _ = _missing_required_research_step(
        plan_steps,
        "資料をもとにスライド化して",
    )
    assert missing is True


def test_no_missing_when_research_step_is_explicit() -> None:
    plan_steps = [
        {
            "id": 1,
            "capability": "researcher",
            "instruction": "中世資料を調査する",
        },
        {
            "id": 2,
            "capability": "writer",
            "instruction": "調査結果をもとに脚本を作成する",
        },
    ]
    missing, reason = _missing_required_research_step(
        plan_steps,
        "中世の出典を必ず含めて漫画化して",
    )
    assert missing is False
    assert reason == ""


def test_no_missing_when_research_not_required() -> None:
    plan_steps = [
        {
            "id": 1,
            "capability": "writer",
            "instruction": "既存設定から漫画プロットを作る",
        }
    ]
    missing, reason = _missing_required_research_step(
        plan_steps,
        "このプロットを4ページ漫画にして",
    )
    assert missing is False
    assert reason == ""
