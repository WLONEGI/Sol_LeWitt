# 03. AI & ストリーミング統合

本フロントエンドは、Vercel AI SDK (v6) を中心に据え、バックエンドの LangGraph ワークフローが発行する多種多様なストリームイベントを処理します。

## 1. `useChat` フックの活用
メインの対話ロジックは `@ai-sdk/react` の `useChat` を通じて実装されています。

- **Transport**: `DefaultChatTransport` を使用し、`/api/chat/stream` エンドポイントと通信。
- **Metadata**: 実行時に `thread_id` や `product_type` (`slide`, `design`, `comic`) を body に含め、バックエンドでの状態復元を実現。
- **Data Stream Protocol**: Vercel AI SDK の Data Stream Protocol を採用し、テキストメッセージ (`0:`) とカスタムデータ (`d:`)、思考プロセス (`e:`) を混在させて受信。

## 2. 統合データストリーム・プロトコル (Unified Data Stream)

フロントエンドは、Vercel AI SDK の Data Stream Protocol を拡張し、バックエンドからの構造化イベント (`data-*`) をリアクティブに処理します。

### タイムライン正規化 (`useChatTimeline`)
`useChatTimeline` フックは、以下のソースを統合して単一のイベントタイムラインを構築します。
1. **チャットメッセージ**: テキストおよび推論（Reasoning）プロセス。
2. **構造化データ**: `data-visual-*`, `data-analyst-*` 等のカスタムイベント。
3. **プラン更新**: `data-plan_update` による現在ステップの可視化。

この正規化により、AI の思考過程、調査状況、生成中の画像、最終成果物が一つの時系列として一貫性を持って表示されます。

### 非破壊的な画像修正 (In-paint Versioning)
In-paint による画像の部分修正時は、以下のフローで「版」を管理します。
1. **修正リクエスト**: ユーザーがマスク範囲と指示を送信。
2. **新画像生成**: バックエンドが `unit_id` を維持したまま新しい URL を発行。
3. **既定の版管理**: `image_versions` 配列に新 URL を追加し、`current_version` を更新。
4. **UI での切り替え**: ユーザーはプレビューパネルの切り替えボタン (`ChevronLeft/Right`) を使用して、修正前後を自由に行き来できます。

これにより、AI の提案を比較検討しながら段階的に磨き上げることが可能です。

## 3. カスタムフック: `useChatTimeline`
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
