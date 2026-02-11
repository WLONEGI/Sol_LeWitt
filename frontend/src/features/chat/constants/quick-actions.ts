import { BookOpen, Palette, Presentation, type LucideIcon } from "lucide-react"

export type QuickActionId = "slide" | "design" | "comics"
export type ProductType = "slide" | "design" | "comic"

export interface QuickActionConfig {
  id: QuickActionId
  productType: ProductType
  title: string
  pillLabel: string
  icon: LucideIcon
  bubbleClassName: string
  pillClassName: string
  gradientClassName: string
  prompts: string[]
}

export const QUICK_ACTIONS: QuickActionConfig[] = [
  {
    id: "slide",
    productType: "slide",
    title: "Create Slide",
    pillLabel: "Create Slide",
    icon: Presentation,
    bubbleClassName: "bg-orange-50/50 text-orange-600 ring-orange-200/40",
    pillClassName: "border-orange-200/80 bg-orange-50/70 text-orange-600",
    gradientClassName: "bg-gradient-to-t from-orange-100/60 to-background",
    prompts: [
      "シリーズA段階のAIスタートアップ向けに、15枚構成の包括的な投資家向けピッチデッキを作成してください。アウトラインは「課題」「ソリューション」「市場規模」「製品デモ」「ビジネスモデル」「競合優位性」「市場参入戦略」「チーム」「財務予測」「オファー」をカバーする必要があります。青と白を基調とした、清潔感のあるモダンな企業向けのデザインスタイルを採用してください。財務チャートなどのデータは視覚的に分かりやすく表現し、テキストは可読性を重視して簡潔にまとめてください。各スライドにはスピーカーノートも含めてください。",
      "大学の講義用に「気候変動の影響」に関する詳細なアカデミックプレゼンテーションを作成してください。構成は「科学的証拠」「世界的影響」「緩和策」「将来予測」の4つのセクションに分けてください。IPCCレポートからのデータグラフや、温室効果のメカニズムを示す図解のためのプレースホルダーを含めてください。トーンは客観的かつ教育的なものにしてください。",
      "SaaS企業向けの10枚構成の四半期ビジネスレビュー（QBR）プレゼンテーションをデザインしてください。ARR成長率、解約率（Churn Rate）、売上維持率（NRR）などの主要指標（KPI）に焦点を当ててください。製品ロードマップの更新や、カスタマーサクセスの事例紹介のセクションも含めてください。ビジュアルスタイルは、役員会議に適したプロフェッショナルでミニマルなものにしてください。",
    ],
  },
  {
    id: "design",
    productType: "design",
    title: "Design",
    pillLabel: "Design",
    icon: Palette,
    bubbleClassName: "bg-emerald-50/50 text-emerald-600 ring-emerald-200/40",
    pillClassName: "border-emerald-200/80 bg-emerald-50/70 text-emerald-600",
    gradientClassName: "bg-gradient-to-t from-emerald-100/30 to-background",
    prompts: [
      "エコツーリズムを専門とする高級旅行代理店のために、高忠実度（High-Fidelity）でレスポンシブなランディングページをデザインしてください。レイアウトには、フルスクリーンのヒーロー動画背景、グラスモーフィズム効果を用いたスティッキーな透明ナビゲーションバー、ホバーアニメーション付きの没入感のある目的地ギャラリー、そして洗練された予約フォームを配置してください。自然にインスパイアされたカラーパレット（深い緑、アースカラー）を使用し、見出しには優雅さを伝えるセリフ体（明朝体）のタイポグラフィを採用してください。",
      "ダークモードを採用したSaaS分析ダッシュボードの包括的なUIデザインを作成してください。レイアウトには、折りたたみ可能なサイドバー、ユーザー設定を含むトップナビゲーションバー、およびインタラクティブな折れ線グラフ、ヒートマップ、ソート可能なデータテーブルを備えたメインコンテンツエリアを含めてください。データポイントにはネオンカラーのアクセントを使用したハイコントラストな配色を採用し、可読性のためにInterフォントを使用してください。",
      "高級家具ブランド向けのミニマリストなECサイト商品詳細ページをデザインしてください。レイアウトは、高解像度の大きな画像を優先し、縦方向のメイソンリーグリッドギャラリーを採用してください。右側にはスティッキーな「カートに追加」セクションを配置し、製品仕様や手入れ方法については展開可能なアコーディオンを使用し、下部には「関連商品」のカルーセルを含めてください。洗練されたタイポグラフィを用いたニュートラルなカラーパレットを使用してください。",
    ],
  },
  {
    id: "comics",
    productType: "comic",
    title: "Draw Comic",
    pillLabel: "Draw Comic",
    icon: BookOpen,
    bubbleClassName: "bg-purple-50/50 text-purple-600 ring-purple-200/40",
    pillClassName: "border-purple-200/80 bg-purple-50/70 text-purple-600",
    gradientClassName: "bg-gradient-to-t from-purple-100/60 to-background",
    prompts: [
      "雨の降るネオ東京を舞台に、サイバーパンクな探偵「カエル」が登場する4コマ漫画を作成してください。1コマ目：ネオン輝く屋上に立ち、激しい雨に打たれるカエルの広角ショット。2コマ目：路地裏の怪しい人物にズームインするカエルのサイバネティック・アイのクローズアップ。3コマ目：その人物がドロイドに光るデータチップを渡している様子。4コマ目：コートをなびかせて屋上から飛び降りるカエル。スタイル：ノワール調のサイバーパンク、高コントラスト、ダークブルーとネオンピンクを使用。",
      "若い魔法使いが隠されたドラゴンの卵を発見する、3ページのファンタジー漫画のシーケンスを描いてください。1ページ目：魔法使いが生物発光する洞窟を進む様子（6コマ）。2ページ目：水晶の巣の中で光り輝く卵を見つけるシーン（スプラッシュページ/全面）。3ページ目：卵が割れ、小さなドラゴンが火をくしゃみする様子（4コマ）。アートスタイルは、柔らかな照明を用いた、気まぐれで水彩画のようなタッチにしてください。",
      "複雑なコーヒーの注文に対応するバリスタの日常を描いた短いコミックストリップを生成してください。1コマ目：長いリストを持ってカウンターに近づく客。2コマ目：アニメ風の汗をかいて圧倒された表情のバリスタ。3コマ目：錬金術のような真剣さでドリンクを調合するバリスタ。4コマ目：一口飲んで「まあまあだね」と言う客。スタイル：キュートでちびキャラ風、すっきりとした線画、パステルカラーを使用。",
    ],
  },
]
