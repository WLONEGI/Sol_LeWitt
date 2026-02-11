"use client"

import { ScrollArea } from "@/components/ui/scroll-area"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

interface WriterCharacterSheetViewerProps {
    content: any
}

export function WriterCharacterSheetViewer({ content }: WriterCharacterSheetViewerProps) {
    const data = (content && typeof content === "object") ? content : {}
    const characters = Array.isArray(data.characters) ? data.characters : []

    return (
        <div className="flex flex-col flex-1 min-h-0 bg-background">
            <ScrollArea className="flex-1 min-h-0 p-3">
                <div className="flex flex-col gap-4 pb-6">
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Execution Summary</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4 text-sm">
                            <div className="whitespace-pre-wrap">
                                {data.execution_summary || "Summary is not available."}
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Characters</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {characters.length === 0 ? (
                                <div className="text-xs text-muted-foreground">No characters defined.</div>
                            ) : characters.map((character: any, index: number) => {
                                const palette = normalizePalette(character?.color_palette)
                                const signatureItems = Array.isArray(character?.signature_items) ? character.signature_items : []
                                const forbiddenElements = Array.isArray(character?.forbidden_drift)
                                    ? character.forbidden_drift
                                    : (Array.isArray(character?.forbidden_elements) ? character.forbidden_elements : [])
                                return (
                                    <div key={character?.character_id || `character-${index}`} className="rounded-md border border-border p-4 space-y-3">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <Badge variant="outline">{character?.character_id || `character-${index + 1}`}</Badge>
                                            <span className="text-sm font-semibold">{character?.name || "Unnamed"}</span>
                                            {(character?.story_role || character?.role) && <Badge>{character?.story_role || character?.role}</Badge>}
                                        </div>
                                        <Field label="Silhouette Signature" value={character?.silhouette_signature || character?.appearance_core} />
                                        <Field label="Face/Hair Anchors" value={character?.face_hair_anchors || character?.appearance_core} />
                                        <Field label="Costume Anchors" value={character?.costume_anchors || character?.costume_core} />
                                        <Field label="Core Personality" value={character?.core_personality || character?.personality} />
                                        <Field label="Motivation" value={character?.motivation} />
                                        <Field label="Weakness or Fear" value={character?.weakness_or_fear} />
                                        <Field label="Speech Style" value={character?.speech_style} />

                                        <div className="space-y-1">
                                            <div className="text-xs uppercase tracking-wider text-muted-foreground">Color Palette</div>
                                            {palette.length === 0 ? (
                                                <div className="text-xs text-muted-foreground">N/A</div>
                                            ) : (
                                                <div className="flex flex-wrap gap-2">
                                                    {palette.map((color: string, paletteIndex: number) => (
                                                        <Badge key={`palette-${index}-${paletteIndex}`} variant="secondary">{color}</Badge>
                                                    ))}
                                                </div>
                                            )}
                                        </div>

                                        <ListField label="Signature Items" values={signatureItems} />
                                        <ListField label="Forbidden Drift" values={forbiddenElements} />
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

function Field({ label, value }: { label: string, value?: string }) {
    return (
        <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">{label}</div>
            <div className="text-sm whitespace-pre-wrap">{value || "N/A"}</div>
        </div>
    )
}

function ListField({ label, values }: { label: string, values: string[] }) {
    return (
        <div className="space-y-1">
            <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
            {values.length === 0 ? (
                <div className="text-xs text-muted-foreground">N/A</div>
            ) : (
                <div className="flex flex-wrap gap-2">
                    {values.map((value, idx) => (
                        <Badge key={`${label}-${idx}`} variant="secondary">{value}</Badge>
                    ))}
                </div>
            )}
        </div>
    )
}

function normalizePalette(raw: any): string[] {
    if (Array.isArray(raw)) {
        return raw.filter((item): item is string => typeof item === "string" && item.length > 0)
    }
    if (raw && typeof raw === "object") {
        const keys = ["main", "sub", "accent"] as const
        return keys
            .map((key) => raw[key])
            .filter((item): item is string => typeof item === "string" && item.length > 0)
    }
    return []
}
