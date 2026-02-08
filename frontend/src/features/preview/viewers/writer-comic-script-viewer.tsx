"use client"

import { ScrollArea } from "@/components/ui/scroll-area"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

interface WriterComicScriptViewerProps {
    content: any
}

export function WriterComicScriptViewer({ content }: WriterComicScriptViewerProps) {
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
                                {data.title && <Badge variant="outline">{data.title}</Badge>}
                                {data.genre && <Badge>{data.genre}</Badge>}
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Pages & Panels</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {pages.length === 0 ? (
                                <div className="text-xs text-muted-foreground">No pages defined.</div>
                            ) : pages.map((page: any, index: number) => {
                                const panels = Array.isArray(page?.panels) ? page.panels : []
                                return (
                                    <div key={`comic-page-${page?.page_number ?? index}`} className="rounded-md border border-border p-4 space-y-3">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <Badge variant="outline">Page {page?.page_number ?? index + 1}</Badge>
                                            <span className="text-sm font-semibold">{page?.page_goal || "Page Goal N/A"}</span>
                                        </div>

                                        <div className="space-y-2">
                                            {panels.length === 0 ? (
                                                <div className="text-xs text-muted-foreground">No panels.</div>
                                            ) : panels.map((panel: any, panelIndex: number) => {
                                                const dialogues = Array.isArray(panel?.dialogue) ? panel.dialogue : []
                                                const sfxList = Array.isArray(panel?.sfx) ? panel.sfx : []
                                                return (
                                                    <div key={`panel-${index}-${panel?.panel_number ?? panelIndex}`} className="rounded border border-border/80 p-3 space-y-2">
                                                        <div className="flex flex-wrap items-center gap-2">
                                                            <Badge variant="secondary">Panel {panel?.panel_number ?? panelIndex + 1}</Badge>
                                                            {panel?.camera && <Badge variant="outline">{panel.camera}</Badge>}
                                                        </div>
                                                        <div className="text-sm whitespace-pre-wrap">{panel?.scene_description || "N/A"}</div>
                                                        <div>
                                                            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Dialogue</div>
                                                            {dialogues.length === 0 ? (
                                                                <div className="text-xs text-muted-foreground">No dialogue.</div>
                                                            ) : (
                                                                <div className="space-y-1">
                                                                    {dialogues.map((line: string, lineIndex: number) => (
                                                                        <div key={`dialogue-${panelIndex}-${lineIndex}`} className="text-sm rounded bg-muted/20 px-2 py-1">
                                                                            {line}
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            )}
                                                        </div>
                                                        <div>
                                                            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">SFX</div>
                                                            {sfxList.length === 0 ? (
                                                                <div className="text-xs text-muted-foreground">No SFX.</div>
                                                            ) : (
                                                                <div className="flex flex-wrap gap-2">
                                                                    {sfxList.map((sfx: string, sfxIndex: number) => (
                                                                        <Badge key={`sfx-${panelIndex}-${sfxIndex}`} variant="secondary">{sfx}</Badge>
                                                                    ))}
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                )
                                            })}
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
