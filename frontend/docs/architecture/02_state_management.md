# 02. 状態管理 (State Management)

本アプリケーションでは **Zustand** を使用して、シンプルかつ強力な状態管理を実現しています。主に「対話セッション」と「成果物プレビュー」の2つのコンテキストをグローバルストアとして管理しています。

## 1. チャットストア (`useChatStore`)
対話スレッドの状態、サイドバーの開閉、および履歴のフェッチを担当します。

- **場所**: `src/features/chat/store/chat.ts`
- **主な状態**:
  - `currentThreadId`: 現在表示中のスレッドID。
  - `threads`: アクセス可能なスレッドのメタデータリスト。
  - `isSidebarOpen`: サイドバーの視認性状態。
- **主なアクション**:
  - `updateThreadTitle`: バックエンドから送信された `title_generated` イベントに基づき、スレッド一覧のタイトルを更新。
  - `fetchHistory`: API からスレッド履歴を同期。

## 2. アーティファクトストア (`useArtifactStore`)
AIエージェントが生成する成果物（スライド、画像、データ等）のプレビュー状態を管理します。

- **場所**: `src/features/preview/store/artifact.ts`
- **主な状態**:
  - `currentArtifact`: 現在右側パネルでプレビュー中の成果物オブジェクト。
  - `artifacts`: ID をキーとした生成済み成果物のキャッシュ。
  - `isPreviewOpen`: サイドパネルの表示状態。
- **主なアクション**:
  - `setArtifact`: プレビュー対象の切り替え。
  - `updateArtifactContent`: ストリーミング中または完了時に成果物の内容を更新。

## 3. コンポーネントとの連携
ストアは React Hooks として提供され、必要なコンポーネントでセレクトすることで、不要な再レンダリングを抑えつつ状態を共有します。

```tsx
const { currentThreadId, setCurrentThreadId } = useChatStore();
```

> [!TIP]
> 状態の永続化には `persist` ミドルウェアを使用しており、ブラウザのリロード後も直近のスレッド ID やサイドバーの状態が保持されます。
