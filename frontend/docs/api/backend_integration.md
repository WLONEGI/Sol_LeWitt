# API & バックエンド統合

フロントエンドがバックエンドと通信するための主要なインターフェースとデータ構造について記述します。

## 1. チャット・ストリーム API
- **Endpoint**: `/api/chat/stream`
- **Method**: `POST`
- **Frontend Handler**: `src/features/chat/chat-interface.tsx` 内の `useChat`

### リクエスト・パラメータ (`extraData`)
`useChat` の `append` または `sendMessage` 呼び出し時に渡されるデータです。

```ts
{
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
  ],
  "aspect_ratio": "16:9"
}
```

## 1.1 添付アップロード API（BFF）
- **Endpoint**: `/api/uploads`
- **Method**: `POST`
- **Content-Type**: `multipart/form-data`
- **Forward先**: backend `/api/files/upload`
- **Auth**: `Authorization: Bearer <Firebase ID Token>` 必須
- **Allowed**: `png/jpg/webp`, `pptx`, `pdf`, `csv`, `txt`, `md`, `json`
- **Excluded**: `xlsx/xls`（Gemini 3 入力フォーマット対象外）

> `attachments` に `kind: "pptx"` を含めると、バックエンド側でPPTX解析が行われ、
> 生成された `pptx_context` は Data Analyst ノードで利用されます。

## 1.2 In-painting API（Visualizer編集）
- **Endpoint**:
  - `/api/image/{imageId}/inpaint`
  - `/api/slide-deck/{deckId}/slides/{slideNumber}/inpaint`
- **Method**: `POST`
- **Usage**:
  - `src/features/preview/viewers/slide-viewer.tsx`
  - `src/features/preview/viewers/slide-deck-viewer.tsx`
- **Request Body**:
```ts
{
  image_url: string;      // 元画像
  mask_image_url: string; // data URL / https / gs://
  prompt: string;         // 修正指示
  reference_images?: Array<{
    image_url: string;
    caption?: string;
  }>; // 任意の参照画像（最大3枚）
}
```

## 2. 履歴・管理 API

### セッション履歴の取得
- **Endpoint**: `/api/history`
- **Usage**: `src/features/chat/store/chat.ts` の `fetchHistory`
- **Auth**: `Authorization: Bearer <Firebase ID Token>` 必須
- **Response**: `Array<{ id: string, title: string, updatedAt: string }>`

### 特定スレッドの復元スナップショット読込
- **Endpoint**: `/api/threads/{threadId}/snapshot`
- **Usage**: `src/features/chat/components/chat-interface.tsx` の初期ロード
- **Auth**: 必須
- **Response**:
  - `messages`: `UIMessage[]`
  - `plan`: 実行プラン
  - `artifacts`: `Record<string, Artifact>`
  - `ui_events`: タイムライン再現用 `data-*` イベント列

## 3. 型定義 (TypeScript)
フロントエンドでのデータ安全性は `src/features/chat/types/` および `src/features/preview/store/artifact.ts` で定義されたインターフェースにより担保されています。

```ts
export interface Artifact {
    id: string;
    type: string;
    title: string;
    content: any;
    version: number;
    status?: string;
}
```

## 4. エラーハンドリング
- **Network Error**: `useChat` の `onError` プロパティでグローバルに捕捉され、コンソールおよび UI (Toast等) へ出力されます。
- **Protocol Error**: `src/app/api/chat/route.ts` のストリームパーサで NDJSON 行を防御的に処理し、不正行があっても継続可能にします。
