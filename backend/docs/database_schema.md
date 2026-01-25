# Database Schema

Spell Backend は、LangGraph のステート永続化のために **PostgreSQL** を使用します。
スキーマは `langgraph.checkpoint.postgres` ライブラリによって管理され、アプリケーション起動時に `initialize_graph()` 内の `checkpointer.setup()` によって自動的に作成されます。

---

## 1. Tables

LangGraph の標準的な永続化スキーマとして、以下の3つのテーブルが使用されます。

### 1.1 `checkpoints`

グラフの各ステップにおける状態（State）のスナップショットを保存するメインテーブルです。

| Column | Type | Description |
| :--- | :--- | :--- |
| `thread_id` | TEXT | セッションID（Primary Key 複合キーの一部）。ユーザーごとの会話スレッドを識別。 |
| `checkpoint_ns` | TEXT | ネームスペース（通常は空文字）。サブグラフなどで使用。 |
| `checkpoint_id` | TEXT | チェックポイントID（Primary Key 複合キーの一部）。通常はタイムスタンプベースのULID。 |
| `parent_checkpoint_id` | TEXT | 前のチェックポイントID。履歴のリンクリストを形成。 |
| `type` | TEXT | チェックポイントの型。 |
| `checkpoint` | BYTEA | シリアライズされたStateデータ（msgpack形式）。 |
| `metadata` | BYTEA | メタデータ（langgraph_step, run_id, etc.）。 |

### 1.2 `checkpoints_blobs`

大きなデータ（Blob）を効率的に格納するためのテーブルです。`checkpoints` テーブルから参照されます。

| Column | Type | Description |
| :--- | :--- | :--- |
| `thread_id` | TEXT | セッションID。 |
| `checkpoint_ns` | TEXT | ネームスペース。 |
| `channel` | TEXT | チャネル名。 |
| `version` | TEXT | バージョンID。 |
| `type` | TEXT | データ型（例: `json`）。 |
| `blob` | BYTEA | バイナリデータ本体。 |

### 1.3 `checkpoints_writes`

各ステップで行われた書き込み操作（Writes）を記録するテーブルです。非同期実行や並列実行の管理に使用されます。

| Column | Type | Description |
| :--- | :--- | :--- |
| `thread_id` | TEXT | セッションID。 |
| `checkpoint_ns` | TEXT | ネームスペース。 |
| `checkpoint_id` | TEXT | チェックポイントID。 |
| `task_id` | TEXT | タスクID。 |
| `idx` | INTEGER | インデックス。 |
| `channel` | TEXT | 書き込み対象のチャネル。 |
| `type` | TEXT | データ型。 |
| `blob` | BYTEA | 書き込まれたデータ。 |

---

## 2. Configuration

データベース接続は `src/service/workflow_service.py` 内の `WorkflowManager` によって管理されます。

*   **Driver**: `psycopg_pool.AsyncConnectionPool`
*   **Environment Variable**: `POSTGRES_DB_URI`
    *   Format: `postgresql://user:password@host:port/dbname`
*   **Pooling**:
    *   Min Size: 1
    *   Max Size: 10
    *   Timeout: 30.0s

### Initialization
アプリケーション起動時に `checkpointer.setup()` が呼ばれ、上記のテーブルが存在しない場合は自動作成されます（`IF NOT EXISTS`）。
これにより、手動でのマイグレーション作業は不要です。
