# Backend Documentation

Spell Backend のドキュメントインデックスです。

## Documentation List

| Document | Description |
| :--- | :--- |
| **[Architecture](./architecture.md)** | システム全体のアーキテクチャ、エージェントの役割、データフローの概要。 |
| **[API Specification](./api_spec.md)** | REST API エンドポイント、リクエスト/レスポンス形式、SSEイベント仕様。 |
| **[LangGraph Workflow](./langgraph_workflow.md)** | LangGraph の詳細設計、State定義、ノードロジック、永続化の仕組み。 |
| **[Database Schema](./database_schema.md)** | PostgreSQL のテーブルスキーマと永続化設定。 |
| **[DevOps Guide](./dev_ops.md)** | ローカル開発環境のセットアップ、環境変数、Dockerビルド、デプロイ手順。 |

## Quick Start

```bash
# ドキュメントディレクトリで作業中
cd backend

# 開発サーバー起動
uv run server.py
```

詳細は [DevOps Guide](./dev_ops.md) を参照してください。
