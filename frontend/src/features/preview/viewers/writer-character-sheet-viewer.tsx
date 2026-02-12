"use client"

import { useEffect, useMemo, useState } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
    CharacterSheetBundleContent,
    CharacterSheetVersion,
    normalizeCharacterSheetBundle,
} from "@/features/preview/lib/character-sheet-bundle"

interface WriterCharacterSheetViewerProps {
    content: any
}

type TabKey = 'settings' | 'sheets'

interface NormalizedViewerData {
    bundle: CharacterSheetBundleContent
}

function statusText(value: unknown): string {
    if (value === 'failed') return 'failed'
    if (value === 'streaming') return 'streaming'
    if (value === 'pending') return 'pending'
    return 'completed'
}

function toRecord(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
    return value as Record<string, unknown>
}

function normalizeViewerData(content: unknown): NormalizedViewerData {
    const bundle = normalizeCharacterSheetBundle(content)
    if (bundle.versions.length > 0) {
        return { bundle }
    }

    const raw = toRecord(content)
    if (Object.keys(raw).length === 0) {
        return { bundle }
    }

    const fallbackVersion: CharacterSheetVersion = {
        version_id: 'legacy:writer_character_sheet',
        writer_artifact_id: 'legacy:writer_character_sheet',
        writer_status: 'completed',
        created_at: Date.now(),
        updated_at: Date.now(),
        writer_output: raw,
        visual_runs: [],
    }

    return {
        bundle: {
            ui_type: 'character_sheet_bundle',
            active_version_id: fallbackVersion.version_id,
            versions: [fallbackVersion],
        },
    }
}

function formatVersionLabel(version: CharacterSheetVersion, index: number): string {
    const stamp = new Date(version.created_at)
    if (Number.isNaN(stamp.getTime())) {
        return `v${index + 1}`
    }
    return `v${index + 1} ${stamp.toLocaleString()}`
}

function ValueView({ value }: { value: unknown }) {
    if (value === null || value === undefined || value === '') {
        return <div className="text-sm text-muted-foreground">N/A</div>
    }

    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
        return <div className="text-sm whitespace-pre-wrap">{String(value)}</div>
    }

    return (
        <pre className="text-xs whitespace-pre-wrap break-words bg-muted/30 rounded-md p-2">
            {JSON.stringify(value, null, 2)}
        </pre>
    )
}

function KeyValueTable({ data }: { data: Record<string, unknown> }) {
    const entries = Object.entries(data)
    if (entries.length === 0) {
        return <div className="text-sm text-muted-foreground">N/A</div>
    }

    return (
        <div className="space-y-3">
            {entries.map(([key, value]) => (
                <div key={key}>
                    <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">{key}</div>
                    <ValueView value={value} />
                </div>
            ))}
        </div>
    )
}

export function WriterCharacterSheetViewer({ content }: WriterCharacterSheetViewerProps) {
    const normalized = useMemo(() => normalizeViewerData(content), [content])
    const { bundle } = normalized

    const [activeVersionId, setActiveVersionId] = useState<string | null>(bundle.active_version_id)
    const [activeTab, setActiveTab] = useState<TabKey>('settings')
    const [activeRunId, setActiveRunId] = useState<string | null>(null)

    useEffect(() => {
        const targetId =
            bundle.active_version_id ||
            (bundle.versions.length > 0 ? bundle.versions[bundle.versions.length - 1].version_id : null)
        setActiveVersionId(targetId)
    }, [bundle.active_version_id, bundle.versions])

    const activeVersion = useMemo(() => {
        return (
            bundle.versions.find((version) => version.version_id === activeVersionId) ||
            bundle.versions[bundle.versions.length - 1]
        )
    }, [activeVersionId, bundle.versions])

    const visualRuns = activeVersion?.visual_runs || []

    useEffect(() => {
        if (visualRuns.length === 0) {
            setActiveRunId(null)
            return
        }
        setActiveRunId((prev) => {
            if (prev && visualRuns.some((run) => run.run_id === prev)) {
                return prev
            }
            return visualRuns[visualRuns.length - 1].run_id
        })
    }, [visualRuns])

    const activeRun = useMemo(() => {
        if (!activeRunId) return visualRuns[visualRuns.length - 1]
        return visualRuns.find((run) => run.run_id === activeRunId) || visualRuns[visualRuns.length - 1]
    }, [activeRunId, visualRuns])

    const writerOutput = toRecord(activeVersion?.writer_output)
    const charactersRaw = Array.isArray(writerOutput.characters) ? writerOutput.characters : []
    const characters = charactersRaw
        .map((item) => toRecord(item))
        .filter((item) => Object.keys(item).length > 0)

    const writerMeta = { ...writerOutput }
    delete writerMeta.characters

    return (
        <div className="flex flex-col flex-1 min-h-0 bg-background">
            <ScrollArea className="flex-1 min-h-0 p-3">
                <div className="flex flex-col gap-4 pb-6">
                    <Card>
                        <CardHeader className="space-y-3">
                            <div className="flex flex-wrap items-center gap-2">
                                <Badge variant="secondary">Writer: {statusText(activeVersion?.writer_status)}</Badge>
                                <Badge variant="secondary">Visualizer: {statusText(activeRun?.status)}</Badge>
                                <Badge variant="outline">Versions: {bundle.versions.length}</Badge>
                            </div>
                            <CardTitle className="text-sm">Character Sheet</CardTitle>
                            {bundle.versions.length > 0 ? (
                                <div className="flex flex-wrap gap-2">
                                    {bundle.versions.map((version, index) => (
                                        <Button
                                            key={version.version_id}
                                            size="sm"
                                            variant={version.version_id === activeVersion?.version_id ? "default" : "outline"}
                                            onClick={() => setActiveVersionId(version.version_id)}
                                        >
                                            {formatVersionLabel(version, index)}
                                        </Button>
                                    ))}
                                </div>
                            ) : null}
                            <div className="flex gap-2">
                                <Button
                                    size="sm"
                                    variant={activeTab === 'settings' ? 'default' : 'outline'}
                                    onClick={() => setActiveTab('settings')}
                                >
                                    Settings
                                </Button>
                                <Button
                                    size="sm"
                                    variant={activeTab === 'sheets' ? 'default' : 'outline'}
                                    onClick={() => setActiveTab('sheets')}
                                >
                                    Sheets
                                </Button>
                            </div>
                        </CardHeader>
                    </Card>

                    {activeTab === 'settings' ? (
                        <>
                            <Card>
                                <CardHeader>
                                    <CardTitle className="text-sm">Writer Output</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <KeyValueTable data={writerMeta} />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle className="text-sm">Characters</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    {characters.length === 0 ? (
                                        <div className="text-sm text-muted-foreground">No characters defined.</div>
                                    ) : (
                                        characters.map((character, index) => {
                                            const characterId = typeof character.character_id === 'string'
                                                ? character.character_id
                                                : `character_${index + 1}`
                                            const name = typeof character.name === 'string'
                                                ? character.name
                                                : `Character ${index + 1}`
                                            return (
                                                <div key={characterId} className="rounded-md border border-border p-4 space-y-3">
                                                    <div className="flex flex-wrap items-center gap-2">
                                                        <Badge variant="outline">{characterId}</Badge>
                                                        <span className="text-sm font-semibold">{name}</span>
                                                    </div>
                                                    <KeyValueTable data={character} />
                                                </div>
                                            )
                                        })
                                    )}
                                </CardContent>
                            </Card>
                        </>
                    ) : (
                        <Card>
                            <CardHeader className="space-y-3">
                                <CardTitle className="text-sm">Generated Character Sheets</CardTitle>
                                {visualRuns.length > 0 ? (
                                    <div className="flex flex-wrap gap-2">
                                        {visualRuns.map((run, index) => (
                                            <Button
                                                key={run.run_id}
                                                size="sm"
                                                variant={run.run_id === activeRun?.run_id ? 'default' : 'outline'}
                                                onClick={() => setActiveRunId(run.run_id)}
                                            >
                                                Run {index + 1}
                                            </Button>
                                        ))}
                                    </div>
                                ) : null}
                            </CardHeader>
                            <CardContent className="space-y-4">
                                {!activeRun ? (
                                    <div className="rounded-md border border-dashed border-border p-6 text-sm text-muted-foreground">
                                        Character sheet images are not generated yet.
                                    </div>
                                ) : (
                                    <div className="space-y-4">
                                        {activeRun.slides.length === 0 ? (
                                            <div className="rounded-md border border-dashed border-border p-6 text-sm text-muted-foreground">
                                                Character sheet images are not generated yet.
                                            </div>
                                        ) : (
                                            activeRun.slides.map((slide) => (
                                                <div key={`sheet-${slide.slide_number}`} className="rounded-md border border-border p-3 space-y-3">
                                                    <div className="flex items-center justify-between gap-2">
                                                        <div className="text-sm font-semibold truncate">
                                                            {slide.title || `Character ${slide.slide_number}`}
                                                        </div>
                                                        <Badge variant="outline">#{slide.slide_number}</Badge>
                                                    </div>
                                                    {slide.image_url ? (
                                                        <img
                                                            src={slide.image_url}
                                                            alt={slide.title || `Character ${slide.slide_number}`}
                                                            className={cn("w-full rounded-md border border-border object-contain bg-muted/20")}
                                                        />
                                                    ) : (
                                                        <div className="rounded-md border border-dashed border-border bg-muted/20 h-64 flex items-center justify-center text-sm text-muted-foreground">
                                                            Image is not available yet.
                                                        </div>
                                                    )}
                                                </div>
                                            ))
                                        )}
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    )}
                </div>
            </ScrollArea>
        </div>
    )
}
