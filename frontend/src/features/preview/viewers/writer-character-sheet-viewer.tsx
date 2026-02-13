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

const FIELD_LABELS: Record<string, string> = {
    execution_summary: "実行サマリー",
    user_message: "ユーザー向けメッセージ",
    character_id: "キャラクターID",
    name: "名前",
    story_role: "役割",
    role: "役割",
    core_personality: "性格の核",
    personality: "性格",
    motivation: "動機",
    weakness_or_fear: "弱点・恐れ",
    silhouette_signature: "シルエット特徴",
    face_hair_anchors: "顔・髪の固定要素",
    costume_anchors: "衣装の固定要素",
    color_palette: "カラーパレット",
    signature_items: "シグネチャーアイテム",
    forbidden_drift: "禁止事項",
    forbidden_elements: "禁止事項",
    speech_style: "口調",
}

function toRecord(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
    return value as Record<string, unknown>
}

const ATTACHMENT_FIELD_PATTERNS = [
    /attachment/i,
    /selected_image_input/i,
    /image_input/i,
    /reference_image/i,
    /添付画像/i,
]

function isAttachmentFieldKey(key: string): boolean {
    return ATTACHMENT_FIELD_PATTERNS.some((pattern) => pattern.test(key))
}

function stripAttachmentFields(value: unknown): unknown {
    if (Array.isArray(value)) {
        return value.map((item) => stripAttachmentFields(item))
    }
    if (!value || typeof value !== 'object') {
        return value
    }

    const next: Record<string, unknown> = {}
    Object.entries(value as Record<string, unknown>).forEach(([key, fieldValue]) => {
        if (isAttachmentFieldKey(key)) return
        next[key] = stripAttachmentFields(fieldValue)
    })
    return next
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

function formatVersionLabel(index: number): string {
    return `候補${index + 1}`
}

function toDisplayLabel(key: string): string {
    return FIELD_LABELS[key] || key.replace(/_/g, " ")
}

function isPrimitiveValue(value: unknown): value is string | number | boolean {
    return typeof value === "string" || typeof value === "number" || typeof value === "boolean"
}

function ValueView({ value, fieldKey }: { value: unknown; fieldKey?: string }) {
    if (value === null || value === undefined || value === '') {
        return <div className="text-sm text-muted-foreground">N/A</div>
    }

    if (fieldKey === "color_palette") {
        const palette = toRecord(value)
        const entries = [
            { key: "main", label: "メイン" },
            { key: "sub", label: "サブ" },
            { key: "accent", label: "アクセント" },
        ]
        return (
            <div className="space-y-1.5">
                {entries.map((entry) => {
                    const rawColor = palette[entry.key]
                    const color = typeof rawColor === "string" && rawColor.trim().length > 0 ? rawColor.trim() : "N/A"
                    return (
                        <div key={entry.key} className="flex items-center gap-2 text-sm">
                            <span className="w-16 text-xs text-muted-foreground">{entry.label}</span>
                            {color !== "N/A" ? (
                                <span
                                    className="inline-block h-3.5 w-3.5 rounded border border-border"
                                    style={{ backgroundColor: color }}
                                />
                            ) : null}
                            <span className="font-mono text-xs">{color}</span>
                        </div>
                    )
                })}
            </div>
        )
    }

    if (fieldKey === "signature_items" || fieldKey === "forbidden_drift" || fieldKey === "forbidden_elements") {
        const items = Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : []
        if (items.length === 0) {
            return <div className="text-sm text-muted-foreground">N/A</div>
        }
        return (
            <ul className="space-y-1">
                {items.map((item, index) => (
                    <li key={`${fieldKey}-${index}`} className="text-sm leading-snug">
                        ・{item}
                    </li>
                ))}
            </ul>
        )
    }

    if (isPrimitiveValue(value)) {
        return <div className="text-sm whitespace-pre-wrap">{String(value)}</div>
    }

    if (Array.isArray(value) && value.every((item) => isPrimitiveValue(item))) {
        const items = value.map((item) => String(item)).filter((item) => item.trim().length > 0)
        if (items.length === 0) {
            return <div className="text-sm text-muted-foreground">N/A</div>
        }
        return (
            <ul className="space-y-1">
                {items.map((item, index) => (
                    <li key={`item-${index}`} className="text-sm leading-snug">
                        ・{item}
                    </li>
                ))}
            </ul>
        )
    }

    const record = toRecord(value)
    const recordEntries = Object.entries(record)
    if (recordEntries.length > 0 && recordEntries.every(([, entryValue]) => isPrimitiveValue(entryValue))) {
        return (
            <div className="space-y-1">
                {recordEntries.map(([entryKey, entryValue]) => (
                    <div key={entryKey} className="text-sm leading-snug">
                        <span className="text-muted-foreground mr-1">{toDisplayLabel(entryKey)}:</span>
                        <span>{String(entryValue)}</span>
                    </div>
                ))}
            </div>
        )
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
                    <div className="text-xs tracking-wider text-muted-foreground mb-1">{toDisplayLabel(key)}</div>
                    <ValueView value={value} fieldKey={key} />
                </div>
            ))}
        </div>
    )
}

export function WriterCharacterSheetViewer({ content }: WriterCharacterSheetViewerProps) {
    const normalized = useMemo(() => normalizeViewerData(content), [content])
    const { bundle } = normalized

    const [activeVersionId, setActiveVersionId] = useState<string | null>(bundle.active_version_id)
    const [activeTab, setActiveTab] = useState<TabKey>('sheets')
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

    const writerOutput = toRecord(stripAttachmentFields(activeVersion?.writer_output))
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
                            {bundle.versions.length > 1 ? (
                                <div className="flex flex-wrap gap-2">
                                    {bundle.versions.map((version, index) => (
                                        <Button
                                            key={version.version_id}
                                            size="sm"
                                            variant={version.version_id === activeVersion?.version_id ? "default" : "outline"}
                                            onClick={() => setActiveVersionId(version.version_id)}
                                        >
                                            {formatVersionLabel(index)}
                                        </Button>
                                    ))}
                                </div>
                            ) : null}
                            <div className="flex gap-2">
                                <Button
                                    size="sm"
                                    variant={activeTab === 'sheets' ? 'default' : 'outline'}
                                    onClick={() => setActiveTab('sheets')}
                                >
                                    シート
                                </Button>
                                <Button
                                    size="sm"
                                    variant={activeTab === 'settings' ? 'default' : 'outline'}
                                    onClick={() => setActiveTab('settings')}
                                >
                                    設定
                                </Button>
                            </div>
                        </CardHeader>
                    </Card>

                    {activeTab === 'sheets' ? (
                        <Card>
                            <CardContent className="space-y-4">
                                {!activeRun ? (
                                    <div className="rounded-md border border-dashed border-border p-6 text-sm text-muted-foreground">
                                        キャラクターシート画像はまだ生成されていません。
                                    </div>
                                ) : (
                                    <div className="space-y-4">
                                        {activeRun.slides.length === 0 ? (
                                            <div className="rounded-md border border-dashed border-border p-6 text-sm text-muted-foreground">
                                                キャラクターシート画像はまだ生成されていません。
                                            </div>
                                        ) : (
                                            activeRun.slides.map((slide) => (
                                                <div key={`sheet-${slide.slide_number}`} className="rounded-md border border-border p-3 space-y-3">
                                                    <div className="flex items-center justify-between gap-2">
                                                        <div className="text-sm font-semibold truncate">
                                                            {slide.title || `キャラクター ${slide.slide_number}`}
                                                        </div>
                                                        <Badge variant="outline">#{slide.slide_number}</Badge>
                                                    </div>
                                                    {slide.image_url ? (
                                                        <img
                                                            src={slide.image_url}
                                                            alt={slide.title || `キャラクター ${slide.slide_number}`}
                                                            className={cn("w-full rounded-md border border-border object-contain bg-muted/20")}
                                                        />
                                                    ) : (
                                                        <div className="rounded-md border border-dashed border-border bg-muted/20 h-64 flex items-center justify-center text-sm text-muted-foreground">
                                                            画像はまだ利用できません。
                                                        </div>
                                                    )}
                                                </div>
                                            ))
                                        )}
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    ) : (
                        <>
                            <Card>
                                <CardHeader>
                                    <CardTitle className="text-sm">全体設定</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <KeyValueTable data={writerMeta} />
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle className="text-sm">キャラクター設定</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    {characters.length === 0 ? (
                                        <div className="text-sm text-muted-foreground">キャラクター設定はまだありません。</div>
                                    ) : (
                                        characters.map((character, index) => {
                                            const characterId = typeof character.character_id === 'string'
                                                ? character.character_id
                                                : `character_${index + 1}`
                                            const name = typeof character.name === 'string'
                                                ? character.name
                                                : `キャラクター ${index + 1}`
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
                    )}
                </div>
            </ScrollArea>
        </div>
    )
}
