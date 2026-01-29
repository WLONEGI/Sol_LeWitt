"use client"

import { ExternalLink } from "lucide-react"
import { useArtifactStore } from "../../preview/store/artifact"

interface ArtifactPreviewProps {
    previewUrls: string[];
    title: string;
    artifactId?: string;
}

export function ArtifactPreview({ previewUrls, title, artifactId }: ArtifactPreviewProps) {
    const { setActiveContextId, setPreviewOpen } = useArtifactStore();

    if (!previewUrls || previewUrls.length === 0) return null;

    const handleClick = (e: React.MouseEvent) => {
        if (artifactId) {
            e.preventDefault();
            setActiveContextId(artifactId);
            setPreviewOpen(true);
        }
    };

    return (
        <div className="flex flex-col gap-2 my-2 ml-2">
            <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
                {title} Preview
            </span>
            <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
                {previewUrls.map((url, idx) => (
                    <a
                        key={`${idx}-${url}`}
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={handleClick}
                        className="relative group aspect-video h-24 flex-shrink-0 rounded-md overflow-hidden border border-white/10 hover:border-emerald-500/50 transition-colors cursor-pointer"
                    >
                        <img
                            src={url}
                            alt={`${title} ${idx + 1}`}
                            className="h-full w-full object-cover transition-transform group-hover:scale-105"
                        />
                        <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                            <ExternalLink className="h-4 w-4 text-white" />
                        </div>
                    </a>
                ))}
            </div>
        </div>
    )
}
