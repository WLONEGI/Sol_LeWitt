# Spell Backend API Specification

本ドキュメントでは、Spell Backend API の仕様について記述します。
Serverは **FastAPI** で実装されており、ポート `8000` (デフォルト) で動作します。

---

## 1. REST Endpoints

### 1.1 Chat Stream

LangGraph ワークフローを実行し、Server-Sent Events (SSE) でリアルタイムに応答を返します。
Vercel AI SDK v6 UI Message Stream Protocol に準拠しています。

*   **URL**: `/api/chat/stream`
*   **Method**: `POST`
*   **Content-Type**: `application/json`

#### Request Body (`ChatRequest`)

```json
{
  "messages": [
    {
      "role": "user",
      "content": "AIの未来についてスライドを作って",
      "parts": [] // Vercel AI SDK 互換
    }
  ],
  "debug": false,
  "thread_id": "optional-uuid-v4",
  "pptx_template_base64": "base64-string...", // オプション: デザインコンテキスト用
  "data": {} // Vercel AI SDK その他のデータ
}
```

#### Response

*   **Content-Type**: `text/event-stream`
*   **Headers**: `x-vercel-ai-ui-message-stream: v1`

ストリームは Vercel AI SDK UI Message Stream Protocol に基づき、以下のイベントを送信します。

| Event Name | Description | Data Structure Example |
| :--- | :--- | :--- |
| `text-delta` | テキストメッセージの差分 | `{"type": "text-delta", "delta": "..."}` |
| `reasoning-delta` | 推論プロセス（Thinking）の差分 | `{"type": "reasoning-delta", "delta": "..."}` |
| `data-artifact` | 生成された成果物 | `{"type": "data", "data": {"type": "artifact", "content": ...}}` |
| `data-workflow` | ワークフロー状態 | `{"type": "data", "data": {"type": "workflow", "status": "started"}}` |
| `data-agent` | エージェント状態 | `{"type": "data", "data": {"type": "agent", "status": "started", "agent_name": "..."}}` |
| `data-progress` | 進捗状況 | `{"type": "data", "data": {"type": "progress", "content": "Analyzing...", "status": "in_progress"}}` |
| `tool-call` | ツール呼び出し | `{"type": "tool-call", "toolName": "search", "args": {...}}` |
| `tool-result` | ツール実行結果 | `{"type": "tool-result", "toolName": "search", "result": ...}` |
| `source-url` | 引用元情報 | `{"type": "source-url", "url": "https://...", "title": "..."}` |
| `error` | エラー情報 | `{"type": "error", "error": "..."}` |

---

### 1.2 History

会話履歴（スレッド一覧）を取得します。

*   **URL**: `/api/history`
*   **Method**: `GET`
*   **Query Params**: `uid` (optional)

#### Response

```json
[
  {
    "id": "thread-uuid",
    "title": "Session thread-uuid...",
    "timestamp": "2024-01-01T00:00:00Z",
    "summary": "No summary available"
  }
]
```

---

### 1.3 Thread Messages

特定のスレッド内のメッセージ履歴を取得します。

*   **URL**: `/api/threads/{thread_id}/messages`
*   **Method**: `GET`

#### Response

```json
[
  {
    "role": "user",
    "content": "...",
    "sources": [],
    "ui_type": null,
    "metadata": {},
    "reasoning": "..."
  },
  {
    "role": "assistant",
    "content": "...",
    "ui_type": "worker_result", 
    "metadata": { "status": "completed" }
  }
]
```

---

### 1.4 Analyze Template

PPTXテンプレートファイルをアップロードし、デザイン情報（`DesignContext`）を抽出します。

*   **URL**: `/api/template/analyze`
*   **Method**: `POST`
*   **Content-Type**: `multipart/form-data`

#### Request
*   `file`: PPTXファイルバイナリ

#### Response (`DesignContext` JSON)

```json
{
  "success": true,
  "filename": "template.pptx",
  "design_context": {
    "color_scheme": { "dk1": "...", "lt1": "...", "accent1": "..." },
    "font_scheme": { "major_latin": "...", "minor_latin": "..." },
    "layouts": [
        {
            "name": "Title Slide",
            "layout_type": "title_slide",
            "placeholders": [ ... ]
        }
    ],
    "background": { "fill_type": "solid", "solid_color": "..." }
  },
  "summary": { ... }
}
```

---

### 1.5 Image Inpainting (Stub)

生成画像の修正（インペインティング）リクエストを受け付けます（現在はスタブ実装）。

*   **URL**: `/api/image/{image_id}/inpaint`
*   **Method**: `POST`

#### Request (`InpaintRequest`)
```json
{
  "rect": { "x": 10, "y": 10, "w": 100, "h": 100 },
  "prompt": "Remove the tree"
}
```

---



## 3. Data Models

主なデータモデル（Pydantic Schema）の定義は `src/schemas/outputs.py` および `src/schemas/design.py` を参照してください。

### Slide Generation Schema (`StorywriterOutput`)

```python
class SlideContent(BaseModel):
    slide_number: int
    title: str
    bullet_points: list[str]
    key_message: str | None

class StorywriterOutput(BaseModel):
    execution_summary: str
    slides: list[SlideContent]
```

### Visualizer Schema (`VisualizerOutput`)

```python
class VisualizerOutput(BaseModel):
    execution_summary: str
    prompts: List[ImagePrompt]
    generation_config: GenerationConfig
    seed: int | None
    parent_id: str | None
```
