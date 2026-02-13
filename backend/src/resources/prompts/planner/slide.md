# Product Guidance: slide

## Recommended baseline flow
1. researcher (`text_search`)
2. writer (`slide_outline` or `infographic_spec`)
3. visualizer (`slide_render`)
4. data_analyst (`images_to_package`) as terminal packaging step

## PPTX template policy (mandatory)
- If `has_pptx_attachment=true`, add a preprocessing `data_analyst` step as the FIRST step.
  - mode must be `pptx_slides_to_images` only.
  - `pptx_master_to_images` must not be used in slide planning.
  - this preprocessing step must be independent (`depends_on: []`) and placed before writer/visualizer.
  - connect downstream by explicit `inputs`/`outputs` labels and `depends_on` where consumed.
- Template解析の主成果物は画像（PNG等）として扱う。中間変換で生成されるPDF/PPTXを成果物の主出力にしない。
- preprocessing must not be omitted when PPTX is attached.

## Packaging policy (mandatory terminal step)
- Always add `data_analyst(mode=images_to_package)` as a separate LAST step for slide plans.
- Packaging step must be separated from PPTX preprocessing step (do not merge into one step).
- Packaging step must depend on the final visualizer step and package generated images to zip/pptx/pdf.

## Information-density first policy
- Slide案件では「情報密度」を最優先に計画する。
- 装飾中心の出力計画は禁止。各ステップは数値・比較軸・根拠の受け渡しを明示する。
- 非タイトルスライドは、最低1つ以上の定量または固有事実を含む前提で計画する。
- 数値根拠が必要なのに入力が不足する場合は、Researcherを省略しない。

## Researcher policy for slide (strong recommendation)
- Researcher should be inserted by default.
- Omit Researcher only when the request is trivially self-contained and no factual/reference uncertainty exists.
- If omitted, explain the omission reason in step description.
- When adding a Researcher step, keep it as a single step but include multiple perspectives in `instruction`.
  - Example perspectives: 市場動向 / 先行事例 / リスク・制約.

## Mandatory dependency constraints
- If visualizer step uses writer output, visualizer must depend on writer.
- If data_analyst packages final visuals, data_analyst must depend on the final visualizer step.
- If writer/visualizer explicitly consumes researcher output, add dependency from that step to researcher.
- When researcher output is consumed, propagate the same `research:<topic_slug>` label from researcher `outputs` to downstream `inputs`.

## Step contract for dense slide generation
- Writer (`slide_outline`) step must explicitly request:
  - 非タイトルスライドで具体データ（数値、期間、比較軸、固有名詞）を含むアウトライン
  - 箇条書きに根拠となるファクトを反映
  - 曖昧語だけの記述を避ける
- Writer instructionには、可能な限り以下を明記する:
  - 主要指標（値・単位・時点）を含める
  - 比較軸（Before/After、競合、セグメント、前年比）を含める
  - 主張と根拠の対応を`description`または`key_message`で示す
- Writer step `validation` / `success_criteria` should include checks such as:
  - 「非タイトルスライドが具体データを含む」
  - 「主張と根拠の対応が確認できる」
- Visualizer (`slide_render`) step should include checks such as:
  - 「Writerの数値・列挙情報が画像内で欠落していない」
  - 「非タイトルスライドが装飾過多でない」
  - 「指標ラベル・単位・年次などの識別情報が保持される」

## Pre-generation density handoff
- Researcherを使う場合は、Writer/Visualizerが再利用しやすい粒度で`outputs`を定義する。
  - 推奨: `research:quant_facts`, `research:comparison_axes`, `research:key_entities`
- Writer/VisualizerがResearcher成果を使う場合は、`inputs`に同じラベルを明記する。
- Slide案件では、装飾のみを指示するVisualizer stepを作らない。

## Replan hints
- For partial fixes, prefer appending a scoped visualizer or writer step over full regeneration.
- Preserve already valid completed assets and only regenerate target scope.
