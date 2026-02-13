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
  "selected_image_inputs": [],
  "attachments": [
    {
      "id": "att_01",
      "filename": "reference.png",
      "mime_type": "image/png",
      "size_bytes": 123456,
      "url": "https://storage.googleapis.com/...",
      "kind": "image"
    }
  ]
}
```

### Response
- **Headers**: `x-vercel-ai-ui-message-stream: v1`
- **Content**: Vercel AI SDK Data Stream Protocol (Prefix形式)
- **Behavior**:
  - `attachments` に `kind: "pptx"` が含まれる場合、バックエンドでPPTXを解析し `pptx_context` を内部Stateに注入
  - 解析結果は Data Analyst ノードのコンテキストでのみ利用される

## 2. 履歴管理

### スレッド一覧の取得
- **URL**: `/api/history`
- **Method**: `GET`
- **Auth**: 必須
- **Response**: `ThreadInfo[]`
  - ログインユーザーの `owner_uid` に紐づくスレッドのみ返却

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

## 4. ファイルアップロード
Gemini 3 系入力フォーマットに合わせて、以下のファイルをアップロードし添付メタデータを返します。

- **URL**: `/api/files/upload`
- **Method**: `POST`
- **Content-Type**: `multipart/form-data`
- **Auth**: `Authorization: Bearer <Firebase ID Token>` 必須
- **Allowed**:
  - 画像: `png/jpg/webp`
  - プレゼン: `pptx`
  - 文書: `pdf`
  - テキスト系: `csv`, `txt`, `md`, `json`
- **Excluded**:
  - `xlsx/xls`（Gemini 3 入力フォーマット対象外として除外）
- **Form Fields**:
  - `files`: 1件以上（最大5件）
  - `thread_id`: 任意（保存先フォルダ識別）
- **Response**:
```json
{
  "attachments": [
    {
      "id": "8f3a...",
      "filename": "sample.pptx",
      "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      "size_bytes": 456789,
      "url": "https://storage.googleapis.com/...",
      "kind": "pptx"
    }
  ]
}
```

## 5. 画像 In-painting
Visualizer の個別画像編集向け。元画像・マスク画像・修正指示の3入力で再生成します。

### 単一画像
- **URL**: `/api/image/{image_id}/inpaint`
- **Method**: `POST`
- **Content-Type**: `application/json`
- **Auth**: 必須

### スライドデッキ内画像
- **URL**: `/api/slide-deck/{deck_id}/slides/{slide_number}/inpaint`
- **Method**: `POST`
- **Content-Type**: `application/json`
- **Auth**: 必須

### Request Body
```json
{
  "image_url": "https://storage.googleapis.com/.../source.png",
  "mask_image_url": "data:image/png;base64,...",
  "prompt": "白く塗った領域だけを、夕方の空に変更",
  "reference_images": [
    {
      "image_url": "https://storage.googleapis.com/.../ref-style.png",
      "caption": "夕方の色味"
    }
  ]
}
```

### Notes
- `mask_image_url` は `data URL`, `https URL`, `gs://` を受け付けます。
- マスクは **白=編集対象 / 黒=保持** として扱います。
- `reference_images` は任意です（最大3枚）。スタイル/モチーフの補助参照として扱われます。
