# Product Guidance: slide

## Recommended baseline flow
1. researcher (`text_search` / `image_search` / `hybrid_search`)
2. writer (`slide_outline` or `infographic_spec`)
3. visualizer (`slide_render` or `infographic_render`)
4. data_analyst (`asset_packaging` or `python_pipeline`) when packaging/post-processing is needed

## Researcher policy for slide (strong recommendation)
- Researcher should be inserted by default.
- Omit Researcher only when the request is trivially self-contained and no factual/reference uncertainty exists.
- If omitted, explain the omission reason in step description.

## Mandatory dependency constraints
- If visualizer step uses writer output, visualizer must depend on writer.
- If data_analyst packages final visuals, data_analyst must depend on the final visualizer step.
- If writer/visualizer explicitly consumes researcher output, add dependency from that step to researcher.

## Replan hints
- For partial fixes, prefer appending a scoped visualizer or writer step over full regeneration.
- Preserve already valid completed assets and only regenerate target scope.
