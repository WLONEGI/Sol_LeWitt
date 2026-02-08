# 02. LangGraph ワークフロー・エンジン

本システムの LangGraph 実装は、**Frozen Plan + Patch** を基盤にしています。  
命名と入出力は canonical 形式（`capability` / `instruction` / `writer`）に統一されています。

## 1. ノード定義と責務

| ノード名 | ラン名/識別 | 責務 |
| :--- | :--- | :--- |
| **Coordinator** | `coordinator` | 会話継続か制作開始かを判定し、制作時は `plan_manager` へ。 |
| **Plan Manager** | `plan_manager` | 初回計画生成（`planner`）か、修正系（`patch_planner` / `patch_gate`）かを分岐。 |
| **Planner** | `planner` | canonical な実行計画を JSON で生成。 |
| **Patch Planner** | `patch_planner` | 追加指示を `PlanPatchOp` に変換。 |
| **Patch Gate** | `patch_gate` | パッチ適用（型崩れのみ hard reject / それ以外 warning）。 |
| **Supervisor** | `supervisor` | `plan` の `pending/in_progress` を管理し、Workerへルーティング。 |
| **Writer** | `writer` | 構成・脚本・設定などの文章系成果物を JSON 生成。 |
| **Researcher** | `researcher` | サブグラフで調査タスクを分解・実行。画像検索結果も返却。 |
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
    plan_patch_log: list[PlanPatchOp]
    selected_image_inputs: list[dict[str, Any]]
    target_scope: TargetScope
```

## 3. オーケストレーション・ロジック

### 3.1 Frozen Plan + Patch
1. 初回は `planner` が `plan` を作成。  
2. 実行中の追加指示は `patch_planner` が `edit_pending/split_pending/append_tail` に変換。  
3. `patch_gate` が `plan` に反映し、`supervisor` が再開。

### 3.2 ルーティング単位
- Worker 選択は `step.capability` のみを使用。  
- `role/objective` などの旧互換キーは使用しない。

### 3.3 Researcher Subgraph
- `research_manager` がタスク分解。  
- `research_worker` が順次実行し、必要に応じて画像候補（URL/出典/ライセンス）を返却。

## 4. ストリーミング契約（要点）

- Plan: `data-plan_update`
- Writer成果物: `data-writer-output`
- Image Search候補: `data-image-search-results`
- Visualizer成果物: `data-visual-*`
- Data Analyst成果物: `data-analyst-*`

フロントは `data-*` パートを UI の単一ソースとして扱います。
