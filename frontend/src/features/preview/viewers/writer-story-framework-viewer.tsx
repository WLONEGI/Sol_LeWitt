"use client"

import { ScrollArea } from "@/components/ui/scroll-area"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

interface WriterStoryFrameworkViewerProps {
    content: any
}

export function WriterStoryFrameworkViewer({ content }: WriterStoryFrameworkViewerProps) {
    const data = (content && typeof content === "object") ? content : {}
    const narrativeArc = Array.isArray(data.narrative_arc) ? data.narrative_arc : []
    const keyBeats = Array.isArray(data.key_beats) ? data.key_beats : []
    const constraints = Array.isArray(data.constraints) ? data.constraints : []

    return (
        <div className="flex flex-col flex-1 min-h-0 bg-background">
            <ScrollArea className="flex-1 min-h-0 p-3">
                <div className="flex flex-col gap-4 pb-6">
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Execution Summary</CardTitle>
                        </CardHeader>
                        <CardContent className="text-sm whitespace-pre-wrap">
                            {data.execution_summary || "Summary is not available."}
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Core Story</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4 text-sm">
                            <div>
                                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Logline</div>
                                <div className="whitespace-pre-wrap">{data.logline || "N/A"}</div>
                            </div>
                            <div>
                                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">World Setting</div>
                                <div className="whitespace-pre-wrap">{data.world_setting || "N/A"}</div>
                            </div>
                            <div>
                                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Background Context</div>
                                <div className="whitespace-pre-wrap">{data.background_context || "N/A"}</div>
                            </div>
                            <div>
                                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Tone & Temperature</div>
                                <div className="whitespace-pre-wrap">{data.tone_and_temperature || "N/A"}</div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Narrative Arc</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2">
                            {narrativeArc.length === 0 ? (
                                <div className="text-xs text-muted-foreground">No narrative arc defined.</div>
                            ) : narrativeArc.map((step: string, index: number) => (
                                <div key={`arc-${index}`} className="text-sm rounded-md border border-border bg-muted/20 px-3 py-2">
                                    <span className="text-xs text-muted-foreground mr-2">{index + 1}.</span>
                                    {step}
                                </div>
                            ))}
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Key Beats</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            {keyBeats.length === 0 ? (
                                <div className="text-xs text-muted-foreground">No key beats defined.</div>
                            ) : keyBeats.map((beat: any, index: number) => (
                                <div key={beat?.beat_id || `beat-${index}`} className="rounded-md border border-border p-3 space-y-2">
                                    <div className="flex items-center gap-2">
                                        <Badge variant="outline">{beat?.beat_id || `beat-${index + 1}`}</Badge>
                                        {beat?.tone && <Badge>{beat.tone}</Badge>}
                                    </div>
                                    <div className="text-sm font-medium">{beat?.summary || "No summary"}</div>
                                    <div className="text-xs text-muted-foreground whitespace-pre-wrap">{beat?.purpose || "No purpose"}</div>
                                </div>
                            ))}
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Constraints</CardTitle>
                        </CardHeader>
                        <CardContent>
                            {constraints.length === 0 ? (
                                <div className="text-xs text-muted-foreground">No constraints.</div>
                            ) : (
                                <div className="flex flex-wrap gap-2">
                                    {constraints.map((item: string, index: number) => (
                                        <Badge key={`constraint-${index}`} variant="secondary">
                                            {item}
                                        </Badge>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>
            </ScrollArea>
        </div>
    )
}
