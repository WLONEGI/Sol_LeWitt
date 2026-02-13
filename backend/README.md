# Sol LeWitt Backend

![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)
![Framework](https://img.shields.io/badge/FastAPI-0.109%2B-009688)
![Orchestration](https://img.shields.io/badge/LangGraph-0.0.10%2B-orange)
![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)

**Sol LeWitt** は **AI Slide with Nano Banana** プロジェクトのためのインテリジェントなバックエンドエンジンです。**LangGraph** を活用してマルチエージェントワークフローをオーケストレーションし、ユーザーのプロンプトに基づいてリサーチ、構成作成、スライドデザイン、レンダリング（PPTX生成）を自律的に実行します。

## 主な機能 (Key Features)

- **マルチエージェント オーケストレーション**: LangGraph を使用して、各タスクに特化したエージェントを協調動作させます。
- **AI駆動ワークフロー**:
  - **Researcher (リサーチャー)**: Web検索を実行し、必要な情報を詳細なレポートとして抽出。
  - **Storywriter (ストーリーライター)**: 構成案（Plan）に基づき、スライドの具体的なコンテンツを執筆。
  - **Designer / Visualizer**: Google Vertex AI (Imagen 3) を使用し、高品質な画像生成や **In-painting** を実行。
  - **Renderer (Data Analyst)**: コンテンツと画像、デザインコンテキストを統合し、`.pptx` や高品質なデザインデータを生成。
- **インテリジェント・リプランニング**: 進捗やエラー状況に応じて Planner が動的に計画を修正し、柔軟にタスクを完遂します。
- **プロダクト・タイプ**: スライド生成 (`slide`) 、デザイン生成 (`design`) 、コミック生成 (`comic`) など、用途に応じた最適化。
- **非同期アーキテクチャ**: 状態管理とチェックポイント機能のために **PostgreSQL** を使用した完全非同期のデータベース操作を実現しています。
- **クラウド統合**: **Google Cloud Platform** (Vertex AI, Cloud Storage) および **Firebase Authentication** とシームレスに統合されています。

## アーキテクチャ

このプロジェクトは、関心の分離と保守性を確保するために、**ドメイン駆動設計 (DDD)** に影響を受けたレイヤードアーキテクチャを採用しています。

```text
backend/
├── main.py              # CLI エントリーポイント（対話的テスト用）
├── server.py            # 本番用 API エントリーポイント (Uvicorn)
├── src/
│   ├── app/             # インターフェース層 (FastAPI)
│   │   ├── routers/     # API エンドポイント
│   │   └── app.py       # アプリケーションファクトリ & ミドルウェア
│   ├── core/            # アプリケーションコア
│   │   └── workflow/    # LangGraph ステートマシン & オーケストレーション
│   ├── domain/          # ビジネスロジック & 特化型エージェント
│   │   ├── researcher/  # Web検索ロジック
│   │   ├── designer/    # 画像生成ロジック
│   │   ├── writer/      # コンテンツ生成ロジック
│   │   └── renderer/    # スライドレンダリングロジック
│   ├── infrastructure/  # インフラストラクチャ & 外部インターフェース
│   │   ├── database/    # Postgres 接続 & チェックポイント
│   │   ├── llm/         # Gemini モデル設定
│   │   └── storage/     # GCS & ファイルシステム操作
│   └── shared/          # 共有カーネル (Utils, Config, Schemas)
```

## はじめに (Getting Started)

### 前提条件 (Prerequisites)

以下のツールがインストールされていることを確認してください:

- **Python 3.12+**
- **[uv](https://github.com/astral-sh/uv)**: 高速なPythonパッケージインストーラー兼リゾルバ。
- **Docker**: ローカルでPostgreSQLインスタンスを実行するために使用（推奨）。
- **Google Cloud SDK**: `gcloud auth application-default login` で認証済みであること。

### インストール (Installation)

1.  **リポジトリのクローン:**
    ```bash
    git clone <repository-url>
    cd ai_slide_with_nano_banana/backend
    ```

2.  **依存関係のインストール:**
    このプロジェクトでは依存関係の管理に `uv` を使用しています。
    ```bash
    uv sync
    ```

3.  **環境設定:**
    サンプルの環境設定ファイルをコピーし、シークレット情報を設定してください。
    ```bash
    cp .env.example .env
    ```
    
    **`.env` で設定すべき重要な変数:**
    - `VERTEX_PROJECT_ID`: GCP プロジェクトID。
    - `VERTEX_LOCATION`: リージョン (例: `asia-northeast1`)。
    - `FIREBASE_SERVICE_ACCOUNT_JSON`: Firebase サービスアカウントJSONの内容。
    - `POSTGRES_DB_URI`: PostgreSQL データベースへの接続文字列。
    - `GCS_BUCKET_NAME`:生成されたアセットを保存するバケット名。

### サーバーの起動 (Running the Server)

ホットリロードを有効にして FastAPI サーバーを起動するには、以下のコマンドを実行します:

```bash
uv run uvicorn server:app --reload --port 8000
```

API は `http://localhost:8000` で利用可能になります。

### CLI の実行 (Running the CLI)

API層を介さずにエージェントワークフローを素早くテストする場合:

```bash
uv run python main.py
```

## API ドキュメント

バックエンドでは、Swagger UI によって生成されたインタラクティブな API ドキュメントを提供しています。

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 主要なエンドポイント

- **`POST /api/chat/invoke`**: LangGraph ワークフローの同期的な呼び出し。
- **`POST /api/chat/stream`**: ワークフローの出力をチャンクごとにストリーミングします。
- **`POST /api/chat/stream_events`**: 詳細なイベントストリーミング（トークン、ツール呼び出し、状態更新など）のためのカスタムエンドポイント。

## テスト

`pytest` を使用してテストスイートを実行します:

```bash
uv run pytest
```

## 技術スタック (Tech Stack)

- **Frameworks**: [FastAPI](https://fastapi.tiangolo.com/), [LangGraph](https://langchain-ai.github.io/langgraph/), [LangServe](https://github.com/langchain-ai/langserve)
- **AI Models**: Google Gemini Pro & Flash (via Vertex AI)
- **Database**: PostgreSQL (via `psycopg` & `langgraph-checkpoint-postgres`)
- **Storage**: Google Cloud Storage
- **Auth**: Firebase Authentication
