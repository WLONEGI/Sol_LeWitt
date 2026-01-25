"use client"

import { Button } from "@/components/ui/button"
import { FileText, Image, BarChart, BookOpen, ExternalLink } from "lucide-react"
import { useArtifactStore } from "@/store/artifact"
import { cn } from "@/lib/utils"

interface ArtifactButtonProps {
    artifactId: string;
    title: string;
    icon?: string;
    type?: string;
}

export function ArtifactButton({ artifactId, title, icon, type }: ArtifactButtonProps) {
    const { setActiveContextId, setPreviewOpen } = useArtifactStore();

    const handleClick = () => {
        // Just trigger the preview logic
        // The artifact content itself must be available in the store or state.
        // Currently, history persistence doesn't save artifact CONTENT in the message,
        // so we assume the Artifact Store has fetched it or we might need to fetch it.
        // For now, we assume this button works in the context where the artifact exists.

        // TODO: If this is loaded from history and artifact content is missing from local store,
        // we might need a mechanism to fetch it. But for the immediate task:
        setActiveContextId(artifactId);
        setPreviewOpen(true);
    };

    const getIcon = () => {
        switch (icon) {
            case "Image": return <Image className="h-4 w-4" />;
            case "BarChart": return <BarChart className="h-4 w-4" />;
            case "BookOpen": return <BookOpen className="h-4 w-4" />;
            default: return <FileText className="h-4 w-4" />;
        }
    }

    return (
        <div className="flex justify-start my-2 ml-2">
            <Button
                variant="outline"
                className="gap-2 bg-gradient-to-r from-emerald-500/10 to-teal-500/10 border-emerald-500/20 hover:bg-emerald-500/20 text-emerald-300"
                onClick={handleClick}
            >
                {getIcon()}
                <span>{title}</span>
                <ExternalLink className="h-3 w-3 opacity-50 ml-1" />
            </Button>
        </div>
    )
}
