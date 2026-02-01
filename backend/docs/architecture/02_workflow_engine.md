# 02. LangGraph ワークフロー・エンジン

本システムの中核である LangGraph によるエージェント・オーケストレーションの詳細について記述します。

## 1. ノード定義と責務

グラフは以下のノードで構成され、各ノードは特定の `tags` を持ちます。これらのタグは SSE ストリーミングのルーティングに使用されます。

| ノード名 | タグ | 責務 |
| :--- | :--- | :--- |
| **Coordinator** | `coordinator` | ユーザー入力の解析、対話の継続、またはプランナーへのハンドオフ。 |
| **Planner** | `planner` | タスク分解と実行プラン（`plan`）の作成。 |
| **Supervisor** | `supervisor` | プランの進捗監視と Worker への動的ルーティング。 |
| **Storywriter** | `storywriter` | スライドのアウトライン、セクション、本文（Markdown）の執筆。 |
| **Visualizer** | `visualizer` | 画像生成プロンプトの設計と `google-genai` SDK による画像生成。 |
| **Data Analyst** | `data_analyst` | Python コードの生成・実行によるデータ分析と可視化案の作成。 |
| **Researcher** | `researcher` | **Subgraph** として実装。Google Search (Native Grounding) による調査。 |

## 2. 状態管理（State Schema）

システムの状態は `MessagesState` を拡張した `State` クラスで管理されます。

```python
class TaskStep(TypedDict):
    id: int
    role: str                       # 担当 Worker
    instruction: str                # 指示内容
    description: str                # ステップ概要
    status: Literal["pending", "in_progress", "complete"]
    result_summary: str | None      # 実行結果の要約

class State(MessagesState):
    plan: list[TaskStep]            # 実行計画
    artifacts: dict[str, Any]       # 生成された成果物（JSON/URL等）
    design_context: DesignContext   # テンプレート（PPTX）から解析されたデザイン情報
```

## 3. オーケストレーション・ロジック

### 3.1 計画駆動型ルーティング
`Supervisor` は、`state.plan` 内のステップを順次スキャンします。
1.  `pending` 状態のステップを見つけ、その `role` に基づいて Worker ノードへ分岐します。
2.  Worker から戻ると、`in_progress` だったステップを `complete` に更新します。
3.  すべてのステップが `complete` になるまでループを継続します。

### 3.2 Subgraph (Researcher)
調査タスクは `Researcher` サブグラフで処理されます。
- `Manager` ノードが調査リクエストを複数のサブタスクに分解。
- `Send` オブジェクトを使用して複数の `Worker` ノードを並列起動（Fan-out）。
- 全結果を `Manager` が集約し、メイングラフに返却（Reduce）。

## 4. 認証と LLM ファクトリ
`src/infrastructure/llm/llm.py` で定義されるファクトリにより、用途に応じたモデルが選択されます。

- **Reasoning**: `gemini-2.0-flash-thinking-exp-1219` (Planner, Researcher)
- **Basic**: `gemini-1.5-flash-002` (Coordinator, Storywriter)
- **Vision**: `gemini-3-pro-image-preview` (Visualizer)

> [!NOTE]
> すべてのモデルは `project` パラメータを指定することで、ADC (Application Default Credentials) を使用して Vertex AI バックエンドに接続されます。
