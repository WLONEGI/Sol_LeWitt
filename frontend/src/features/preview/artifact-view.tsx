"use client"

import { useArtifactStore } from "./store/artifact"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Markdown } from "@/components/ui/markdown"
import { LogViewer } from "@/features/preview/viewers/log-viewer"
import { SlideViewer } from "@/features/preview/viewers/slide-viewer"
import { Button } from "@/components/ui/button"
import { X } from "lucide-react"

// Reuse Markdown component for Report/Outline
function ReportViewer({ content }: { content: string }) {
    return (
        <div className="flex flex-col h-full bg-background">
            <ScrollArea className="flex-1 p-6">
                <div className="prose dark:prose-invert max-w-none">
                    <Markdown>{content}</Markdown>
                </div>
            </ScrollArea>
        </div>
    )
}

function DefaultJsonViewer({ data }: { data: any }) {
    return (
        <ScrollArea className="h-full w-full p-4 bg-muted/20">
            <pre className="text-xs font-mono">{JSON.stringify(data, null, 2)}</pre>
        </ScrollArea>
    )
}

export function ArtifactView() {
    const { currentArtifact, artifacts, activeContextId, setPreviewOpen } = useArtifactStore()

    // Key Logic for Dual Pane / Polymorphic Viewport:
    // If user manually selected a context (from Left Pane), show that.
    // Otherwise, default to the latest current artifact.
    const displayArtifact = activeContextId && artifacts[activeContextId]
        ? artifacts[activeContextId]
        : currentArtifact;

    if (!displayArtifact) {
        return (
            <div className="h-full w-full flex items-center justify-center text-muted-foreground bg-muted/10">
                <p>No artifact selected</p>
            </div>
        )
    }

    const renderContent = () => {
        switch (displayArtifact.type) {
            case 'analysis_log':
            case 'log':
            case 'reasoning':
                return <LogViewer content={displayArtifact.content} title={displayArtifact.title} status={displayArtifact.status} />
            case 'report':
            case 'outline':
                return <ReportViewer content={displayArtifact.content} />
            case 'slide':
                return <SlideViewer content={displayArtifact.content} imageId={displayArtifact.id} />
            default:
                return <DefaultJsonViewer data={displayArtifact} />
        }
    }

    return (
        <div className="flex flex-col h-full w-full relative group bg-black/40 backdrop-blur-3xl rounded-r-2xl overflow-hidden border-l border-white/5">
            {/* Ambient Glows */}
            <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-primary/10 rounded-full blur-[100px] pointer-events-none" />

            {/* Global Close Button (Mobile/Desktop) */}
            <div className="absolute top-4 right-4 z-50 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                <Button variant="outline" size="icon" className="h-8 w-8 glass-button rounded-full" onClick={() => setPreviewOpen(false)}>
                    <X className="h-4 w-4" />
                </Button>
            </div>

            <div className="flex-1 relative z-10">
                {renderContent()}
            </div>
        </div>
    )
}
