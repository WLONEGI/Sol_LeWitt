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
                            {data.setting_notes && (
                                <div>
                                    <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Setting Notes</div>
                                    <div className="whitespace-pre-wrap">{data.setting_notes}</div>
                                </div>
                            )}
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
                                const palette = Array.isArray(character?.color_palette) ? character.color_palette : []
                                const keywords = Array.isArray(character?.visual_keywords) ? character.visual_keywords : []
                                const relationships = Array.isArray(character?.relationships) ? character.relationships : []
                                const signatureItems = Array.isArray(character?.signature_items) ? character.signature_items : []
                                const forbiddenElements = Array.isArray(character?.forbidden_elements) ? character.forbidden_elements : []
                                return (
                                    <div key={character?.character_id || `character-${index}`} className="rounded-md border border-border p-4 space-y-3">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <Badge variant="outline">{character?.character_id || `character-${index + 1}`}</Badge>
                                            <span className="text-sm font-semibold">{character?.name || "Unnamed"}</span>
                                            {character?.role && <Badge>{character.role}</Badge>}
                                        </div>
                                        <Field label="Appearance Core" value={character?.appearance_core || character?.appearance} />
                                        <Field label="Costume Core" value={character?.costume_core} />
                                        <Field label="Personality" value={character?.personality} />
                                        <Field label="Backstory" value={character?.backstory} />
                                        <Field label="Motivation" value={character?.motivation} />

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

                                        <ListField label="Relationships" values={relationships} />
                                        <ListField label="Signature Items" values={signatureItems} />
                                        <ListField label="Forbidden Elements" values={forbiddenElements} />

                                        <div className="space-y-1">
                                            <div className="text-xs uppercase tracking-wider text-muted-foreground">Visual Keywords</div>
                                            {keywords.length === 0 ? (
                                                <div className="text-xs text-muted-foreground">N/A</div>
                                            ) : (
                                                <div className="flex flex-wrap gap-2">
                                                    {keywords.map((keyword: string, keywordIndex: number) => (
                                                        <Badge key={`keyword-${index}-${keywordIndex}`} variant="secondary">{keyword}</Badge>
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
