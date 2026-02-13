# Visualizer JSONフィールド棚卸

最終更新: 2026-02-13

対象: `VisualizerOutput` の各行（`slides` / `design_pages` / `comic_pages` / `characters`）に含まれるフィールド。

## 現役フィールド（フロント表示 or 実行制御で使用）

| フィールド | 用途 | 主な参照先 |
| --- | --- | --- |
| `generated_image_url` | 生成画像URL（表示本体） | `backend/src/app/app.py`, `frontend/src/features/chat/hooks/use-chat-timeline.ts` |
| `compiled_prompt` | 画像生成へ渡した最終プロンプト | `backend/src/app/app.py`, `frontend/src/features/preview/viewers/slide-deck-viewer.tsx` |
| `structured_prompt` | 構造化プロンプト（デバッグ/UI補助） | `backend/src/app/app.py`, `frontend/src/features/chat/hooks/use-chat-timeline.ts` |
| `layout_type` | レイアウト分類 | `frontend/src/features/chat/hooks/use-chat-timeline.ts` |
| `rationale` | 生成意図の説明 | `frontend/src/features/chat/hooks/use-chat-timeline.ts` |
| `selected_inputs` | 入力根拠のトレース | `frontend/src/features/chat/hooks/use-chat-timeline.ts` |
| `status` | completed/failed 等の状態 | `backend/src/app/app.py`, `frontend/src/features/chat/components/chat-interface.tsx` |
| `title` | ページ/スライド名 | `backend/src/app/app.py` |

## バックエンド専用（フロント表示には直接使わない）

| フィールド | 用途 | 主な参照先 |
| --- | --- | --- |
| `thought_signature` | Deep Edit 再生成の一貫性維持 | `backend/src/core/workflow/nodes/visualizer.py` |

## 互換フィールド（新規出力では非推奨）

| フィールド | 現状 | 主な参照先 |
| --- | --- | --- |
| `image_generation_prompt` | レガシー plain-text プロンプト。現在は `structured_prompt` がある場合は保存しない。comic 機械整形や旧成果物復元のフォールバック用途のみ。 | `backend/src/core/workflow/nodes/visualizer.py`, `backend/src/app/app.py` |
| `prompt_text` | イベント層/旧形式の互換名。保存JSONの正規キーは `compiled_prompt`。 | `backend/src/app/app.py`, `frontend/src/features/chat/hooks/use-chat-timeline.ts` |

## `structured_prompt` 内の廃止項目（slide/design）

| フィールド | 方針 |
| --- | --- |
| `text_policy` | slide/design では廃止。出力しない。 |
| `negative_constraints` | slide/design では廃止。出力しない。 |

## 今回の方針

- `document_layout_render` も `structured_prompt` を標準入力に統一。
- `image_generation_prompt` は「必要時のみ出力」に縮退（空キーを出さない）。
- `text_policy` / `negative_constraints` は slide/design で出力しない（Writerにも生成させない）。
- 互換読み取りは維持（既存セッションや旧アーティファクトを壊さない）。
