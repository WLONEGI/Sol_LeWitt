---
trigger: model_decision
description: Strictly apply this rule for Gemini Model ID selection, Vertex AI library usage, and DB proxy checks. Use it as the absolute standard for all coding, debugging, and review decisions.
---

## 1. AI Model Strategy (Strict Enforcement)

Geminiモデルの選定において、AIの自己判断によるモデル変更を禁止します。
タスクの性質に応じて、必ず以下の定数（Model ID）を使用してください。

| Role | Environment Variable | Model ID (Strict) | Description |
| :--- | :--- | :--- | :--- |
| **Reasoning** | `REASONING_MODEL` | `gemini-3-flash-preview` | Planner, Researcherなど、複合的な推論タスク用 |
| **Basic** | `BASIC_MODEL` | `gemini-3-flash-preview` | Coordinatorなど、単純なタスクやルーティング用 |
| **Vision** | `VL_MODEL` | `gemini-3-pro-image-preview` | 画像理解、生成、Visualizerタスク用 |
| **High Reasoning** | `HIGH_REASONING_MODEL` | `gemini-3-pro-preview` | 高度な論理的推論、複雑なコード生成用 |

> **注意:** `gemini-1.5` 系や `gemini-pro` などの古いモデルID、あるいはOpenAI等の他社モデルを勝手に提案・使用しないでください。

## 2. Tech Stack & Libraries

Vertex AIへの接続には、以下のライブラリ指定を遵守してください。

- **Library:** `langchain-google-vertexai`
- **Constraint:** `langchain-google-genai` (API Keyベース) ではなく、Vertex AI (Google Cloud IAMベース) のライブラリを使用すること。

### Implementation Example (Python)
```python
from langchain_google_vertexai import VertexAI

# Initialize with the specific model config
llm = VertexAI(
    model_name="gemini-3-flash-preview", # Must match the defined Rule
    location="us-central1" # or your specific region
)
3. Database Connectivity Workflow
データベース（Cloud SQL等）への接続を行う際は、必ずプロキシを経由する必要があります。

Requirement: cloud-sql-proxy の起動が必須です。

Workflow:

cloud-sql-proxy を起動し、接続を確立する。

アプリケーション/スクリプトからのDB接続を開始する。

Note: 直接のPublic IP接続や、プロキシなしでの接続試行は行わないでください。