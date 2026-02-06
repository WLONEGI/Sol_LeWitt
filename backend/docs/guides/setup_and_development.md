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
- `python scripts/init_db.py`: `users` / `threads` テーブル初期化

## 4. 既存スレッドの `owner_uid` バックフィル

ユーザー分離を有効化した後、既存データ (`threads.owner_uid IS NULL`) はバックフィルが必要です。  
このプロジェクトでは `thread_id -> owner_uid` の対応表を入力として、以下を一括移行します。

- `threads.owner_uid` の更新
- LangGraph チェックポイント (`checkpoint_ns=''`) を `checkpoint_ns=<owner_uid>` へ移行
  - `checkpoints`
  - `checkpoint_blobs`
  - `checkpoint_writes`

### 4.1 Cloud SQL Proxy を使って接続する場合

```bash
# 別ターミナルで起動
cloud-sql-proxy <PROJECT_ID>:<REGION>:<INSTANCE_NAME> --port 5432
```

`.env` の `POSTGRES_DB_URI` は `127.0.0.1:5432` を向くように設定してください。

### 4.2 事前確認（レポートモード）

```bash
uv run python scripts/backfill_thread_ownership.py \
  --mapping-csv /path/to/thread_owner_mapping.csv \
  --unresolved-csv /tmp/unresolved_threads.csv
```

`--apply` を付けない場合は更新しません（dry-run相当）。

### 4.3 適用

```bash
uv run python scripts/backfill_thread_ownership.py \
  --apply \
  --mapping-csv /path/to/thread_owner_mapping.csv \
  --unresolved-csv /tmp/unresolved_threads.csv
```

CSV 形式:

```csv
thread_id,owner_uid
<thread-id-1>,<firebase-uid-1>
<thread-id-2>,<firebase-uid-2>
```

### 4.4 単一オーナーへ一括付与（検証環境向け）

```bash
uv run python scripts/backfill_thread_ownership.py \
  --apply \
  --default-owner-uid <firebase-uid>
```

本番では誤割当を避けるため、`--mapping-csv` を推奨します。
