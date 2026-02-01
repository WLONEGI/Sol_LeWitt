# Vercel AI SDK Data Stream Protocol (v1)

このドキュメントでは、Vercel AI SDK (主に v5.0 以降) で使用されている **Data Stream Protocol (UI Message Stream Protocol)** の詳細な仕様について記述します。このプロトコルは Server-Sent Events (SSE) をベースにしており、テキスト、推論（Reasoning）、ツール実行、カスタムデータなどを統合してストリーミングするための標準的な形式を提供します。

## 1. プロトコルの概要

### 通信形式
- **Transport**: HTTP Server-Sent Events (SSE)
- **MIME Type**: `text/event-stream`
- **データ構造**: 各イベントは `data: {JSON}\n\n` という形式で送信されます。

### 必須レスポンスヘッダー
クライアント（`useChat` 等）がこのプロトコルを正しく認識し、自動的にパースするためには、以下のヘッダーをレスポンスに含める必要があります。

```http
x-vercel-ai-ui-message-stream: v1
```

---

## 2. メッセージタイプ全量 (Message Chunks)

SDK のソースコード (`ai/src/ui-message-stream/ui-message-chunks.ts`) に基づく全メッセージタイプの一覧です。

### 2.1. テキスト (Text)
回答のメインコンテンツに関連するメッセージです。

| タイプ (`type`) | 説明 | パラメータ |
| :--- | :--- | :--- |
| `text-start` | テキスト生成の開始 | `id` (string), `providerMetadata`? |
| `text-delta` | テキストの増分データ | `id` (string), `delta` (string), `providerMetadata`? |
| `text-end` | テキスト生成の終了 | `id` (string), `providerMetadata`? |

### 2.2. 推論・思考 (Reasoning)
モデルの思考プロセス（Gemini 2.0 Thinking 等）に関連するメッセージです。

| タイプ (`type`) | 説明 | パラメータ |
| :--- | :--- | :--- |
| `reasoning-start` | 思考プロセスの開始 | `id` (string), `providerMetadata`? |
| `reasoning-delta` | 思考内容の増分データ | `id` (string), `delta` (string), `providerMetadata`? |
| `reasoning-end` | 思考プロセスの終了 | `id` (string), `providerMetadata`? |

### 2.3. ツール実行・入力 (Tool Input)
モデルがツールを呼び出そうとしている進行状況や引数に関連します。

| タイプ (`type`) | 説明 | パラメータ |
| :--- | :--- | :--- |
| `tool-input-start` | ツール入力の生成開始 | `toolCallId`, `toolName`, `providerExecuted`?, `providerMetadata`?, `dynamic`?, `title`? |
| `tool-input-delta` | ツール引数(JSON文字列)の増分 | `toolCallId`, `inputTextDelta` (string) |
| `tool-input-available` | 確定したツール入力データ | `toolCallId`, `toolName`, `input` (any), `providerExecuted`?, `providerMetadata`?, `dynamic`?, `title`? |
| `tool-input-error` | ツール入力生成時のエラー | `toolCallId`, `toolName`, `input`, `errorText`, `title`? |

### 2.4. ツール結果・承認 (Tool Output)
ツールの実行結果やユーザーへの承認要求に関連します。

| タイプ (`type`) | 説明 | パラメータ |
| :--- | :--- | :--- |
| `tool-output-available` | ツールの実行結果 | `toolCallId`, `output` (any), `providerExecuted`?, `dynamic`?, `preliminary`? |
| `tool-output-error` | ツール実行時のエラー | `toolCallId`, `errorText`, `providerExecuted`?, `dynamic`? |
| `tool-output-denied` | ユーザーによる承認拒否 | `toolCallId` |
| `tool-approval-request` | ユーザーへの承認要求 | `approvalId`, `toolCallId` |

### 2.5. 引用元・ファイル (Source / File)
生成されたコンテンツの根拠となるURLやファイル情報です。

| タイプ (`type`) | 説明 | パラメータ |
| :--- | :--- | :--- |
| `source-url` | 引用元URL | `sourceId`, `url`, `title`?, `providerMetadata`? |
| `source-document` | 引用ドキュメント | `sourceId`, `mediaType`, `title`, `filename`?, `providerMetadata`? |
| `file` | 参照または生成されたファイル | `url`, `mediaType`, `providerMetadata`? |

### 2.6. カスタムデータ (Custom Data)
アプリケーション固有のデータを送信するための拡張枠です。

| タイプ (`type`) | 説明 | パラメータ |
| :--- | :--- | :--- |
| `data-${string}` | `data-` で始まる任意のタイプ | `id`?, `data` (any), `transient`? |

> **注意**: カスタムデータとして認識されるためには、必ず `type` が `data-` という文字列で始まる必要があります（例: `data-ui_step_update`）。

### 2.7. ライフサイクル・制御 (Lifecycle)
メッセージやストリームの状態を制御します。

| タイプ (`type`) | 説明 | パラメータ |
| :--- | :--- | :--- |
| `start` | メッセージ全体の開始 | `messageId`?, `messageMetadata`? |
| `finish` | メッセージ全体の終了 | `finishReason`?, `messageMetadata`? |
| `start-step` | マルチステップの実行開始 | - |
| `finish-step` | マルチステップの実行終了 | - |
| `abort` | ストリームの切断 | `reason`? |
| `message-metadata` | メタデータの明示的な更新 | `messageMetadata` (any) |
| `error` | 致命的なエラー | `errorText` (string) |

---

## 3. 送信フォーマットの例

実際の SSE チャンクの送信イメージです。

```text
data: {"type":"start","messageId":"msg-123"}

data: {"type":"reasoning-start","id":"rs-1"}

data: {"type":"reasoning-delta","id":"rs-1","delta":"何らかの思考プロセス..."}

data: {"type":"reasoning-end","id":"rs-1"}

data: {"type":"text-start","id":"txt-1"}

data: {"type":"text-delta","id":"txt-1","delta":"こんにちは！"}

data: {"type":"text-end","id":"txt-1"}

data: {"type":"data-ui_step_update","data":{"status":"completed","label":"presenter"}}

data: {"type":"finish","finishReason":"stop"}
```

---

## 4. 実装時のポイント

1. **ID の一貫性**: `text-start`, `text-delta`, `text-end` で共通の `id` を使用することで、一つのテキストブロックとしてまとめられます。
2. **JSON形式**: 文字列のエスケープなどは `JSON.stringify` を通して正しく行う必要があります。
3. **改行**: 各 `data:` 行の末尾には 2 つの改行 (`\n\n`) が必要です。

# 参考情報
https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol#data-parts
