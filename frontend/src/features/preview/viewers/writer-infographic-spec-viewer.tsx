"use client"

import { ScrollArea } from "@/components/ui/scroll-area"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

interface WriterInfographicSpecViewerProps {
    content: any
}

export function WriterInfographicSpecViewer({ content }: WriterInfographicSpecViewerProps) {
    const data = (content && typeof content === "object") ? content : {}
    const blocks = Array.isArray(data.blocks) ? data.blocks : []

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
                            <CardTitle className="text-sm">Infographic Overview</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-3 text-sm">
                            <OverviewRow label="Title" value={data.title} />
                            <OverviewRow label="Audience" value={data.audience} />
                            <OverviewRow label="Key Message" value={data.key_message} />
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Blocks</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {blocks.length === 0 ? (
                                <div className="text-xs text-muted-foreground">No blocks defined.</div>
                            ) : blocks.map((block: any, index: number) => {
                                const points = Array.isArray(block?.data_points) ? block.data_points : []
                                return (
                                    <div key={block?.block_id || `block-${index}`} className="rounded-md border border-border p-4 space-y-3">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <Badge variant="outline">{block?.block_id || `block-${index + 1}`}</Badge>
                                            <span className="text-sm font-semibold">{block?.heading || "Untitled Block"}</span>
                                        </div>
                                        <div className="text-sm whitespace-pre-wrap">{block?.body || "N/A"}</div>
                                        <div>
                                            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Visual Hint</div>
                                            <div className="text-sm whitespace-pre-wrap">{block?.visual_hint || "N/A"}</div>
                                        </div>
                                        <div>
                                            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Data Points</div>
                                            {points.length === 0 ? (
                                                <div className="text-xs text-muted-foreground">No data points.</div>
                                            ) : (
                                                <div className="flex flex-wrap gap-2">
                                                    {points.map((point: string, pointIndex: number) => (
                                                        <Badge key={`point-${index}-${pointIndex}`} variant="secondary">{point}</Badge>
                                                    ))}
                                                </div>
                                            )}
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

function OverviewRow({ label, value }: { label: string, value?: string }) {
    return (
        <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">{label}</div>
            <div className="whitespace-pre-wrap">{value || "N/A"}</div>
        </div>
    )
}
