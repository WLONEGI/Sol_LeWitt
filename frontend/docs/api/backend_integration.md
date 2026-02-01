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
  "pptx_template_base64": "..." // テンプレート解析が必要な場合に送信
}
```

## 2. 履歴・管理 API

### セッション履歴の取得
- **Endpoint**: `/api/history`
- **Usage**: `src/features/chat/store/chat.ts` の `fetchHistory`
- **Response**: `Array<{ id: string, title: string, updatedAt: string }>`

### 特定スレッドのメッセージ読込
- **Endpoint**: `/api/threads/{threadId}/messages`
- **Usage**: `src/features/chat/chat-interface.tsx` 内の `useEffect`
- **Response**: `Message[]` (LangChain 互換形式)

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
- **Protocol Error**: `stream-transformer.ts` で NDJSON のパースエラーを穏やかに処理し、ストリーム全体が停止するのを防ぎます。
