# 02. LangGraph ワークフロー・エンジン

本システムの LangGraph 実装は、**Planner 集約型の再計画** を基盤にしています。  
命名と入出力は canonical 形式（`capability` / `instruction` / `writer`）に統一されています。

## 1. ノード定義と責務

| ノード名 | ラン名/識別 | 責務 |
| :--- | :--- | :--- |
| **Coordinator** | `coordinator` | 会話継続か制作開始かを判定し、制作時は `planner` へ。 |
| **Planner** | `planner` | canonical な実行計画を JSON で生成。 |
| **Supervisor** | `supervisor` | `plan` の `pending/in_progress` を管理し、Workerへルーティング。 |
| **Writer** | `writer` | 構成・脚本・設定などの文章系成果物を JSON 生成。 |
| **Researcher** | `researcher` | サブグラフで調査タスクを分解・実行。調査レポートを返却。 |
| **Visualizer** | `visualizer` | 画像生成計画と画像生成実行。 |
| **Data Analyst** | `data_analyst` | Python実行やパッケージングなどの後処理。 |
| **Retry/Alt Mode** | `retry_or_alt_mode` | blocked ステップの再試行・代替タスク追加。 |

## 2. 状態管理（State Schema）

`State` は `MessagesState` を拡張し、主要フィールドは以下です。

```python
class TaskStep(TypedDict, total=False):
    id: int
    capability: Literal["writer", "researcher", "visualizer", "data_analyst"]
    mode: str
    instruction: str
    title: str
    description: str
    inputs: list[str]
    outputs: list[str]
    preconditions: list[str]
    validation: list[str]
    success_criteria: list[str]
    fallback: list[str]
    depends_on: list[int]
    target_scope: TargetScope
    status: Literal["pending", "in_progress", "completed", "blocked"]
    result_summary: str | None

class State(MessagesState):
    plan: list[TaskStep]
    artifacts: dict[str, Any]
    selected_image_inputs: list[dict[str, Any]]
    target_scope: TargetScope
```

## 3. オーケストレーション・ロジック

### 3.1 Planner 集約リプラン
1. 初回は `planner` が `plan` を作成。  
2. 追加指示・中断後の再開時も `planner` が既存 `plan` を参照して再計画。  
3. `supervisor` が最新 `plan` を実行再開。

### 3.2 ルーティング単位
- Worker 選択は `step.capability` のみを使用。  
- `role/objective` などの旧互換キーは使用しない。

### 3.3 Researcher Subgraph
- `research_manager` がタスク分解。  
- `research_worker` が順次実行し、調査レポート（本文・出典）を返却。

## 4. ストリーミング契約（要点）

- Plan: `data-plan_update`
- Writer成果物: `data-writer-output`
- Research成果物: `data-research-report`
- Visualizer成果物: `data-visual-*`
- Data Analyst成果物: `data-analyst-*`

フロントは `data-*` パートを UI の単一ソースとして扱います。
