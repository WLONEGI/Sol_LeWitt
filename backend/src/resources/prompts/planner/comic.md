# Product Guidance: comic

## Recommended baseline flow
1. writer (`story_framework`)
2. writer (`character_sheet`)
3. visualizer (`character_sheet_render`)
4. writer (`comic_script`)
5. visualizer (`comic_page_render`)
6. data_analyst (`asset_packaging` or `python_pipeline`) when packaging/post-processing is needed

## Mandatory dependency constraints
- `character_sheet` must depend on `story_framework`.
- `character_sheet_render` must depend on `character_sheet`.
- `comic_script` must depend on both `story_framework` and `character_sheet`.
- `comic_page_render` must depend on `comic_script`.
- If data_analyst packages final pages, data_analyst must depend on the final visualizer step.

## Researcher policy
- Insert Researcher proactively when references, factual grounding, or style evidence improves quality.
- If inserted, use explicit `research:<topic_slug>` outputs and carry the same labels into dependent writer/visualizer `inputs` with matching `depends_on`.

## Replan hints
- Keep story continuity and character identity consistency.
- Prefer minimal page/panel-scoped replanning over full restart.
