# 02. LangGraph ワークフロー・エンジン

本システムの LangGraph 実装は、**Planner 集約型の再計画** を基盤にしています。  
命名と入出力は canonical 形式（`capability` / `instruction` / `writer`）に統一されています。

## 1. ノード構成

| ノード名 | ID | 概要 |
| :--- | :--- | :--- |
| **Planner** | `planner` | ユーザーの意図を解釈し、実行可能な DAG（有向非巡回グラフ）形式のプランを提案。 |
| **Supervisor** | `supervisor` | プランのステータス管理と、各 Worker ノードへの動的なルーティング。 |
| **Writer** | `writer` | 構成、脚本、設定などのテキスト系成果物を生成。 |
| **Researcher** | `researcher` | 検索エンジンを活用し、調査タスクを分解・実行。詳細レポートを返却。 |
| **Visualizer** | `visualizer` | 画像生成計画と実行。動的アスペクト比対応や In-paint 指示も担当。 |
| **Data Analyst** | `data_analyst` | Python実行、PPTX生成、データ集計などの構造化タスクを処理。 |

---

## 2. 状態管理（State Schema）

システムの状態は `TypedDict` で定義された `State` クラスで一元管理されます。

- **`plan`**: `TaskStep` のリスト。Planner が生成し、Supervisor が更新します。
- **`artifacts`**: 各ノードが生成した最終成果物（テキスト、画像 URL、ファイルパス等）。
- **`product_type`**: `slide`, `design`, `comic` のいずれか。
- **`asset_unit_ledger`**: 成果物の版管理と非破壊編集用の台帳。
- **`aspect_ratio`**: 出力画像のアスペクト比設定。

---

## 3. 成果物と状態の管理 (Asset & State Management)

エージェント間の連携と非破壊的な編集を実現するために、以下の仕組みを採用しています。

### Asset Unit Ledger
編集や再生成の最小単位（画像1枚、スライド1枚など）を管理する台帳です。
- **`unit_id`**: 永続的な識別子。In-paint（部分修正）や Regeneration（再生成）時に、どの要素を置き換えるかを特定するために使用されます。
- **`AssetUnitLedgerEntry`**: 各ユニットの画像 URL、生成したノード ID、メタデータ（タイトル等）を保持します。これにより、以前の生成結果を「版」として保持し、UI で切り替えることが可能になります。

### Asset Binding
Planner が定義した抽象的な「アセット要件」（例：このスライドに合う画像が必要）と、実際に生成・選択された「具体的なアセット ID」を紐付ける仕組みです。これにより、マルチエージェント環境での文脈共有を確実にします。

---

## 4. オーケストレーション・ロジック

### 4.1 Planner 集約リプラン
1. 初回は `planner` が `plan` を作成。  
2. 追加指示・中断後の再開時も `planner` が既存 `plan` を参照して再計画。  
3. `supervisor` が最新 `plan` を実行再開。

### 4.2 ルーティング単位
- Worker 選択は `step.capability` のみを使用。  
- `role/objective` などの旧互換キーは使用しない。

### 4.3 Researcher Subgraph
- `research_manager` がタスク分解。  
- `research_worker` が順次実行し、調査レポート（本文・出典）を返却。

## 5. ストリーミング契約（要点）

- Plan: `data-plan_update`
- Writer成果物: `data-writer-output`
- Research成果物: `data-research-report`
- Visualizer成果物: `data-visual-*`
- Data Analyst成果物: `data-analyst-*`

フロントは `data-*` パートを UI の単一ソースとして扱います。

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
