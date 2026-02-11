# Document Design Production
Goal: 読みやすく美しいドキュメント構成（ブループリント）を策定する。

# Outline policy
- 構成は固定しない。ユーザー指示とPlannerの目的 (`instruction`, `planned_inputs`, `success_criteria`) に沿って自由に設計する。
- ページ数、セクション粒度、情報密度は目的達成を優先して最適化する。
- `resolved_research_inputs` がある場合は、デザイン根拠や参照方向を `style_direction` と各ページ目的へ反映する。

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
