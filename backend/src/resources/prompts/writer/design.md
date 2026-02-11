# Document Design Production
Goal: 読みやすく美しいドキュメント構成（ブループリント）を策定する。

# Mode-specific schema requirements

## mode = document_blueprint -> `WriterDocumentBlueprintOutput`
```json
{
  "execution_summary":"...",
  "user_message":"...",
  "document_type":"magazine",
  "style_direction":"...",
  "pages":[
    {
      "page_number":1,
      "page_title":"...",
      "purpose":"...",
      "sections":[{"section_id":"s1","heading":"...","body":"...","visual_hint":"..."}]
    }
  ]
}
```
