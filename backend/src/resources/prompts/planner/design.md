# Product Guidance: design

## Recommended baseline flow
1. researcher (`image_search`) as first candidate for reference collection
2. writer (`document_blueprint`)
3. visualizer (`document_layout_render`)
4. data_analyst (`asset_packaging` or `python_pipeline`) when packaging/post-processing is needed

## Researcher policy for design
- `researcher(image_search)` is strongly recommended at the beginning.
- It is not mandatory. Skip only when the user already provides sufficient references and constraints.

## Mandatory dependency constraints
- If writer uses researcher findings, writer must depend on researcher.
- visualizer (`document_layout_render`) must depend on writer (`document_blueprint`).
- If data_analyst packages final visuals/documents, data_analyst must depend on the final visualizer step.
- When researcher findings are consumed, keep `research:<topic_slug>` labels consistent between researcher `outputs` and consumer `inputs`.

## Replan hints
- Keep editorial structure stable; apply minimal diffs to target pages/sections.
- Prefer targeted append/split steps instead of restarting all pages.
