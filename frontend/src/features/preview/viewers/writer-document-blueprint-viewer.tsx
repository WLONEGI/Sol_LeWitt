"use client"

import { ScrollArea } from "@/components/ui/scroll-area"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

interface WriterDocumentBlueprintViewerProps {
    content: any
}

export function WriterDocumentBlueprintViewer({ content }: WriterDocumentBlueprintViewerProps) {
    const data = (content && typeof content === "object") ? content : {}
    const pages = Array.isArray(data.pages) ? data.pages : []

    return (
        <div className="flex flex-col flex-1 min-h-0 bg-background">
            <ScrollArea className="flex-1 min-h-0 p-3">
                <div className="flex flex-col gap-4 pb-6">
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Execution Summary</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-3 text-sm">
                            <div className="whitespace-pre-wrap">
                                {data.execution_summary || "Summary is not available."}
                            </div>
                            <div className="flex flex-wrap gap-2">
                                <Badge variant="outline">{data.document_type || "unknown"}</Badge>
                                {data.style_direction && <Badge>{data.style_direction}</Badge>}
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Pages</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {pages.length === 0 ? (
                                <div className="text-xs text-muted-foreground">No pages defined.</div>
                            ) : pages.map((page: any, index: number) => {
                                const sections = Array.isArray(page?.sections) ? page.sections : []
                                return (
                                    <div key={`page-${page?.page_number ?? index}`} className="rounded-md border border-border p-4 space-y-3">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <Badge variant="outline">Page {page?.page_number ?? index + 1}</Badge>
                                            <span className="text-sm font-semibold">{page?.page_title || "Untitled Page"}</span>
                                        </div>
                                        <div>
                                            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Purpose</div>
                                            <div className="text-sm whitespace-pre-wrap">{page?.purpose || "N/A"}</div>
                                        </div>

                                        <div className="space-y-2">
                                            <div className="text-xs uppercase tracking-wider text-muted-foreground">Sections</div>
                                            {sections.length === 0 ? (
                                                <div className="text-xs text-muted-foreground">No sections.</div>
                                            ) : sections.map((section: any, sectionIndex: number) => (
                                                <div key={section?.section_id || `section-${index}-${sectionIndex}`} className="rounded border border-border/80 p-3">
                                                    <div className="flex flex-wrap items-center gap-2 mb-1">
                                                        <Badge variant="secondary">{section?.section_id || `section-${sectionIndex + 1}`}</Badge>
                                                        <span className="text-sm font-medium">{section?.heading || "Untitled Section"}</span>
                                                    </div>
                                                    <div className="text-sm whitespace-pre-wrap">{section?.body || "N/A"}</div>
                                                    {section?.visual_hint && (
                                                        <div className="mt-2">
                                                            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Visual Hint</div>
                                                            <div className="text-xs whitespace-pre-wrap">{section.visual_hint}</div>
                                                        </div>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )
                            })}
                        </CardContent>
                    </Card>
                </div>
            </ScrollArea>
        </div>
    )
}
