# Mode-specific Prompting: Document Layout

- `document_layout_render`:
  - editorial grid, margin rhythm, section clarity
  - output must use `structured_prompt`; `image_generation_prompt` must be null
  - map writer content directly into:
    - `main_title` / `sub_title` for heading hierarchy
    - `contents` for section text that must be rendered in-image
    - `visual_style` for editorial direction (grid, type hierarchy, palette/material cues)
  - do not output `text_policy` / `negative_constraints` in `structured_prompt`
  - preserve writer text faithfully and keep in-image text legible
  - avoid decorative noise; prioritize readability, alignment rhythm, and whitespace balance

# Quality Direction
- Include anti-artifact intent directly in `visual_style` wording (e.g., no clutter, high readability, avoid gibberish text).
