# 03. ストリーミング・プロトコル (SSE)

本システムは `POST /api/chat/stream_events` で LangGraph のイベントストリームを配信し、フロント BFF (`frontend/src/app/api/chat/route.ts`) が UI 向け `data-*` パートへ変換します。

## 1. 基本フロー
- バックエンド SSE は `data: { ...event payload... }\n\n` 形式。
- 主なイベントは `on_chat_model_stream`（トークン）と `on_custom_event`（構造化データ）。
- フロントは `on_custom_event.name` を解釈し、`data-plan_update` などの UI パートへ正規化。

## 2. 主要カスタムイベント（バックエンド発行）

| `on_custom_event.name` | 配信元ノード | 用途 |
| :--- | :--- | :--- |
| `data-plan_update` | planner / supervisor | 実行プランの全量更新（配列）。 |
| `data-writer-output` | writer | Writer成果物（JSON）通知。`artifact_type`: `report`, `outline`, `writer_character_sheet` 等。 |
| `data-visual-plan` | visualizer | 画像生成計画の開始。 |
| `data-visual-prompt` | visualizer | 各画像の生成プロンプト。`slide_number`, `prompt_text` 等を含む。 |
| `data-visual-image` | visualizer | 生成直後の画像 URL。`unit_id` を含む。 |
| `data-visual-pdf` | visualizer | 全スライドを統合した PDF URL。これを受信するとプレビュー全体が完了扱いとなる。 |
| `data-research-report` | researcher | 調査レポート。`report` (テキスト) と `sources` (URL配列) を含む。 |
| `data-analyst-output` | data_analyst | Python コード、実行ログ、成果物 URL（CSV, PNG等）の随時配信。 |

### 2.1 Visualizer モードの推論
フロントエンドは受信したペイロードから `mode` を推論し、表示コンポーネントを切り替えます。
- **`character_sheet_render`**: `artifact_type` が `writer_character_sheet` またはプロンプト内容から推論。
- **`comic_page_render`**: `product_type` が `comic` または画像が `panels` 構造を持つ場合に推論。
- **`slide_render`**: 上記以外（標準）。

---

## 3. ペイロード仕様 (Schema)

### `data-visual-image` の例
```json
{
  "artifact_id": "visual_deck_123",
  "slide_number": 1,
  "image_url": "https://storage.../image.png",
  "unit_id": "image_unit_abc",
  "status": "completed",
  "metadata": {
    "aspect_ratio": "16:9"
  }
}
```

### `data-analyst-output` の例
```json
{
  "artifact_id": "data_analyst_456",
  "title": "Sales Data Analysis",
  "code": "print('Hello')",
  "logs": "Hello\n",
  "files": [
    { "url": "...", "filename": "chart.png", "kind": "image" }
  ]
}
```

> [!CAUTION]
> 旧 `Storywriter` / `artifact_open` / `artifact_ready` 前提の実装は廃止済みです。現在は `writer` と `data-*` ベースのイベント契約を使用してください。
