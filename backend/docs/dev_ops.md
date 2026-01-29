# Development & Operations Guide

本ドキュメントでは、Spell Backend の開発環境セットアップ、設定、デプロイ方法について解説します。

---

## 1. Local Development Setup

### 前提条件 (Prerequisites)
*   Python 3.12+
*   [uv](https://github.com/astral-sh/uv) (推奨パッケージマネージャー)
*   PostgreSQL (ローカル実行またはCloud SQL Proxy経由)
*   LibreOffice & Poppler (PPTX解析・PDF変換用)
    *   Mac: `brew install libreoffice poppler`

### インストール手順

```bash
# リポジトリのクローン
git clone https://github.com/langmanus/langmanus.git
cd backend/langgraph

# 仮想環境の作成と依存関係のインストール
uv venv --python 3.12
source .venv/bin/activate
uv sync
```

### サーバー起動

```bash
# 環境変数の設定
cp .env.example .env
# .env を編集してVertex AI Project ID設定

# 開発サーバー起動 (Hot Reload有効)
uv run server.py
# または
make serve
```

---

## 2. Configuration (`.env`)

アプリケーションの動作には以下の環境変数が必要です。

### LLM Configuration
*   `BASIC_MODEL`: 基本モデル名 (例: `gemini-1.5-flash`)
*   `REASONING_MODEL`: 推論モデル名 (例: `gemini-1.5-pro`)
*   `VL_MODEL`: Vision-Languageモデル名

### Database
*   `POSTGRES_DB_URI`: 接続文字列 (`postgresql://user:pass@host:port/dbname`)

### External Tools
*   `GCS_BUCKET_NAME`: 成果物保存用 GCS バケット
*   `GCP_PROJECT_ID`: Google Cloud Project ID
*   `VERTEX_LOCATION`: Vertex AI のリージョン (例: `us-central1`)

---

## 3. Docker

アプリケーションはコンテナ化されており、Cloud Run で動作することを前提に設計されています。

### Dockerfile の構成
*   Base Image: `python:3.12-slim-bookworm`
*   System Deps: `libreoffice-impress`, `poppler-utils`, `fonts-noto-cjk` (日本語フォント)
*   User: 非rootユーザー (`appuser`) で実行

### ビルドと実行

```bash
# ビルド
docker build -t ai-slide-backend .

# 実行 (ポート8080)
# 注意: ローカルでGCP認証を通すにはクレデンシャルマウントが必要な場合があります
docker run -p 8080:8080 -e PORT=8080 --env-file .env ai-slide-backend
```

---

## 4. Deployment (Cloud Run)

デプロイは Google Cloud Build を使用して自動化されています。

### `cloudbuild.yaml`
1.  **Build**: Dockerイメージを作成
2.  **Push**: Google Container Registry (GCR) へプッシュ
3.  **Deploy**: Cloud Run へデプロイ
    *   Memory: 2Gi
    *   CPU: 2
    *   Cloud SQL Connection: 自動接続設定 (`--add-cloudsql-instances`)

### 手動デプロイコマンド

```bash
gcloud builds submit --config cloudbuild.yaml .
```
