# データベース & ストレージ

## 1. 永続化スキーマ (PostgreSQL)

LangGraph の `AsyncPostgresSaver` を使用し、以下のテーブルで状態を管理します。初回起動時に `IF NOT EXISTS` で自動生成されます。

- **`checkpoints`**: グラフの各ステップにおける State スナップショット（msgpack形式）。
- **`checkpoints_blobs`**: 大容量データ（Artifacts等）の効率的な格納。
- **`checkpoints_writes`**: 非同期処理での書き込みログ。

加えて、アプリケーションの認証・履歴管理用に以下を利用します。

- **`users`**: Firebase ユーザー情報 (`uid` 主キー)。
- **`threads`**: スレッドメタデータ。
  - `thread_id` (PK)
  - `owner_uid` (FK -> `users.uid`)
  - `title`, `summary`, `created_at`, `updated_at`

`threads.owner_uid` により、履歴取得 API はユーザー単位でスコープされます。
LangGraph のチェックポイント参照時は `checkpoint_ns = owner_uid` を設定し、同一 `thread_id` でもユーザー間で状態が分離されます。

既存データ移行時は `scripts/backfill_thread_ownership.py` を使い、`threads.owner_uid` 更新と `checkpoint_ns=''` から `checkpoint_ns=<owner_uid>` へのコピー/削除を実施します。

### 認証設定
`POSTGRES_DB_URI` 環境変数を使用します。Cloud Run 環境下では、`CLOUD_SQL_CONNECTION_NAME` が設定されている場合に自動的に Unix Domain Socket 接続へと切り替わります。

## 2. 成果物ストレージ (GCS)
画像などのバイナリ資産は Google Cloud Storage に保存されます。

- **バケット名**: `GCS_BUCKET_NAME` 環境変数で指定。
- **ライフサイクル**: 生成された画像は公開 URL (Signed URL または Public URL) としてフロントエンドに渡されます。

## 3. 成果物スキーマ (JSON)
Worker が生成する主な成果物形式：

```json
// Writer(mode=slide_outline)
{
  "execution_summary": "5枚のスライド構成を作成",
  "slides": [
    {
      "slide_number": 1,
      "title": "導入",
      "bullet_points": ["背景", "問題提起"],
      "description": "導入スライド"
    }
  ]
}

// Researcher(text_search)
{
  "task_id": 1,
  "perspective": "市場規模と推移",
  "report": "主要指標を比較して要点を整理...",
  "sources": [
    "https://example.com/source-1",
    "https://example.com/source-2"
  ]
}

// Visualizer
{
  "prompts": [
    {
      "slide_number": 1,
      "title": "導入",
      "compiled_prompt": "clean infographic style ...",
      "generated_image_url": "https://storage.googleapis.com/..."
    }
  ],
  "combined_pdf_url": "https://storage.googleapis.com/.../slides.pdf"
}

// Data Analyst
{
  "execution_summary": "集計処理を実行",
  "analysis_report": "処理結果の要約",
  "outputs": [
    "https://storage.googleapis.com/.../result.csv"
  ]
}
```

補足:
- 旧 `Storywriter` 形式は廃止し、`Writer` の mode 別 JSON 出力に統一。
- Researcher は現在 `text_search` のみを使用する。
