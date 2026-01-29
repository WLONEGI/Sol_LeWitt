# Pydanticスキーマ: LangGraphノードの構造化出力定義
from typing import List, Literal, Optional
from pydantic import BaseModel, Field





# === Planner Output ===
class TaskStep(BaseModel):
    """実行計画の1ステップ"""
    id: int = Field(description="ステップ番号（1から始まる）")
    role: Literal["researcher", "storywriter", "visualizer", "coder", "data_analyst"] = Field(
        description="担当エージェント名"
    )
    instruction: str = Field(
        description="エージェントへの詳細な指示（トーン、対象読者、具体的な要件を含む）"
    )
    title: str = Field(description="このステップの短いタイトル（例：競合調査、構成案作成）")
    description: str = Field(description="このステップの概要説明")
    design_direction: Optional[str] = Field(
        default=None,
        description="Visualizerへのデザイン指示（トーン、スタイル、モチーフなど）。Storywriterの場合はNoneでよい。"
    )
    status: Literal["pending", "in_progress", "complete"] = Field(
        default="pending",
        description="ステップの実行ステータス"
    )
    result_summary: Optional[str] = Field(
        default=None,
        description="実行結果の要約"
    )



class PlannerOutput(BaseModel):
    """Plannerノードの出力"""
    steps: List[TaskStep] = Field(description="実行計画のステップリスト")




# === Storywriter Output ===
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




class StorywriterOutput(BaseModel):
    """Storywriterノードの出力"""
    execution_summary: str = Field(description="実行結果の要約（例：『◯◯に関するスライド構成を5枚作成しました』）")
    slides: List[SlideContent] = Field(description="スライドコンテンツのリスト")




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
    aspect_ratio: Literal["16:9", "4:3", "1:1"] = Field(
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




# === Parallel Researcher Schemas ===
class ResearchTask(BaseModel):
    """調査タスク（Plannerが生成）"""
    id: int = Field(description="タスクID")
    perspective: str = Field(description="調査観点（例: 市場規模、技術動向）")
    query_hints: List[str] = Field(description="検索クエリのヒント（最大3つ）")
    priority: Literal["high", "medium", "low"] = Field(default="medium")
    expected_output: str = Field(description="期待する出力形式の説明")


class ResearchResult(BaseModel):
    """調査結果（Workerが生成）"""
    task_id: int = Field(description="対応するタスクID")
    perspective: str = Field(description="調査観点")
    report: str = Field(description="Markdown形式のレポート（引用付き）")
    sources: List[str] = Field(description="参照URL一覧")
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

class DataAnalystOutput(BaseModel):
    """DataAnalystノードの出力"""
    execution_summary: str = Field(description="実行結果の要約")
    analysis_report: str = Field(description="Markdown形式の分析レポート")
    blueprints: List[VisualBlueprint] = Field(
        default_factory=list,
        description="生成されたビジュアル・ブループリントのリスト"
    )
    visualization_code: Optional[str] = Field(default=None, description="可視化用のPythonコード（オプション）")
    data_sources: List[str] = Field(default_factory=list, description="使用したデータソース")
