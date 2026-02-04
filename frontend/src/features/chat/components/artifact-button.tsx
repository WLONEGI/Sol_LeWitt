"use client"

import { Button } from "@/components/ui/button"
import { FileText, Image, BarChart, BookOpen, ExternalLink } from "lucide-react"
import { useArtifactStore } from "@/features/preview/stores/artifact"
import { cn } from "@/lib/utils"
import { ActionPill } from "./action-pill"

interface ArtifactButtonProps {
    artifactId: string;
    title: string;
    icon?: string;
    type?: string;
}

export function ArtifactButton({ artifactId, title, icon, type }: ArtifactButtonProps) {
    const { setActiveContextId, setPreviewOpen } = useArtifactStore();
    const handleClick = () => {
        setActiveContextId(artifactId);
        setPreviewOpen(true);
    };

    const getIconComponent = (iconName?: string) => {
        switch (iconName) {
            case "Image": return Image;
            case "BarChart": return BarChart;
            case "BookOpen": return BookOpen;
            default: return FileText;
        }
    }

    return (
        <div className="flex justify-start my-1 ml-6 relative cursor-pointer group" onClick={handleClick}>
            <div className="absolute -left-6 top-1/2 -translate-y-1/2 w-4 h-[2px] bg-gray-200" />
            <ActionPill
                icon={getIconComponent(icon)}
                label={title}
                className="bg-gray-50 border-gray-200 hover:bg-white hover:shadow-sm text-gray-700 pr-2"
            />
            <ExternalLink className="absolute right-2 top-1/2 -translate-y-1/2 h-3 w-3 text-gray-400 opacity-0 group-hover:opacity-100" />
        </div>
    )
}
