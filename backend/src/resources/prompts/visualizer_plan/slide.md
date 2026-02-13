# Mode-specific Planning Guidance: Slide

- `slide_render`:
  - readability and hierarchy first
  - reserve clear text area
  - include composition intent (e.g., right-side negative space, split screen)
  - prefer data-forward layouts for non-title slides (comparison blocks, metric cards, structured lists)

# Input Selection Policy (`slide_render`)
- For non-title slides, prioritize `selected_inputs` that contain concrete facts:
  - Writer bullet points/descriptions with key claims,
  - Research-derived numeric evidence,
  - DataAnalyst outputs when available.
- Avoid selecting only generic style hints when factual inputs are available.
- If quantitative evidence exists, include at least one fact-bearing input in `selected_inputs`.

# generation_notes Policy (`slide_render`)
- Add concise directives that force dense, faithful rendering:
  - "render all key bullets",
  - "preserve exact numeric values/units",
  - "use comparison/ranking structure where applicable".
- Do not output notes that bias toward decorative/abstract visuals.
- For non-title slides, include at least one directive about data structure:
  - metric cards with labeled values,
  - comparison matrix with explicit axes,
  - ranked list with criteria,
  - timeline with dated events.
- Disallow unlabeled decorative charts in `generation_notes`.
