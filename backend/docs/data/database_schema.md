# データベース & ストレージ

## 1. 永続化スキーマ (PostgreSQL)

LangGraph の `AsyncPostgresSaver` を使用し、以下のテーブルで状態を管理します。初回起動時に `IF NOT EXISTS` で自動生成されます。

- **`checkpoints`**: グラフの各ステップにおける State スナップショット（msgpack形式）。
- **`checkpoints_blobs`**: 大容量データ（Artifacts等）の効率的な格納。
- **`checkpoints_writes`**: 非同期処理での書き込みログ。

### 認証設定
`POSTGRES_DB_URI` 環境変数を使用します。Cloud Run 環境下では、`CLOUD_SQL_CONNECTION_NAME` が設定されている場合に自動的に Unix Domain Socket 接続へと切り替わります。

## 2. 成果物ストレージ (GCS)
画像などのバイナリ資産は Google Cloud Storage に保存されます。

- **バケット名**: `GCS_BUCKET_NAME` 環境変数で指定。
- **ライフサイクル**: 生成された画像は公開 URL (Signed URL または Public URL) としてフロントエンドに渡されます。

## 3. 成果物スキーマ (JSON)
Worker が生成する主な成果物形式：

```json
// Storywriter (Markdown)
{ "kind": "document", "content": "# タイトル...", "format": "markdown" }

// Visualizer (Image)
{ "kind": "image", "url": "https://...", "prompt": "..." }
```
