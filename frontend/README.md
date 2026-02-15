# Sol LeWitt Frontend (Next.js)

![Next.js](https://img.shields.io/badge/Next.js-16-black)
![React](https://img.shields.io/badge/React-19-61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-5.9-blue)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-38B2AC)
![Vercel AI SDK](https://img.shields.io/badge/Vercel_AI_SDK-6-000000)
![License](https://img.shields.io/badge/license-MIT-green)

**Sol LeWitt Frontend** は、**AI Slide with Nano Banana** プロジェクトのためのリアクティブな Web インターフェースです。**Next.js (App Router)** と **Vercel AI SDK** を採用し、ユーザーが直感的に AI エージェントと対話し、生成されたスライドや成果物をリアルタイムでプレビューできる環境を提供します。

## 🌟 主な機能

- **Feature-Sliced Design**: 保守性と拡張性を高めるため、機能ごとに分割されたモジュラーアーキテクチャ (`features/chat`, `features/preview`, `features/auth`) を採用。
- **AI 統合 (AI Integration)**: **Vercel AI SDK (`ai` v6)** を使用し、バックエンドの LangGraph エージェントとシームレスに連携。`createUIMessageStreamResponse` による UI メッセージストリームプロトコルでリアルタイム表示を実現。
- **BFF (Backend for Frontend) アーキテクチャ**: Next.js の API Routes (`/api/chat`, `/api/history`, `/api/uploads`) をバックエンドへのプロキシとして使用し、認証トークンの受け渡しと SSE ストリーム変換を担当。
- **インタラクティブ UI**:
  - **Chat**: Markdown、コードハイライト、ツール実行ログ、Thinking/Reasoning プロセスの表示に対応。
  - **Visualizer**: AI が生成したスライド、画像、デザインデータをリアルタイムでレンダリング。動的なアスペクト比の切り替えに対応。
  - **In-paint Editor**: 生成された画像の一部をブラシで指定し、AI によって部分修正可能。
- **状態管理**: **Zustand** を使ったプレビュー状態やスレッド情報の管理。
- **認証**: **Firebase Authentication** (Google ログイン) を `AuthProvider` 経由で統合。
- **スタイリング**: **Tailwind CSS v4** + **Shadcn UI (Radix UI)** + **Framer Motion** アニメーション。

## 🏗️ アーキテクチャ

```text
frontend/
├── src/
│   ├── app/                    # Next.js App Router
│   │   ├── layout.tsx          # ルートレイアウト (AuthProvider, ThemeProvider)
│   │   ├── page.tsx            # ランディングページ
│   │   ├── chat/               # チャットページ
│   │   ├── _components/        # ページレベルの共有コンポーネント
│   │   └── api/                # BFF API Routes (Backend Proxy)
│   │       ├── chat/route.ts   # SSE ストリーム変換 & Vercel AI SDK 互換出力
│   │       ├── history/route.ts  # スレッド履歴プロキシ
│   │       └── uploads/route.ts  # ファイルアップロードプロキシ
│   ├── components/
│   │   └── ui/                 # 基本 UI パーツ (Shadcn UI: Button, Input, Dialog 等)
│   ├── features/               # ビジネスドメイン (機能単位でカプセル化)
│   │   ├── auth/               # 認証 UI コンポーネント
│   │   ├── chat/               # チャット機能
│   │   │   ├── components/     # メッセージリスト、入力フォーム 等
│   │   │   ├── hooks/          # チャット関連カスタムフック
│   │   │   ├── stores/         # Zustand ストア
│   │   │   ├── types/          # Chat / Plan 型定義
│   │   │   ├── lib/            # ユーティリティ
│   │   │   └── constants/      # 定数
│   │   └── preview/            # プレビュー機能
│   │       ├── viewers/        # SlideViewer, SlideDeckViewer 等
│   │       ├── components/     # プレビュー共通コンポーネント
│   │       ├── stores/         # プレビュー状態管理
│   │       ├── types/          # プレビュー型定義
│   │       ├── lib/            # レンダリングユーティリティ
│   │       └── utils/          # ヘルパー関数
│   ├── hooks/                  # アプリ全体で共有されるカスタムフック
│   ├── lib/                    # ユーティリティ関数 (cn, API 設定)
│   └── providers/              # コンテキストプロバイダー
│       ├── auth-provider.tsx   # Firebase Auth プロバイダー
│       └── theme-provider.tsx  # ダーク/ライトテーマ
├── tests/                      # テスト (Vitest 単体 + Playwright E2E)
├── public/                     # 静的アセット
├── next.config.ts              # Next.js 設定 (BFF rewrites, Firebase 環境変数)
├── apphosting.yaml             # Firebase App Hosting 設定
└── package.json
```

## 🚀 はじめに

### 前提条件

- **Node.js 20+**
- **npm**
- バックエンドサーバーが `http://localhost:8000` で起動していること（ローカル開発時）

### インストール

1.  依存関係をインストール:
    ```bash
    cd frontend
    npm install
    ```

2.  環境変数を設定:
    ```bash
    cp .env.example .env.local
    ```

    **必要な環境変数:**

    | 変数名 | 説明 |
    | :--- | :--- |
    | `NEXT_PUBLIC_FIREBASE_API_KEY` | Firebase API キー |
    | `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Firebase Auth ドメイン |
    | `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Firebase プロジェクト ID |
    | `NEXT_PUBLIC_FIREBASE_APP_ID` | Firebase アプリ ID |

    **オプション:**

    | 変数名 | デフォルト | 説明 |
    | :--- | :--- | :--- |
    | `BACKEND_URL` | `http://localhost:8000` (dev) | バックエンド API の URL |
    | `STREAM_BENCH_ENABLED` | `1` | ストリームベンチマークログの有効化 |
    | `STREAM_BENCH_SAMPLE_RATE` | `1.0` | ベンチマークのサンプリング率 |
    | `STREAM_UI_EVENT_FILTER_ENABLED` | `1` | UI イベントフィルタリングの有効化 |

### 開発サーバーの起動

```bash
npm run dev
```

ブラウザで [http://localhost:3000](http://localhost:3000) を開きます。

> **Note**: `next.config.ts` の `rewrites` により `/api/*` への全リクエストはバックエンド (`BACKEND_URL`) に自動プロキシされます。ただし `api/chat/route.ts` 等の BFF ルートが存在する場合はそちらが優先されます。

## 🔌 BFF API Routes

フロントエンドは Next.js API Routes を BFF (Backend for Frontend) として使用し、バックエンドへのプロキシとストリーム変換を行います。

| Route | メソッド | 概要 |
| :--- | :--- | :--- |
| `/api/chat` | `POST` | バックエンドの SSE ストリームを Vercel AI SDK の UI Message Stream に変換 |
| `/api/history` | `GET` | スレッド一覧の取得プロキシ |
| `/api/uploads` | `POST` | ファイルアップロード (画像・PPTX) のプロキシ |

## 🧪 テスト

### 単体テスト (Vitest)
```bash
npm run test
```

### E2E テスト (Playwright)
```bash
npm run test:e2e
```

> **Note**: E2E テスト実行前にポート 3000 が自動的に解放されます (`pretest:e2e`)。

## 🚢 デプロイ

### Firebase App Hosting

本番環境は **Firebase App Hosting** を使用してデプロイされます。`apphosting.yaml` に環境変数と Cloud Run ランタイム設定が定義されています。

```yaml
# apphosting.yaml (抜粋)
runConfig:
  minInstances: 0
  maxInstances: 10
  memory: "2Gi"
  cpu: 2
```

### 手動ビルド

```bash
npm run build   # Next.js standalone ビルド
npm start       # プロダクション起動
```

## 🛠️ 技術スタック

| カテゴリ | 技術 |
| :--- | :--- |
| **Framework** | Next.js 16 (App Router, `output: 'standalone'`) |
| **Language** | TypeScript 5.9 |
| **UI** | React 19, Radix UI, Shadcn UI, Lucide React |
| **Styling** | Tailwind CSS v4, Tailwind Animate, Framer Motion |
| **State Management** | Zustand 5 |
| **AI SDK** | Vercel AI SDK v6 (`ai`, `@ai-sdk/react`) |
| **Auth** | Firebase Authentication (Google Sign-In) |
| **Rendering** | React Markdown, React Syntax Highlighter, Resizable Panels |
| **Testing** | Vitest 4, Playwright |
| **Deployment** | Firebase App Hosting (Cloud Run) |
