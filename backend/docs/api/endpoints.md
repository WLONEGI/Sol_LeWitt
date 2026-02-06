# API エンドポイント

## 1. チャット・ストリーム
LangGraph ワークフローを実行し、SSE ストリームを返します。

- **URL**: `/api/chat/stream`
- **Method**: `POST`
- **Content-Type**: `application/json`
- **Auth**: `Authorization: Bearer <Firebase ID Token>` 必須

### Request Body
```json
{
  "messages": [
    { "role": "user", "content": "スライドを作って", "parts": [] }
  ],
  "thread_id": "uuid-v4",
  "pptx_template_base64": "..."
}
```

### Response
- **Headers**: `x-vercel-ai-ui-message-stream: v1`
- **Content**: Vercel AI SDK Data Stream Protocol (Prefix形式)

## 2. 履歴管理

### スレッド一覧の取得
- **URL**: `/api/history`
- **Method**: `GET`
- **Auth**: 必須
- **Response**: `ThreadInfo[]`
  - ログインユーザーの `owner_uid` に紐づくスレッドのみ返却

### 特定スレッドのメッセージ取得
- **URL**: `/api/threads/{thread_id}/messages`
- **Method**: `GET`
- **Auth**: 必須
- **Response**: `Message[]` (UIMessage 互換形式)
  - 対象 `thread_id` の所有者がログインユーザーである場合のみ取得可能

### 特定スレッドのUIスナップショット取得
- **URL**: `/api/threads/{thread_id}/snapshot`
- **Method**: `GET`
- **Auth**: 必須
- **Response**:
  - `messages`: `UIMessage[]`
  - `plan`: 正規化済み実行プラン
  - `artifacts`: フロント描画用 Artifact マップ
  - `ui_events`: `data-*` 再構築イベント（ロード時復元用）
  - 対象 `thread_id` の所有者がログインユーザーである場合のみ取得可能

## 3. テンプレート解析
PPTX ファイルから `DesignContext` を抽出します。

- **URL**: `/api/template/analyze`
- **Method**: `POST`
- **Content-Type**: `multipart/form-data`
- **Response**: `DesignContext`
