# 03. ストリーミング・プロトコル (SSE)

本システムは `POST /api/chat/stream_events` で LangGraph のイベントストリームを配信し、フロント BFF (`frontend/src/app/api/chat/route.ts`) が UI 向け `data-*` パートへ変換します。

## 1. 基本フロー
- バックエンド SSE は `data: { ...event payload... }\n\n` 形式。
- 主なイベントは `on_chat_model_stream`（トークン）と `on_custom_event`（構造化データ）。
- フロントは `on_custom_event.name` を解釈し、`data-plan_update` などの UI パートへ正規化。

## 2. 主要カスタムイベント（バックエンド発行）

| `on_custom_event.name` | 配信元ノード | 用途 |
| :--- | :--- | :--- |
| `plan_update` | planner / supervisor | 実行プラン更新（全量）。 |
| `writer-output` | writer | Writer成果物（JSON）通知。 |
| `data-visual-plan` | visualizer | 画像生成計画。 |
| `data-visual-prompt` | visualizer | 各画像の生成プロンプト。 |
| `data-visual-image` | visualizer | 生成画像 URL とメタ情報。 |
| `data-visual-pdf` | visualizer | 統合 PDF URL。 |
| `data-research-report` | researcher | 調査レポート（本文・出典URL）。 |
| `data-analyst-start` / `data-analyst-output` / `data-analyst-complete` | data_analyst | 実行開始・出力・完了。 |
| `title_generated` | coordinator | スレッドタイトル候補。 |

## 3. フロント変換ルール（要点）
- `plan_update` → `data-plan_update`
- `writer-output` → `data-writer-output`
- `name` が `data-` で始まるイベントは原則そのまま UI へ転送
- `on_chat_model_stream` のテキスト/推論は `text-*` / `reasoning-*` に分離

## 4. スナップショット再生
`GET /api/threads/{thread_id}/snapshot` は以下を返し、画面再読込時に同じ状態を復元します。
- `messages`
- `plan`
- `artifacts`
- `ui_events`（`data-*` イベント列）

> [!CAUTION]
> 旧 `Storywriter` / `artifact_open` / `artifact_ready` 前提の実装は廃止済みです。現在は `writer` と `data-*` ベースのイベント契約を使用してください。
