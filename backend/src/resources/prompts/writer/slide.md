# Slide & Infographic Production
Goal: 可読性と視覚的インパクトを両立した構成案を生成する。

# Mode-specific schema requirements

## mode = slide_outline -> `WriterSlideOutlineOutput`
```json
{
  "execution_summary": "...",
  "user_message": "...",
  "slides": [
    {
      "slide_number": 1,
      "title": "...",
      "bullet_points": ["...", "..."],
      "description": "...",
      "key_message": "..."
    }
  ]
}
```

## mode = infographic_spec -> `WriterInfographicSpecOutput`
```json
{
  "execution_summary":"...",
  "user_message":"...",
  "title":"...",
  "audience":"...",
  "key_message":"...",
  "blocks":[
    {"block_id":"b1","heading":"...","body":"...","visual_hint":"...","data_points":["..."]}
  ]
}
```
