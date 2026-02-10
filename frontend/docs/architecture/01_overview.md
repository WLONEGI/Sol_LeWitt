# 01. フロントエンド概要 & アーキテクチャ

## 1. ビジョン
**Sol LeWitt Frontend** は、AIエージェントとの対話を通じて、リアルタイムに進捗や成果物（スライド、画像、データ分析）を可視化するモダンなインターフェースを提供します。ユーザーは単なるチャットに留まらず、生成過程を「監視」し、最終成果物を「プレビュー」することができます。

## 2. コア・テクノロジースタック
- **Framework**: Next.js 15+ (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **UI Components**: shadcn/ui (Radix UI)
- **Icons**: Lucide React
- **AI Integration**: Vercel AI SDK (v6)
- **State Management**: Zustand
- **Animations**: Framer Motion / CSS Transitions

## 3. ディレクトリ構造（Feature-based Organization）
プロジェクトは機能（Feature）単位でカプセル化されており、再利用性と凝集度を高めています。

```text
src/
├── app/             # App Router (Pages, Layouts)
├── features/        # 機能別コンポーネント・ロジック
│   ├── chat/        # メインチャットインターフェース
│   └── preview/     # アーティファクトプレビュー（スライド等）
├── components/      # UI共通コンポーネント (Atomic UI)
├── lib/             # 汎用ライブラリ統合
│   └── chat/        # ストリーミング処理ユーティリティ
├── hooks/           # 共有カスタムフック
└── types/           # グローバル型定義
```

## 4. デザイン原則
- **Responsive Layout**: モバイル・デスクトップ両対応の柔軟なレイアウト。
- **Glassmorphism**: 半透明な背景やぼかし効果を用いた、清潔感のあるモダンなデザイン。
- **Micro-animations**: インタラクションを豊かにする微細なアニメーション。
- **Skeleton Loaders**: 非同期通信中の体感待ち時間を軽減するプレースホルダー。

## 5. コンポーネント設計
### UI コンポーネント
`src/components/ui/` に配置される shadcn/ui ベースの低レイヤーコンポーネント。一貫したスタイルを保つために使用されます。

### フィーチャーコンポーネント
`src/features/chat/components/` のように、特定のビジネスロジックに紐づく高レイヤーコンポーネント。グローバルストア（Zustand）と直接接続することが許容されます。
