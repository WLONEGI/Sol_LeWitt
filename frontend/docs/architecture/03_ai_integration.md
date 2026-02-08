# 03. AI & ストリーミング統合

本フロントエンドは、Vercel AI SDK (v6) を中心に据え、バックエンドの LangGraph ワークフローが発行する多種多様なストリームイベントを処理します。

## 1. `useChat` フックの活用
メインの対話ロジックは `@ai-sdk/react` の `useChat` を通じて実装されています。

- **Transport**: `DefaultChatTransport` を使用し、`/api/chat/stream` エンドポイントと通信。
- **Metadata**: 実行時に `thread_id` を body に含め、バックエンドでの状態復元を実現。
- **Flexible Data**: `data` オブジェクトを通じて、通常のテキストメッセージ (`0:`) 以外のカスタムデータ (`d:`) をリアルタイムに取得。

## 2. カスタムフック: `useChatTimeline`
`useChat` の生データ（`data`, `messages`）を受け取り、UI に表示するための「タイムライン」へと変換するリアクティブなフックです。

- **役割**:
  - バックエンドからの `plan_update` イベントを解釈し、プランナーの計画を表示。
  - `artifact_open` / `artifact_ready` イベントを検知し、サイドパネルの表示状態やコンテンツを同期。
  - 処理中の「思考プロセス（Thinking）」や「進捗ログ」の差分更新を管理。

## 3. ストリーム・イベント・ハンドリング
`ChatInterface` 内で `data` の変更を監視し、特定のグローバルイベントを処理します。

```tsx
useEffect(() => {
    if (!data) return;
    const newItems = data.slice(processedDataCountRef.current);
    newItems.forEach((item) => {
        if (item.type === 'title_generated') {
            updateThreadTitle(item.threadId, item.title);
        }
    });
    processedDataCountRef.current = data.length;
}, [data]);
```

## 4. UI フィードバック (UX)
- **Skeleton State**: `artifact_open` を受信すると、実際のコンテンツが届く前にサイドパネルを「読み込み中」スタイルで開き、UX を向上させます。
- **Bulk Swap**: `artifact_ready` を受信すると、スケルトンから実際の実データ（Markdown, Image等）へフェードインで切り替えます。

> [!IMPORTANT]
> ストリーミングデータは NDJSON 形式で送信されるため、`src/app/api/chat/route.ts` 側のパーサで不正行を防御的に処理し、ストリーム全体の継続性を担保します。
