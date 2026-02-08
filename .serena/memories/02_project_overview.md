# Project Overview Report

## 1. プロジェクトの目的
**AI_Slide_with_nano_banana** は、AIを活用してスライド、ドキュメント、コミックなどのコンテンツを自動生成するアプリケーションです。
ユーザーの入力（チャット）を元に、調査（Research）、構成（Plan）、執筆（Writing）、可視化（Visualization）のプロセスを経て、最終的な成果物（Artifact）を作成します。

## 2. アーキテクチャの主要な構成要素

### Backend (Python / FastAPI / LangGraph)
- **Core Workflow (`src/core/workflow`)**:
    - **LangGraph**: アプリケーションの中核ロジック。`StateGraph`を使用して、Coordinate, Plan, Research, Write, Visualizeといった複数のエージェント（ノード）をオーケストレーションします。
    - **Supervisor Pattern**: `supervisor`ノードが各ワーカーノード（Researcher, Writer, Visualizer）へのタスク委譲と結果の集約を管理します。
    - **Custom State**: `MessagesState`を拡張した`State`クラスで、実行計画（`plan`）、成果物（`artifacts`）、会話履歴を一元管理します。
- **Infrastructure (`src/infrastructure`)**:
    - **LLM**: Google Vertex AI / Gemini モデルを使用。
    - **Database**: PostgreSQL（`langgraph-checkpoint-postgres`）を使用してグラフの状態を永続化。

### Frontend (TypeScript / Next.js / React)
- **Feature-Based Design**: `src/features/chat` など、機能ごとにモジュール化されたディレクトリ構造。
- **UI Components**: Shadcn UI (@radix-ui) と Tailwind CSS を使用したモダンなUI。
- **State Management**: Zustand と Context Providers (`AuthProvider`, `ThemeProvider`) を併用。

## 3. 開発者が注意すべき特異な設計パターンやルール

### 1. State Management & Merging
- バックエンドの `State` クラスでは、`artifacts` や `summary` などのフィールドに対してカスタムなマージ関数（`merge_artifacts`, `merge_research_results`）が定義されています。
- これにより、並列実行されるノードからの部分的な更新を適切に統合したり、意図的にデータを削除（`None`を設定）したりすることが可能です。

### 2. Hierarchical Graphs (Subgraphs)
- `Researcher` はメインのグラフ（Main Graph）の中に埋め込まれた **サブグラフ（Subgraph）** として実装されています（`build_researcher_subgraph`）。
- メイングラフの `supervisor` は `researcher` ノードを単一の作業単位として扱いますが、内部ではさらに詳細なステートマシンが動作しています。

### 3. Plan-Driven Execution
- 単なる会話の往復ではなく、`TaskStep` オブジェクトのリスト（`plan`）に基づいて処理が進みます。
- `planner` や `plan_manager` ノードがこの計画を動的に生成・修正し、`supervisor` がそれに従って実行を制御する「Pre-planning + Execution」パターンが採用されています。

### 4. Artifact-Centric Output
- チャットの応答文だけでなく、構造化された「Artifact」（スライドデータ、画像URL、テキストブロックなど）が生成の主目的です。これらは `State.artifacts` に辞書形式で保持され、フロントエンドでレンダリングされます。
