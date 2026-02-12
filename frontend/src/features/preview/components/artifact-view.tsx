"use client"

import { useResearchStore } from "@/features/preview/stores/research"
import { useArtifactStore } from "@/features/preview/stores/artifact"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Markdown } from "@/components/ui/markdown"
import { LogViewer } from "@/features/preview/viewers/log-viewer"
import { SlideViewer } from "@/features/preview/viewers/slide-viewer"
import { SlideDeckViewer } from "@/features/preview/viewers/slide-deck-viewer"
import { DataAnalystViewer } from "@/features/preview/viewers/data-analyst-viewer"
import { WriterStoryFrameworkViewer } from "@/features/preview/viewers/writer-story-framework-viewer"
import { WriterCharacterSheetViewer } from "@/features/preview/viewers/writer-character-sheet-viewer"
import { WriterInfographicSpecViewer } from "@/features/preview/viewers/writer-infographic-spec-viewer"
import { WriterDocumentBlueprintViewer } from "@/features/preview/viewers/writer-document-blueprint-viewer"
import { WriterComicScriptViewer } from "@/features/preview/viewers/writer-comic-script-viewer"
import { ArtifactContainer } from "./artifact-container"

// Reuse Markdown component for Report/Outline
function ReportViewer({ content, citations = [] }: { content: string, citations?: Array<{ title: string; uri: string }> }) {
    return (
        <div className="flex flex-col flex-1 min-h-0 bg-white relative">
            {/* Report Content */}
            <ScrollArea className="flex-1 min-h-0 p-6">
                <div className="prose dark:prose-invert max-w-none pb-32"> {/* Move padding here */}
                    <Markdown>{content}</Markdown>
                </div>
            </ScrollArea>

            {/* Citations Footer (if available) - mimicking the requested UI roughly */}
            {citations.length > 0 && (
                <div className="absolute bottom-0 left-0 right-0 bg-muted/80 backdrop-blur-md border-t border-border p-4 max-h-40 overflow-y-auto">
                    <h4 className="text-xs font-semibold uppercase text-muted-foreground mb-2">Sources</h4>
                    <div className="flex flex-col gap-2">
                        {citations.map((cite, i) => (
                            <a
                                key={i}
                                href={cite.uri}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center gap-2 text-sm hover:bg-white/5 p-2 rounded-md transition-colors"
                            >
                                <span className="text-xs bg-primary/10 text-primary px-1.5 py-0.5 rounded border border-primary/20">{i + 1}</span>
                                <div className="flex-1 truncate">
                                    <div className="font-medium truncate">{cite.title || "No Title"}</div>
                                    <div className="text-xs text-muted-foreground truncate opacity-70">{cite.uri}</div>
                                </div>
                            </a>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}

function DefaultJsonViewer({ data: _data }: { data: any }) {
    return (
        <div className="flex-1 min-h-0 p-6 bg-muted/20 flex items-center justify-center">
            <div className="text-sm text-muted-foreground">このデータのプレビュー表示は準備中です。</div>
        </div>
    )
}

export function ArtifactView() {
    const { currentArtifact, artifacts, activeContextId } = useArtifactStore()
    const researchTasks = useResearchStore((state) => state.tasks)

    const activeResearchTask = activeContextId ? researchTasks[activeContextId] : null
    const displayArtifact = activeContextId && artifacts[activeContextId]
        ? artifacts[activeContextId]
        : currentArtifact;

    if (!displayArtifact && !activeResearchTask) {
        return (
            <div className="h-full w-full flex items-center justify-center text-muted-foreground bg-white">
                <ArtifactContainer title="Preview" subtitle="No content selected">
                    <div className="h-full w-full flex items-center justify-center italic text-muted-foreground/50">
                        Select a task or artifact to preview
                    </div>
                </ArtifactContainer>
            </div>
        )
    }

    const title = activeResearchTask ? "Research Report" : (displayArtifact?.title || "Artifact")
    const subtitle = activeResearchTask ? activeResearchTask.perspective : undefined
    const renderContent = () => {
        if (activeResearchTask) {
            return <ReportViewer content={activeResearchTask.content} citations={activeResearchTask.citations} />
        }

        if (!displayArtifact) return null;

        switch (displayArtifact.type) {
            case 'analysis_log':
            case 'log':
            case 'reasoning':
                return <LogViewer content={displayArtifact.content} title={displayArtifact.title} />
            case 'report':
            case 'outline':
                return <ReportViewer content={displayArtifact.content} />
            case 'slide':
                return (
                    <SlideViewer
                        content={displayArtifact.content}
                        imageId={displayArtifact.id}
                        aspectRatio={displayArtifact.content?.metadata?.aspect_ratio}
                    />
                )
            case 'slide_deck':
                return (
                    <SlideDeckViewer
                        content={displayArtifact.content}
                        artifactId={displayArtifact.id}
                        aspectRatio={displayArtifact.content?.metadata?.aspect_ratio}
                    />
                )
            case 'data_analyst':
                return <DataAnalystViewer content={displayArtifact.content} />
            case 'writer_story_framework':
                return <WriterStoryFrameworkViewer content={displayArtifact.content} />
            case 'writer_character_sheet':
                return <WriterCharacterSheetViewer content={displayArtifact.content} />
            case 'writer_infographic_spec':
                return <WriterInfographicSpecViewer content={displayArtifact.content} />
            case 'writer_document_blueprint':
                return <WriterDocumentBlueprintViewer content={displayArtifact.content} />
            case 'writer_comic_script':
                return <WriterComicScriptViewer content={displayArtifact.content} />
            default:
                return <DefaultJsonViewer data={displayArtifact} />
        }
    }

    return (
        <ArtifactContainer
            title={title}
            subtitle={subtitle}
        >
            {renderContent()}
        </ArtifactContainer>
    )
}
