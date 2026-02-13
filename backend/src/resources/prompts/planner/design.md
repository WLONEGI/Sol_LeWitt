# Product Guidance: design

## Recommended baseline flow
1. researcher (`text_search`) as first candidate for reference collection
2. writer (`slide_outline`)
3. visualizer (`document_layout_render`)
4. data_analyst (`pptx_master_to_images` / `pptx_slides_to_images` / `images_to_package` / `template_manifest_extract`) when post-processing is needed

## Researcher policy for design
- `researcher(text_search)` is strongly recommended at the beginning.
- It is not mandatory. Skip only when the user already provides sufficient references and constraints.
- When adding Researcher, specify multiple perspectives in one step instruction
  (minimum 3 perspectives) so Researcher can decompose them into separate tasks.

## Mandatory dependency constraints
- If writer uses researcher findings, writer must depend on researcher.
- visualizer (`document_layout_render`) must depend on writer (`slide_outline`).
- If data_analyst packages final visuals/documents, data_analyst must depend on the final visualizer step.
- When researcher findings are consumed, keep `research:<topic_slug>` labels consistent between researcher `outputs` and consumer `inputs`.

## Replan hints
- Keep editorial structure stable; apply minimal diffs to target pages/sections.
- Prefer targeted append/split steps instead of restarting all pages.
