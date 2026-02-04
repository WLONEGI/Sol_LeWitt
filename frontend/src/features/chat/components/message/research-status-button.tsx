
"use client"

import { Button } from "@/components/ui/button"
import { Loader2, FileText, CheckCircle2 } from "lucide-react"
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
            size="sm"
            className={cn(
                "flex items-center gap-2 transition-all duration-300 border",
                status === 'running' ? "border-primary/20 bg-primary/5" : "border-green-500/20 bg-green-500/5"
            )}
            onClick={handleClick}
        >
            {status === 'running' ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
            ) : (
                <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
            )}

            <span className="text-xs truncate max-w-[200px]">
                {perspective}
            </span>

            {status === 'completed' && (
                <FileText className="h-3.5 w-3.5 text-muted-foreground ml-1 opacity-50" />
            )}
        </Button>
    )
}
