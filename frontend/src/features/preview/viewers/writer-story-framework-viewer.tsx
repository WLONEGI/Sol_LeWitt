"use client"

import { ScrollArea } from "@/components/ui/scroll-area"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

interface WriterStoryFrameworkViewerProps {
    content: any
}

function normalizeStoryFramework(content: any) {
    const data = (content && typeof content === "object") ? content : {}
    const payload = (data.story_framework && typeof data.story_framework === "object") ? data.story_framework : null

    if (payload) {
        const arcOverview = Array.isArray(payload.arc_overview) ? payload.arc_overview : []
        const worldPolicy = (payload.world_policy && typeof payload.world_policy === "object") ? payload.world_policy : {}
        const directionPolicy = (payload.direction_policy && typeof payload.direction_policy === "object") ? payload.direction_policy : {}
        const artStylePolicy = (payload.art_style_policy && typeof payload.art_style_policy === "object") ? payload.art_style_policy : {}
        const formatPolicy = (payload.format_policy && typeof payload.format_policy === "object") ? payload.format_policy : {}
        const pageBudget = (formatPolicy.page_budget && typeof formatPolicy.page_budget === "object") ? formatPolicy.page_budget : {}
        const negativeConstraints = Array.isArray(artStylePolicy.negative_constraints)
            ? artStylePolicy.negative_constraints
            : []
        const locations = Array.isArray(worldPolicy.primary_locations) ? worldPolicy.primary_locations : []
        const socialRules = Array.isArray(worldPolicy.social_rules) ? worldPolicy.social_rules : []

        return {
            data,
            concept: payload.concept,
            theme: payload.theme,
            structureType: payload.structure_type,
            coreConflict: payload.core_conflict,
            arcOverview,
            formatText: `${formatPolicy.series_type || "N/A"} / ${formatPolicy.medium || "N/A"} / ${formatPolicy.reading_direction || "N/A"} / ${pageBudget.min || "?"}-${pageBudget.max || "?"}p`,
            worldText: [worldPolicy.era, locations.join(", "), socialRules.join(", ")].filter(Boolean).join(" / "),
            directionPolicy,
            artStylePolicy,
            negativeConstraints,
        }
    }

    const narrativeArc = Array.isArray(data.narrative_arc) ? data.narrative_arc : []
    const constraints = Array.isArray(data.constraints) ? data.constraints : []
    return {
        data,
        concept: data.logline,
        theme: data.tone_and_temperature,
        structureType: "legacy",
        coreConflict: data.background_context,
        arcOverview: narrativeArc.map((item: string, index: number) => ({ phase: `${index + 1}`, purpose: item })),
        formatText: "legacy format",
        worldText: data.world_setting,
        directionPolicy: {
            paneling_policy: constraints.join(" / "),
            eye_guidance_policy: "",
            page_turn_policy: "",
            dialogue_policy: "",
        },
        artStylePolicy: {
            line_style: "",
            shading_style: "",
        },
        negativeConstraints: constraints,
    }
}

export function WriterStoryFrameworkViewer({ content }: WriterStoryFrameworkViewerProps) {
    const normalized = normalizeStoryFramework(content)
    const arcOverview = Array.isArray(normalized.arcOverview) ? normalized.arcOverview : []
    const negativeConstraints = Array.isArray(normalized.negativeConstraints) ? normalized.negativeConstraints : []

    return (
        <div className="flex flex-col flex-1 min-h-0 bg-background">
            <ScrollArea className="flex-1 min-h-0 p-3">
                <div className="flex flex-col gap-4 pb-6">
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Execution Summary</CardTitle>
                        </CardHeader>
                        <CardContent className="text-sm whitespace-pre-wrap">
                            {normalized.data.execution_summary || "Summary is not available."}
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Core Framework</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4 text-sm">
                            <div>
                                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Concept</div>
                                <div className="whitespace-pre-wrap">{normalized.concept || "N/A"}</div>
                            </div>
                            <div>
                                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Theme</div>
                                <div className="whitespace-pre-wrap">{normalized.theme || "N/A"}</div>
                            </div>
                            <div>
                                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Format Policy</div>
                                <div className="whitespace-pre-wrap">{normalized.formatText || "N/A"}</div>
                            </div>
                            <div>
                                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Structure Type</div>
                                <div className="whitespace-pre-wrap">{normalized.structureType || "N/A"}</div>
                            </div>
                            <div>
                                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Core Conflict</div>
                                <div className="whitespace-pre-wrap">{normalized.coreConflict || "N/A"}</div>
                            </div>
                            <div>
                                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">World Policy</div>
                                <div className="whitespace-pre-wrap">{normalized.worldText || "N/A"}</div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Arc Overview</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2">
                            {arcOverview.length === 0 ? (
                                <div className="text-xs text-muted-foreground">No arc overview defined.</div>
                            ) : arcOverview.map((step: any, index: number) => (
                                <div key={`arc-${index}`} className="text-sm rounded-md border border-border bg-muted/20 px-3 py-2">
                                    <span className="text-xs text-muted-foreground mr-2">{step?.phase || index + 1}.</span>
                                    {step?.purpose || "N/A"}
                                </div>
                            ))}
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Direction Policy</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            {[
                                { label: "Paneling", value: normalized.directionPolicy?.paneling_policy },
                                { label: "Eye Guidance", value: normalized.directionPolicy?.eye_guidance_policy },
                                { label: "Page Turn", value: normalized.directionPolicy?.page_turn_policy },
                                { label: "Dialogue", value: normalized.directionPolicy?.dialogue_policy },
                            ].map((item, index) => (
                                <div key={`direction-${index}`} className="rounded-md border border-border p-3 space-y-1">
                                    <div className="text-xs uppercase tracking-wider text-muted-foreground">{item.label}</div>
                                    <div className="text-sm whitespace-pre-wrap">{item.value || "N/A"}</div>
                                </div>
                            ))}
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Art Style Policy</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            <div>
                                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Line Style</div>
                                <div className="text-sm whitespace-pre-wrap">{normalized.artStylePolicy?.line_style || "N/A"}</div>
                            </div>
                            <div>
                                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Shading Style</div>
                                <div className="text-sm whitespace-pre-wrap">{normalized.artStylePolicy?.shading_style || "N/A"}</div>
                            </div>
                            <div>
                                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Negative Constraints</div>
                                {negativeConstraints.length === 0 ? (
                                    <div className="text-xs text-muted-foreground">No constraints.</div>
                                ) : (
                                    <div className="flex flex-wrap gap-2">
                                        {negativeConstraints.map((item: string, index: number) => (
                                        <Badge key={`constraint-${index}`} variant="secondary">
                                            {item}
                                        </Badge>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </ScrollArea>
        </div>
    )
}
