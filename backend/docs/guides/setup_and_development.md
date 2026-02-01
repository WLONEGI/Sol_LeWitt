# セットアップ & 開発ガイド

## 1. ローカル開発環境の構築

### 前提条件
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (推奨)
- Google Cloud SDK (認証用)
- PostgreSQL (ローカルまたは Cloud SQL Proxy)

### インストール
```bash
# 依存関係の同期
uv sync

# 仮想環境の有効化
source .venv/bin/activate
```

### 環境設定 (`.env`)
`.env.example` をコピーし、以下の必須項目を設定してください。
- `VERTEX_PROJECT_ID`: Google Cloud プロジェクト ID
- `POSTGRES_DB_URI`: データベース接続 URI

## 2. サーバーの起動
```bash
# 開発モード（Hot Reload）で起動
uv run server.py
```

## 3. 便利なコマンド
- `python scripts/cleanup_db.py`: グラフ状態のリセット
- `python scripts/test_search.py`: Google Search Grounding のテスト
