# Spell Backend Documentation

Spell バックエンドの技術ドキュメントへようこそ。本システムは、LangGraph を用いた高度なエージェント・ワークフロー・エンジンです。

## 📚 ドキュメント構成

### 🏗️ Architecture
- **[01. システム概要](./architecture/01_overview.md)**: 全体像とデザイン原則。
- **[02. ワークフロー・エンジン](./architecture/02_workflow_engine.md)**: ノードの詳細と状態管理。
- **[03. ストリーミング・プロトコル](./architecture/03_streaming_protocol.md)**: SSE と Vercel AI SDK の統合。

### 🔌 API & Data
- **[API エンドポイント](./api/endpoints.md)**: REST API 仕様。
- **[DB & ストレージ](./data/database_schema.md)**: データの永続化と成果物管理。

### 🚀 Guides
- **[セットアップ & 開発](./guides/setup_and_development.md)**: ローカル環境構築。
- **[デプロイ & 運用](./guides/deployment_and_ops.md)**: Cloud Run へのデプロイ。

### 📊 エージェント出力マッピング
各ノードが出力するイベントと、BFF (`/api/chat/route.ts`) で変換される前端データ形式の対応表です。詳細な挙動は **[ストリーミング・プロトコル](./architecture/03_streaming_protocol.md)** を参照してください。

| ノード名 (Node) | バックエンド出力 (`stream_event`) | フロントエンド変換形式 (Vercel AI SDK) |
| :--- | :--- | :--- |
| **coordinator** | `title_generated`, `on_chat_model_stream` | `title_update`, `text-delta` |
| **planner** | `plan_update`, `on_chat_model_stream` | `plan_update`, `tool-approval-request`, `reasoning-delta` |
| **supervisor** | `on_chat_model_stream` | `text-delta` |
| **researcher** | `on_chat_model_stream`, `on_chain_end` | `text-delta`, (Artifacts) |
| **storywriter** | `slide_outline_updated`, `on_chat_model_stream` | `data-outline`, `tool-approval-request`, `reasoning-delta` |
| **visualizer** | `on_chat_model_stream`, `on_chain_end` | `reasoning-delta`, (Artifacts) |
| **data_analyst** | `on_chat_model_stream` | `reasoning-delta`, `text-delta` |

---

## 🔍 クイックスタート
1. `uv sync` で環境構築。
2. `.env` に GCP プロジェクト情報を設定。
3. `uv run server.py` でサーバー起動。
