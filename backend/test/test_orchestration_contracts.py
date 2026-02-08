import pytest
from pydantic import ValidationError

from src.shared.schemas.outputs import (
    ArtifactEnvelope,
    OrchestrationTaskStep,
    PlanPatchOp,
    QualityReport,
    ResearchImageCandidate,
    TargetScope,
)


def test_orchestration_task_step_defaults() -> None:
    scope = TargetScope(
        slide_numbers=[3],
        character_ids=["hero"],
        asset_unit_ids=["slide:3"],
        asset_units=[{"unit_id": "slide:3", "unit_kind": "slide", "unit_index": 3}],
    )
    step = OrchestrationTaskStep(
        id=10,
        capability="writer",
        mode="story_framework",
        instruction="漫画の世界観を定義する",
        title="世界観定義",
        description="漫画の世界観を定義する",
        success_criteria=["世界観を3要素で定義"],
        target_scope=scope,
    )

    assert step.status == "pending"
    assert step.retries_used == 0
    assert step.target_scope is not None
    assert step.target_scope.slide_numbers == [3]
    assert step.target_scope.asset_unit_ids == ["slide:3"]


def test_plan_patch_op_rejects_unknown_op() -> None:
    with pytest.raises(ValidationError):
        PlanPatchOp(op="rebuild_all", payload={})  # type: ignore[arg-type]


def test_artifact_envelope_rejects_unknown_product_type() -> None:
    with pytest.raises(ValidationError):
        ArtifactEnvelope(
            artifact_id="a_1",
            artifact_type="writer.story_framework.v1",
            producer="writer",
            product_type="poster",  # type: ignore[arg-type]
            content={"theme": "x"},
        )


def test_research_image_candidate_requires_source_and_license() -> None:
    with pytest.raises(ValidationError):
        ResearchImageCandidate(
            image_url="https://example.com/image.png",
            provider="search-engine",
        )


def test_quality_report_score_bounds() -> None:
    ok = QualityReport(step_id=1, passed=True, score=0.8)
    assert ok.score == 0.8

    with pytest.raises(ValidationError):
        QualityReport(step_id=1, passed=False, score=1.2)
