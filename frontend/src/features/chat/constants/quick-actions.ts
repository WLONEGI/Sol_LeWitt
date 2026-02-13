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
      "目的: 社内朝会で意思決定を速める進捗共有。成果物: 5枚の簡潔な報告スライド。要件: 1) タイトル 2) 今週の達成3点 3) 課題2点 4) 来週の優先タスク3点 5) 依頼事項。制約: 白背景+ネイビー+アクセント1色、1スライド1メッセージ、箇条書きは1行20文字前後。出力品質: 会議でそのまま読める短文と、読み上げ時間30秒以内のスピーカーノートを各ページに付与。",
      "目的: 自治体向け政策提案「高齢化と地域交通の再設計」の合意形成。成果物: インフォグラフィック中心の8枚スライド。必須データ: 人口推移、免許返納率、通院距離、バス便数、財政負担。可視化: 地図、時系列、比較バー、ファネルを使い分ける。制約: すべての図版に単位と期間を明記し、結論は「オンデマンド交通+拠点集約」で統一。各スライドに要点1行と示唆1行を入れ、3分で判断できる構成にする。",
      "目的: B2B SaaSの経営会議でQBRを即断可能にする。成果物: 12枚の役員向けQBRスライド。必須セクション: ARR/NRR/Churn推移、セグメント別収益性、失注理由の構造化、次四半期の打ち手。定量要件: 前年同期比と前四半期比を併記し、主要KPIは赤黄緑でしきい値管理。記述要件: 原因分析を仮説で止めず、担当者・期限・期待効果まで実行計画化。文体は簡潔かつ反論耐性の高い論理順で統一。",
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
      "夜明け直前の都市が低音で震える瞬間を、音楽フェスのA2ポスターとして描いてください。テーマは「都市の夜明けと電子音」。タイトル、開催日、会場、出演者、QRコードはリズムを壊さず読める順で配置し、遠景では太いタイポが刺さり、近景では粒子や擦れの質感が効く二層構造にしてください。ネオン3色+黒の限定パレットで、視線は中央から右下へ滑り落ちる構図に統一。",
      "5-8歳向け絵本『まいごの星くじら』の見開きを、読んだ瞬間に呼吸がゆっくり深くなる画面で設計してください。左は短文、右は情景イラストを基本に、めくりたくなる余白と導線を残す。群青の夜空をベースに、希望だけを暖色で灯す。キャラクターの表情は1見開き1感情に絞り、文章のリズムと画面密度を連動させ、読み聞かせの声色が自然に変化するよう演出してください。",
      "工房向け木製スツールの blueprint を、手仕事の感触が伝わる厳密さで作成してください。正面図・側面図・断面図・分解図を揃え、全寸法(mm)、公差、材種、仕口、接着条件、面取りR、仕上げ工程、必要工具、加工順、検査項目まで欠けなく記述。図面記号はJIS相当の一般表記に統一し、曖昧語は排除。職人がこの1枚を開けば、そのまま試作へ入れる再現度を目指してください。",
      "共働き世帯の一週間に寄り添う家計管理UIをデザインしてください。画面は「ダッシュボード」「予算設定」「異常支出アラート」「サブスク整理」の4系統。数字を並べるだけでなく、次の行動をそっと促す提案カードを主役に据える。初回起動から習慣化までの導線を途切れさせず、色覚多様性、最小タップ領域、読み上げラベルまで含めて、使うたび不安が減る体験に仕上げてください。",
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
      "潮の満ち引きで記憶が形を持つ近未来都市を舞台に、美少女SFを6ページで紡いでください。主人公は17歳の潮位予報士見習い。世界の核は「満潮で記憶が物質化」「市民は記憶税を納める」「愛着ある記憶ほどインフラに消費される」の3点で固定し、背景制度を全ページで揺らさない。冒頭2ページで強いフックを置き、出来事→判断→行動→結果の連鎖で、主人公の小さな誤りが都市停電へ転がる必然を描いてください。",
      "美少女剣士とAI僧侶のバディ譚を8ページで描いてください。剣と冒険という既知の骨格に、祈祷アルゴリズムが斬撃を最適化する未発見の切り口を重ねる。1話で世界ルールが直感的に伝わるよう配置し、主人公の口調・弱点・執着を初会話で焼き付ける。5ページ以降も服装、髪、持ち物、話し方を崩さず、各ページ末に小さな逆転を置いて、最後は次話を読まずにいられない問いで閉じてください。",
      "学園魔法ミステリーを5ページで設計してください。ヒロインは完璧に見える生徒会長、ただし「嘘を見抜くほど自分の記憶が欠ける」致命的な代償を持つ。校舎、寮、時計塔、掲示板ルールなどの背景要素はコマを跨いでも連続性を維持し、同一場所は同じ視覚情報で再現。各コマにセリフと状況描写を十分に入れ、誰が何を知り、どこで虚偽が混入したのかを読者が追跡できる情報開示順で構成してください。",
      "日常の光の中に不穏を沈めた4ページ短編を描いてください。アイドル研究部の美少女3人が文化祭準備を進めるが、台本の改稿履歴に未来の日付が紛れ込んでいる。可憐な会話と異物感を同時成立させるため、1ページごとに違和感を一段深く積み、ラストで「誰かが最終回を先に書いている」事実を提示する。ポスター、部誌、時計、机配置などの小物はページ間で連続させ、世界の手触りを切らさないでください。",
    ],
  },
]
