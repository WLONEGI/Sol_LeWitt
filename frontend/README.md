# Spell Frontend (Next.js)

![TypeScript](https://img.shields.io/badge/TypeScript-5.0%2B-blue)
![Next.js](https://img.shields.io/badge/Next.js-15%2B-black)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4.0%2B-38B2AC)
![License](https://img.shields.io/badge/license-MIT-green)

**Spell Frontend** は、**AI Slide with Nano Banana** プロジェクトのためのリアクティブなWebインターフェースです。**Next.js (App Router)** と **Vercel AI SDK** を採用し、ユーザーが直感的にAIエージェントと対話し、生成されたスライドや成果物をリアルタイムでプレビューできる環境を提供します。

## 主な機能 (Key Features)

- **Feature-Sliced Design**: 保守性と拡張性を高めるため、機能ごとに分割されたモジュラーアーキテクチャ (`features/chat`, `features/preview`) を採用しています。
- **AI統合 (AI Integration)**: **Vercel AI SDK** (`useChat`) を使用し、バックエンドのLangGraphエージェントとシームレスに連携。ストリーミングレスポンスによる高速な対話体験を実現します。
- **インタラクティブUI**:
  - **Chat**: Markdown、コードハイライト、ツール実行ログの表示に対応したタイムライン形式のチャットインターフェース。
  - **Preview**: AIが生成したスライド、画像、ドキュメントをリアルタイムでレンダリングするプレビュー画面。
- **状態管理 (State Management)**: **Zustand** を使用したスケーラブルなグローバル状態管理により、複雑なアプリケーションの状態を効率的に処理します。
- **スタイリング**: **Tailwind CSS v4** と **Shadcn UI** (Radix UIベース) を組み合わせ、美しくアクセシブルなデザインコンポーネントを構築しています。

## アーキテクチャ (Architecture)

```text
src/
├── app/                  # Next.js App Router (ルーティング & レイアウト)
│   ├── layout.tsx        # ルートレイアウト
│   └── page.tsx          # メインページ
├── components/           # 共有UIコンポーネント (ビジネスロジックを含まない)
│   ├── ui/               # 基本UIパーツ (Button, Input, Dialogなど - Shadcn)
│   └── layout/           # ヘッダー、サイドバーなどのレイアウト部品
├── features/             # ビジネスドメイン (機能単位でカプセル化)
│   ├── chat/             # チャット機能 (コンポーネント, ストア, フック)
│   └── preview/          # プレビュー機能 (スライドビューワー, 成果物表示)
├── hooks/                # アプリケーション全体で共有されるカスタムフック
├── lib/                  # ユーティリティ関数, APIクライアント設定
└── types/                # グローバルな型定義
```

## はじめに (Getting Started)

### 前提条件 (Prerequisites)

- **Node.js 20+**
- **npm** または **pnpm**

### インストール (Installation)

1.  依存関係をインストールします:
    ```bash
    npm install
    ```

2.  環境変数を設定します:
    `.env.example` を `.env.local` にコピーし、Firebaseの設定を入力してください。
    ```bash
    cp .env.example .env.local
    ```
    
    **必要な環境変数:**
    - `NEXT_PUBLIC_FIREBASE_API_KEY`
    - `NEXT_PUBLIC_FIREBASE_PROJECT_ID`
    - `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`
    - `NEXT_PUBLIC_FIREBASE_APP_ID`

### 開発サーバーの起動 (Development)

開発サーバーを起動します:

```bash
npm run dev
```

ブラウザで [http://localhost:3000](http://localhost:3000) を開くとアプリケーションが表示されます。

## テスト (Testing)

このプロジェクトでは、単体テストに **Vitest**、E2Eテストに **Playwright** を使用しています。

### 単体テスト (Unit Tests)
```bash
npm run test
```

### E2Eテスト (End-to-End Tests)
Next.jsサーバーがポート3000で起動していないことを確認してから実行してください（自動的にポートキルを試みます）。
```bash
npm run test:e2e
```

## 技術スタック (Tech Stack)

- **Framework**: Next.js 15+ (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS v4, Tailwind Animate
- **UI library**: Radix UI, Shadcn UI, Lucide React
- **State Management**: Zustand
- **AI SDK**: Vercel AI SDK
- **Animation**: Framer Motion
- **Testing**: Vitest, Playwright
