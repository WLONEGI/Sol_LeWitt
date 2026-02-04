
"use client"

import { Button } from "@/components/ui/button"
import { Search } from "lucide-react"
import { cn } from "@/lib/utils"
import { useArtifactStore } from "@/features/preview/stores/artifact"

interface ResearchStatusButtonProps {
    taskId: string;
    perspective: string;
    status: 'running' | 'completed';
}

export function ResearchStatusButton({ taskId, perspective, status }: ResearchStatusButtonProps) {
    const { setActiveContextId, setPreviewOpen } = useArtifactStore()

    const handleClick = () => {
        setActiveContextId(taskId)
        setPreviewOpen(true)
    }

    return (
        <Button
            variant="secondary"
            className={cn(
                "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                "bg-muted/60 hover:bg-muted border-muted-foreground/20 text-muted-foreground",
                status === 'running' ? "opacity-100" : "opacity-80"
            )}
            onClick={handleClick}
        >
            <Search className="h-3.5 w-3.5" />
            <span className="tracking-wide">Searching</span>
            <span className="text-foreground">{perspective}</span>
        </Button>
    )
}
