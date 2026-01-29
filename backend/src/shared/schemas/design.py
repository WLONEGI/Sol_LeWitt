# Pydanticスキーマ: PPTXテンプレートから抽出されたデザインコンテキスト
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# レイアウトタイプの定義
LayoutType = Literal[
    "title_slide",
    "title_and_content", 
    "section_header",
    "two_content",
    "comparison",
    "content_with_caption",
    "picture_with_caption",
    "title_only",
    "title_and_vertical_text",
    "vertical_title_and_text",
    "blank",
    "other"
]


class ColorScheme(BaseModel):
    """PPTXテーマから抽出したカラースキーム"""
    dk1: str = Field(description="Dark 1 (背景色): HEX e.g. '#1E1E1E'")
    dk2: str = Field(description="Dark 2: HEX")
    lt1: str = Field(description="Light 1 (テキスト色): HEX e.g. '#FFFFFF'")
    lt2: str = Field(description="Light 2: HEX")
    accent1: str = Field(description="Accent 1 (主要アクセントカラー): HEX")
    accent2: str = Field(description="Accent 2: HEX")
    accent3: str = Field(description="Accent 3: HEX")
    accent4: str = Field(description="Accent 4: HEX")
    accent5: str = Field(description="Accent 5: HEX")
    accent6: str = Field(description="Accent 6: HEX")
    hlink: str = Field(description="Hyperlink color: HEX")
    folHlink: str = Field(description="Followed hyperlink color: HEX")


class FontScheme(BaseModel):
    """PPTXテーマから抽出したフォントスキーム"""
    major_latin: str = Field(description="見出し用フォント (Latin) e.g. 'Calibri Light'")
    minor_latin: str = Field(description="本文用フォント (Latin) e.g. 'Calibri'")
    major_east_asian: Optional[str] = Field(default=None, description="見出し用フォント (日本語等)")
    minor_east_asian: Optional[str] = Field(default=None, description="本文用フォント (日本語等)")


class LayoutPlaceholder(BaseModel):
    """スライドレイアウトのプレースホルダー情報"""
    type: Literal["title", "body", "subtitle", "picture", "chart", "table", "footer", "slide_number", "date"]
    left_percent: float = Field(description="左からの位置 (%)")
    top_percent: float = Field(description="上からの位置 (%)")
    width_percent: float = Field(description="幅 (%)")
    height_percent: float = Field(description="高さ (%)")


class SlideLayoutInfo(BaseModel):
    """スライドレイアウト1つ分の情報"""
    name: str = Field(description="レイアウト名 e.g. 'Title Slide', 'Comparison'")
    layout_type: LayoutType
    placeholders: List[LayoutPlaceholder]
    index: int = Field(default=0, description="スライドマスター内でのレイアウトインデックス")
    # このレイアウトのレンダリング画像URL
    template_image_url: Optional[str] = Field(
        default=None,
        description="このレイアウトのテンプレート画像URL（GCS）"
    )


class BackgroundInfo(BaseModel):
    """背景設定"""
    fill_type: Literal["solid", "gradient", "picture", "pattern", "none"]
    solid_color: Optional[str] = Field(default=None, description="単色背景の場合のHEX")


class DesignContext(BaseModel):
    """PPTXテンプレートから抽出した統合デザインコンテキスト"""
    # 構造的データ (python-pptx)
    color_scheme: ColorScheme
    font_scheme: FontScheme
    layouts: List[SlideLayoutInfo]
    background: BackgroundInfo
    
    # レイアウトタイプ別のテンプレート画像マップ (GCS URL / Optional)
    layout_images: Dict[str, str] = Field(
        default_factory=dict,
        description="レイアウトタイプ → テンプレート画像URL のマッピング"
    )
    
    # レイアウトタイプ別の画像バイトデータ（内部使用 - State保存用にBase64化）
    # JSONシリアライズ可能な形式でStateに保存するため Base64 str を使用
    layout_images_base64: Dict[str, str] = Field(
        default_factory=dict,
        description="レイアウトタイプ → テンプレート画像(Base64 encoded PNG)"
    )
    
    # デフォルトのテンプレート画像
    default_template_image_base64: Optional[str] = Field(
        default=None, 
        description="デフォルトのテンプレートスライド画像(Base64 encoded PNG)"
    )
    default_template_image_url: Optional[str] = Field(
        default=None, 
        description="デフォルトのテンプレートスライド画像のURL"
    )
    
    # メタデータ
    source_filename: str
    slide_master_count: int
    layout_count: int
    
    # Pydantic V2 設定
    model_config = {"arbitrary_types_allowed": True}
    
    def get_template_image_for_layout(self, layout_type: str) -> Optional[bytes]:
        """指定されたレイアウトタイプに対応するテンプレート画像(Bytes)を取得
        
        Args:
            layout_type: 取得したいレイアウトタイプ
            
        Returns:
            テンプレート画像のバイトデータ、見つからない場合はデフォルト画像
        """
        import base64
        
        target_b64 = None
        
        # 1. 完全一致で検索
        if layout_type in self.layout_images_base64:
            target_b64 = self.layout_images_base64[layout_type]
        
        # 2. フォールバックマッピング
        else:
            fallback_map: Dict[str, str] = {
                "section_header": "title_slide",
                "two_content": "comparison",
                "content_with_caption": "title_and_content",
                "picture_with_caption": "title_and_content",
            }
            fallback_type = fallback_map.get(layout_type)
            if fallback_type and fallback_type in self.layout_images_base64:
                target_b64 = self.layout_images_base64[fallback_type]
        
        # 3. デフォルト画像
        if not target_b64:
            target_b64 = self.default_template_image_base64
            
        if target_b64:
            try:
                return base64.b64decode(target_b64)
            except Exception:
                return None
        return None
