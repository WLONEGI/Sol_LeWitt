"use client"

import {
    CHARACTER_SHEET_BUNDLE_ARTIFACT_ID,
    normalizeCharacterSheetBundle,
} from "@/features/preview/lib/character-sheet-bundle"
import { useArtifactStore } from "@/features/preview/stores/artifact"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollText } from "lucide-react"
import { cn } from "@/lib/utils"
import { useShallow } from "zustand/react/shallow"

interface CharacterSheetSummaryProps {
    artifactId?: string
    className?: string
}

export function CharacterSheetSummary({
    artifactId = CHARACTER_SHEET_BUNDLE_ARTIFACT_ID,
    className,
}: CharacterSheetSummaryProps) {
    const { artifacts, setActiveContextId, setPreviewOpen } = useArtifactStore(
        useShallow((state) => ({
            artifacts: state.artifacts,
            setActiveContextId: state.setActiveContextId,
            setPreviewOpen: state.setPreviewOpen,
        }))
    )

    const artifact = artifacts[artifactId]
    const bundle = normalizeCharacterSheetBundle(artifact?.content)
    const activeVersion =
        bundle.versions.find((version) => version.version_id === bundle.active_version_id) ||
        bundle.versions[bundle.versions.length - 1]

    const writerOutput = activeVersion?.writer_output || {}
    const charactersRaw = Array.isArray(writerOutput.characters) ? writerOutput.characters : []
    const characters = charactersRaw.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
    const handleOpenPreview = () => {
        setActiveContextId(artifactId)
        setPreviewOpen(true)
    }

    return (
        <div className={cn("w-full max-w-2xl my-4", className)}>
            <Accordion type="single" collapsible defaultValue="character-sheet" className="border rounded-xl bg-card text-card-foreground shadow-sm overflow-hidden">
                <AccordionItem value="character-sheet" className="border-none">
                    <AccordionTrigger className="flex items-center justify-between p-4 transition-colors hover:no-underline pointer-events-auto">
                        <div className="flex items-center gap-3">
                            <div className="flex items-center justify-center w-8 h-8 rounded-lg shadow-sm bg-primary text-primary-foreground">
                                <ScrollText className="w-4 h-4" />
                            </div>
                            <div className="flex flex-col text-left gap-1">
                                <span className="text-sm font-semibold leading-none">Character Sheet</span>
                                <div className="flex flex-wrap items-center gap-2">
                                    <Badge variant="outline" className="text-[11px]">Characters: {characters.length}</Badge>
                                </div>
                            </div>
                        </div>
                    </AccordionTrigger>
                    <AccordionContent className="px-4 pb-4 pt-2">
                        {characters.length === 0 ? (
                            <div className="text-sm text-muted-foreground">No characters available yet.</div>
                        ) : (
                            <div className="flex flex-col gap-3 pl-1">
                                {characters.map((character, index) => {
                                    const characterId = typeof character.character_id === 'string' ? character.character_id : `character_${index + 1}`
                                    const name = typeof character.name === 'string' ? character.name : `Character ${index + 1}`
                                    const role = typeof character.story_role === 'string'
                                        ? character.story_role
                                        : (typeof character.role === 'string' ? character.role : undefined)
                                    return (
                                        <div key={characterId} className="flex items-start gap-3">
                                            <div className="flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold bg-foreground text-background">
                                                {index + 1}
                                            </div>
                                            <div className="flex flex-col gap-1 text-left min-w-0">
                                                <div className="text-sm font-semibold leading-none truncate">{name}</div>
                                                <div className="text-xs text-muted-foreground truncate">{characterId}</div>
                                                {role ? (
                                                    <div className="text-xs text-muted-foreground truncate">{role}</div>
                                                ) : null}
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        )}
                        <div className="pt-4">
                            <Button size="sm" variant="outline" onClick={handleOpenPreview}>
                                Open Character Sheet
                            </Button>
                        </div>
                    </AccordionContent>
                </AccordionItem>
            </Accordion>
        </div>
    )
}
