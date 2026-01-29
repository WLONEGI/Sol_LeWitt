1. アーキテクチャ概要
本システムは、LangGraphの複雑なエージェントワークフローを、Vercel AI SDKの Data Stream Protocol (v1) を用いてフロントエンドに配信します。

設計の核となる3つの原則
Multi-Channel Routing (多層ルーティング):

会話（Text）はチャット欄、成果物（Artifact）はサイドパネル、制御情報（Plan）はヘッダーへと、データの種類に応じて表示領域を厳密に分離します。

Bulk Artifact Transfer (成果物の一括転送):

成果物（ドキュメント、画像、コード）はストリーミング（1文字ずつの表示）を行わず、サーバー側で生成完了を待ってから一括送信します。これによりペイロードを削減し、レンダリング負荷を下げます。

Pseudo-Tool States (擬似ツール状態):

バックグラウンドで動くLangGraphノード（Worker）の開始をフロントエンドに通知し、UI上では「ツールが実行中」であるかのようなインジケータ（Skeleton/Spinner）を表示して、ユーザーの体感待ち時間を最適化します。

2. プロトコル定義 (JSON Schema)
サーバーからクライアントへ 2: Data Part として送信されるJSONイベントの厳密な定義です。

TypeScript

/**
 * Stream Event Definition (Discriminated Union)
 */
type StreamEvent =
  // -------------------------------------------------------
  // 1. Control & Plan (Supervisor)
  // -------------------------------------------------------
  | {
      type: "plan_update";
      plan: {
        tasks: Array<{
          id: string;
          title: string;
          status: "pending" | "in_progress" | "complete";
        }>;
      };
    }

  // -------------------------------------------------------
  // 2. Artifact Lifecycle (Workers: Storywriter, Visualizer, Analyst)
  // -------------------------------------------------------
  // [開始通知] フロントエンドで「ローディング/ツール実行中」UIを表示するトリガー
  | {
      type: "artifact_open";
      artifactId: string; // RunID等の一意なID
      kind: "document" | "image" | "code_analysis";
      title: string;      // UI表示用タイトル (例: "スライド構成案を作成中...")
    }
  // [完了通知] データの実体を一括送信 (Bulk Transfer)
  | {
      type: "artifact_ready";
      artifactId: string;
      payload: ArtifactPayload; // 下記定義
    }

  // -------------------------------------------------------
  // 3. Glass Box Logs (Researcher)
  // -------------------------------------------------------
  | {
      type: "log_update";
      id: string;
      parentId?: string;
      status: "running" | "complete";
      message: string;
    }

  // -------------------------------------------------------
  // 4. System & Error (Global)
  // -------------------------------------------------------
  // [提案1対応] エラーハンドリング
  | {
      type: "error";
      code: string;
      message: string;
      details?: any;
    }
  // [アノテーション対応] ターンの最後に送信し、メッセージとArtifactを紐付ける
  | {
      type: "message_metadata";
      relatedArtifactIds: string[]; // このターンで生成・更新されたArtifact ID一覧
    };

/**
 * Payload Definitions
 */
type ArtifactPayload =
  | { kind: "document"; content: string; format: "markdown" } // 完成テキスト
  | { kind: "image"; url: string; prompt: string }            // 画像URL
  | { kind: "code_analysis"; code: string; result: any };     // コードと実行結果
3. ノード別 挙動仕様 (実装詳細)

各ノードの状態遷移と、それに対応するプロトコルイベントのマッピングです。`src/service/workflow_service.py` に実装されています。

### 3.1. Planner (計画策定)
- **Role**: ユーザーの要望を分析し、タスクプランを作成する。
- **Trigger**: `on_chain_end`
- **Condition**: ノード名が `planner` かつ出力に `plan` が含まれる場合。
- **Event**: `d: {"type": "plan_update", "plan": [...]}`
  - これによりフロントエンドのヘッダー部分にタスクリストが即座に表示されます。

### 3.2. Storywriter (ドキュメント作成) / Visualizer (画像生成) / Data Analyst
- **Role**: 各専門領域の成果物を作成するWorker。
- **Start Trigger**: `on_chain_start`
- **Start Event**: `d: {"type": "artifact_open", "artifactId": "...", "kind": "...", "title": "..."}`
  - **Storywriter**: `kind="document"`, Title="ドキュメントを作成中..."
  - **Visualizer**: `kind="image"`, Title="画像を生成中..."
  - **Data Analyst**: `kind="code_analysis"`, Title="コードを実行中..."
  - これにより、生成完了を待たずにサイドパネルが開き、スケルトンローダーが表示されます。

- **End Trigger**: `on_chain_end`
- **End Event**: `d: {"type": "artifact_ready", "artifactId": "...", "payload": {...}}`
  - **Storywriter**: `payload={kind: "document", content: "Markdown...", format: "markdown"}`
  - **Visualizer**: `payload={kind: "image", url: "http...", prompt: "..."}`
  - **Data Analyst**: `payload={kind: "code_analysis", code: "...", result: "..."}`
  - これにより、サイドパネルのコンテンツが実データに置換されます。

### 3.3. Supervisor (監督)
- **Role**: 次のステップを決定するオーケストレーター。
- **Behavior**: ストリームイベントは発行しません（内部ルーティングのみ）。

### 3.4. Reasoning Models (思考プロセス)
- **Role**: Gemini 2.0 Flash Thinking 等の推論モデル。
- **Stream**: `on_chat_model_stream`
- **Event**: `d: {"type": "reasoning_delta", "delta": "..."}`
  - モデルが思考トークンを出力した場合、通常のテキスト (`0:`) ではなく推論データ (`d:`) として送信します。

### 3.5. Researcher (調査)
- **Role**: 外部検索と情報の集約。
- **Stream**: `progress` Custom Event
- **Event**: `d: {"type": "progress", "content": "..."}`
  - 現状は簡易的な進捗ログとして送信されます。（Glass Box Logとしての構造化は今後の課題）

4. サーバーサイド実装 (Route Handler)
Next.js App Routerでの実装例です。エラーハンドリングとアノテーション付与ロジックを含みます。

TypeScript

import { createDataStreamResponse, DataStream } from 'ai';

export async function POST(req: Request) {
  const { messages } = await req.json();

  return createDataStreamResponse({
    execute: async (dataStream) => {
      // このターンで生成されたArtifact IDを保持するセット
      const createdArtifactIds = new Set<string>();

      try {
        // LangGraphのイベントストリームを開始
        const eventStream = app.streamEvents(
          { messages },
          { version: "v1" }
        );

        for await (const event of eventStream) {
          const tags = event.tags || [];
          const eventType = event.event;
          const runId = event.run_id;

          // --- 1. Coordinator (Text Stream) ---
          if (tags.includes("coordinator") && eventType === "on_chat_model_stream") {
            dataStream.writeText(event.data.chunk.content);
            continue;
          }

          // --- 2. Supervisor (Plan Update) ---
          if (tags.includes("supervisor") && eventType === "on_chain_end") {
            if (event.data.output?.plan) {
              dataStream.writeData({
                type: "plan_update",
                plan: event.data.output.plan
              });
            }
            continue;
          }

          // --- 3. Artifact Workers (Bulk Transfer) ---
          if (tags.some(t => ["storywriter", "visualizer", "data_analyst"].includes(t))) {
            let kind = "document";
            if (tags.includes("visualizer")) kind = "image";
            if (tags.includes("data_analyst")) kind = "code_analysis";

            // [A] 開始通知 (Artifact Open) -> 擬似ツールUI起動
            if (eventType === "on_chain_start") {
              createdArtifactIds.add(runId); // IDを記録
              dataStream.writeData({
                type: "artifact_open",
                artifactId: runId,
                kind,
                title: getTitleForNode(kind) // "執筆中...", "描画中..." 等を返すヘルパー
              });
            }

            // [B] 完了通知 (Artifact Ready) -> データ一括送信
            if (eventType === "on_chain_end") {
              const payload = extractPayload(kind, event.data.output); // 出力整形ヘルパー
              if (payload) {
                dataStream.writeData({
                  type: "artifact_ready",
                  artifactId: runId,
                  payload
                });
              }
            }
            continue;
          }

          // --- 4. Researcher (Logs) ---
          if (tags.includes("researcher")) {
            dataStream.writeData({
              type: "log_update",
              id: runId,
              parentId: event.parent_ids?.[0],
              status: "running",
              message: `${event.name}: 処理中`
            });
          }
        }

        // --- 5. Finalize: Message Annotation ---
        // 処理正常終了時、生成されたArtifact情報をメタデータとして送信
        if (createdArtifactIds.size > 0) {
          dataStream.writeData({
            type: "message_metadata",
            relatedArtifactIds: Array.from(createdArtifactIds)
          });
        }

      } catch (error) {
        // [提案1] エラーハンドリング
        console.error("Agent Execution Error:", error);
        dataStream.writeData({
          type: "error",
          code: "AGENT_EXECUTION_FAILED",
          message: "処理中に予期せぬエラーが発生しました。",
          details: String(error)
        });
        // 必要に応じて throw してストリームを閉じる
      }
    },
    
    // SDKレベルのエラー処理
    onError: (error) => {
      return error instanceof Error ? error.message : "Unknown error";
    }
  });
}

// ヘルパー関数 (簡易実装)
function extractPayload(kind: string, output: any) {
  if (!output) return null;
  if (kind === "document") return { kind, content: output.text, format: "markdown" };
  if (kind === "image") return { kind, url: output.url, prompt: output.prompt };
  if (kind === "code_analysis") return { kind, code: output.code, result: output.result };
  return null;
}
5. フロントエンド実装戦略 (UX設計)
5.1. アノテーションによる紐付け (Annotation Linking)
Coordinatorのメッセージ（チャットバブル）内に、生成されたアーティファクトへの参照リンクを表示します。

データフロー:

useChat でメッセージを受信。

data 配列に含まれる message_metadata イベントを探す。

メッセージコンポーネントのPropsとして relatedArtifactIds を渡す。

表示:

チャットバブルの下部に 「📎 作成された資料: スライド構成案」 のようなチップを表示。

クリックすると、サイドパネルの該当Artifactが開く。

5.2. 擬似ツールUI (Pseudo-Tool State)
artifact_open イベントを活用し、非同期処理の待ち時間をリッチな体験に変えます。

状態管理 (React State):

TypeScript

type ArtifactState = {
  status: "loading" | "ready"; // loading = 擬似ツール実行中
  kind: string;
  title: string;
  data: any | null; // readyになるまでnull
};
UIレンダリング分岐:

status === "loading" の場合:

Document: 文章のラインが波打つスケルトンローダーを表示。

Image: "Generating..." のスピナーと、ぼかしたプレースホルダーを表示。

Code: "Running Analysis..." のターミナル風ローダーを表示。

status === "ready" の場合:

実際のコンテンツ（Markdownビュワー、画像、グラフ）にフェードインで切り替える。