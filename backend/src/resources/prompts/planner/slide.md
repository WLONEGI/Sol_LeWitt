# Product Guidance: slide

## Recommended baseline flow
1. researcher (`text_search`)
2. writer (`slide_outline` or `infographic_spec`)
3. visualizer (`slide_render`)
4. data_analyst (`python_pipeline`) when packaging/post-processing is needed

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

## Replan hints
- For partial fixes, prefer appending a scoped visualizer or writer step over full regeneration.
- Preserve already valid completed assets and only regenerate target scope.
