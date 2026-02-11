# Pydanticスキーマ: LangGraphノードの構造化出力定義
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator





# === Orchestration Contracts (v1) ===
ProductType = Literal["slide", "design", "comic"]
IntentType = Literal["new", "refine", "regenerate"]
TaskCapability = Literal["writer", "visualizer", "researcher", "data_analyst"]
TaskStatus = Literal["pending", "in_progress", "completed", "blocked"]
ArtifactStatus = Literal["streaming", "completed", "failed"]


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


class CharacterProfile(BaseModel):
    """キャラクター設定。"""
    character_id: str = Field(description="キャラクターID")
    name: str = Field(description="表示名")
    role: str = Field(description="物語上の役割")
    appearance_core: str = Field(description="外見の核となる特徴（体型・顔立ち・髪型など）")
    costume_core: str = Field(description="衣装・装身具の核となる特徴")
    personality: str = Field(description="性格")
    backstory: str = Field(description="背景")
    motivation: str = Field(description="動機")
    relationships: List[str] = Field(default_factory=list, description="主要な関係性（人物名: 関係）")
    color_palette: List[str] = Field(default_factory=list, description="推奨配色")
    signature_items: List[str] = Field(default_factory=list, description="象徴的な持ち物・意匠")
    forbidden_elements: List[str] = Field(default_factory=list, description="避けるべき要素")
    visual_keywords: List[str] = Field(default_factory=list, description="画像生成向けキーワード")


class WriterCharacterSheetOutput(BaseModel):
    """Writer(mode=character_sheet) の出力。"""
    execution_summary: str = Field(description="実行結果の要約")
    user_message: str = Field(description="ユーザー向けの簡潔な進捗・成果メッセージ")
    setting_notes: Optional[str] = Field(default=None, description="キャラ共通の設定メモ")
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


class ComicPanel(BaseModel):
    """漫画コマ定義。"""
    panel_number: int = Field(description="コマ番号")
    scene_description: str = Field(description="コマの状況説明")
    camera: Optional[str] = Field(default=None, description="カメラ指示")
    dialogue: List[str] = Field(default_factory=list, description="セリフ")
    sfx: List[str] = Field(default_factory=list, description="効果音")


class ComicPageScript(BaseModel):
    """漫画1ページ分の脚本。"""
    page_number: int = Field(description="ページ番号")
    page_goal: str = Field(description="このページの目的")
    panels: List[ComicPanel] = Field(description="コマ一覧")


class WriterComicScriptOutput(BaseModel):
    """Writer(mode=comic_script) の出力。"""
    execution_summary: str = Field(description="実行結果の要約")
    user_message: str = Field(description="ユーザー向けの簡潔な進捗・成果メッセージ")
    title: str = Field(description="作品タイトル")
    genre: str = Field(description="ジャンル")
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
    text_policy: Literal["render_all_text", "render_title_only", "no_text"] = Field(
        default="render_all_text",
        description="画像内テキストのレンダリング方針。通常はrender_all_text。"
    )
    negative_constraints: List[str] = Field(
        default_factory=list,
        description="避けるべきアーティファクトや構図崩れ等のネガティブ制約。"
    )



class ImagePrompt(BaseModel):
    """画像生成プロンプト（構造化対応版）
    
    従来の `image_generation_prompt` (str) に加え、
    新たに `structured_prompt` (StructuredImagePrompt) をサポート。
    
    優先度: structured_prompt > image_generation_prompt
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
        description="JSON構造化プロンプト（Nano Banana Pro最適化）。指定された場合、image_generation_promptより優先される。"
    )
    
    # --- 従来のプロンプト（後方互換性） ---
    image_generation_prompt: Optional[str] = Field(
        default=None,
        description="従来形式のプロンプト文字列。structured_promptが指定されていない場合に使用。"
    )

    compiled_prompt: Optional[str] = Field(
        default=None,
        description="structured_promptから生成した最終プロンプト（UI表示用）。"
    )
    
    rationale: str = Field(description="このビジュアルを選んだ理由（推論の根拠）")
    generated_image_url: Optional[str] = Field(default=None, description="生成された画像のGCS URL（生成後に入力される）")
    thought_signature: Optional[ThoughtSignature] = Field(default=None, description="Deep Edit用の思考署名")




class GenerationConfig(BaseModel):
    """画像生成設定"""
    thinking_level: Literal["low", "high"] = Field(
        default="high",
        description="推論レベル (High: 複雑な図解, Low: 単純なアイコン)"
    )
    media_resolution: Literal["medium", "high"] = Field(
        default="high",
        description="解像度設定 (High: スライド用, Medium: プレビュー用)"
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
    """Visualizerノードの出力（v2: Markdown Slide Format 対応版）"""
    
    execution_summary: str = Field(description="実行結果の要約（例：『全スライドの画像生成プロンプトを作成しました』）")
    prompts: List[ImagePrompt] = Field(description="各スライド用の画像生成プロンプト")
    generation_config: GenerationConfig = Field(
        default_factory=lambda: GenerationConfig(
            thinking_level="high", 
            media_resolution="high", 
            aspect_ratio="16:9"
        ),
        description="画像生成エンジンの設定パラメータ"
    )
    seed: Optional[int] = Field(default=None, description="画像生成に使用するランダムシード（一貫性用）")
    parent_id: Optional[str] = Field(default=None, description="修正元の画像ID（編集時）")
    combined_pdf_url: Optional[str] = Field(default=None, description="生成済みスライドを統合したPDFのURL")


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
    search_mode: Optional[Literal["text_search", "image_search", "hybrid_search"]] = Field(
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
        description="画像候補一覧（image/hybrid search時）"
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


class DataAnalystOutput(BaseModel):
    """DataAnalystノードの出力"""
    execution_summary: str = Field(description="実行結果の要約")
    analysis_report: str = Field(description="Markdown形式の分析レポート")
    failed_checks: List[str] = Field(
        default_factory=list,
        description="失敗時の明示チェックコード（例: missing_research）"
    )
    output_files: List[OutputFile] = Field(
        default_factory=list,
        description="生成された成果物ファイルのリスト"
    )
    blueprints: List[VisualBlueprint] = Field(
        default_factory=list,
        description="生成されたビジュアル・ブループリントのリスト"
    )
    visualization_code: Optional[str] = Field(default=None, description="可視化用のPythonコード（オプション）")
    data_sources: List[str] = Field(default_factory=list, description="使用したデータソース")
