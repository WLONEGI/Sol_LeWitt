# API エンドポイント

## 1. チャット・ストリーム
LangGraph ワークフローを実行し、SSE ストリームを返します。

- **URL**: `/api/chat/stream`
- **Method**: `POST`
- **Content-Type**: `application/json`

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
- **Response**: `ThreadInfo[]`

### 特定スレッドのメッセージ取得
- **URL**: `/api/threads/{thread_id}/messages`
- **Method**: `GET`
- **Response**: `Message[]` (LangChain message objects)

## 3. テンプレート解析
PPTX ファイルから `DesignContext` を抽出します。

- **URL**: `/api/template/analyze`
- **Method**: `POST`
- **Content-Type**: `multipart/form-data`
- **Response**: `DesignContext`
