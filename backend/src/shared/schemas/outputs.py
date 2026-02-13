# Pydanticスキーマ: LangGraphノードの構造化出力定義
import re
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator





# === Orchestration Contracts (v1) ===
ProductType = Literal["slide", "design", "comic"]
IntentType = Literal["new", "refine", "regenerate"]
TaskCapability = Literal["writer", "visualizer", "researcher", "data_analyst"]
TaskStatus = Literal["pending", "in_progress", "completed", "blocked"]
ArtifactStatus = Literal["streaming", "completed", "failed"]
AssetRequirementScope = Literal["global", "per_unit"]


class TargetScope(BaseModel):
    """部分修正の対象範囲."""
    asset_unit_ids: List[str] = Field(default_factory=list, description="最小更新単位のID（例: slide:3）")
    asset_units: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="最小更新単位の詳細（unit_kind/unit_index/artifact_id等）"
    )
    slide_numbers: List[int] = Field(default_factory=list)
    page_numbers: List[int] = Field(default_factory=list)
    panel_numbers: List[int] = Field(default_factory=list)
    character_ids: List[str] = Field(default_factory=list)
    artifact_ids: List[str] = Field(default_factory=list)


class AssetRequirement(BaseModel):
    """Plannerが宣言するアセット要求（抽象条件）."""
    role: str = Field(description="用途ロール（例: style_reference, layout_reference, template_source）")
    required: bool = Field(default=False, description="満たせない場合に失敗扱いにするか")
    scope: AssetRequirementScope = Field(default="global", description="適用範囲")
    mime_allow: List[str] = Field(
        default_factory=list,
        description="許可MIME（例: image/*, application/pdf）",
    )
    source_preference: List[str] = Field(
        default_factory=list,
        description="優先ソースヒント（例: user_upload, pptx_derived）",
    )
    max_items: int = Field(default=3, ge=1, le=8, description="最大選択数")
    instruction: Optional[str] = Field(default=None, description="補足条件")


class OrchestrationTaskStep(BaseModel):
    """実行時のTask Card."""
    id: int = Field(description="ステップ番号（1から始まる）")
    capability: TaskCapability = Field(description="実行担当のCapability")
    mode: str = Field(description="Workerの実行モード")
    instruction: str = Field(description="このステップの実行指示")
    title: str = Field(default="タスク", description="ステップタイトル")
    description: str = Field(default="タスク", description="ステップ説明")
    inputs: List[str] = Field(default_factory=list, description="入力成果物・前提条件")
    success_criteria: List[str] = Field(default_factory=list, description="受け入れ条件")
    asset_requirements: List[AssetRequirement] = Field(
        default_factory=list,
        description="このステップで必要なアセット要求",
    )
    target_scope: Optional[TargetScope] = Field(default=None, description="部分修正の対象範囲")
    status: TaskStatus = Field(default="pending", description="実行ステータス")
    result_summary: Optional[str] = Field(default=None, description="実行結果の要約")
    retries_used: int = Field(default=0, ge=0, description="当ステップで消費した再思考回数")


class TaskBoard(BaseModel):
    """実行キューの状態."""
    pending: List[int] = Field(default_factory=list)
    in_progress: List[int] = Field(default_factory=list)
    completed: List[int] = Field(default_factory=list)
    blocked: List[int] = Field(default_factory=list)


class QualityReport(BaseModel):
    """ステップ評価レポート."""
    step_id: int
    passed: bool
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    failed_checks: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class ArtifactEnvelope(BaseModel):
    """全成果物の共通エンベロープ."""
    artifact_id: str
    artifact_type: str
    producer: TaskCapability
    product_type: ProductType
    schema_version: Literal[1] = 1
    version: int = Field(default=1, ge=1)
    status: ArtifactStatus = "completed"
    depends_on: List[str] = Field(default_factory=list)
    content: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = Field(default=None, description="ISO8601")
    updated_at: Optional[str] = Field(default=None, description="ISO8601")


class ResearchImageCandidate(BaseModel):
    """Researcherが返す画像候補（UI表示用）."""
    image_url: str = Field(description="画像URL")
    source_url: str = Field(description="出典URL")
    license_note: str = Field(description="ライセンス・利用条件メモ")
    provider: str = Field(description="取得元プロバイダー名")
    caption: Optional[str] = Field(default=None, description="補足説明")
    relevance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


# === Planner Output ===
class TaskStep(BaseModel):
    """実行計画の1ステップ"""
    id: int = Field(description="ステップ番号（1から始まる）")
    capability: TaskCapability = Field(
        description="担当Capability（正規フォーマット）"
    )
    mode: Optional[str] = Field(
        default=None,
        description="Capability内の実行モード"
    )
    instruction: str = Field(
        description="エージェントへの詳細な指示（トーン、対象読者、具体的な要件を含む）"
    )
    title: Optional[str] = Field(default=None, description="このステップの短いタイトル（例：競合調査、構成案作成）")
    description: Optional[str] = Field(default=None, description="このステップの概要説明")
    inputs: List[str] = Field(
        default_factory=list,
        description="このステップで必要な入力（参照する成果物や前提）"
    )
    outputs: List[str] = Field(
        default_factory=list,
        description="このステップで生成すべき成果物"
    )
    preconditions: List[str] = Field(
        default_factory=list,
        description="実行前に満たすべき条件"
    )
    validation: List[str] = Field(
        default_factory=list,
        description="出力の妥当性を確認するためのチェック項目"
    )
    fallback: List[str] = Field(
        default_factory=list,
        description="失敗時の代替手段や再試行方針"
    )
    success_criteria: List[str] = Field(
        default_factory=list,
        description="受け入れ条件（新フォーマット）"
    )
    target_scope: Optional[TargetScope] = Field(
        default=None,
        description="部分修正対象"
    )
    depends_on: List[int] = Field(
        default_factory=list,
        description="依存するステップID（順序・参照関係）"
    )
    asset_requirements: List[AssetRequirement] = Field(
        default_factory=list,
        description="このステップで必要なアセット要求（抽象条件）",
    )
    design_direction: Optional[str] = Field(
        default=None,
        description="Visualizerへのデザイン指示（トーン、スタイル、モチーフなど）。Writerの場合はNoneでよい。"
    )
    status: TaskStatus = Field(
        default="pending",
        description="ステップの実行ステータス"
    )
    result_summary: Optional[str] = Field(
        default=None,
        description="実行結果の要約"
    )

    @model_validator(mode="after")
    def _normalize_step_shape(self) -> "TaskStep":
        if not self.instruction.strip():
            self.instruction = "タスクを実行する"

        if not self.description:
            self.description = self.title or self.instruction or "タスク"
        if not self.title:
            self.title = self.description or "タスク"

        if not self.validation and self.success_criteria:
            self.validation = list(self.success_criteria)
        if not self.success_criteria and self.validation:
            self.success_criteria = list(self.validation)

        return self



class PlannerOutput(BaseModel):
    """Plannerノードの出力"""
    steps: List[TaskStep] = Field(description="実行計画のステップリスト")




# === Writer Output ===
class SlideContent(BaseModel):
    """スライド1枚分のコンテンツ"""
    slide_number: int = Field(description="スライド番号")
    title: str = Field(description="スライドのタイトル（短く印象的に）")
    bullet_points: List[str] = Field(
        description="箇条書きのリスト（各項目は20文字以内を推奨）"
    )
    description: Optional[str] = Field(
        default=None,
        description="スライド内容の要約説明。アウトライン表示に使用される。"
    )
    key_message: Optional[str] = Field(
        default=None, 
        description="このスライドで伝えたい核心メッセージ（オプション）"
    )




class WriterSlideOutlineOutput(BaseModel):
    """Writer(mode=slide_outline) の出力。"""
    execution_summary: str = Field(description="実行結果の要約（例：『◯◯に関するスライド構成を5枚作成しました』）")
    user_message: str = Field(description="ユーザー向けの簡潔な進捗・成果メッセージ")
    slides: List[SlideContent] = Field(description="スライドコンテンツのリスト")


class StoryFrameworkPageBudget(BaseModel):
    """ページ数レンジ."""
    min: int = Field(ge=1, description="最小ページ数")
    max: int = Field(ge=1, description="最大ページ数")

    @model_validator(mode="after")
    def _validate_range(self) -> "StoryFrameworkPageBudget":
        if self.max < self.min:
            self.max = self.min
        return self


class StoryFrameworkFormatPolicy(BaseModel):
    """媒体・形式の方針."""
    series_type: Literal["oneshot", "serialized"] = Field(description="読切または連載")
    medium: Literal["print", "digital", "webtoon"] = Field(description="主媒体")
    page_budget: StoryFrameworkPageBudget = Field(description="ページ数レンジ")
    reading_direction: Literal["rtl", "ltr", "vertical_scroll"] = Field(description="読み方向")


class StoryFrameworkArcPhase(BaseModel):
    """物語フェーズ."""
    phase: str = Field(description="フェーズ名")
    purpose: str = Field(description="フェーズの目的")


class StoryFrameworkWorldPolicy(BaseModel):
    """世界観の方針."""
    era: str = Field(description="時代設定")
    primary_locations: List[str] = Field(default_factory=list, description="主舞台")
    social_rules: List[str] = Field(default_factory=list, description="社会ルール")


class StoryFrameworkDirectionPolicy(BaseModel):
    """演出方針."""
    paneling_policy: str = Field(description="コマ割り方針")
    eye_guidance_policy: str = Field(description="視線誘導方針")
    page_turn_policy: str = Field(description="ページめくり方針")
    dialogue_policy: str = Field(description="セリフ運用方針")


class StoryFrameworkArtStylePolicy(BaseModel):
    """画風方針."""
    line_style: str = Field(description="線画仕様")
    shading_style: str = Field(description="陰影仕様")
    negative_constraints: List[str] = Field(default_factory=list, description="禁止表現")


class StoryFrameworkPayload(BaseModel):
    """story_framework 本体."""
    concept: str = Field(description="作品コンセプト")
    theme: str = Field(description="テーマ")
    format_policy: StoryFrameworkFormatPolicy = Field(description="形式方針")
    structure_type: Literal["kishotenketsu", "three_act", "jo_ha_kyu", "other"] = Field(
        description="物語構成の型"
    )
    arc_overview: List[StoryFrameworkArcPhase] = Field(default_factory=list, description="物語フェーズ概要")
    core_conflict: str = Field(description="中核対立")
    world_policy: StoryFrameworkWorldPolicy = Field(description="世界観方針")
    direction_policy: StoryFrameworkDirectionPolicy = Field(description="演出方針")
    art_style_policy: StoryFrameworkArtStylePolicy = Field(description="画風方針")


class WriterStoryFrameworkOutput(BaseModel):
    """Writer(mode=story_framework) の出力。"""
    execution_summary: str = Field(description="実行結果の要約")
    user_message: str = Field(description="ユーザー向けの簡潔な進捗・成果メッセージ")
    story_framework: StoryFrameworkPayload = Field(description="作品全体方針")

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_shape(cls, value: Any) -> Any:
        """旧形式(logline/world_setting...)から新形式へ移行する互換処理."""
        if not isinstance(value, dict):
            return value

        if isinstance(value.get("story_framework"), dict):
            return value

        arc_raw = value.get("narrative_arc")
        arc_overview: list[dict[str, str]] = []
        if isinstance(arc_raw, list):
            for idx, item in enumerate(arc_raw, start=1):
                if isinstance(item, str) and item.strip():
                    arc_overview.append({"phase": f"phase_{idx}", "purpose": item.strip()})

        constraints = value.get("constraints")
        constraint_items = [str(item).strip() for item in constraints if isinstance(item, str)] if isinstance(constraints, list) else []

        upgraded = {
            **value,
            "story_framework": {
                "concept": str(value.get("logline") or "未設定のコンセプト"),
                "theme": str(value.get("tone_and_temperature") or "未設定のテーマ"),
                "format_policy": {
                    "series_type": "oneshot",
                    "medium": "digital",
                    "page_budget": {"min": 8, "max": 16},
                    "reading_direction": "rtl",
                },
                "structure_type": "kishotenketsu",
                "arc_overview": arc_overview or [{"phase": "phase_1", "purpose": "物語導入"}],
                "core_conflict": str(value.get("background_context") or "主要対立は未定義"),
                "world_policy": {
                    "era": str(value.get("world_setting") or "未設定"),
                    "primary_locations": [],
                    "social_rules": [],
                },
                "direction_policy": {
                    "paneling_policy": "通常は5-6コマ、要点で大ゴマを使う",
                    "eye_guidance_policy": "右上から左下へ視線誘導する",
                    "page_turn_policy": "章末や転換点でめくりを強調する",
                    "dialogue_policy": "1フキダシ1情報で簡潔にする",
                },
                "art_style_policy": {
                    "line_style": "主線はGペン基調",
                    "shading_style": "スクリーントーン中心",
                    "negative_constraints": constraint_items or ["フォトリアル禁止"],
                },
            },
        }
        return upgraded


class CharacterColorPalette(BaseModel):
    """キャラクター配色."""
    main: str = Field(description="メインカラー")
    sub: str = Field(description="サブカラー")
    accent: str = Field(description="アクセントカラー")


class CharacterProfile(BaseModel):
    """キャラクター設定（最小項目）."""
    character_id: str = Field(description="キャラクターID")
    name: str = Field(description="表示名")
    story_role: str = Field(description="物語上の役割")
    core_personality: str = Field(description="性格の核")
    motivation: str = Field(description="動機")
    weakness_or_fear: str = Field(description="弱点または恐れ")
    silhouette_signature: str = Field(description="シルエット識別要素")
    face_hair_anchors: str = Field(description="顔・髪の固定要素")
    costume_anchors: str = Field(description="衣装の固定要素")
    color_palette: CharacterColorPalette = Field(description="推奨配色")
    signature_items: List[str] = Field(default_factory=list, description="象徴的な持ち物・意匠")
    forbidden_drift: List[str] = Field(default_factory=list, description="崩してはいけない要素")
    speech_style: Optional[str] = Field(default=None, description="口調（任意）")

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        def _pick_text(*keys: str, default: str = "") -> str:
            for key in keys:
                raw = value.get(key)
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
            return default

        palette_raw = value.get("color_palette")
        palette: dict[str, str]
        if isinstance(palette_raw, dict):
            palette = {
                "main": str(palette_raw.get("main") or palette_raw.get("primary") or "#4A4A4A"),
                "sub": str(palette_raw.get("sub") or palette_raw.get("secondary") or "#9A9A9A"),
                "accent": str(palette_raw.get("accent") or palette_raw.get("highlight") or "#D9A441"),
            }
        elif isinstance(palette_raw, list):
            colors = [str(item).strip() for item in palette_raw if isinstance(item, str) and item.strip()]
            palette = {
                "main": colors[0] if len(colors) > 0 else "#4A4A4A",
                "sub": colors[1] if len(colors) > 1 else "#9A9A9A",
                "accent": colors[2] if len(colors) > 2 else "#D9A441",
            }
        else:
            palette = {"main": "#4A4A4A", "sub": "#9A9A9A", "accent": "#D9A441"}

        forbidden_raw = value.get("forbidden_drift")
        if not isinstance(forbidden_raw, list):
            forbidden_raw = value.get("forbidden_elements")
        forbidden_items = [str(item).strip() for item in forbidden_raw if isinstance(item, str) and item.strip()] if isinstance(forbidden_raw, list) else []

        signature_raw = value.get("signature_items")
        signature_items = [str(item).strip() for item in signature_raw if isinstance(item, str) and item.strip()] if isinstance(signature_raw, list) else []

        upgraded = {
            **value,
            "character_id": _pick_text("character_id", default="character_01"),
            "name": _pick_text("name", default="Unnamed"),
            "story_role": _pick_text("story_role", "role", default="未設定"),
            "core_personality": _pick_text("core_personality", "personality", default="未設定"),
            "motivation": _pick_text("motivation", default="未設定"),
            "weakness_or_fear": _pick_text("weakness_or_fear", "weakness", "fear", default="未設定"),
            "silhouette_signature": _pick_text("silhouette_signature", "appearance_core", default="未設定"),
            "face_hair_anchors": _pick_text(
                "face_hair_anchors",
                "appearance_core",
                "face_features_lock",
                "hairstyle_lock",
                default="未設定",
            ),
            "costume_anchors": _pick_text("costume_anchors", "costume_core", default="未設定"),
            "color_palette": palette,
            "signature_items": signature_items,
            "forbidden_drift": forbidden_items,
            "speech_style": _pick_text("speech_style", default="") or None,
        }
        return upgraded


class WriterCharacterSheetOutput(BaseModel):
    """Writer(mode=character_sheet) の出力。"""
    execution_summary: str = Field(description="実行結果の要約")
    user_message: str = Field(description="ユーザー向けの簡潔な進捗・成果メッセージ")
    characters: List[CharacterProfile] = Field(description="キャラクター一覧")


class InfographicBlock(BaseModel):
    """インフォグラフィック構成ブロック。"""
    block_id: str = Field(description="ブロックID")
    heading: str = Field(description="見出し")
    body: str = Field(description="本文")
    visual_hint: str = Field(description="図表・アイコン等の指示")
    data_points: List[str] = Field(default_factory=list, description="表示すべきデータ点")


class WriterInfographicSpecOutput(BaseModel):
    """Writer(mode=infographic_spec) の出力。"""
    execution_summary: str = Field(description="実行結果の要約")
    user_message: str = Field(description="ユーザー向けの簡潔な進捗・成果メッセージ")
    title: str = Field(description="全体タイトル")
    audience: str = Field(description="想定読者")
    key_message: str = Field(description="中心メッセージ")
    blocks: List[InfographicBlock] = Field(description="構成ブロック")


class DocumentSection(BaseModel):
    """ドキュメントページ内のセクション。"""
    section_id: str = Field(description="セクションID")
    heading: str = Field(description="見出し")
    body: str = Field(description="本文")
    visual_hint: Optional[str] = Field(default=None, description="図版指示")


class DocumentPage(BaseModel):
    """ドキュメント設計のページ定義。"""
    page_number: int = Field(description="ページ番号")
    page_title: str = Field(description="ページタイトル")
    purpose: str = Field(description="ページ目的")
    sections: List[DocumentSection] = Field(default_factory=list, description="ページセクション")


class WriterDocumentBlueprintOutput(BaseModel):
    """Writer(mode=document_blueprint) の出力。"""
    execution_summary: str = Field(description="実行結果の要約")
    user_message: str = Field(description="ユーザー向けの簡潔な進捗・成果メッセージ")
    document_type: Literal["magazine", "manual"] = Field(description="ドキュメント種別")
    style_direction: str = Field(description="スタイル方針")
    pages: List[DocumentPage] = Field(description="ページ設計")


_SCENE_TAG_PATTERN = re.compile(r"\[(被写体|構図|動作|舞台|画風)\]\s*")


def _parse_scene_description_tags(scene_description: str) -> dict[str, str]:
    text = str(scene_description or "").strip()
    if not text:
        return {}

    matches = list(_SCENE_TAG_PATTERN.finditer(text))
    if not matches:
        return {}

    parsed: dict[str, str] = {}
    for idx, match in enumerate(matches):
        tag = match.group(1)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        value = text[start:end].strip()
        if value:
            parsed[tag] = value
    return parsed


class ComicPanel(BaseModel):
    """漫画コマ定義（ページ/コマの描画詳細に限定）。"""
    panel_number: int = Field(description="コマ番号")
    foreground: str = Field(description="前景（主被写体）")
    background: str = Field(description="背景（舞台）")
    composition: str = Field(description="構図")
    camera: str = Field(description="カメラ")
    lighting: str = Field(description="照明")
    dialogue: List[str] = Field(default_factory=list, description="セリフ")
    negative_constraints: List[str] = Field(default_factory=list, description="禁止事項")

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        scene_description = value.get("scene_description")
        parsed = _parse_scene_description_tags(scene_description) if isinstance(scene_description, str) else {}

        foreground = str(value.get("foreground") or parsed.get("被写体") or scene_description or "未指定").strip()
        background = str(value.get("background") or parsed.get("舞台") or "未指定").strip()

        composition_parts: list[str] = []
        if isinstance(value.get("composition"), str) and str(value.get("composition")).strip():
            composition_parts.append(str(value.get("composition")).strip())
        else:
            if parsed.get("構図"):
                composition_parts.append(parsed["構図"].strip())
            if parsed.get("動作"):
                composition_parts.append(f"動作: {parsed['動作'].strip()}")
        composition = " / ".join([part for part in composition_parts if part]) or "未指定"

        camera = str(value.get("camera") or "未指定").strip() or "未指定"
        lighting = str(value.get("lighting") or "未指定").strip() or "未指定"

        dialogue_raw = value.get("dialogue")
        dialogue = [
            str(item).strip()
            for item in dialogue_raw
            if isinstance(item, str) and item.strip()
        ] if isinstance(dialogue_raw, list) else []

        negatives_raw = value.get("negative_constraints")
        if not isinstance(negatives_raw, list):
            negatives_raw = value.get("forbidden_drift")
        negative_constraints = [
            str(item).strip()
            for item in negatives_raw
            if isinstance(item, str) and item.strip()
        ] if isinstance(negatives_raw, list) else []

        return {
            **value,
            "panel_number": int(value.get("panel_number") or 1),
            "foreground": foreground,
            "background": background,
            "composition": composition,
            "camera": camera,
            "lighting": lighting,
            "dialogue": dialogue,
            "negative_constraints": negative_constraints,
        }


class ComicPageScript(BaseModel):
    """漫画1ページ分の脚本。"""
    page_number: int = Field(description="ページ番号")
    panels: List[ComicPanel] = Field(description="コマ一覧")


class WriterComicScriptOutput(BaseModel):
    """Writer(mode=comic_script) の出力。"""
    execution_summary: str = Field(description="実行結果の要約")
    user_message: str = Field(description="ユーザー向けの簡潔な進捗・成果メッセージ")
    pages: List[ComicPageScript] = Field(description="ページ構成")




# === Visualizer Output ===
class ThoughtSignature(BaseModel):
    """思考署名: 一貫性のある修正（Deep Edit）に必要な生成メタデータ"""
    seed: int = Field(description="生成に使用された乱数シード")
    base_prompt: str = Field(description="生成に使用されたベースプロンプト")
    refined_prompt: Optional[str] = Field(default=None, description="修正後のプロンプト（編集時）")
    model_version: str = Field(default="gemini-exp-1121", description="使用モデルバージョン")
    reference_image_url: Optional[str] = Field(default=None, description="使用されたリファレンス画像のURL")
    api_thought_signature: Optional[str] = Field(default=None, description="Gemini 3.0 APIからの不透明な思考署名トークン")




# === Structured Image Prompt (v2: Markdown Slide Format) ===
class StructuredImagePrompt(BaseModel):
    """Markdownベースのスライド画像生成プロンプト
    
    シンプルなMarkdown形式でスライド情報を構造化し、
    Geminiに直接送信可能な形式にコンパイルする。
    
    出力形式例:
    ```
    # Slide1: Title Slide
    ## The Evolution of Japan's Economy
    ### From Post-War Recovery to Future Innovation
    
    [Contents]
    
    Visual style: [English description]
    ```
    """
    
    # === Slide Identity ===
    slide_type: str = Field(
        default="Content",
        description="スライドの種類（例: 'Title Slide', 'Content', 'Section Header', 'Data Visualization', 'Comparison'）"
    )
    
    # === Text Content (日本語) ===
    main_title: str = Field(
        description="メインタイトル（日本語または英語）。画像内にレンダリングされる。"
    )
    sub_title: Optional[str] = Field(
        default=None,
        description="サブタイトル（オプション）。画像内にレンダリングされる。"
    )
    contents: Optional[str] = Field(
        default=None,
        description="本文コンテンツ（テキスト、リスト、データ、markdownテーブル、mermaid図など）"
    )
    
    # === Visual Style (英語) ===
    visual_style: str = Field(
        description="ビジュアルスタイルの詳細な説明（英語）。デザイン、色、構図、モチーフなどを自由に記述。"
    )
    text_policy: Optional[Literal["render_all_text", "render_title_only", "no_text"]] = Field(
        default=None,
        description="レガシー互換項目。slide/design では使用しない。"
    )
    negative_constraints: Optional[List[str]] = Field(
        default=None,
        description="レガシー互換項目。slide/design では使用しない。"
    )



class ImagePrompt(BaseModel):
    """画像生成プロンプト（構造化対応版）
    
    標準入力は `structured_prompt`。
    `image_generation_prompt` は後方互換性のためのレガシー入力として保持する。
    """
    slide_number: int = Field(description="対象スライド番号")
    
    # レイアウトタイプ（テンプレート参照画像の選択に使用）
    layout_type: Literal[
        "title_slide", "title_and_content", "section_header",
        "two_content", "comparison", "content_with_caption",
        "picture_with_caption", "blank", "other"
    ] = Field(
        default="title_and_content",
        description="このスライドに適用するレイアウトタイプ（テンプレート参照画像の選択に使用）"
    )
    
    # --- NEW: 構造化プロンプト ---
    structured_prompt: Optional[StructuredImagePrompt] = Field(
        default=None,
        description="JSON構造化プロンプト（標準）。"
    )
    
    # --- 従来のプロンプト（後方互換性） ---
    image_generation_prompt: Optional[str] = Field(
        default=None,
        description="レガシー互換のプレーン文字列プロンプト。structured_prompt未指定時のフォールバックとしてのみ使用。"
    )

    compiled_prompt: Optional[str] = Field(
        default=None,
        description="最終的に画像生成へ送るプロンプト（structured_prompt もしくは legacy prompt から生成）。"
    )
    
    rationale: str = Field(description="このビジュアルを選んだ理由（推論の根拠）")
    generated_image_url: Optional[str] = Field(default=None, description="生成された画像のGCS URL（生成後に入力される）")
    thought_signature: Optional[ThoughtSignature] = Field(default=None, description="Deep Edit用の思考署名")

    @model_validator(mode="after")
    def _validate_prompt_presence(self) -> "ImagePrompt":
        has_structured = self.structured_prompt is not None
        plain_prompt = (
            self.image_generation_prompt.strip()
            if isinstance(self.image_generation_prompt, str)
            else ""
        )
        if not has_structured and not plain_prompt:
            raise ValueError(
                "ImagePrompt requires either structured_prompt or non-empty image_generation_prompt."
            )
        # structured_prompt がある場合は legacy plain prompt を保持しない。
        self.image_generation_prompt = None if has_structured else (plain_prompt or None)
        return self




class GenerationConfig(BaseModel):
    """画像生成設定"""
    thinking_level: Literal["low", "high"] = Field(
        default="high",
        description="推論レベル (High: 複雑な図解, Low: 単純なアイコン)"
    )
    media_resolution: Literal["medium", "high"] = Field(
        default="medium",
        description="解像度設定 (Medium=1K, High=2K)"
    )
    aspect_ratio: Literal["16:9", "4:3", "1:1", "4:5", "3:4", "9:16", "2:3", "21:9"] = Field(
        default="16:9",
        description="強制アスペクト比"
    )
    reference_anchor: Optional[str] = Field(
        default=None,
        description="アスペクト比固定用のリファレンス画像（Base64またはURL）"
    )



class VisualizerOutput(BaseModel):
    """Visualizerノードの出力（product_type別フォーマット）"""

    execution_summary: str = Field(description="実行結果の要約")
    product_type: Optional[Literal["slide", "design", "comic"]] = Field(
        default=None,
        description="対象プロダクト種別",
    )
    mode: Optional[str] = Field(
        default=None,
        description="Visualizer mode（例: slide_render, document_layout_render, comic_page_render）",
    )
    slides: Optional[List[dict[str, Any]]] = Field(
        default=None,
        description="slide向け出力（slide_numberベース）",
    )
    design_pages: Optional[List[dict[str, Any]]] = Field(
        default=None,
        description="design向け出力（page_numberベース）",
    )
    comic_pages: Optional[List[dict[str, Any]]] = Field(
        default=None,
        description="comic page向け出力（page_numberベース）",
    )
    characters: Optional[List[dict[str, Any]]] = Field(
        default=None,
        description="comic character_sheet向け出力（character_numberベース）",
    )
    generation_config: GenerationConfig = Field(
        default_factory=lambda: GenerationConfig(
            thinking_level="high", 
            media_resolution="medium", 
            aspect_ratio="16:9"
        ),
        description="画像生成エンジンの設定パラメータ"
    )
    seed: Optional[int] = Field(default=None, description="画像生成に使用するランダムシード（一貫性用）")
    parent_id: Optional[str] = Field(default=None, description="修正元の画像ID（編集時）")
    combined_pdf_url: Optional[str] = Field(default=None, description="生成済みスライドを統合したPDFのURL")

    @model_validator(mode="after")
    def _validate_visual_payload(self) -> "VisualizerOutput":
        slide_count = len(self.slides or [])
        design_page_count = len(self.design_pages or [])
        comic_page_count = len(self.comic_pages or [])
        character_count = len(self.characters or [])
        total = slide_count + design_page_count + comic_page_count + character_count
        if total == 0:
            raise ValueError("VisualizerOutput must include slides, design_pages, comic_pages, or characters.")

        if self.product_type == "slide" and slide_count == 0:
            raise ValueError("slide product_type requires non-empty slides.")
        if self.product_type == "design":
            if design_page_count == 0:
                raise ValueError("design product_type requires non-empty design_pages.")
            self.mode = None
        if self.product_type == "comic":
            if character_count > 0 and comic_page_count > 0:
                raise ValueError("comic product_type cannot include both characters and comic_pages in one output.")
            if not self.mode:
                if character_count > 0 and comic_page_count == 0:
                    self.mode = "character_sheet_render"
                elif comic_page_count > 0 and character_count == 0:
                    self.mode = "comic_page_render"
            if self.mode == "character_sheet_render" and character_count == 0:
                raise ValueError("comic character_sheet_render requires non-empty characters.")
            if self.mode == "comic_page_render" and comic_page_count == 0:
                raise ValueError("comic comic_page_render requires non-empty comic_pages.")
        return self


# === Visualizer Plan (v3) ===
class VisualizerPlanSlide(BaseModel):
    """Visualizer Plannerが決めるスライドごとの生成方針"""
    slide_number: int = Field(description="対象スライド番号（アウトライン準拠）")
    layout_type: Optional[str] = Field(
        default=None,
        description="推奨レイアウトタイプ（例: title_slide, content, comparison など）"
    )
    selected_inputs: List[str] = Field(
        default_factory=list,
        description="このスライド生成に使う入力の要約（Story/Planner/Data Analyst等）"
    )
    reference_policy: Literal["none", "previous", "explicit"] = Field(
        default="none",
        description="参照画像の利用方針"
    )
    reference_url: Optional[str] = Field(
        default=None,
        description="参照画像URL（explicitの場合）"
    )
    generation_notes: Optional[str] = Field(
        default=None,
        description="このスライドの生成上の注意点"
    )


class VisualizerPlan(BaseModel):
    """Visualizer Plannerの出力"""
    execution_summary: str = Field(description="計画の要約")
    generation_order: List[int] = Field(description="生成順序（slide_numberの配列）")
    slides: List[VisualizerPlanSlide] = Field(description="スライドごとの生成方針")




# === Parallel Researcher Schemas ===
class ResearchTask(BaseModel):
    """調査タスク（Plannerが生成）"""
    id: int = Field(description="タスクID")
    perspective: str = Field(description="調査観点（例: 市場規模、技術動向）")
    search_mode: Optional[Literal["text_search"]] = Field(
        default="text_search",
        description="調査モード"
    )
    query_hints: List[str] = Field(description="検索クエリのヒント（最大3つ）")
    priority: Literal["high", "medium", "low"] = Field(default="medium")
    expected_output: str = Field(description="期待する出力形式の説明")


class ResearchResult(BaseModel):
    """調査結果（Workerが生成）"""
    task_id: int = Field(description="対応するタスクID")
    perspective: str = Field(description="調査観点")
    report: str = Field(description="Markdown形式のレポート（引用付き）")
    sources: List[str] = Field(description="参照URL一覧")
    image_candidates: List[ResearchImageCandidate] = Field(
        default_factory=list,
        description="互換目的の未使用フィールド（現在は常に空）"
    )
    confidence: float = Field(description="信頼度スコア (0.0-1.0)")


class ResearchTaskList(BaseModel):
    """リサーチタスクリスト（動的分解の結果）"""
    tasks: List[ResearchTask] = Field(description="分解された調査タスクのリスト")

# === Data Analyst Output ===
class VisualBlueprint(BaseModel):
    """可視化の設計図（グラフや図解の定義）"""
    visual_type: Literal["bar_chart", "line_chart", "pie_chart", "flowchart", "infographic", "table"] = Field(
        description="可視化の種類"
    )
    title: str = Field(description="可視化のタイトル")
    data_series: List[dict] = Field(description="ラベルと値のリスト（例: [{'label': 'A', 'value': 10}]）")
    annotations: List[str] = Field(default_factory=list, description="注釈や強調ポイント")
    design_notes: Optional[str] = Field(default=None, description="デザイン上の注意点（配色、強調など）")

class OutputFile(BaseModel):
    """DataAnalystが生成した成果物ファイル"""
    url: str = Field(description="成果物のGCS URL")
    title: Optional[str] = Field(default=None, description="成果物の短い名称")
    mime_type: Optional[str] = Field(default=None, description="MIMEタイプ（例: application/pdf）")
    description: Optional[str] = Field(default=None, description="成果物の説明（オプション）")
    source_title: Optional[str] = Field(
        default=None,
        description="PPTX由来画像の場合の元スライドタイトル",
    )
    source_texts: List[str] = Field(
        default_factory=list,
        description="PPTX由来画像の場合の元スライド本文テキスト抜粋",
    )
    source_layout_name: Optional[str] = Field(
        default=None,
        description="PPTX由来画像の場合の元レイアウト名",
    )
    source_layout_placeholders: List[str] = Field(
        default_factory=list,
        description="PPTX由来画像の場合のレイアウトplaceholder type一覧",
    )
    source_master_name: Optional[str] = Field(
        default=None,
        description="PPTX由来画像の場合の元スライドマスター名",
    )
    source_master_texts: List[str] = Field(
        default_factory=list,
        description="PPTX由来画像の場合の元スライドマスター内テキスト抜粋",
    )
    source_mode: Optional[str] = Field(
        default=None,
        description="生成元モード（例: pptx_slides_to_images）",
    )


class DataAnalystOutput(BaseModel):
    """DataAnalystノードの出力"""
    implementation_code: str = Field(default="", description="実装したPython/Bashコード")
    execution_log: str = Field(default="", description="実行ログ")
    output_value: Any | None = Field(default=None, description="ファイル以外の出力値（JSON互換）")
    failed_checks: List[str] = Field(
        default_factory=list,
        description="失敗時の明示チェックコード（例: missing_research）"
    )
    output_files: List[OutputFile] = Field(
        default_factory=list,
        description="生成された成果物ファイルのリスト"
    )
